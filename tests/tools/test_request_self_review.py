from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent.tools.request_self_review import request_self_review

_MODULE = "agent.tools.request_self_review"


@pytest.mark.asyncio
async def test_delegates_to_request_pr_review() -> None:
    with patch(
        f"{_MODULE}.request_pr_review",
        new_callable=AsyncMock,
        return_value={"success": True, "run_id": "r1"},
    ) as mock_request:
        result = await request_self_review("https://github.com/acme/repo/pull/1")

    mock_request.assert_awaited_once_with("https://github.com/acme/repo/pull/1")
    assert result == {"success": True, "run_id": "r1"}


@pytest.mark.asyncio
async def test_propagates_failure_from_request_pr_review() -> None:
    with patch(
        f"{_MODULE}.request_pr_review",
        new_callable=AsyncMock,
        return_value={"success": False, "error": "bad url"},
    ):
        result = await request_self_review("not-a-url")

    assert result == {"success": False, "error": "bad url"}
