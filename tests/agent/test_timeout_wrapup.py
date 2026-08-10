from __future__ import annotations

from typing import cast

import pytest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage

from agent.middleware.timeout_wrapup import TimeoutWrapupMiddleware


@pytest.mark.asyncio
async def test_timeout_wrapup_starts_clock_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    times = [100.0, 105.0, 111.0]

    def monotonic() -> float:
        return times.pop(0) if times else 111.0

    monkeypatch.setattr("agent.middleware.timeout_wrapup.time.monotonic", monotonic)
    middleware = TimeoutWrapupMiddleware(timeout_seconds=10)
    seen: list[ModelRequest] = []

    async def handler(request: ModelRequest) -> ModelResponse:
        seen.append(request)
        return ModelResponse(result=[AIMessage(content="ok")])

    request = ModelRequest(
        model=cast(BaseChatModel, object()),
        messages=[],
        system_message=SystemMessage(content="base"),
    )

    await middleware.awrap_model_call(request, handler)
    await middleware.awrap_model_call(request, handler)

    assert seen[0].system_message is not None
    assert seen[1].system_message is not None
    assert seen[0].system_message.content == "base"
    assert isinstance(seen[1].system_message.content, str)
    assert "time_limit_warning" in seen[1].system_message.content


@pytest.mark.asyncio
async def test_timeout_wrapup_preserves_structured_system_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agent.middleware.timeout_wrapup.time.monotonic", lambda: 100.0)
    middleware = TimeoutWrapupMiddleware(timeout_seconds=1)
    middleware._start = 99.0
    seen: list[ModelRequest] = []

    async def handler(request: ModelRequest) -> ModelResponse:
        seen.append(request)
        return ModelResponse(result=[AIMessage(content="ok")])

    request = ModelRequest(
        model=cast(BaseChatModel, object()),
        messages=[],
        system_message=SystemMessage(
            content=[{"type": "text", "text": "base", "cache_control": {"type": "ephemeral"}}]
        ),
    )

    await middleware.awrap_model_call(request, handler)

    assert seen[0].system_message is not None
    content = seen[0].system_message.content
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "base", "cache_control": {"type": "ephemeral"}}
    warning_block = content[1]
    assert isinstance(warning_block, dict)
    assert warning_block["type"] == "text"
    assert "time_limit_warning" in warning_block["text"]


# ---------------------------------------------------------------------------
# Jira-run timeout behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_jira_run_timeout_uses_generic_instruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-Jira runs inject the generic wrapup instruction and do NOT mention jira_park_at_gate."""
    monkeypatch.setattr("agent.middleware.timeout_wrapup.time.monotonic", lambda: 100.0)
    middleware = TimeoutWrapupMiddleware(timeout_seconds=10, is_jira_run=False)
    middleware._start = 89.0  # 11 seconds elapsed — over the 10-second limit

    seen: list[ModelRequest] = []

    async def handler(request: ModelRequest) -> ModelResponse:
        seen.append(request)
        return ModelResponse(result=[AIMessage(content="ok")])

    request = ModelRequest(
        model=cast(BaseChatModel, object()),
        messages=[],
        system_message=SystemMessage(content="base"),
    )
    await middleware.awrap_model_call(request, handler)

    assert seen[0].system_message is not None
    content = seen[0].system_message.content
    assert isinstance(content, str)
    assert "time_limit_warning" in content
    assert "jira_park_at_gate" not in content


@pytest.mark.asyncio
async def test_jira_run_no_timeout_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Jira runs are not interrupted regardless of elapsed time when no timeout is configured."""
    monkeypatch.delenv("JIRA_RUN_WRAPUP_TIMEOUT_SECONDS", raising=False)
    # Simulate an enormous elapsed time (well beyond any normal timeout).
    monkeypatch.setattr("agent.middleware.timeout_wrapup.time.monotonic", lambda: 999_999.0)
    middleware = TimeoutWrapupMiddleware(is_jira_run=True)
    middleware._start = 0.0

    seen: list[ModelRequest] = []

    async def handler(request: ModelRequest) -> ModelResponse:
        seen.append(request)
        return ModelResponse(result=[AIMessage(content="ok")])

    request = ModelRequest(
        model=cast(BaseChatModel, object()),
        messages=[],
        system_message=SystemMessage(content="base"),
    )
    await middleware.awrap_model_call(request, handler)

    # System message must be untouched — no wrapup injection.
    assert seen[0].system_message is not None
    assert seen[0].system_message.content == "base"


@pytest.mark.asyncio
async def test_jira_run_no_timeout_when_env_var_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """JIRA_RUN_WRAPUP_TIMEOUT_SECONDS=0 explicitly disables the timeout."""
    monkeypatch.setenv("JIRA_RUN_WRAPUP_TIMEOUT_SECONDS", "0")
    monkeypatch.setattr("agent.middleware.timeout_wrapup.time.monotonic", lambda: 999_999.0)
    middleware = TimeoutWrapupMiddleware(is_jira_run=True)
    middleware._start = 0.0

    seen: list[ModelRequest] = []

    async def handler(request: ModelRequest) -> ModelResponse:
        seen.append(request)
        return ModelResponse(result=[AIMessage(content="ok")])

    request = ModelRequest(
        model=cast(BaseChatModel, object()),
        messages=[],
        system_message=SystemMessage(content="base"),
    )
    await middleware.awrap_model_call(request, handler)

    assert seen[0].system_message is not None
    assert seen[0].system_message.content == "base"


@pytest.mark.asyncio
async def test_jira_run_timeout_instruction_mentions_park_at_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the Jira timeout fires the injected instruction directs the agent to park at gate."""
    monkeypatch.setattr("agent.middleware.timeout_wrapup.time.monotonic", lambda: 100.0)
    # Pass an explicit timeout so this test is not affected by the env var.
    middleware = TimeoutWrapupMiddleware(timeout_seconds=10, is_jira_run=True)
    middleware._start = 89.0  # 11 seconds elapsed — over the 10-second limit

    seen: list[ModelRequest] = []

    async def handler(request: ModelRequest) -> ModelResponse:
        seen.append(request)
        return ModelResponse(result=[AIMessage(content="ok")])

    request = ModelRequest(
        model=cast(BaseChatModel, object()),
        messages=[],
        system_message=SystemMessage(content="base"),
    )
    await middleware.awrap_model_call(request, handler)

    assert seen[0].system_message is not None
    content = seen[0].system_message.content
    assert isinstance(content, str)
    assert "time_limit_warning" in content
    assert "jira_park_at_gate" in content
