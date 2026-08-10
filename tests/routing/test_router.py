"""Per-role routing: the default table, escalation, and the effort guard."""

from __future__ import annotations

import pytest

from agent.routing import (
    HAIKU_MODEL_ID,
    OPUS_MODEL_ID,
    RETRY_ESCALATION_THRESHOLD,
    SONNET_MODEL_ID,
    AgentRole,
    ComplexityTier,
    coerce_role,
    resolve_model,
    routing_table,
    supports_effort,
)

# The table the plan specifies, role by role, at baseline complexity.
_DEFAULT_ROUTES: list[tuple[AgentRole, str, str | None]] = [
    (AgentRole.JIRA_TRIAGE, HAIKU_MODEL_ID, None),
    (AgentRole.PYTHON_HARNESS, HAIKU_MODEL_ID, None),
    (AgentRole.ARCHIVE_AGENT, HAIKU_MODEL_ID, None),
    (AgentRole.DIFF_GROUPING, HAIKU_MODEL_ID, None),
    (AgentRole.DOCS_AGENT, HAIKU_MODEL_ID, None),
    (AgentRole.SPEC_AUTHOR, SONNET_MODEL_ID, "high"),
    (AgentRole.SPEC_ADJUSTER, SONNET_MODEL_ID, "high"),
    (AgentRole.OPENSPEC_VERIFIER, SONNET_MODEL_ID, "high"),
    (AgentRole.CODING_AGENT, SONNET_MODEL_ID, "medium"),
    (AgentRole.CODE_ADJUSTER, SONNET_MODEL_ID, "medium"),
    (AgentRole.REVIEW_CHAT, SONNET_MODEL_ID, "medium"),
    (AgentRole.STYLE_ANALYZER, SONNET_MODEL_ID, "medium"),
    (AgentRole.SPEC_REVIEWER, OPUS_MODEL_ID, "high"),
    (AgentRole.CODE_REVIEWER, OPUS_MODEL_ID, "high"),
    (AgentRole.ESCALATION_AGENT, OPUS_MODEL_ID, "high"),
]

_CODING_ROLES = (AgentRole.CODING_AGENT, AgentRole.CODE_ADJUSTER)


@pytest.mark.parametrize(("role", "model", "effort"), _DEFAULT_ROUTES)
def test_default_route_per_role(role: AgentRole, model: str, effort: str | None) -> None:
    decision = resolve_model(role)

    assert decision.model == model
    assert decision.effort == effort
    assert decision.role is role
    assert decision.reason


def test_every_role_has_a_route() -> None:
    """A role added without a route would raise at the first call in production."""
    assert {role for role, _model, _effort in _DEFAULT_ROUTES} == set(AgentRole)


def test_cheap_roles_send_no_effort_at_all() -> None:
    """``None``, not the string "none": extra reasoning is billed on every call."""
    for role in (AgentRole.JIRA_TRIAGE, AgentRole.PYTHON_HARNESS, AgentRole.ARCHIVE_AGENT):
        assert resolve_model(role).effort is None


def test_role_accepts_its_wire_value() -> None:
    """Roles travel through JSON and thread metadata as plain strings."""
    assert resolve_model("code_reviewer").role is AgentRole.CODE_REVIEWER
    assert coerce_role("coding_agent") is AgentRole.CODING_AGENT


def test_unknown_role_is_rejected_loudly() -> None:
    with pytest.raises(ValueError, match="unknown agent role"):
        resolve_model("marketing_agent")


# --- escalation -----------------------------------------------------------


@pytest.mark.parametrize("role", _CODING_ROLES)
def test_second_attempt_raises_effort_but_keeps_the_model(role: AgentRole) -> None:
    decision = resolve_model(role, retry_count=1)

    assert decision.model == SONNET_MODEL_ID
    assert decision.effort == "high"
    assert decision.escalation_reason is not None


@pytest.mark.parametrize("role", _CODING_ROLES)
def test_two_failed_attempts_escalate_to_opus(role: AgentRole) -> None:
    decision = resolve_model(role, retry_count=RETRY_ESCALATION_THRESHOLD)

    assert decision.model == OPUS_MODEL_ID
    assert decision.effort == "high"
    assert decision.escalated
    assert "failed attempts" in (decision.escalation_reason or "")


@pytest.mark.parametrize("role", _CODING_ROLES)
def test_further_retries_stay_on_opus(role: AgentRole) -> None:
    assert resolve_model(role, retry_count=7).model == OPUS_MODEL_ID


@pytest.mark.parametrize("signal", ["has_auth_change", "has_concurrency", "has_migration"])
def test_risk_signals_escalate_the_first_attempt(signal: str) -> None:
    """No failure needed: these are the areas where the first answer must be right."""
    decision = resolve_model(AgentRole.CODING_AGENT, workflow_context={signal: True})

    assert decision.complexity is ComplexityTier.HIGH
    assert decision.model == OPUS_MODEL_ID
    assert decision.effort == "high"
    assert signal in (decision.escalation_reason or "")


def test_high_complexity_without_risk_signals_only_raises_effort() -> None:
    """Big is not the same as dangerous — pay for care, not for Opus."""
    decision = resolve_model(
        AgentRole.CODING_AGENT,
        complexity=ComplexityTier.HIGH,
    )

    assert decision.model == SONNET_MODEL_ID
    assert decision.effort == "high"
    assert "without risk signals" in (decision.escalation_reason or "")


def test_critical_complexity_escalates_without_any_named_signal() -> None:
    decision = resolve_model(AgentRole.CODING_AGENT, complexity="critical")

    assert decision.model == OPUS_MODEL_ID
    assert decision.escalation_reason == "complexity CRITICAL"


def test_retry_count_feeds_the_classifier() -> None:
    """One retry plus a wide diff is a harder task than either on its own."""
    decision = resolve_model(
        AgentRole.CODING_AGENT,
        retry_count=1,
        workflow_context={"files_changed": 25},
    )

    assert decision.complexity is ComplexityTier.HIGH


def test_explicit_complexity_wins_over_the_signals() -> None:
    """A caller that already classified must not be reclassified underneath."""
    decision = resolve_model(
        AgentRole.CODING_AGENT,
        complexity=ComplexityTier.LOW,
        workflow_context={"has_security": True, "files_changed": 40},
    )

    assert decision.complexity is ComplexityTier.LOW
    assert decision.model == SONNET_MODEL_ID
    assert decision.effort == "medium"
    assert decision.escalation_reason is None


@pytest.mark.parametrize(
    "role",
    [
        AgentRole.JIRA_TRIAGE,
        AgentRole.SPEC_AUTHOR,
        AgentRole.SPEC_REVIEWER,
        AgentRole.CODE_REVIEWER,
        AgentRole.OPENSPEC_VERIFIER,
        AgentRole.ARCHIVE_AGENT,
        AgentRole.ESCALATION_AGENT,
    ],
)
def test_non_coding_roles_never_escalate(role: AgentRole) -> None:
    """Triage failing twice is not a sign Haiku was too weak to move a card."""
    baseline = resolve_model(role)
    stressed = resolve_model(
        role,
        retry_count=5,
        workflow_context={"has_migration": True, "has_security": True, "files_changed": 40},
    )

    assert (stressed.model, stressed.effort) == (baseline.model, baseline.effort)
    assert stressed.escalation_reason is None


# --- docs agent -----------------------------------------------------------


def test_docs_agent_is_haiku_for_mechanical_work() -> None:
    decision = resolve_model(AgentRole.DOCS_AGENT, workflow_context={"docs_mode": "mechanical"})

    assert decision.model == HAIKU_MODEL_ID
    assert decision.effort is None


def test_docs_agent_is_sonnet_for_semantic_review() -> None:
    decision = resolve_model(AgentRole.DOCS_AGENT, workflow_context={"docs_mode": "semantic"})

    assert decision.model == SONNET_MODEL_ID
    assert decision.effort == "high"


def test_docs_agent_treats_a_complex_change_as_semantic() -> None:
    """Nobody says "semantic" on a migration; the change itself says it."""
    decision = resolve_model(AgentRole.DOCS_AGENT, workflow_context={"has_migration": True})

    assert decision.model == SONNET_MODEL_ID
    assert decision.effort == "high"


def test_docs_agent_mechanical_wins_over_complexity() -> None:
    decision = resolve_model(
        AgentRole.DOCS_AGENT,
        complexity=ComplexityTier.CRITICAL,
        workflow_context={"docs_mode": "mechanical"},
    )

    assert decision.model == HAIKU_MODEL_ID


# --- lite mode override ---------------------------------------------------


def test_lite_mode_forces_haiku_on_every_role(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the toggle is on, no Opus or Sonnet call is ever made."""
    from agent.routing import router

    monkeypatch.setattr(router, "lite_mode_override", lambda: True)

    for role in AgentRole:
        decision = resolve_model(role)
        assert decision.model == HAIKU_MODEL_ID, f"{role}: expected Haiku, got {decision.model}"
        assert decision.effort is None, f"{role}: expected no effort, got {decision.effort}"
        assert "lite mode" in decision.reason


def test_lite_mode_bypasses_escalation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry-count and risk signals must not override the lite mode short-circuit."""
    from agent.routing import router

    monkeypatch.setattr(router, "lite_mode_override", lambda: True)

    decision = resolve_model(
        AgentRole.CODING_AGENT,
        retry_count=10,
        workflow_context={"has_migration": True, "has_security": True},
    )

    assert decision.model == HAIKU_MODEL_ID
    assert decision.effort is None
    assert decision.escalation_reason is None


def test_lite_mode_bypasses_docs_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """The semantic docs route (Sonnet) must also be suppressed."""
    from agent.routing import router

    monkeypatch.setattr(router, "lite_mode_override", lambda: True)

    for docs_mode in ("mechanical", "semantic", None):
        ctx = {"docs_mode": docs_mode} if docs_mode is not None else {}
        decision = resolve_model(AgentRole.DOCS_AGENT, workflow_context=ctx)
        assert decision.model == HAIKU_MODEL_ID
        assert decision.effort is None


def test_lite_mode_off_restores_normal_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disabling the override must give back the full routing table."""
    from agent.routing import router

    monkeypatch.setattr(router, "lite_mode_override", lambda: False)

    # CODE_REVIEWER is Opus by default — it must come back when lite mode is off
    decision = resolve_model(AgentRole.CODE_REVIEWER)

    assert decision.model == OPUS_MODEL_ID
    assert decision.effort == "high"


def test_lite_mode_none_treated_as_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """``None`` from the config file (field absent) must not activate lite mode."""
    from agent.routing import router

    monkeypatch.setattr(router, "lite_mode_override", lambda: None)

    decision = resolve_model(AgentRole.SPEC_REVIEWER)

    assert decision.model == OPUS_MODEL_ID


# --- capability guard -----------------------------------------------------


def test_effort_is_dropped_when_the_model_cannot_take_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """A model that rejects the routed effort must get no effort, not a wrong one."""
    from agent.routing import router

    monkeypatch.setattr(router, "safe_effort_for", lambda _model, _effort: None)

    decision = resolve_model(AgentRole.CODE_REVIEWER)

    assert decision.effort is None
    assert "dropped" in decision.reason


def test_every_routed_effort_is_one_the_model_advertises() -> None:
    for role in AgentRole:
        decision = resolve_model(role)
        if decision.effort is not None:
            assert supports_effort(decision.model, decision.effort), role


# --- serialization --------------------------------------------------------


def test_decision_serializes_for_the_api_and_telemetry() -> None:
    payload = resolve_model(AgentRole.CODING_AGENT, retry_count=3).as_dict()

    assert payload["role"] == "coding_agent"
    assert payload["model"] == OPUS_MODEL_ID
    assert payload["effort"] == "high"
    assert payload["effort_supported"] is True
    assert payload["complexity"] == "medium"
    assert payload["escalation_reason"]


def test_routing_table_reports_the_baseline_for_every_role() -> None:
    table = routing_table()

    assert [entry["role"] for entry in table] == [role.value for role in AgentRole]
    for entry in table:
        assert entry["complexity"] == "low"
        assert entry["escalation_reason"] is None
        assert entry["selected_by"]
        if not entry["effort_supported"]:
            assert entry["effort"] is None
