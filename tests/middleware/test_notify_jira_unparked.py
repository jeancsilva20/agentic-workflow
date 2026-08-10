from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware import AgentState
from langchain_core.messages import AIMessage, HumanMessage

from agent.middleware.notify_jira_unparked import notify_jira_on_unparked_termination

_MODULE = "agent.middleware.notify_jira_unparked"


def _runtime() -> MagicMock:
    return MagicMock()


def _fake_client(metadata: dict | None) -> MagicMock:
    client = MagicMock()
    thread = {"metadata": metadata} if metadata is not None else {"metadata": {}}
    client.threads.get = AsyncMock(return_value=thread)
    return client


@pytest.mark.asyncio
async def test_skips_when_not_a_jira_thread() -> None:
    state: AgentState = {
        "messages": [AIMessage(content="Model call limits exceeded: run limit reached")]
    }
    with (
        patch(f"{_MODULE}.get_config", return_value={"configurable": {"thread_id": "t1"}}),
        patch(f"{_MODULE}.add_comment", new_callable=AsyncMock) as mock_add_comment,
    ):
        result = await notify_jira_on_unparked_termination.aafter_agent(state, _runtime())

    assert result is None
    mock_add_comment.assert_not_called()


@pytest.mark.asyncio
async def test_reports_dead_on_call_limit_marker_when_unparked() -> None:
    state: AgentState = {
        "messages": [AIMessage(content="Model call limits exceeded: run limit reached")]
    }
    with (
        patch(
            f"{_MODULE}.get_config",
            return_value={"configurable": {"thread_id": "t1", "jira_issue_key": "SSAI-1"}},
        ),
        patch(f"{_MODULE}.get_client", return_value=_fake_client(None)),
        patch(
            f"{_MODULE}.add_comment", new_callable=AsyncMock, return_value={"success": True}
        ) as mock_add_comment,
        patch(f"{_MODULE}.console_events.push_run_event", new_callable=AsyncMock) as mock_push,
    ):
        result = await notify_jira_on_unparked_termination.aafter_agent(state, _runtime())

    assert result is None
    mock_add_comment.assert_awaited_once()
    assert mock_add_comment.await_args.args[0] == "SSAI-1"
    mock_push.assert_awaited_once_with("SSAI-1", "dead", reason="model call limit")


@pytest.mark.asyncio
async def test_skips_when_already_parked() -> None:
    state: AgentState = {
        "messages": [AIMessage(content="Model call limits exceeded: run limit reached")]
    }
    with (
        patch(
            f"{_MODULE}.get_config",
            return_value={"configurable": {"thread_id": "t1", "jira_issue_key": "SSAI-1"}},
        ),
        patch(f"{_MODULE}.get_client", return_value=_fake_client({"jira_parked": True})),
        patch(f"{_MODULE}.add_comment", new_callable=AsyncMock) as mock_add_comment,
    ):
        result = await notify_jira_on_unparked_termination.aafter_agent(state, _runtime())

    assert result is None
    mock_add_comment.assert_not_called()


@pytest.mark.asyncio
async def test_skips_when_ended_with_pending_tool_call() -> None:
    ai_message = AIMessage(content="", tool_calls=[{"name": "read_file", "args": {}, "id": "1"}])
    state: AgentState = {"messages": [ai_message]}
    with (
        patch(
            f"{_MODULE}.get_config",
            return_value={"configurable": {"thread_id": "t1", "jira_issue_key": "SSAI-1"}},
        ),
        patch(f"{_MODULE}.add_comment", new_callable=AsyncMock) as mock_add_comment,
    ):
        result = await notify_jira_on_unparked_termination.aafter_agent(state, _runtime())

    assert result is None
    mock_add_comment.assert_not_called()


@pytest.mark.asyncio
async def test_skips_when_trajectory_already_parked_via_tool_call() -> None:
    parked_call = AIMessage(
        content="",
        tool_calls=[{"name": "jira_park_at_gate", "args": {"issue_key": "SSAI-1"}, "id": "1"}],
    )
    final_text = AIMessage(content="All done for this turn.")
    state: AgentState = {"messages": [parked_call, final_text]}
    with (
        patch(
            f"{_MODULE}.get_config",
            return_value={"configurable": {"thread_id": "t1", "jira_issue_key": "SSAI-1"}},
        ),
        patch(f"{_MODULE}.add_comment", new_callable=AsyncMock) as mock_add_comment,
    ):
        result = await notify_jira_on_unparked_termination.aafter_agent(state, _runtime())

    assert result is None
    mock_add_comment.assert_not_called()


@pytest.mark.asyncio
async def test_skips_when_trajectory_transitioned_to_done() -> None:
    done_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "jira_transition_issue",
                "args": {"issue_key": "SSAI-1", "column_name": "Done"},
                "id": "1",
            }
        ],
    )
    final_text = AIMessage(content="Workflow complete.")
    state: AgentState = {"messages": [done_call, final_text]}
    with (
        patch(
            f"{_MODULE}.get_config",
            return_value={"configurable": {"thread_id": "t1", "jira_issue_key": "SSAI-1"}},
        ),
        patch(f"{_MODULE}.add_comment", new_callable=AsyncMock) as mock_add_comment,
    ):
        result = await notify_jira_on_unparked_termination.aafter_agent(state, _runtime())

    assert result is None
    mock_add_comment.assert_not_called()


@pytest.mark.asyncio
async def test_reports_dead_on_plain_text_ending_never_reaching_gate() -> None:
    state: AgentState = {
        "messages": [HumanMessage(content="go"), AIMessage(content="I'm stuck, giving up here.")]
    }
    with (
        patch(
            f"{_MODULE}.get_config",
            return_value={"configurable": {"thread_id": "t1", "jira_issue_key": "SSAI-1"}},
        ),
        patch(f"{_MODULE}.get_client", return_value=_fake_client(None)),
        patch(
            f"{_MODULE}.add_comment", new_callable=AsyncMock, return_value={"success": True}
        ) as mock_add_comment,
        patch(f"{_MODULE}.console_events.push_run_event", new_callable=AsyncMock) as mock_push,
    ):
        result = await notify_jira_on_unparked_termination.aafter_agent(state, _runtime())

    assert result is None
    mock_add_comment.assert_awaited_once()
    mock_push.assert_awaited_once_with("SSAI-1", "dead", reason="step/time limit")
