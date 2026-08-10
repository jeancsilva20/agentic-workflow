"""Tool: ``jira_park_at_gate``. Post a Jira comment, transition the card to a
gate column, mark the thread parked in metadata, and signal the agent to end
its turn — the non-blocking-gate mechanism from design.md Decision 1 /
specs/column-approval-gate/spec.md ("Agent ends its run at a gate instead of
blocking").

The agent MUST commit its work *before* calling this tool. The branch is the
only thing that survives a lost sandbox while parked for hours; this tool
does not touch git itself.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from langgraph.config import get_config
from langgraph_sdk import get_client

from ..utils import console_events
from ..utils.adf import markdown_to_jira_comment_body
from ..utils.jira import JiraTransitionError, add_comment, transition_to_column

logger = logging.getLogger(__name__)


def _langgraph_url() -> str:
    return os.environ.get("LANGGRAPH_URL") or os.environ.get(
        "LANGGRAPH_URL_PROD", "http://localhost:2024"
    )


async def _existing_gate_history(client: Any, thread_id: str) -> list[dict[str, str]]:
    try:
        thread = await client.threads.get(thread_id)
    except Exception:  # noqa: BLE001
        return []
    metadata = thread.get("metadata") if isinstance(thread, dict) else None
    history = metadata.get("jira_gate_history") if isinstance(metadata, dict) else None
    return list(history) if isinstance(history, list) else []


async def _mark_thread_parked(thread_id: str, issue_key: str, column_name: str) -> None:
    """Mark the thread parked and append this gate visit to its timestamp
    history (tasks.md §10.3 — approval gate timestamps)."""
    client = get_client(url=_langgraph_url())
    parked_at = datetime.now(UTC).isoformat()
    history = await _existing_gate_history(client, thread_id)
    history.append({"column": column_name, "parked_at": parked_at})

    metadata = {
        "jira_issue_key": issue_key,
        "jira_parked": True,
        "jira_parked_column": column_name,
        "jira_parked_at": parked_at,
        "jira_gate_history": history,
    }
    try:
        await client.threads.update(thread_id=thread_id, metadata=metadata)
    except Exception:  # noqa: BLE001
        try:
            await client.threads.create(
                thread_id=thread_id, if_exists="do_nothing", metadata=metadata
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to mark thread %s parked in metadata", thread_id)


async def jira_park_at_gate(issue_key: str, column_name: str, comment_body: str) -> dict[str, Any]:
    """Park at a Jira approval gate: comment, transition, mark metadata, stop.

    Use this when a workflow phase (spec generation, implementation, or
    merge-ready) is complete and needs human approval, or when a self-review
    loop exhausted its guidance cycles with issues remaining — either way,
    post what's ready or what's unresolved and hand off; do not keep working.

    Args:
        issue_key: The Jira issue key, e.g. "SSAI-88".
        column_name: The gate column to move the card to, e.g. "Em Revisão de Spec".
        comment_body: Markdown explaining what's ready for review, or — on
            auto-review exhaustion — what could not be resolved.

    Returns:
        On success, a dictionary with ``success: True`` and ``end_run: True``
        — the caller must not invoke any further tools this turn once it sees
        ``end_run``. On failure, ``success: False`` and an ``error`` message;
        the card was not moved and the thread was not marked parked.
    """
    try:
        config = get_config()
    except Exception:  # noqa: BLE001
        config = {}
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    thread_id = configurable.get("thread_id") if isinstance(configurable, dict) else None
    if not thread_id:
        return {"success": False, "error": "no thread_id in run config"}

    adf_body = markdown_to_jira_comment_body(comment_body, truncate_pointer=f"issue {issue_key}")
    comment_result = await add_comment(issue_key, adf_body)
    if "error" in comment_result:
        return {"success": False, "error": f"failed to post comment: {comment_result['error']}"}

    try:
        await transition_to_column(issue_key, column_name)
    except JiraTransitionError as exc:
        return {"success": False, "error": f"failed to transition: {exc}"}

    await _mark_thread_parked(thread_id, issue_key, column_name)
    await console_events.push_run_event(issue_key, "parked", column=column_name)

    return {
        "success": True,
        "end_run": True,
        "message": (
            f"Parked {issue_key} at '{column_name}'. This gate is now waiting on a human. "
            "Do not call any further tools — end your turn now."
        ),
    }
