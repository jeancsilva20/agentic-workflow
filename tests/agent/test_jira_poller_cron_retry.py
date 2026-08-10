from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent import jira_poller

_MODULE = "agent.jira_poller"


@pytest.mark.asyncio
async def test_retry_succeeds_on_first_attempt_after_delay() -> None:
    with (
        patch(f"{_MODULE}.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        patch(f"{_MODULE}.ensure_jira_poller_cron", new_callable=AsyncMock, return_value="cron-1"),
    ):
        await jira_poller.ensure_jira_poller_cron_with_retry(attempts=5, initial_delay_seconds=2.0)

    mock_sleep.assert_awaited_once_with(2.0)


@pytest.mark.asyncio
async def test_retry_backs_off_and_eventually_succeeds() -> None:
    with (
        patch(f"{_MODULE}.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        patch(
            f"{_MODULE}.ensure_jira_poller_cron",
            new_callable=AsyncMock,
            side_effect=[None, None, "cron-2"],
        ) as mock_ensure,
    ):
        await jira_poller.ensure_jira_poller_cron_with_retry(
            attempts=5, initial_delay_seconds=1.0, max_delay_seconds=30.0
        )

    assert mock_ensure.await_count == 3
    assert [call.args[0] for call in mock_sleep.await_args_list] == [1.0, 2.0, 4.0]


@pytest.mark.asyncio
async def test_retry_gives_up_after_exhausting_attempts() -> None:
    with (
        patch(f"{_MODULE}.asyncio.sleep", new_callable=AsyncMock),
        patch(
            f"{_MODULE}.ensure_jira_poller_cron", new_callable=AsyncMock, return_value=None
        ) as mock_ensure,
    ):
        await jira_poller.ensure_jira_poller_cron_with_retry(attempts=3, initial_delay_seconds=1.0)

    assert mock_ensure.await_count == 3


@pytest.mark.asyncio
async def test_retry_caps_delay_at_max() -> None:
    with (
        patch(f"{_MODULE}.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        patch(f"{_MODULE}.ensure_jira_poller_cron", new_callable=AsyncMock, return_value=None),
    ):
        await jira_poller.ensure_jira_poller_cron_with_retry(
            attempts=4, initial_delay_seconds=10.0, max_delay_seconds=15.0
        )

    assert [call.args[0] for call in mock_sleep.await_args_list] == [10.0, 15.0, 15.0, 15.0]
