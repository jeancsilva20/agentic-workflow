"""Run-level telemetry: the metadata every agent execution carries into LangSmith.

A Jira card is not a trace. One card spans several runs — spec, review, code,
adjustments — each with its own trace id, separated by hours of a human sitting
on a gate. So the aggregation unit here is ``jira_issue_key`` + ``thread_id``,
not the trace, and it only works if every run is *tagged* at dispatch: LangSmith
can group by metadata it was given, never by metadata it could have inferred.

Data-availability assessment
----------------------------
Classified against what the LangSmith SDK actually returns for a run
(``langsmith.schemas.Run``) and what ``agent/review/trace_context.py`` already
does with it. This ran *before* any instrumentation was added, and it is the
reason the fields below are attached at dispatch rather than reconstructed:

AVAILABLE_NOW — LangSmith already has it, no instrumentation needed
    - ``thread_id``: every LangGraph run puts it in the run's metadata; the
      review tooling already filters runs by it.
    - ``run_id``, ``status``, ``start_time``, ``end_time``: first-class fields
      on ``Run``.
    - ``input_tokens`` / ``output_tokens`` / ``total_tokens``: ``Run``'s
      ``prompt_tokens`` / ``completion_tokens`` / ``total_tokens``, aggregated
      over the trace on the root run. Only meaningful once the run has ended —
      which is why collection is post-run and never per token.
    - ``cost``: ``Run.total_cost``, but only for models LangSmith prices. It is
      ``None`` (not zero) for anything it does not know, so a fallback is
      required — see ``agent/routing/pricing.py``. ``None`` must survive all the
      way to the API: a missing cost is not a free run.

AVAILABLE_WITH_METADATA — the value exists in-process, nothing carries it today
    - ``jira_issue_key``: the poller knows it, and it is on the *thread*
      metadata; LangSmith only sees *run* metadata, so it has to be attached
      per run.
    - ``agent_role``, ``model``, ``effort``, ``complexity_tier``,
      ``routing_reason``, ``routing_mode``, ``workflow_stage``: all produced by
      the router (``ModelConfig``) before the run starts. Attaching them is what
      makes "how much did Opus cost us on this card" answerable without
      re-deriving the routing decision from logs.

REQUIRES_INSTRUMENTATION — obtainable, but only by adding a call site
    - Child-run inheritance: metadata set on the run's ``RunnableConfig``
      propagates to child runs automatically, so tagging the root run is
      enough — but *only* if it goes through ``config["metadata"]`` at
      ``runs.create`` time (see ``agent.dispatch``), not through the payload.
    - Post-run collection: nothing reads a finished run back today. The
      run-completion webhook is the hook (``agent.completion``).
    - Finding the trace again: the id that webhook carries is the *LangGraph*
      run id, and LangSmith indexes its own run ids. Neither derives from the
      other, so reading the trace by that id cannot be relied on. The dispatch
      therefore stamps its own correlation id into the run's metadata
      (``telemetry_dispatch_id``) and the collector searches the graph's tracing
      project for it — see ``agent/routing/usage_collection.py``.
    - ``model`` on the root run: LangSmith has it on the child LLM runs
      (``extra.invocation_params``), never on the root — walking children on
      every read is far more expensive than one metadata field.

NOT_AVAILABLE — out of reach here, deliberately not faked
    - Per-token / streaming usage: LangSmith aggregates on completion; there is
      no cheap live counter, and streaming one is explicitly out of scope.
    - Non-LLM cost (sandbox time, tool calls, Jira/GitHub API): no source.
    - Cost for a model LangSmith does not price *and* our table does not
      list: stays ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from ..utils.json_types import as_json_object
from ..utils.tracing import AGENT_TRACING_PROJECT, REVIEW_TRACING_PROJECT
from .complexity import ComplexityTier
from .dispatch_route import resolve_dispatch_route
from .roles import AgentRole, coerce_role
from .router import ModelConfig

# Routing has no override: the role decides the model. The field is recorded
# anyway so a future reader of a trace does not have to know that to read it.
ROUTING_MODE = "automatic"

# Prefix for every telemetry key in a run's metadata. LangGraph and LangSmith
# both put their own keys in the same dict; a prefix keeps ours identifiable
# and makes "is this an instrumented run?" a cheap check.
TELEMETRY_KEY_PREFIX = "telemetry_"
_KEY_PREFIX = TELEMETRY_KEY_PREFIX


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class RunMetadata:
    """What one agent execution is, decided before it starts.

    Everything here is known at dispatch time. Nothing in it is a measurement —
    measurements arrive later as :class:`UsageData`.
    """

    thread_id: str
    agent_role: str
    workflow_stage: str
    model: str
    effort: str | None
    complexity_tier: str
    routing_reason: str
    jira_issue_key: str | None = None
    routing_mode: str = ROUTING_MODE
    start_time: str | None = None
    # Not part of the aggregation key: carried so an escalation can be reported
    # as an event without re-deriving it by parsing ``routing_reason``.
    escalation_reason: str | None = None
    # How the finished trace is found again. A LangGraph run id is not a
    # LangSmith run id, so the dispatch stamps its own id into the run's
    # metadata and the completion path looks the trace up by it, in the
    # tracing project that graph traces into.
    dispatch_id: str | None = None
    tracing_project: str = AGENT_TRACING_PROJECT

    def as_metadata(self) -> dict[str, Any]:
        """The dict handed to ``runs.create`` as ``config["metadata"]``.

        JSON-safe by construction — LangSmith stores this verbatim and a
        non-serialisable value would drop the whole run's metadata, not just
        the offending key.
        """
        return {
            f"{_KEY_PREFIX}version": 1,
            f"{_KEY_PREFIX}dispatch_id": self.dispatch_id,
            "jira_issue_key": self.jira_issue_key,
            "thread_id": self.thread_id,
            "agent_role": self.agent_role,
            "workflow_stage": self.workflow_stage,
            "model": self.model,
            "effort": self.effort,
            "routing_mode": self.routing_mode,
            "complexity_tier": self.complexity_tier,
            "routing_reason": self.routing_reason,
            "escalation_reason": self.escalation_reason,
            "start_time": self.start_time,
        }

    def as_dict(self) -> dict[str, Any]:
        """Serialisation for the console push and the observability API."""
        return {
            "jira_issue_key": self.jira_issue_key,
            "thread_id": self.thread_id,
            "agent_role": self.agent_role,
            "workflow_stage": self.workflow_stage,
            "model": self.model,
            "effort": self.effort,
            "routing_mode": self.routing_mode,
            "complexity_tier": self.complexity_tier,
            "routing_reason": self.routing_reason,
            "escalation_reason": self.escalation_reason,
            "start_time": self.start_time,
        }

    @classmethod
    def from_metadata(cls, payload: Any) -> RunMetadata | None:
        """Rebuild from a metadata dict, or ``None`` if it is not one of ours.

        Used on the two sides that receive a run second-hand: the console
        (ingesting a pushed event) and the completion path (reading a run back
        from LangSmith after a restart lost the in-memory registry).
        """
        if not isinstance(payload, dict):
            return None
        thread_id = payload.get("thread_id")
        agent_role = payload.get("agent_role")
        model = payload.get("model")
        if not isinstance(thread_id, str) or not isinstance(agent_role, str):
            return None
        if not isinstance(model, str):
            return None
        return cls(
            thread_id=thread_id,
            agent_role=agent_role,
            workflow_stage=str(payload.get("workflow_stage") or "unknown"),
            model=model,
            effort=payload.get("effort") if isinstance(payload.get("effort"), str) else None,
            complexity_tier=str(payload.get("complexity_tier") or ComplexityTier.LOW.value),
            routing_reason=str(payload.get("routing_reason") or ""),
            jira_issue_key=(
                payload.get("jira_issue_key")
                if isinstance(payload.get("jira_issue_key"), str)
                else None
            ),
            routing_mode=str(payload.get("routing_mode") or ROUTING_MODE),
            start_time=(
                payload.get("start_time") if isinstance(payload.get("start_time"), str) else None
            ),
            escalation_reason=(
                payload.get("escalation_reason")
                if isinstance(payload.get("escalation_reason"), str)
                else None
            ),
            dispatch_id=(
                payload.get(f"{_KEY_PREFIX}dispatch_id")
                if isinstance(payload.get(f"{_KEY_PREFIX}dispatch_id"), str)
                else None
            ),
        )


@dataclass(frozen=True)
class UsageData:
    """What one finished run consumed. Every field is nullable on purpose.

    ``None`` means "not known", and it has to stay distinguishable from ``0``
    all the way to the API: a run whose cost LangSmith could not price is not a
    free run, and reporting it as ``$0.00`` would quietly understate a card.
    """

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost: float | None = None
    # "langsmith" (reported directly), "estimated" (our pricing table), or None.
    cost_source: str | None = None

    @property
    def known(self) -> bool:
        return self.total_tokens is not None or self.cost is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost": self.cost,
            "cost_source": self.cost_source,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> UsageData:
        if not isinstance(payload, dict):
            return cls()

        def _int(name: str) -> int | None:
            value = payload.get(name)
            return (
                int(value)
                if isinstance(value, int | float) and not isinstance(value, bool)
                else None
            )

        cost = payload.get("cost")
        return cls(
            input_tokens=_int("input_tokens"),
            output_tokens=_int("output_tokens"),
            total_tokens=_int("total_tokens"),
            cost=float(cost)
            if isinstance(cost, int | float) and not isinstance(cost, bool)
            else None,
            cost_source=(
                payload.get("cost_source") if isinstance(payload.get("cost_source"), str) else None
            ),
        )


def build_run_metadata(
    agent_role: AgentRole | str,
    thread_id: str,
    jira_issue_key: str | None,
    complexity_tier: ComplexityTier | str,
    routing_config: ModelConfig,
    *,
    workflow_stage: str,
    start_time: str | None = None,
    dispatch_id: str | None = None,
    tracing_project: str = AGENT_TRACING_PROJECT,
) -> RunMetadata:
    """Assemble the metadata for one run from the router's decision.

    ``routing_config`` is the authority for model, effort and reason — this
    never picks or second-guesses a model, it only records the one the router
    already chose.
    """
    role = coerce_role(agent_role) if not isinstance(agent_role, AgentRole) else agent_role
    tier = (
        complexity_tier.value
        if isinstance(complexity_tier, ComplexityTier)
        else str(complexity_tier)
    )
    return RunMetadata(
        thread_id=thread_id,
        agent_role=role.value,
        workflow_stage=workflow_stage,
        model=routing_config.model,
        effort=routing_config.effort,
        complexity_tier=tier,
        routing_reason=routing_config.reason,
        jira_issue_key=jira_issue_key,
        routing_mode=ROUTING_MODE,
        start_time=start_time or _now_iso(),
        escalation_reason=routing_config.escalation_reason,
        dispatch_id=dispatch_id,
        tracing_project=tracing_project,
    )


# Each graph traces into one project; a run's trace can only be found again in
# the project it was written to.
_TRACING_PROJECTS: dict[str, str] = {
    "reviewer": REVIEW_TRACING_PROJECT,
    "analyzer": REVIEW_TRACING_PROJECT,
}


def tracing_project_for(assistant_id: str) -> str:
    """The LangSmith project the given graph traces into."""
    return _TRACING_PROJECTS.get(assistant_id, AGENT_TRACING_PROJECT)


def build_dispatch_metadata(
    thread_id: str,
    assistant_id: str,
    *,
    source: str,
    metadata: Any = None,
    configurable: Any = None,
    dispatch_id: str | None = None,
) -> RunMetadata:
    """Telemetry for a run from the two dicts it is being created with.

    This is the default every dispatch gets, so that a Slack reply, a PR review
    and a Jira card are all measured the same way. It derives the route with the
    same function the graph factory uses, so the tag names the model that will
    actually run.

    ``workflow_stage`` is the most specific thing known about where the run sits:
    the Jira column, else the phase the caller declared, else the trigger that
    caused it — never blank, because "unlabelled" runs would silently collapse
    into one bucket.
    """
    metadata_dict = as_json_object(metadata)
    configurable_dict = as_json_object(configurable)
    route = resolve_dispatch_route(metadata_dict, configurable_dict, assistant_id)

    jira_issue_key = metadata_dict.get("jira_issue_key") or configurable_dict.get("jira_issue_key")
    stage = (
        configurable_dict.get("jira_new_column")
        or metadata_dict.get("jira_column")
        or metadata_dict.get("workflow_phase")
        or source
    )
    return build_run_metadata(
        route.role,
        thread_id,
        jira_issue_key if isinstance(jira_issue_key, str) else None,
        route.complexity,
        route,
        workflow_stage=str(stage),
        dispatch_id=dispatch_id,
        tracing_project=tracing_project_for(assistant_id),
    )


def with_start_time(metadata: RunMetadata, start_time: str) -> RunMetadata:
    """Copy of ``metadata`` pinned to ``start_time`` (tests, replays)."""
    return replace(metadata, start_time=start_time)


def model_label(model_id: str) -> str:
    """Short human label for a model id, for log lines: ``Sonnet``, ``Opus``.

    Falls back to the bare model name so an unrecognised id still reads as
    itself rather than as a guess.
    """
    name = model_id.split(":", 1)[-1]
    for family in ("haiku", "sonnet", "opus"):
        if family in name.lower():
            return family.capitalize()
    return name


def route_label(metadata: RunMetadata) -> str:
    """``Sonnet/medium`` — or just ``Haiku`` for a role that runs with no effort."""
    label = model_label(metadata.model)
    return f"{label}/{metadata.effort}" if metadata.effort else label
