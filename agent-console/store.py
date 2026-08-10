"""In-memory state for the Jira agent console.

Deliberately not persisted: on restart the console starts blank and rebuilds
from the next few ticks/events. It is never the system of record — Jira holds
column state, LangSmith holds traces — so losing this history on restart costs
nothing but a few seconds of blank dashboard (design.md Risks: "Console is an
extra service").
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Literal

RunStatus = Literal["working", "waiting", "dead"]

_LOG_RING_BUFFER_SIZE = 500
# Poller health degrades once this many tick intervals have been missed.
_DEGRADED_TICK_MULTIPLIER = 2


@dataclass
class RunRecord:
    issue_key: str
    status: RunStatus = "working"
    column: str | None = None
    parked_at: float | None = None
    human_filed: bool | None = None
    reason: str | None = None
    updated_at: float = field(default_factory=time.time)


class ConsoleStore:
    """Thread-safe in-memory state, since Flask's dev server is multi-threaded."""

    def __init__(self, poll_interval_seconds: int = 60) -> None:
        self._lock = threading.Lock()
        self._poll_interval_seconds = poll_interval_seconds
        self._last_tick_at: float | None = None
        self._runs: dict[str, RunRecord] = {}
        self._queue: dict[str, float] = {}  # issue_key -> first_seen_at
        self._log: deque[dict[str, Any]] = deque(maxlen=_LOG_RING_BUFFER_SIZE)

    # --- ingest -------------------------------------------------------

    def record_tick(self, step_a: dict[str, Any], step_b: dict[str, Any]) -> None:
        with self._lock:
            self._last_tick_at = time.time()
        self._append_log(f"tick: step_a={step_a} step_b={step_b}")

    def record_run_event(self, issue_key: str, action: str, **extra: Any) -> None:
        now = time.time()
        with self._lock:
            if action == "launched":
                self._runs[issue_key] = RunRecord(
                    issue_key=issue_key,
                    status="working",
                    human_filed=extra.get("human_filed"),
                )
                self._queue.pop(issue_key, None)
            elif action == "resumed":
                self._runs[issue_key] = RunRecord(
                    issue_key=issue_key, status="working", column=extra.get("column")
                )
            elif action == "parked":
                self._runs[issue_key] = RunRecord(
                    issue_key=issue_key,
                    status="waiting",
                    column=extra.get("column"),
                    parked_at=now,
                )
            elif action == "dead":
                self._runs[issue_key] = RunRecord(
                    issue_key=issue_key, status="dead", reason=extra.get("reason")
                )
        self._append_log(f"run {issue_key}: {action} {extra}")

    def record_queue_event(self, issue_key: str, **_extra: Any) -> None:
        with self._lock:
            self._queue.setdefault(issue_key, time.time())
        self._append_log(f"queue: {issue_key}")

    def record_log(self, message: str) -> None:
        self._append_log(message)

    def reset_run(self, issue_key: str) -> None:
        """Forget the console's live/queued view for one card.

        The console is not the source of truth and this does not touch usage
        history.  It only removes the stale lifecycle row so the next poll
        reflects the thread reset performed by the runtime bridge.
        """
        with self._lock:
            self._runs.pop(issue_key, None)
            self._queue.pop(issue_key, None)
        self._append_log(f"run {issue_key}: reset")

    def _append_log(self, message: str) -> None:
        with self._lock:
            self._log.append({"at": time.time(), "message": message})

    # --- derive --------------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._lock:
            last_tick_at = self._last_tick_at
            runs = list(self._runs.values())
            queue = dict(self._queue)
            log = list(self._log)[-100:]

        now = time.time()
        seconds_since_tick = (now - last_tick_at) if last_tick_at is not None else None
        poller_healthy = (
            seconds_since_tick is not None
            and seconds_since_tick <= self._poll_interval_seconds * _DEGRADED_TICK_MULTIPLIER
        )

        working = [r for r in runs if r.status == "working"]
        waiting = [r for r in runs if r.status == "waiting"]
        dead = [r for r in runs if r.status == "dead"]

        if last_tick_at is None:
            overall = "no_tick_ever"
        elif not poller_healthy:
            overall = "degraded_poller"
        elif working:
            overall = "working"
        elif waiting or queue:
            overall = "waiting"
        else:
            overall = "idle"

        return {
            "overall_status": overall,
            "poller": {
                "last_tick_at": last_tick_at,
                "seconds_since_tick": seconds_since_tick,
                "healthy": poller_healthy,
            },
            "metrics": {
                "working": len(working),
                "waiting": len(waiting),
                "queued": len(queue),
                "dead": len(dead),
            },
            "queue": [
                {"issue_key": key, "waiting_seconds": now - since}
                for key, since in sorted(queue.items(), key=lambda kv: kv[1])
            ],
            "runs": [
                {
                    "issue_key": r.issue_key,
                    "status": r.status,
                    "column": r.column,
                    "human_filed": r.human_filed,
                    "reason": r.reason,
                    "time_parked_seconds": (now - r.parked_at) if r.parked_at else None,
                }
                for r in sorted(runs, key=lambda r: r.updated_at, reverse=True)
            ],
            "log": log,
        }


store = ConsoleStore(
    poll_interval_seconds=int(os.environ.get("JIRA_POLL_INTERVAL_SECONDS") or "60")
)
