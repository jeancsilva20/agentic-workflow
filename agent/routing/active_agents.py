"""Which agent executions are running right now.

"Active" is the one question LangSmith answers badly: a run in flight has no
end time and no usage yet, and polling its API on every page refresh would put
an external service on the console's critical path. So dispatch registers a run
here and the completion path removes it.

Entries are bounded and evictable on purpose. A run whose completion webhook
never arrives (server recycle, dropped delivery) would otherwise stay "active"
forever and inflate the panel; the oldest entry is dropped once the cap is hit,
and stale entries can be swept by age.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .telemetry import RunMetadata, UsageData

# Far more than the Jira workflow can have in flight; the cap is a leak guard.
MAX_ACTIVE_RUNS = 100


def _now() -> datetime:
    return datetime.now(UTC)


def _parse(timestamp: str | None) -> datetime | None:
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp).astimezone(UTC)
    except ValueError:
        return None


@dataclass(frozen=True)
class ActiveRun:
    run_id: str
    metadata: RunMetadata
    started_at: str

    def as_dict(self, now: datetime | None = None) -> dict[str, Any]:
        started = _parse(self.started_at)
        reference = now or _now()
        elapsed = (reference - started).total_seconds() if started else None
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "elapsed_seconds": round(elapsed, 1) if elapsed is not None else None,
            **self.metadata.as_dict(),
        }


@dataclass(frozen=True)
class FinishedRun:
    run_id: str
    metadata: RunMetadata
    status: str | None
    usage: UsageData


class ActiveAgentRegistry:
    """Thread-safe registry of in-flight runs, keyed by run id."""

    def __init__(self, max_runs: int = MAX_ACTIVE_RUNS) -> None:
        self._lock = threading.RLock()
        self._runs: OrderedDict[str, ActiveRun] = OrderedDict()
        self._max_runs = max_runs

    def start(self, run_id: str, metadata: RunMetadata) -> ActiveRun:
        """Register a run as active. Re-registering a run id replaces it."""
        entry = ActiveRun(
            run_id=run_id,
            metadata=metadata,
            started_at=metadata.start_time or _now().isoformat(),
        )
        with self._lock:
            self._runs.pop(run_id, None)
            self._runs[run_id] = entry
            while len(self._runs) > self._max_runs:
                self._runs.popitem(last=False)
        return entry

    def finish(
        self,
        run_id: str,
        status: str | None = None,
        usage: UsageData | None = None,
    ) -> FinishedRun | None:
        """Remove a run and return what was known about it, if it was tracked.

        ``None`` for an untracked run id — a completion for a run this process
        never dispatched (restart, another replica) is normal, not an error.
        """
        with self._lock:
            entry = self._runs.pop(run_id, None)
        if entry is None:
            return None
        return FinishedRun(
            run_id=run_id,
            metadata=entry.metadata,
            status=status,
            usage=usage or UsageData(),
        )

    def get(self, run_id: str) -> ActiveRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def list_active(self) -> list[dict[str, Any]]:
        """Active runs, longest-running first."""
        now = _now()
        with self._lock:
            entries = list(self._runs.values())
        rows = [entry.as_dict(now) for entry in entries]
        return sorted(rows, key=lambda row: row["started_at"])

    def sweep_stale(self, max_age_seconds: float) -> list[ActiveRun]:
        """Drop entries older than ``max_age_seconds`` and return them.

        For the run whose completion signal never arrived: without this it stays
        on the live panel indefinitely, which is worse than losing it.
        """
        now = _now()
        dropped: list[ActiveRun] = []
        with self._lock:
            for run_id, entry in list(self._runs.items()):
                started = _parse(entry.started_at)
                if started is None or (now - started).total_seconds() > max_age_seconds:
                    self._runs.pop(run_id, None)
                    dropped.append(entry)
        return dropped

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()


# The agent process's registry; the console keeps its own, fed by pushed events.
active_agents = ActiveAgentRegistry()
