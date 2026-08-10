"""Tool: ``log_review_cycle``. Push a self-review cycle event to the agent
console so iteration depth is observable after the fact (tasks.md §6.3b).

The cycle count itself is guidance, not an enforced limit (design.md
Decision 5) — nothing here counts toward a hard cap. This only makes drift
visible in the execution log; it does not gate anything.
"""

from __future__ import annotations

from typing import Any

from langgraph.config import get_config
from langgraph_sdk import get_client

from ..utils import console_events

_METADATA_KEY_TEMPLATE = "jira_review_cycles_{phase}"


async def _bump_cycle_counter(thread_id: str, phase: str, cycle_number: int) -> None:
    """Best-effort: record the highest cycle number seen for this phase, for
    later correlation with LangSmith traces via the thread's Jira metadata
    (tasks.md §10.1's "review cycles" metric)."""
    from ..jira_poller import _langgraph_url

    client = get_client(url=_langgraph_url())
    key = _METADATA_KEY_TEMPLATE.format(phase=phase)
    try:
        await client.threads.update(thread_id=thread_id, metadata={key: cycle_number})
    except Exception:  # noqa: BLE001
        pass


async def log_review_cycle(
    phase: str, cycle_number: int, outcome: str, issue_key: str | None = None
) -> dict[str, Any]:
    """Log one self-review cycle to the console's execution log.

    Args:
        phase: `"spec"` or `"code"`.
        cycle_number: Which pass this is (1, 2, 3, ...).
        outcome: A short note — what was found, or "clean" if nothing was.
        issue_key: The Jira issue key, if known, for correlation in the log.

    Returns:
        Dictionary with 'success': True.
    """
    prefix = f"[{issue_key}] " if issue_key else ""
    await console_events.push_log(f"{prefix}{phase} self-review cycle {cycle_number}: {outcome}")

    try:
        config = get_config()
        configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    except Exception:  # noqa: BLE001
        configurable = {}
    thread_id = configurable.get("thread_id") if isinstance(configurable, dict) else None
    if isinstance(thread_id, str) and thread_id:
        await _bump_cycle_counter(thread_id, phase, cycle_number)

    return {"success": True}
