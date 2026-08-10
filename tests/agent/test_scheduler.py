from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent.scheduler import _launch


@pytest.mark.asyncio
async def test_launch_dispatches_jira_poll_task() -> None:
    with patch(
        "agent.scheduler.jira_poller_tick",
        new_callable=AsyncMock,
        return_value={"step_a": {}, "step_b": {}},
    ) as mock_tick:
        result = await _launch({"task": "jira_poll"}, {"configurable": {}})

    mock_tick.assert_awaited_once()
    assert result == {"result": {"step_a": {}, "step_b": {}}}


@pytest.mark.asyncio
async def test_launch_still_dispatches_reconcile_task() -> None:
    with patch(
        "agent.scheduler.reconcile_stale_runs",
        new_callable=AsyncMock,
        return_value={"status": "ok"},
    ) as mock_reconcile:
        result = await _launch({"task": "reconcile"}, {"configurable": {}})

    mock_reconcile.assert_awaited_once()
    assert result == {"result": {"status": "ok"}}


@pytest.mark.asyncio
async def test_launch_reports_missing_schedule_id() -> None:
    result = await _launch({}, {"configurable": {}})

    assert result == {"result": {"status": "missing_schedule_id"}}
