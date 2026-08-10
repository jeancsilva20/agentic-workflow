"""The metadata a run carries into LangSmith, and what survives a round trip."""

from __future__ import annotations

from agent.routing import resolve_model
from agent.routing.complexity import ComplexityTier
from agent.routing.roles import AgentRole
from agent.routing.telemetry import (
    ROUTING_MODE,
    RunMetadata,
    UsageData,
    build_run_metadata,
    model_label,
    route_label,
)

_REQUIRED_FIELDS = (
    "jira_issue_key",
    "thread_id",
    "agent_role",
    "workflow_stage",
    "model",
    "effort",
    "routing_mode",
    "complexity_tier",
    "routing_reason",
    "start_time",
)


def _metadata(role: AgentRole = AgentRole.CODING_AGENT, **kwargs) -> RunMetadata:
    route = resolve_model(role, **kwargs)
    return build_run_metadata(
        route.role,
        "thread-1",
        "SSAI-88",
        route.complexity,
        route,
        workflow_stage="Spec Aprovada",
    )


def test_trace_metadata_carries_every_required_field() -> None:
    trace = _metadata().as_metadata()

    missing = [field for field in _REQUIRED_FIELDS if field not in trace]
    assert not missing, f"missing from the trace metadata: {missing}"
    assert trace["jira_issue_key"] == "SSAI-88"
    assert trace["thread_id"] == "thread-1"
    assert trace["agent_role"] == AgentRole.CODING_AGENT.value
    assert trace["workflow_stage"] == "Spec Aprovada"
    assert trace["routing_mode"] == ROUTING_MODE == "automatic"
    assert trace["start_time"]


def test_metadata_never_invents_a_model_or_effort() -> None:
    """Telemetry records the router's decision; it does not make one."""
    route = resolve_model(AgentRole.JIRA_TRIAGE)
    metadata = build_run_metadata(
        route.role, "t", None, route.complexity, route, workflow_stage="BACKLOG"
    )

    assert metadata.model == route.model
    # Haiku roles carry no effort at all — telemetry must not substitute one.
    assert metadata.effort is route.effort is None
    assert metadata.routing_reason == route.reason


def test_escalation_reason_is_carried_for_reporting() -> None:
    metadata = _metadata(AgentRole.CODING_AGENT, retry_count=2)

    assert metadata.escalation_reason
    assert metadata.as_metadata()["escalation_reason"] == metadata.escalation_reason


def test_metadata_survives_the_round_trip_through_a_dict() -> None:
    """The console and the completion path both rebuild from a plain dict."""
    original = _metadata()

    assert RunMetadata.from_metadata(original.as_metadata()) == original
    assert RunMetadata.from_metadata(original.as_dict()) == original


def test_foreign_metadata_is_not_mistaken_for_ours() -> None:
    assert RunMetadata.from_metadata({"thread_id": "t"}) is None
    assert RunMetadata.from_metadata(None) is None
    assert RunMetadata.from_metadata({"agent_role": "coding_agent", "model": "x"}) is None


def test_complexity_tier_accepts_the_enum_or_its_value() -> None:
    route = resolve_model(AgentRole.CODING_AGENT)
    from_enum = build_run_metadata(
        route.role, "t", "SSAI-1", ComplexityTier.HIGH, route, workflow_stage="x"
    )
    from_value = build_run_metadata(
        route.role, "t", "SSAI-1", ComplexityTier.HIGH.value, route, workflow_stage="x"
    )

    assert from_enum.complexity_tier == from_value.complexity_tier == ComplexityTier.HIGH.value


def test_route_label_reads_as_the_routing_decision() -> None:
    assert model_label("anthropic:claude-opus-5") == "Opus"
    assert model_label("openai:gpt-5.6") == "gpt-5.6"
    assert route_label(_metadata(AgentRole.SPEC_REVIEWER)).startswith("Opus/")
    assert "/" not in route_label(_metadata(AgentRole.JIRA_TRIAGE))


def test_unknown_usage_is_none_not_zero() -> None:
    empty = UsageData()

    assert empty.as_dict() == {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "cost": None,
        "cost_source": None,
    }
    assert empty.known is False


def test_usage_from_dict_rejects_non_numbers() -> None:
    usage = UsageData.from_dict({"input_tokens": "lots", "cost": None, "cost_source": 7})

    assert usage.input_tokens is None
    assert usage.cost is None
    assert usage.cost_source is None
