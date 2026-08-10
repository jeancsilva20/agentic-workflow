from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from agent.utils import console_events


class _FakeAsyncClient:
    def __init__(self) -> None:
        self.post = AsyncMock()

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class _RaisingAsyncClient:
    async def __aenter__(self) -> _RaisingAsyncClient:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def post(self, *args: Any, **kwargs: Any) -> None:
        raise ConnectionError("console is down")


async def test_push_is_noop_when_console_url_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(console_events, "AGENT_CONSOLE_URL", "")
    fake_client = _FakeAsyncClient()
    monkeypatch.setattr(console_events.httpx, "AsyncClient", lambda **_kwargs: fake_client)

    await console_events.push_log("hello")

    fake_client.post.assert_not_called()


async def test_push_tick_event_posts_to_expected_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(console_events, "AGENT_CONSOLE_URL", "http://localhost:5000")
    fake_client = _FakeAsyncClient()
    monkeypatch.setattr(console_events.httpx, "AsyncClient", lambda **_kwargs: fake_client)

    await console_events.push_tick_event({"launched": 1}, {"resumed": 0})

    fake_client.post.assert_awaited_once_with(
        "http://localhost:5000/api/events/tick",
        json={"step_a": {"launched": 1}, "step_b": {"resumed": 0}},
    )


async def test_push_run_event_posts_extra_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(console_events, "AGENT_CONSOLE_URL", "http://localhost:5000")
    fake_client = _FakeAsyncClient()
    monkeypatch.setattr(console_events.httpx, "AsyncClient", lambda **_kwargs: fake_client)

    await console_events.push_run_event("SSAI-1", "dead", reason="model call limit")

    fake_client.post.assert_awaited_once_with(
        "http://localhost:5000/api/events/run",
        json={"issue_key": "SSAI-1", "action": "dead", "reason": "model call limit"},
    )


async def test_push_swallows_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(console_events, "AGENT_CONSOLE_URL", "http://localhost:5000")
    monkeypatch.setattr(
        console_events.httpx, "AsyncClient", lambda **_kwargs: _RaisingAsyncClient()
    )

    # Must not raise.
    await console_events.push_log("this will fail to send")
