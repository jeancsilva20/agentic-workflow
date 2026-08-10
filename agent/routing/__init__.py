"""Automatic per-role model routing.

``resolve_model(role, complexity, retry_count, workflow_context)`` is the only
entry point callers need: it answers which model and reasoning effort a given
piece of workflow runs with, and why.
"""

from .active_agents import ActiveAgentRegistry, active_agents
from .capabilities import (
    ModelCapability,
    model_capability,
    safe_effort_for,
    supports_effort,
)
from .complexity import (
    RISK_SIGNALS,
    ComplexityTier,
    active_risk_signals,
    classify_complexity,
    complexity_score,
)
from .dispatch_route import (
    ROUTING_SIGNALS_KEY,
    dispatch_role,
    resolve_dispatch_route,
    routing_signals,
)
from .phases import (
    ACTIVE_ROLES,
    DEFAULT_DISPATCH_ROLE,
    ROLE_SELECTION,
    is_active,
    role_for_column,
    role_for_dispatch,
)
from .pricing import MODEL_PRICING, PRICING_LAST_UPDATED, estimate_cost, pricing_table
from .roles import AgentRole, coerce_role
from .router import (
    HAIKU_MODEL_ID,
    OPUS_MODEL_ID,
    RETRY_ESCALATION_THRESHOLD,
    SONNET_MODEL_ID,
    ModelConfig,
    resolve_model,
    routing_table,
)
from .telemetry import RunMetadata, UsageData, build_run_metadata, route_label
from .usage_store import (
    AgentUsageSummary,
    DailyUsage,
    JiraUsageSummary,
    ModelUsageSummary,
    RunEntry,
    UsageStore,
    usage_store,
)

__all__ = [
    "ACTIVE_ROLES",
    "DEFAULT_DISPATCH_ROLE",
    "HAIKU_MODEL_ID",
    "MODEL_PRICING",
    "OPUS_MODEL_ID",
    "PRICING_LAST_UPDATED",
    "RETRY_ESCALATION_THRESHOLD",
    "RISK_SIGNALS",
    "ROLE_SELECTION",
    "ROUTING_SIGNALS_KEY",
    "SONNET_MODEL_ID",
    "ActiveAgentRegistry",
    "AgentRole",
    "AgentUsageSummary",
    "ComplexityTier",
    "DailyUsage",
    "JiraUsageSummary",
    "ModelCapability",
    "ModelConfig",
    "ModelUsageSummary",
    "RunEntry",
    "RunMetadata",
    "UsageData",
    "UsageStore",
    "active_agents",
    "active_risk_signals",
    "build_run_metadata",
    "classify_complexity",
    "coerce_role",
    "complexity_score",
    "dispatch_role",
    "estimate_cost",
    "is_active",
    "model_capability",
    "pricing_table",
    "resolve_dispatch_route",
    "resolve_model",
    "role_for_column",
    "role_for_dispatch",
    "route_label",
    "routing_signals",
    "routing_table",
    "safe_effort_for",
    "supports_effort",
    "usage_store",
]
