"""After-agent middleware: the Jira-side equivalent of `notify_step_limit`.

`notify_step_limit_reached` (agent/middleware/notify_step_limit.py) only fires
when `slack_thread` is present in `configurable` — a Jira-triggered thread
never has one, so today hitting the model-call limit produces zero signal
anywhere for a Jira card: no Slack reply (no thread), no Jira comment, no
console update. The card just sits wherever it was, silently, with nothing
telling a human it happened (tasks.md §5.14 / the "dead" console status added
in §5b.8).

This closes that gap without touching the Slack path: it targets Jira threads
specifically, and — beyond the same `ModelCallLimitMiddleware` marker check
`notify_step_limit` uses — also catches the "ended on plain text, never
reached a gate or Done" shape a `timeout_wrapup`-driven finish can leave
behind, since that middleware injects a generic instruction with no Jira
awareness at all and nothing guarantees the model responds by calling
`jira_park_at_gate`.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any

from langchain.agents.middleware import AgentState, after_agent
from langgraph.config import get_config
from langgraph.runtime import Runtime
from langgraph_sdk import get_client

from ..utils import console_events
from ..utils.adf import markdown_to_jira_comment_body
from ..utils.jira import add_comment

logger = logging.getLogger(__name__)

_CALL_LIMIT_MARKER = "Model call limits exceeded"


def _langgraph_url() -> str:
    return os.environ.get("LANGGRAPH_URL") or os.environ.get(
        "LANGGRAPH_URL_PROD", "http://localhost:2024"
    )


def _content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    parts: list[str] = []
    for block in content:
        if isinstance(block, Mapping):
            text = block.get("text", "")
            parts.append(text if isinstance(text, str) else str(text))
        else:
            parts.append(str(block))
    return " ".join(parts)


def _tool_call_name(call: Any) -> str | None:
    if isinstance(call, Mapping):
        return call.get("name")
    return getattr(call, "name", None)


def _tool_call_args(call: Any) -> Mapping[str, Any]:
    if isinstance(call, Mapping):
        args = call.get("args")
    else:
        args = getattr(call, "args", None)
    return args if isinstance(args, Mapping) else {}


def _reached_gate_or_done(messages: list[Any], done_column: str) -> bool:
    """Whether the trajectory already parked at a gate or transitioned to Done."""
    for msg in messages:
        for call in getattr(msg, "tool_calls", None) or []:
            name = _tool_call_name(call)
            if name == "jira_park_at_gate":
                return True
            if (
                name == "jira_transition_issue"
                and _tool_call_args(call).get("column_name") == done_column
            ):
                return True
    return False


@after_agent
async def notify_jira_on_unparked_termination(
    state: AgentState,
    runtime: Runtime,  # noqa: ARG001
) -> dict[str, Any] | None:
    """Comment on Jira and mark the run `dead` if it ended without parking."""
    messages = state.get("messages", [])
    if not messages:
        return None

    try:
        config = get_config()
    except Exception:  # noqa: BLE001
        return None
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    if not isinstance(configurable, dict):
        return None
    issue_key = configurable.get("jira_issue_key")
    thread_id = configurable.get("thread_id")
    if not issue_key or not thread_id:
        return None  # not a Jira-triggered thread — leave this to notify_step_limit

    last_msg = messages[-1]
    content = _content_to_text(getattr(last_msg, "content", "") or "")
    hit_call_limit = _CALL_LIMIT_MARKER in content

    from .. import jira_poller  # deferred: avoid a hard import cycle at module load

    if not hit_call_limit:
        last_tool_calls = getattr(last_msg, "tool_calls", None) or []
        if last_tool_calls:
            return None  # still mid-turn with a pending tool call, not an ending state to judge
        if _reached_gate_or_done(messages, jira_poller.COLUMN_DONE):
            return None  # legitimate completion, or already parked via the tool call itself

    client = get_client(url=_langgraph_url())
    try:
        thread = await client.threads.get(thread_id)
        metadata = thread.get("metadata") if isinstance(thread, dict) else {}
    except Exception:  # noqa: BLE001
        metadata = {}
    if isinstance(metadata, dict) and metadata.get("jira_parked"):
        return None  # parked properly this run

    limit_name = "model call limit" if hit_call_limit else "step/time limit"
    comment = (
        f"Run ended ({limit_name} reached) without completing this step and without "
        "parking at a gate. This card needs human attention — nothing is actively "
        "working on it right now."
    )
    adf_body = markdown_to_jira_comment_body(comment)
    try:
        await add_comment(issue_key, adf_body)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to post 'dead' comment to Jira issue %s", issue_key)

    await console_events.push_run_event(issue_key, "dead", reason=limit_name)
    return None
