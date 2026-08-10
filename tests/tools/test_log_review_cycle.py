from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.tools.log_review_cycle import log_review_cycle

_MODULE = "agent.tools.log_review_cycle"


@pytest.mark.asyncio
async def test_logs_to_console_with_issue_key_prefix() -> None:
    with (
        patch(f"{_MODULE}.get_config", return_value={"configurable": {"thread_id": "t1"}}),
        patch(f"{_MODULE}.console_events.push_log", new_callable=AsyncMock) as mock_push,
        patch(f"{_MODULE}._bump_cycle_counter", new_callable=AsyncMock) as mock_bump,
    ):
        result = await log_review_cycle("spec", 2, "missing sad path", issue_key="SSAI-1")

    assert result == {"success": True}
    mock_push.assert_awaited_once_with("[SSAI-1] spec self-review cycle 2: missing sad path")
    mock_bump.assert_awaited_once_with("t1", "spec", 2)


@pytest.mark.asyncio
async def test_logs_without_issue_key_prefix() -> None:
    with (
        patch(f"{_MODULE}.get_config", return_value={"configurable": {}}),
        patch(f"{_MODULE}.console_events.push_log", new_callable=AsyncMock) as mock_push,
    ):
        result = await log_review_cycle("code", 1, "clean")

    assert result == {"success": True}
    mock_push.assert_awaited_once_with("code self-review cycle 1: clean")


@pytest.mark.asyncio
async def test_bump_cycle_counter_updates_thread_metadata() -> None:
    from agent.tools.log_review_cycle import _bump_cycle_counter

    client = MagicMock()
    client.threads.update = AsyncMock()
    with patch(f"{_MODULE}.get_client", return_value=client):
        await _bump_cycle_counter("t1", "spec", 3)

    client.threads.update.assert_awaited_once_with(
        thread_id="t1", metadata={"jira_review_cycles_spec": 3}
    )
