from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent.middleware.sandbox_circuit_breaker import post_sandbox_unreachable_notification

_MODULE = "agent.middleware.sandbox_circuit_breaker"


@pytest.mark.asyncio
async def test_notifies_jira_when_no_slack_or_linear_target() -> None:
    config = {"configurable": {"jira_issue_key": "SSAI-1"}}
    with patch(f"{_MODULE}.add_comment", new_callable=AsyncMock) as mock_add_comment:
        await post_sandbox_unreachable_notification(config, sandbox_id="sb-dead")

    mock_add_comment.assert_awaited_once()
    assert mock_add_comment.await_args.args[0] == "SSAI-1"
    adf_body = mock_add_comment.await_args.args[1]
    assert adf_body["type"] == "doc"


@pytest.mark.asyncio
async def test_slack_target_takes_priority_over_jira() -> None:
    config = {
        "configurable": {
            "jira_issue_key": "SSAI-1",
            "slack_thread": {"channel_id": "C123", "thread_ts": "171.1"},
        }
    }
    with (
        patch(f"{_MODULE}.post_slack_thread_reply", new_callable=AsyncMock) as mock_slack,
        patch(f"{_MODULE}.add_comment", new_callable=AsyncMock) as mock_add_comment,
    ):
        await post_sandbox_unreachable_notification(config, sandbox_id="sb-dead")

    mock_slack.assert_awaited_once()
    mock_add_comment.assert_not_called()


@pytest.mark.asyncio
async def test_no_target_configured_notifies_nothing() -> None:
    config = {"configurable": {}}
    with patch(f"{_MODULE}.add_comment", new_callable=AsyncMock) as mock_add_comment:
        await post_sandbox_unreachable_notification(config, sandbox_id="sb-dead")

    mock_add_comment.assert_not_called()
