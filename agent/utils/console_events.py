"""Push client for the Jira agent console (``agent-console/``).

Fire-and-forget: a console that is down or slow must never affect a run
(design.md Risks — "Console is an extra service"). Every push carries a short
timeout and swallows its own failure; the console holds no workflow state and
is never read from here, only written to.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

AGENT_CONSOLE_URL = os.environ.get("AGENT_CONSOLE_URL", "").rstrip("/")
_PUSH_TIMEOUT_SECONDS = 2.0


async def _push(kind: str, payload: dict[str, Any]) -> None:
    if not AGENT_CONSOLE_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=_PUSH_TIMEOUT_SECONDS) as client:
            await client.post(f"{AGENT_CONSOLE_URL}/api/events/{kind}", json=payload)
    except Exception:  # noqa: BLE001
        logger.debug("Console push failed for event kind=%s (ignored)", kind, exc_info=True)


async def push_tick_event(
    step_a: dict[str, Any],
    step_b: dict[str, Any],
) -> None:
    """Report one poller tick's outcome (task 5.9 / 5b.4)."""
    await _push("tick", {"step_a": step_a, "step_b": step_b})


async def push_run_event(issue_key: str, action: str, **extra: Any) -> None:
    """Report a run lifecycle event: launched / resumed / parked / dead."""
    await _push("run", {"issue_key": issue_key, "action": action, **extra})


async def push_queue_event(issue_key: str, **extra: Any) -> None:
    """Report a card sitting in the trigger column without a thread yet."""
    await _push("queue", {"issue_key": issue_key, **extra})


async def push_log(message: str) -> None:
    """Append one line to the console's execution log ring buffer."""
    await _push("log", {"message": message})


async def push_agent_start(run_id: str, metadata: dict[str, Any]) -> None:
    """Report an agent execution starting, with its routing decision.

    The console mirrors the agent's telemetry stores from these two events —
    it cannot read the agent's memory, and the spec keeps it from calling back
    into the runtime. A dropped push costs the console one row, never a run.
    """
    await _push("agent_start", {"run_id": run_id, "metadata": metadata})


async def push_agent_finish(
    run_id: str,
    status: str | None,
    metadata: dict[str, Any],
    usage: dict[str, Any],
) -> None:
    """Report an agent execution finishing, with its post-run token/cost totals."""
    await _push(
        "agent_finish",
        {"run_id": run_id, "status": status, "metadata": metadata, "usage": usage},
    )
