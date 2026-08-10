from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.tools.jira_park_at_gate import jira_park_at_gate
from agent.utils.jira import JiraTransitionError

_MODULE = "agent.tools.jira_park_at_gate"


def _fake_client(existing_metadata: dict | None = None) -> MagicMock:
    client = MagicMock()
    client.threads.get = AsyncMock(return_value={"metadata": existing_metadata or {}})
    client.threads.update = AsyncMock(return_value=None)
    client.threads.create = AsyncMock(return_value=None)
    return client


@pytest.mark.asyncio
async def test_parks_successfully_and_signals_end_run() -> None:
    with (
        patch(f"{_MODULE}.get_config", return_value={"configurable": {"thread_id": "t1"}}),
        patch(f"{_MODULE}.add_comment", new_callable=AsyncMock, return_value={"success": True}),
        patch(
            f"{_MODULE}.transition_to_column",
            new_callable=AsyncMock,
            return_value={"success": True},
        ),
        patch(f"{_MODULE}.get_client", return_value=_fake_client()) as mock_get_client,
        patch(f"{_MODULE}.console_events.push_run_event", new_callable=AsyncMock) as mock_push,
    ):
        result = await jira_park_at_gate("SSAI-1", "Em Revisão de Spec", "Ready for review.")

    assert result["success"] is True
    assert result["end_run"] is True
    mock_get_client.return_value.threads.update.assert_awaited_once()
    update_kwargs = mock_get_client.return_value.threads.update.await_args.kwargs
    assert update_kwargs["metadata"]["jira_parked"] is True
    assert update_kwargs["metadata"]["jira_parked_column"] == "Em Revisão de Spec"
    assert update_kwargs["metadata"]["jira_gate_history"] == [
        {"column": "Em Revisão de Spec", "parked_at": update_kwargs["metadata"]["jira_parked_at"]}
    ]
    mock_push.assert_awaited_once_with("SSAI-1", "parked", column="Em Revisão de Spec")


@pytest.mark.asyncio
async def test_gate_history_accumulates_across_visits() -> None:
    prior_history = [{"column": "Em Revisão de Spec", "parked_at": "2026-01-01T00:00:00+00:00"}]
    with (
        patch(f"{_MODULE}.get_config", return_value={"configurable": {"thread_id": "t1"}}),
        patch(f"{_MODULE}.add_comment", new_callable=AsyncMock, return_value={"success": True}),
        patch(
            f"{_MODULE}.transition_to_column",
            new_callable=AsyncMock,
            return_value={"success": True},
        ),
        patch(
            f"{_MODULE}.get_client",
            return_value=_fake_client({"jira_gate_history": prior_history}),
        ) as mock_get_client,
        patch(f"{_MODULE}.console_events.push_run_event", new_callable=AsyncMock),
    ):
        await jira_park_at_gate("SSAI-1", "Em Code Review", "Ready for code review.")

    update_kwargs = mock_get_client.return_value.threads.update.await_args.kwargs
    history = update_kwargs["metadata"]["jira_gate_history"]
    assert len(history) == 2
    assert history[0] == prior_history[0]
    assert history[1]["column"] == "Em Code Review"


@pytest.mark.asyncio
async def test_missing_thread_id_returns_error() -> None:
    with patch(f"{_MODULE}.get_config", return_value={"configurable": {}}):
        result = await jira_park_at_gate("SSAI-1", "Em Revisão de Spec", "body")

    assert result == {"success": False, "error": "no thread_id in run config"}


@pytest.mark.asyncio
async def test_comment_failure_does_not_transition_or_park() -> None:
    with (
        patch(f"{_MODULE}.get_config", return_value={"configurable": {"thread_id": "t1"}}),
        patch(f"{_MODULE}.add_comment", new_callable=AsyncMock, return_value={"error": "boom"}),
        patch(f"{_MODULE}.transition_to_column", new_callable=AsyncMock) as mock_transition,
    ):
        result = await jira_park_at_gate("SSAI-1", "Em Revisão de Spec", "body")

    assert result["success"] is False
    assert "boom" in result["error"]
    mock_transition.assert_not_called()


@pytest.mark.asyncio
async def test_transition_failure_reports_error() -> None:
    with (
        patch(f"{_MODULE}.get_config", return_value={"configurable": {"thread_id": "t1"}}),
        patch(f"{_MODULE}.add_comment", new_callable=AsyncMock, return_value={"success": True}),
        patch(
            f"{_MODULE}.transition_to_column",
            new_callable=AsyncMock,
            side_effect=JiraTransitionError("no such column"),
        ),
    ):
        result = await jira_park_at_gate("SSAI-1", "Bogus", "body")

    assert result["success"] is False
    assert "no such column" in result["error"]
