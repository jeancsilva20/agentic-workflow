"""The console's mirror of the agent's telemetry.

The console is a separate process from the LangGraph server, so it cannot read
the agent's in-memory stores — and by spec it may not call back into the
runtime either (specs/agent-console: "read-only display fed by events pushed to
it"). So it keeps its own instance of the very same store classes, filled from
the two events the agent pushes: one when a run starts, one when it finishes
with its post-run token and cost totals.

Consequences worth knowing:

- A console restart empties this. It repopulates from subsequent events; the
  durable copy of every run is LangSmith's, and the agent's own store is the
  read-acceleration layer on that side.
- A dropped push costs one row here and nothing at all to the run.
- No LangSmith call is ever made from this process, so no LangSmith credential
  is ever loaded into it, let alone served from an endpoint.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Same bridge as config_store/runtime_bridge: the store classes are the agent's,
# reused verbatim so the console and the agent aggregate identically.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent.routing.active_agents import ActiveAgentRegistry  # noqa: E402
from agent.routing.telemetry import RunMetadata, UsageData, route_label  # noqa: E402
from agent.routing.usage_store import UsageStore  # noqa: E402

usage_store = UsageStore()
active_agents = ActiveAgentRegistry()


def reset() -> None:
    """Drop everything — for tests, and for nothing else."""
    usage_store.clear()
    active_agents.clear()


def record_start(payload: dict[str, Any]) -> tuple[list[str], str | None]:
    """Ingest an ``agent_start`` push.

    Returns the execution-log lines to write and an error string when the
    payload is unusable.
    """
    run_id = payload.get("run_id")
    metadata = RunMetadata.from_metadata(payload.get("metadata"))
    if not isinstance(run_id, str) or not run_id:
        return [], "run_id is required"
    if metadata is None:
        return [], "a telemetry metadata object is required"

    active_agents.start(run_id, metadata)

    card = metadata.jira_issue_key or metadata.thread_id
    lines = [f"routing: {card} {metadata.agent_role} → {route_label(metadata)}"]
    if metadata.escalation_reason:
        lines.append(
            f"escalation: {card} {metadata.agent_role} escalated to "
            f"{route_label(metadata)} ({metadata.escalation_reason})"
        )
    return lines, None


def record_finish(payload: dict[str, Any]) -> tuple[list[str], str | None]:
    """Ingest an ``agent_finish`` push: usage totals plus the log lines for them."""
    run_id = payload.get("run_id")
    metadata = RunMetadata.from_metadata(payload.get("metadata"))
    if not isinstance(run_id, str) or not run_id:
        return [], "run_id is required"
    if metadata is None:
        return [], "a telemetry metadata object is required"

    status = payload.get("status") if isinstance(payload.get("status"), str) else None
    usage = UsageData.from_dict(payload.get("usage"))

    active_agents.finish(run_id, status, usage)
    usage_store.record_run(metadata, usage, run_id=run_id, status=status)

    return _usage_log_lines(metadata, usage), None


def _usage_log_lines(metadata: RunMetadata, usage: UsageData) -> list[str]:
    """One line for the run's tokens, one for the card's cost. Never per token."""
    if usage.total_tokens is None:
        lines = [f"usage: {metadata.agent_role} tokens unavailable"]
    else:
        lines = [f"usage: {metadata.agent_role} {usage.total_tokens:,} tokens"]

    card = metadata.jira_issue_key
    if not card:
        return lines

    summary = usage_store.get_card_summary(card).as_dict()
    total_cost = summary.get("cost")
    if total_cost is None:
        lines.append(f"cost: {card} unavailable (no price for {metadata.model})")
    else:
        estimated = " (estimated)" if usage.cost_source == "estimated" else ""
        lines.append(f"cost: {card} updated to ${total_cost:.4f}{estimated}")
    return lines


def live() -> dict[str, Any]:
    """What is executing right now."""
    return {"active": active_agents.list_active()}


def today_usage() -> dict[str, Any]:
    return usage_store.get_today_usage().as_dict()


def card_usage(jira_issue_key: str) -> dict[str, Any]:
    return usage_store.get_card_summary(jira_issue_key).as_dict()


def card_timeline(jira_issue_key: str) -> dict[str, Any]:
    entries = usage_store.get_card_timeline(jira_issue_key)
    return {
        "jira_issue_key": jira_issue_key,
        "runs": [entry.as_dict() for entry in entries],
    }
