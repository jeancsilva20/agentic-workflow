"""Automatic per-role model routing.

``resolve_model(role, complexity, retry_count, workflow_context)`` is the only
entry point callers need: it answers which model and reasoning effort a given
piece of workflow runs with, and why.
"""

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
from .phases import (
    ACTIVE_ROLES,
    DEFAULT_DISPATCH_ROLE,
    ROLE_SELECTION,
    is_active,
    role_for_column,
    role_for_dispatch,
)
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

__all__ = [
    "ACTIVE_ROLES",
    "DEFAULT_DISPATCH_ROLE",
    "HAIKU_MODEL_ID",
    "OPUS_MODEL_ID",
    "RETRY_ESCALATION_THRESHOLD",
    "RISK_SIGNALS",
    "ROLE_SELECTION",
    "SONNET_MODEL_ID",
    "AgentRole",
    "ComplexityTier",
    "ModelCapability",
    "ModelConfig",
    "active_risk_signals",
    "classify_complexity",
    "coerce_role",
    "complexity_score",
    "is_active",
    "model_capability",
    "resolve_model",
    "role_for_column",
    "role_for_dispatch",
    "routing_table",
    "safe_effort_for",
    "supports_effort",
]
