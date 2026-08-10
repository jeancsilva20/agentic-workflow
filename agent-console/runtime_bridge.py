"""Applies a console config change to the running LangGraph server.

Only one of the two settings needs anything here. Shadow mode does not: the
poller reads the same file the console writes, so the next tick picks it up.
The polling interval is a cron on the LangGraph server and has to be pushed.

Every apply function returns ``None`` on success or a human-readable warning on
failure, never raising: the operator's choice is already persisted at that
point, so the honest outcome is "saved, but the runtime did not take it",
not a 500 that implies nothing was saved.

It also reads one thing the console never writes: the model router's per-role
table, exposed here because the same ``sys.path`` bridge into the sibling
``agent/`` package is already set up.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, TypeVar

# Same reason as config_store: the sibling `agent/` package is the runtime this
# console configures, and it is not importable from the console's own directory.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logger = logging.getLogger(__name__)

T = TypeVar("T")

# A single admin action must never hang a request thread on an unreachable
# LangGraph server; the timeout turns that into a warning the operator can see.
_CALL_TIMEOUT_SECONDS = 30.0

_loop_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None


def _runtime_loop() -> asyncio.AbstractEventLoop:
    """One long-lived event loop for every call into the agent runtime.

    ``asyncio.run`` per call closes its loop on the way out, and the LangGraph
    client is deliberately cached (a new connection pool per admin action would
    be wasteful) — so the second call would find its HTTP client bound to a
    closed loop and fail with "Event loop is closed". Keeping one loop alive on
    a daemon thread is what makes the cached client legal.
    """
    global _loop

    with _loop_lock:
        if _loop is None or _loop.is_closed():
            loop = asyncio.new_event_loop()
            threading.Thread(
                target=loop.run_forever, name="console-runtime-bridge", daemon=True
            ).start()
            _loop = loop
        return _loop


def _run(coro: Coroutine[Any, Any, T]) -> T:
    future = asyncio.run_coroutine_threadsafe(coro, _runtime_loop())
    try:
        return future.result(_CALL_TIMEOUT_SECONDS)
    except TimeoutError:
        future.cancel()
        raise


def apply_polling_interval(minutes: int) -> str | None:
    """Point the poller cron at a new interval (exactly one cron survives)."""
    from agent.poller_cron import PollerCronStopped, reconfigure_poller_cron

    try:
        cron_id = _run(reconfigure_poller_cron(minutes))
    except PollerCronStopped as exc:
        logger.error("Jira poller cron removed but not recreated", exc_info=True)
        return (
            f"polling interval saved as {minutes}m, but {exc} — retry the change, or restart the "
            f"LangGraph server, which reinstalls the cron at the saved interval"
        )
    except Exception as exc:  # noqa: BLE001 — reported to the operator, never raised
        logger.warning("Failed to reconfigure the Jira poller cron", exc_info=True)
        return (
            f"polling interval saved as {minutes}m, but the LangGraph poller cron was not "
            f"reconfigured ({exc}); the poller keeps its previous interval until this succeeds"
        )
    logger.info("Jira poller cron reconfigured to %sm (id=%s)", minutes, cron_id)
    return None


def routing_table() -> list[dict[str, Any]]:
    """The router's per-role model table, read straight from the runtime.

    Read-only and local: no LangGraph call, no operator input. Routing is
    automatic, so the console reports the table rather than editing it.
    """
    from agent.routing import routing_table as _routing_table

    return _routing_table()
