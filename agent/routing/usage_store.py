"""In-process accumulation of what each Jira card has cost so far.

A read-acceleration layer, not a system of record: LangSmith keeps the runs,
this keeps the sums so the console can answer "what has SSAI-88 spent" without
a LangSmith query per page refresh. It is deliberately in-memory and bounded —
losing it on a restart costs a repopulation, not data.

The aggregation unit is the card (``jira_issue_key``), because a card spans
several threads' worth of runs and several traces; the thread ids that made up
a card's total are reported alongside it so the number can be traced back.

Every total carries its unknowns. A run whose cost LangSmith could not price is
counted in ``runs_missing_cost`` and contributes nothing to ``cost`` — and when
*no* run in a group has a cost, ``cost`` is ``None``, not ``0.0``.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .telemetry import RunMetadata, UsageData

# Roughly a week of Jira-workflow runs. The window exists to bound memory, not
# to define a retention policy — LangSmith is the durable copy.
MAX_RUN_ENTRIES = 500


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _date_of(timestamp: str | None) -> str | None:
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp).astimezone(UTC).date().isoformat()
    except ValueError:
        return None


@dataclass(frozen=True)
class RunEntry:
    """One finished (or terminated) run, with whatever usage was recoverable."""

    run_id: str | None
    metadata: RunMetadata
    usage: UsageData
    status: str | None
    recorded_at: str

    @property
    def jira_issue_key(self) -> str | None:
        return self.metadata.jira_issue_key

    @property
    def start_time(self) -> str:
        return self.metadata.start_time or self.recorded_at

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "recorded_at": self.recorded_at,
            **self.metadata.as_dict(),
            **self.usage.as_dict(),
        }


@dataclass
class _Totals:
    """Accumulator shared by every grouping (card, model, role, day)."""

    runs: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    runs_missing_tokens: int = 0
    cost: float = 0.0
    runs_missing_cost: int = 0
    runs_with_cost: int = 0
    threads: set[str] = field(default_factory=set)

    def add(self, entry: RunEntry) -> None:
        usage = entry.usage
        self.runs += 1
        self.threads.add(entry.metadata.thread_id)
        if usage.total_tokens is None and usage.input_tokens is None:
            self.runs_missing_tokens += 1
        else:
            self.input_tokens += usage.input_tokens or 0
            self.output_tokens += usage.output_tokens or 0
            self.total_tokens += usage.total_tokens or (
                (usage.input_tokens or 0) + (usage.output_tokens or 0)
            )
        if usage.cost is None:
            self.runs_missing_cost += 1
        else:
            self.cost += usage.cost
            self.runs_with_cost += 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "runs": self.runs,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "runs_missing_tokens": self.runs_missing_tokens,
            # None, not 0.0: nothing here was priced, so the cost is unknown.
            "cost": round(self.cost, 6) if self.runs_with_cost else None,
            "runs_missing_cost": self.runs_missing_cost,
        }


@dataclass(frozen=True)
class AgentUsageSummary:
    """One role's slice of a card (or of a day)."""

    agent_role: str
    totals: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"agent_role": self.agent_role, **self.totals}


@dataclass(frozen=True)
class ModelUsageSummary:
    model: str
    totals: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"model": self.model, **self.totals}


@dataclass(frozen=True)
class JiraUsageSummary:
    """Everything one card has consumed, across every thread and run."""

    jira_issue_key: str
    totals: dict[str, Any]
    threads: list[str]
    by_agent: list[AgentUsageSummary]
    by_model: list[ModelUsageSummary]
    first_run_at: str | None
    last_run_at: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "jira_issue_key": self.jira_issue_key,
            **self.totals,
            "threads": self.threads,
            "by_agent": [item.as_dict() for item in self.by_agent],
            "by_model": [item.as_dict() for item in self.by_model],
            "first_run_at": self.first_run_at,
            "last_run_at": self.last_run_at,
        }


@dataclass(frozen=True)
class DailyUsage:
    """Today's totals across every card, split by model and by role."""

    date: str
    totals: dict[str, Any]
    by_agent: list[AgentUsageSummary]
    by_model: list[ModelUsageSummary]
    cards: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            **self.totals,
            "by_agent": [item.as_dict() for item in self.by_agent],
            "by_model": [item.as_dict() for item in self.by_model],
            "cards": self.cards,
        }


class UsageStore:
    """Thread-safe, bounded ring of run entries with aggregate views.

    Thread-safe because the writer is the run-completion path (one event loop,
    but a webhook handler) and the readers are HTTP requests on other threads.
    """

    def __init__(self, max_entries: int = MAX_RUN_ENTRIES) -> None:
        self._lock = threading.RLock()
        self._entries: deque[RunEntry] = deque(maxlen=max_entries)

    def record_run(
        self,
        run_metadata: RunMetadata,
        usage_data: UsageData | None = None,
        *,
        run_id: str | None = None,
        status: str | None = None,
        recorded_at: str | None = None,
    ) -> RunEntry:
        """Append one finished run and return the stored entry."""
        entry = RunEntry(
            run_id=run_id,
            metadata=run_metadata,
            usage=usage_data or UsageData(),
            status=status,
            recorded_at=recorded_at or _now_iso(),
        )
        with self._lock:
            self._entries.append(entry)
        return entry

    def get_card_timeline(self, jira_issue_key: str) -> list[RunEntry]:
        """This card's runs, oldest first, ordered by when the run started."""
        with self._lock:
            entries = [e for e in self._entries if e.jira_issue_key == jira_issue_key]
        return sorted(entries, key=lambda e: (e.start_time, e.recorded_at))

    def get_card_summary(self, jira_issue_key: str) -> JiraUsageSummary:
        """Totals for one card. A card with no recorded run reports zero runs.

        Absence here means "not in the window", not "never ran" — the window is
        bounded, and LangSmith remains the authority for older runs.
        """
        entries = self.get_card_timeline(jira_issue_key)
        totals = _Totals()
        by_agent: dict[str, _Totals] = {}
        by_model: dict[str, _Totals] = {}
        for entry in entries:
            totals.add(entry)
            by_agent.setdefault(entry.metadata.agent_role, _Totals()).add(entry)
            by_model.setdefault(entry.metadata.model, _Totals()).add(entry)

        return JiraUsageSummary(
            jira_issue_key=jira_issue_key,
            totals=totals.as_dict(),
            threads=sorted(totals.threads),
            by_agent=_agent_summaries(by_agent),
            by_model=_model_summaries(by_model),
            first_run_at=entries[0].start_time if entries else None,
            last_run_at=entries[-1].start_time if entries else None,
        )

    def get_today_usage(self, today: str | None = None) -> DailyUsage:
        """Totals for every run started today (UTC)."""
        day = today or datetime.now(UTC).date().isoformat()
        with self._lock:
            entries = [e for e in self._entries if _date_of(e.start_time) == day]

        totals = _Totals()
        by_agent: dict[str, _Totals] = {}
        by_model: dict[str, _Totals] = {}
        cards: set[str] = set()
        for entry in entries:
            totals.add(entry)
            by_agent.setdefault(entry.metadata.agent_role, _Totals()).add(entry)
            by_model.setdefault(entry.metadata.model, _Totals()).add(entry)
            if entry.jira_issue_key:
                cards.add(entry.jira_issue_key)

        return DailyUsage(
            date=day,
            totals=totals.as_dict(),
            by_agent=_agent_summaries(by_agent),
            by_model=_model_summaries(by_model),
            cards=sorted(cards),
        )

    def entries(self) -> list[RunEntry]:
        with self._lock:
            return list(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def _agent_summaries(grouped: dict[str, _Totals]) -> list[AgentUsageSummary]:
    return [AgentUsageSummary(role, totals.as_dict()) for role, totals in sorted(grouped.items())]


def _model_summaries(grouped: dict[str, _Totals]) -> list[ModelUsageSummary]:
    return [ModelUsageSummary(model, totals.as_dict()) for model, totals in sorted(grouped.items())]


# The agent process's store. The console keeps its own instance of this class,
# fed by pushed events — it is a separate process and cannot read this one.
usage_store = UsageStore()
