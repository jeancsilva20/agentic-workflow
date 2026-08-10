"""The routing decision for one dispatched run, derived from what it carries.

Two callers need the same answer from the same inputs: the graph factory, which
routes the run when it builds the agent, and the dispatcher, which has to *tag*
the run with the route before it starts so the trace can be aggregated later.
If those two derived the route independently they would drift, and telemetry
that reports a different model from the one that ran is worse than none.

So the derivation lives here once, over the two dicts a run is created with —
its ``config["metadata"]`` and its ``configurable``.
"""

from __future__ import annotations

from typing import Any

from ..utils.json_types import as_json_object
from .phases import DEFAULT_DISPATCH_ROLE, role_for_column
from .roles import AgentRole
from .router import ModelConfig, resolve_model

# `log_review_cycle` records the highest self-review pass per phase on the
# thread. The first pass is not a retry — it is the review every change gets —
# so only the passes after it count as work coming back.
REVIEW_CYCLE_METADATA_KEYS = ("jira_review_cycles_code", "jira_review_cycles_spec")

# Anything the workflow learns about a change (files touched, whether it moves
# a migration or touches auth) is written here, on the thread, rather than
# passed per run: the router is called on every graph build, including resumes
# that carry no such context of their own.
ROUTING_SIGNALS_KEY = "routing_signals"

# Three of the five graphs are one job each and route themselves, from inside,
# to a fixed role — the Jira column they were dispatched at says nothing about
# them. Mirrored here so a dispatcher can tag such a run with the role it will
# actually run as instead of falling through to "coding work".
GRAPH_ROLES: dict[str, AgentRole] = {
    "reviewer": AgentRole.CODE_REVIEWER,
    "analyzer": AgentRole.STYLE_ANALYZER,
    "chat": AgentRole.REVIEW_CHAT,
}

# The graph whose role comes from the workflow rather than from the graph.
DEFAULT_ASSISTANT_ID = "agent"


def _positive_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, value)


def dispatch_role(
    metadata: Any, configurable: Any, assistant_id: str = DEFAULT_ASSISTANT_ID
) -> AgentRole:
    """Which phase of the workflow this run has to cover.

    The poller says which column it resumed the card from; that column is the
    instruction the run follows, so it is also what decides the route. A run
    with no column — dashboard, Slack, Linear, a PR comment — is coding work.

    A run on one of the single-purpose graphs is that graph's job regardless of
    where the card sits.
    """
    graph_role = GRAPH_ROLES.get(assistant_id)
    if graph_role is not None:
        return graph_role
    metadata = as_json_object(metadata)
    configurable = as_json_object(configurable)
    for source in (configurable.get("jira_new_column"), metadata.get("jira_column")):
        role = role_for_column(source if isinstance(source, str) else None)
        if role is not None:
            return role
    return DEFAULT_DISPATCH_ROLE


def routing_signals(metadata: Any, configurable: Any) -> dict[str, Any]:
    """Complexity signals for this thread, for :func:`resolve_model`.

    Explicit signals win over derived ones: a caller that already knows the
    change touches auth should not have that overwritten by a counter.
    """
    metadata = as_json_object(metadata)
    configurable = as_json_object(configurable)
    signals: dict[str, Any] = {
        **as_json_object(metadata.get(ROUTING_SIGNALS_KEY)),
        **as_json_object(configurable.get(ROUTING_SIGNALS_KEY)),
    }

    review_cycles = max(
        (_positive_int(metadata.get(key)) for key in REVIEW_CYCLE_METADATA_KEYS), default=0
    )
    returns = max(0, review_cycles - 1)
    signals.setdefault("retry_count", returns)
    signals.setdefault("review_return_count", returns)
    return signals


def resolve_dispatch_route(
    metadata: Any, configurable: Any, assistant_id: str = DEFAULT_ASSISTANT_ID
) -> ModelConfig:
    """The model, effort and reason a run created with these dicts will get.

    The single-purpose graphs are resolved on the bare role, because that is
    exactly what they do themselves when they build their model — a card's
    retry counter must not escalate a review-chat reply.
    """
    role = dispatch_role(metadata, configurable, assistant_id)
    if assistant_id in GRAPH_ROLES:
        return resolve_model(role)
    signals = routing_signals(metadata, configurable)
    return resolve_model(
        role,
        retry_count=int(signals.get("retry_count") or 0),
        workflow_context=signals,
    )
