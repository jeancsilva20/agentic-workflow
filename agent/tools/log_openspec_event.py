"""Tool: ``log_openspec_event``. Push one OpenSpec lifecycle event to the agent
console's execution log, so an SDD run's four checkpoints (version loaded,
proposal generated, verification passed, archived) are observable after the
fact — the same pattern ``log_review_cycle`` uses for self-review cycles.

Observability only: this gates nothing. The SDD gates themselves live in
``AGENTS.md`` ("SDD Mandatory Gates") and in the skills under
``agent/skills/openspec-*``.
"""

from __future__ import annotations

from typing import Any

from ..utils import console_events

_EVENTS = {
    "version_loaded": "version {detail} loaded",
    "proposal_generated": "proposal generated",
    "verification_passed": "verification passed",
    "archived": "archived",
}


async def log_openspec_event(
    event: str, detail: str | None = None, issue_key: str | None = None
) -> dict[str, Any]:
    """Log an OpenSpec lifecycle event to the console's execution log.

    Args:
        event: One of `"version_loaded"`, `"proposal_generated"`,
            `"verification_passed"`, `"archived"`.
        detail: Extra context — the OpenSpec version for `version_loaded`, the
            change name for the others.
        issue_key: The Jira issue key, if known, for correlation in the log.

    Returns:
        Dictionary with 'success': True, or 'success': False and an 'error'
        naming the valid events when `event` is not one of them.
    """
    template = _EVENTS.get(event)
    if template is None:
        return {
            "success": False,
            "error": f"unknown event '{event}'; expected one of {sorted(_EVENTS)}",
        }

    message = template.format(detail=detail or "unknown")
    if detail and event != "version_loaded":
        message = f"{message} ({detail})"
    prefix = f"[{issue_key}] " if issue_key else ""
    await console_events.push_log(f"{prefix}openspec: {message}")

    return {"success": True}
