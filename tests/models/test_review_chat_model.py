"""The PR review chat runs on its routed role, whatever the client asks for."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.graph.state import RunnableConfig

from agent.routing import SONNET_MODEL_ID, AgentRole, resolve_model


def _config(extra: dict[str, object] | None = None) -> RunnableConfig:
    configurable: dict[str, object] = {
        "__is_for_execution__": True,
        "thread_id": "chat-1",
        "chat_repo_owner": "octo",
        "chat_repo_name": "repo",
        "chat_pr_number": 7,
    }
    configurable.update(extra or {})
    return {"configurable": configurable}


async def _build_chat_agent(config: RunnableConfig):
    from agent import chat

    fake_pregel = MagicMock()
    fake_pregel.with_config = MagicMock(return_value=fake_pregel)

    with (
        patch("agent.chat.create_deep_agent", return_value=fake_pregel),
        patch("agent.chat.make_model") as make_model,
        patch(
            "agent.chat.get_effective_gateway_enabled",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        await chat.get_chat_agent(config)

    return make_model


@pytest.mark.asyncio
async def test_review_chat_runs_on_its_routed_model() -> None:
    make_model = await _build_chat_agent(_config())

    route = resolve_model(AgentRole.REVIEW_CHAT)
    assert make_model.call_args.args == (route.model,)
    assert make_model.call_args.kwargs["effort"] == route.effort


@pytest.mark.asyncio
async def test_a_client_supplied_chat_model_is_ignored() -> None:
    """The review page used to be able to pick the model; that path is gone."""
    make_model = await _build_chat_agent(
        _config({"chat_model_id": "anthropic:claude-opus-5", "chat_effort": "max"})
    )

    assert make_model.call_args.args == (SONNET_MODEL_ID,)
