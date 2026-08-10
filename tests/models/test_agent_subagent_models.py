"""Which model the agent graph and its general-purpose subagent are built with.

Model choice is not configurable any more: the router decides it from the
agent role and what the thread already went through. These tests pin the two
things that could regress silently — the subagent must not drift onto a
different model than its parent, and the escalation signals on the thread must
actually reach the router.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.graph.state import RunnableConfig

from agent import jira_poller
from agent.routing import HAIKU_MODEL_ID, OPUS_MODEL_ID, SONNET_MODEL_ID
from agent.server import get_agent


class _DummyAgent:
    def with_config(self, config: RunnableConfig) -> "_DummyAgent":
        self.config = config
        return self


def _config(metadata: dict[str, object] | None = None) -> RunnableConfig:
    return {
        "configurable": {
            "__is_for_execution__": True,
            "thread_id": "thread-123",
            "github_login": "octocat",
        },
        "metadata": metadata or {},
    }


async def _build_agent(config: RunnableConfig, *, profile: dict[str, object] | None = None):
    """Build the agent with everything but model resolution stubbed out."""
    main_model = MagicMock(name="main_model")
    subagent_model = MagicMock(name="subagent_model")
    captured: dict[str, object] = {}

    def fake_create_deep_agent(**kwargs: object) -> _DummyAgent:
        captured.update(kwargs)
        return _DummyAgent()

    with (
        patch(
            "agent.server.resolve_github_token",
            new_callable=AsyncMock,
            return_value=("ghp", None),
        ),
        patch("agent.server.resolve_triggering_user_identity", return_value=None),
        patch(
            "agent.server.ensure_sandbox_for_thread",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ),
        patch(
            "agent.server.aresolve_sandbox_work_dir",
            new_callable=AsyncMock,
            return_value="/workspace",
        ),
        patch("agent.server.load_profile", new_callable=AsyncMock, return_value=profile),
        patch("agent.server.fallback_model_id_for", return_value=None),
        patch("agent.server.make_model", side_effect=[main_model, subagent_model]) as make_model,
        patch("agent.server.construct_system_prompt", return_value="prompt"),
        patch("agent.server.create_deep_agent", side_effect=fake_create_deep_agent),
    ):
        await get_agent(config)

    return captured, make_model, main_model, subagent_model


@pytest.mark.asyncio
async def test_agent_and_subagent_run_the_routed_coding_model() -> None:
    captured, make_model, main_model, subagent_model = await _build_agent(_config())

    assert captured["model"] is main_model
    subagents = captured["subagents"]
    assert isinstance(subagents, list)
    assert subagents[0]["name"] == "general-purpose"
    assert subagents[0]["model"] is subagent_model

    main_call, subagent_call = make_model.call_args_list
    assert main_call.args == (SONNET_MODEL_ID,)
    assert main_call.kwargs["effort"] == "medium"
    # The general-purpose subagent does the parent's work; splitting the model
    # between them is how a run ends up reviewing its own weaker output.
    assert subagent_call.args == (SONNET_MODEL_ID,)
    assert subagent_call.kwargs["effort"] == "medium"


@pytest.mark.asyncio
async def test_dashboard_profile_no_longer_picks_the_model() -> None:
    """A profile may still carry an old model choice; routing ignores it."""
    _captured, make_model, _main, _subagent = await _build_agent(
        _config(),
        profile={
            "default_model": HAIKU_MODEL_ID,
            "reasoning_effort": "low",
            "default_subagent_model": OPUS_MODEL_ID,
            "subagent_reasoning_effort": "max",
        },
    )

    assert make_model.call_args_list[0].args == (SONNET_MODEL_ID,)
    assert make_model.call_args_list[0].kwargs["effort"] == "medium"
    assert make_model.call_args_list[1].args == (SONNET_MODEL_ID,)


@pytest.mark.asyncio
async def test_second_review_cycle_raises_effort_without_changing_model() -> None:
    config = _config({"jira_review_cycles_code": 2})
    _captured, make_model, _main, _subagent = await _build_agent(config)

    assert make_model.call_args_list[0].args == (SONNET_MODEL_ID,)
    assert make_model.call_args_list[0].kwargs["effort"] == "high"


@pytest.mark.asyncio
async def test_third_review_cycle_escalates_to_opus() -> None:
    config = _config({"jira_review_cycles_code": 3})
    _captured, make_model, _main, _subagent = await _build_agent(config)

    assert make_model.call_args_list[0].args == (OPUS_MODEL_ID,)
    assert make_model.call_args_list[0].kwargs["effort"] == "high"
    assert make_model.call_args_list[1].args == (OPUS_MODEL_ID,)


@pytest.mark.asyncio
async def test_recorded_risk_signals_escalate_the_first_attempt() -> None:
    config = _config({"routing_signals": {"has_migration": True, "files_changed": 12}})
    _captured, make_model, _main, _subagent = await _build_agent(config)

    assert make_model.call_args_list[0].args == (OPUS_MODEL_ID,)
    assert make_model.call_args_list[0].kwargs["effort"] == "high"


@pytest.mark.asyncio
async def test_resumed_column_decides_which_role_the_run_is() -> None:
    """The poller says which column it resumed from; that is the phase to route."""
    config = _config({"jira_column": jira_poller.COLUMN_CODE_APPROVED})
    _captured, make_model, _main, _subagent = await _build_agent(config)

    # Pre-merge preparation: verification work, not plain coding.
    assert make_model.call_args_list[0].args == (SONNET_MODEL_ID,)
    assert make_model.call_args_list[0].kwargs["effort"] == "high"


@pytest.mark.asyncio
async def test_closing_run_after_a_merge_drops_to_the_cheap_model() -> None:
    config = _config({"jira_column": jira_poller.COLUMN_MERGED})
    _captured, make_model, _main, _subagent = await _build_agent(config)

    # Administrative closing: no reasoning budget to spend, so no effort is sent.
    assert make_model.call_args_list[0].args == (HAIKU_MODEL_ID,)
    assert "effort" not in make_model.call_args_list[0].kwargs
    assert "thinking" not in make_model.call_args_list[0].kwargs


@pytest.mark.asyncio
async def test_column_on_the_run_config_beats_the_thread_metadata() -> None:
    """A resume carries the new column in its configurable; it is the fresher one."""
    config = _config({"jira_column": jira_poller.COLUMN_MERGED})
    config.get("configurable", {})["jira_new_column"] = jira_poller.COLUMN_ADJUST_CODE
    _captured, make_model, _main, _subagent = await _build_agent(config)

    assert make_model.call_args_list[0].args == (SONNET_MODEL_ID,)
    assert make_model.call_args_list[0].kwargs["effort"] == "medium"
