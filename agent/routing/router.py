"""The model router: one place that decides which model runs which role.

Before this, a run's model came from whatever layer happened to set it last —
a console-wide default, a dashboard profile, a per-thread key. That made every
step of the Jira workflow run on the same model, which is either too expensive
for moving a card or too weak for reviewing a spec.

Routing is automatic and has no override on purpose: the role, the measured
complexity, and the retry count are the whole input. Every decision carries a
``reason`` so a surprising choice can be explained after the fact from the
run's logs rather than reconstructed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..dashboard.options import DEFAULT_MODEL_ID, SUPPORTED_MODELS
from .capabilities import safe_effort_for, supports_effort
from .complexity import (
    ComplexityTier,
    active_risk_signals,
    classify_complexity,
)
from .roles import AgentRole, coerce_role


def _model_for_family(*prefixes: str) -> str:
    """First catalog id in one of ``prefixes``, else the catalog default.

    Routing names families ("Haiku", "Sonnet", "Opus"), not versions. Resolving
    through the catalog means a version bump in ``dashboard/options.py`` moves
    routing with it instead of leaving the router pointing at an id that no
    longer exists.
    """
    for prefix in prefixes:
        for model in SUPPORTED_MODELS:
            if model["id"].startswith(prefix):
                return model["id"]
    return DEFAULT_MODEL_ID


HAIKU_MODEL_ID: str = _model_for_family("anthropic:claude-haiku")
SONNET_MODEL_ID: str = _model_for_family("anthropic:claude-sonnet")
OPUS_MODEL_ID: str = _model_for_family("anthropic:claude-opus")


@dataclass(frozen=True)
class ModelConfig:
    """A routing decision: what to run, how hard, and why."""

    model: str
    effort: str | None
    reason: str
    role: AgentRole
    complexity: ComplexityTier
    escalation_reason: str | None = None

    @property
    def escalated(self) -> bool:
        return self.escalation_reason is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "model": self.model,
            "effort": self.effort,
            "effort_supported": supports_effort(self.model),
            "complexity": self.complexity.value,
            "reason": self.reason,
            "escalation_reason": self.escalation_reason,
        }


# The baseline table. Haiku roles carry no effort at all: they move cards, run
# a fixed harness, or archive a change — extra reasoning buys nothing there and
# is billed on every call.
_DEFAULT_ROUTES: dict[AgentRole, tuple[str, str | None]] = {
    AgentRole.JIRA_TRIAGE: (HAIKU_MODEL_ID, None),
    AgentRole.PYTHON_HARNESS: (HAIKU_MODEL_ID, None),
    AgentRole.ARCHIVE_AGENT: (HAIKU_MODEL_ID, None),
    AgentRole.SPEC_AUTHOR: (SONNET_MODEL_ID, "high"),
    AgentRole.SPEC_ADJUSTER: (SONNET_MODEL_ID, "high"),
    AgentRole.SPEC_REVIEWER: (OPUS_MODEL_ID, "high"),
    AgentRole.CODING_AGENT: (SONNET_MODEL_ID, "medium"),
    AgentRole.CODE_ADJUSTER: (SONNET_MODEL_ID, "medium"),
    AgentRole.OPENSPEC_VERIFIER: (SONNET_MODEL_ID, "high"),
    AgentRole.CODE_REVIEWER: (OPUS_MODEL_ID, "high"),
    AgentRole.DIFF_GROUPING: (HAIKU_MODEL_ID, None),
    # Interactive: a person is waiting on each turn, and the hard reasoning
    # was already done by the review being discussed.
    AgentRole.REVIEW_CHAT: (SONNET_MODEL_ID, "medium"),
    AgentRole.STYLE_ANALYZER: (SONNET_MODEL_ID, "medium"),
    AgentRole.DOCS_AGENT: (HAIKU_MODEL_ID, None),
    AgentRole.ESCALATION_AGENT: (OPUS_MODEL_ID, "high"),
}

# Only the roles that write code escalate. A reviewer already runs on Opus, and
# a triage call that failed twice is not failing because Haiku was too weak.
_ESCALATING_ROLES: frozenset[AgentRole] = frozenset(
    {AgentRole.CODING_AGENT, AgentRole.CODE_ADJUSTER}
)

# Two failed attempts is the point where "try again on the same model" stops
# being a plausible fix.
RETRY_ESCALATION_THRESHOLD = 2


def _docs_route(
    complexity: ComplexityTier, workflow_context: Mapping[str, Any]
) -> tuple[str, str | None, str]:
    """Docs work splits in two: mechanical edits vs. reading for meaning.

    Regenerating an index or moving a file is Haiku work. Deciding whether the
    documentation still tells the truth after a change is not, so the caller
    says which one it is via ``docs_mode``; a complex change is treated as
    semantic even when the caller didn't say so.
    """
    mode = workflow_context.get("docs_mode")
    semantic = mode == "semantic" or (mode != "mechanical" and complexity >= ComplexityTier.HIGH)
    if semantic:
        return (
            SONNET_MODEL_ID,
            "high",
            "docs_agent semantic review (docs_mode=semantic or complexity >= HIGH)",
        )
    return HAIKU_MODEL_ID, None, "docs_agent mechanical documentation operation"


def _escalate(
    role: AgentRole,
    complexity: ComplexityTier,
    retry_count: int,
    workflow_context: Mapping[str, Any],
) -> tuple[str, str | None, str] | None:
    """The stronger route for a coding role, or ``None`` to keep the default."""
    if retry_count >= RETRY_ESCALATION_THRESHOLD:
        return (
            OPUS_MODEL_ID,
            "high",
            f"{retry_count} failed attempts (>= {RETRY_ESCALATION_THRESHOLD})",
        )

    risk_signals = active_risk_signals(workflow_context)
    if complexity is ComplexityTier.CRITICAL:
        return OPUS_MODEL_ID, "high", "complexity CRITICAL"
    if complexity >= ComplexityTier.HIGH and risk_signals:
        return (
            OPUS_MODEL_ID,
            "high",
            f"complexity {complexity.value.upper()} with risk signals: {', '.join(risk_signals)}",
        )
    if complexity >= ComplexityTier.HIGH:
        return (
            SONNET_MODEL_ID,
            "high",
            f"complexity {complexity.value.upper()} without risk signals: effort raised, model kept",
        )
    if retry_count >= 1:
        return SONNET_MODEL_ID, "high", "attempt 2: effort raised, model kept"
    return None


def resolve_model(
    agent_role: AgentRole | str,
    complexity: ComplexityTier | str | None = None,
    retry_count: int = 0,
    workflow_context: Mapping[str, Any] | None = None,
) -> ModelConfig:
    """Resolve the model and effort for one role.

    ``complexity`` is classified from ``workflow_context`` when not given, so a
    caller that already has the signals never has to classify twice.
    ``retry_count`` is counted in that classification too — a task that keeps
    coming back is, by definition, harder than it looked.
    """
    role = coerce_role(agent_role)
    context: dict[str, Any] = dict(workflow_context or {})
    retries = max(0, int(retry_count))
    if retries:
        context.setdefault("retry_count", retries)

    if complexity is None:
        tier = classify_complexity(context)
    elif isinstance(complexity, ComplexityTier):
        tier = complexity
    else:
        tier = ComplexityTier(complexity)

    default_model, default_effort = _DEFAULT_ROUTES[role]
    escalation_reason: str | None = None

    if role is AgentRole.DOCS_AGENT:
        model, effort, reason = _docs_route(tier, context)
    else:
        model, effort = default_model, default_effort
        reason = f"{role.value} default route"
        if role in _ESCALATING_ROLES:
            escalated = _escalate(role, tier, retries, context)
            if escalated is not None:
                model, effort, escalation_reason = escalated
                reason = f"{role.value} escalated: {escalation_reason}"

    requested_effort = effort
    effort = safe_effort_for(model, requested_effort)
    if requested_effort is not None and effort is None:
        reason = f"{reason}; effort {requested_effort!r} dropped ({model} does not support it)"

    return ModelConfig(
        model=model,
        effort=effort,
        reason=reason,
        role=role,
        complexity=tier,
        escalation_reason=escalation_reason,
    )


def routing_table() -> list[dict[str, Any]]:
    """Every role's baseline decision — zero retries, no complexity signals.

    This is what the console renders: the table as configured, not the routing
    a particular run happened to get. Each entry also says where the role is
    selected at runtime, and whether anything selects it at all — a role the
    current graph topology never reaches would otherwise read as a live route.
    """
    from .phases import ROLE_SELECTION, is_active

    table: list[dict[str, Any]] = []
    for role in AgentRole:
        entry = resolve_model(role, complexity=ComplexityTier.LOW, retry_count=0).as_dict()
        entry["active"] = is_active(role)
        entry["selected_by"] = ROLE_SELECTION[role]
        table.append(entry)
    return table
