from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent.tools.log_openspec_event import log_openspec_event

_MODULE = "agent.tools.log_openspec_event"


@pytest.mark.asyncio
async def test_version_loaded_event_carries_the_pinned_version() -> None:
    with patch(f"{_MODULE}.console_events.push_log", new_callable=AsyncMock) as mock_push:
        result = await log_openspec_event("version_loaded", detail="v1.8.0", issue_key="SSAI-1")

    assert result == {"success": True}
    mock_push.assert_awaited_once_with("[SSAI-1] openspec: version v1.8.0 loaded")


@pytest.mark.asyncio
async def test_lifecycle_event_appends_the_change_name() -> None:
    with patch(f"{_MODULE}.console_events.push_log", new_callable=AsyncMock) as mock_push:
        result = await log_openspec_event("archived", detail="ssai-88-fix-status")

    assert result == {"success": True}
    mock_push.assert_awaited_once_with("openspec: archived (ssai-88-fix-status)")


@pytest.mark.asyncio
async def test_lifecycle_event_without_detail() -> None:
    with patch(f"{_MODULE}.console_events.push_log", new_callable=AsyncMock) as mock_push:
        result = await log_openspec_event("verification_passed")

    assert result == {"success": True}
    mock_push.assert_awaited_once_with("openspec: verification passed")


@pytest.mark.asyncio
async def test_unknown_event_is_rejected_without_logging() -> None:
    with patch(f"{_MODULE}.console_events.push_log", new_callable=AsyncMock) as mock_push:
        result = await log_openspec_event("merged")

    assert result["success"] is False
    assert "unknown event" in result["error"]
    mock_push.assert_not_awaited()
