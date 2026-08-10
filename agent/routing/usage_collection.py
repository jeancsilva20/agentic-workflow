"""Reading back what a finished run consumed, and filing it.

Post-run, once: LangSmith aggregates a trace's token counts when it ends, so
there is nothing useful to read before that and nothing to gain from streaming
it. The run-completion webhook (``agent.completion``) is the single trigger.

Everything here degrades to "unknown" rather than to zero. No LangSmith key, a
run LangSmith never saw, a model neither side prices — all of them end as
``None`` fields on :class:`~agent.routing.telemetry.UsageData`, because a run
reported as costing ``$0.00`` is a wrong number, while an empty one is an
honest one.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..utils import console_events
from ..utils.langsmith import async_langsmith_client
from .active_agents import active_agents
from .pricing import estimate_cost
from .telemetry import TELEMETRY_KEY_PREFIX, RunMetadata, UsageData
from .usage_store import RunEntry, usage_store

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = "https://api.smith.langchain.com"


def _client() -> Any | None:
    """A LangSmith client from the environment, or ``None`` when unconfigured.

    Credentials are read here and never leave this process — no endpoint
    returns them, and nothing in a run entry carries them.
    """
    api_key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
    if not api_key:
        return None
    api_url = os.environ.get("LANGSMITH_ENDPOINT", _DEFAULT_ENDPOINT)
    return async_langsmith_client(api_key, api_url)


async def read_langsmith_run(run_id: str) -> Any | None:
    """Fetch one run from LangSmith *by LangSmith id*, or ``None``.

    Only useful when the id is known to be a LangSmith run id — see
    :func:`resolve_langsmith_run` for the completion path, where it is not.
    """
    client = _client()
    if client is None:
        logger.debug("Telemetry: no LangSmith credentials; usage for run %s unavailable", run_id)
        return None
    try:
        return await client.read_run(run_id)
    except Exception:  # noqa: BLE001
        # A run the platform completed may not be queryable yet, or at all
        # (tracing off). Neither is worth failing a webhook over.
        logger.debug("Telemetry: could not read LangSmith run %s", run_id, exc_info=True)
        return None


def _is_instrumented(run: Any) -> bool:
    """Whether this run carries the metadata a dispatch of ours stamps on it."""
    return f"{TELEMETRY_KEY_PREFIX}version" in run_metadata_of(run)


async def find_run_by_dispatch_id(dispatch_id: str, project: str) -> Any | None:
    """The root trace stamped with ``dispatch_id``, or ``None``.

    A LangGraph run id and a LangSmith run id are different identifiers from
    different systems: the platform creates the run, the tracer creates the
    trace, and neither is derivable from the other. What does bridge them is
    the metadata the dispatch wrote, which LangGraph propagates into the trace
    — so the trace is found by searching the project for that id.
    """
    client = _client()
    if client is None or not dispatch_id:
        return None
    query = (
        f'and(eq(metadata_key, "{TELEMETRY_KEY_PREFIX}dispatch_id"), '
        f'eq(metadata_value, "{dispatch_id}"))'
    )
    try:
        async for run in client.list_runs(
            project_name=project, filter=query, is_root=True, limit=1
        ):
            return run
    except Exception:  # noqa: BLE001
        logger.debug(
            "Telemetry: LangSmith search failed for dispatch %s in %s",
            dispatch_id,
            project,
            exc_info=True,
        )
    return None


async def resolve_langsmith_run(run_id: str, metadata: RunMetadata | None) -> Any | None:
    """The LangSmith trace for a finished LangGraph run, or ``None``.

    Tries the cheap path first — some deployments do reuse the dispatched run
    id as the trace's root id, and a direct read is one request — then falls
    back to the metadata search, which does not depend on that being true. A
    run that is read but carries none of our metadata is somebody else's run
    under a colliding id and is discarded rather than reported as this one's.
    """
    direct = await read_langsmith_run(run_id)
    if direct is not None and _is_instrumented(direct):
        return direct

    if metadata is None or not metadata.dispatch_id:
        if direct is not None:
            logger.debug("Telemetry: run %s read from LangSmith carries no telemetry", run_id)
        return None

    found = await find_run_by_dispatch_id(metadata.dispatch_id, metadata.tracing_project)
    if found is None:
        logger.info(
            "Telemetry: no LangSmith trace found for run %s (dispatch %s in %s); "
            "usage recorded as unknown",
            run_id,
            metadata.dispatch_id,
            metadata.tracing_project,
        )
    return found


def run_metadata_of(run: Any) -> dict[str, Any]:
    """A LangSmith run's metadata, from either place the SDK puts it."""
    metadata = getattr(run, "metadata", None)
    if isinstance(metadata, dict):
        return metadata
    extra = getattr(run, "extra", None)
    if isinstance(extra, dict):
        nested = extra.get("metadata")
        if isinstance(nested, dict):
            return nested
    return {}


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value)


def _cache_read_tokens(run: Any) -> int | None:
    details = getattr(run, "prompt_token_details", None)
    if isinstance(details, dict):
        return _int_or_none(details.get("cache_read"))
    return _int_or_none(getattr(details, "cache_read", None))


def usage_from_run(run: Any | None, model: str | None) -> UsageData:
    """Turn a LangSmith run into usage, filling in cost when LangSmith cannot.

    LangSmith's own ``total_cost`` wins whenever it exists — it is the number
    that matches the invoice. The pricing table is the fallback, and says so
    through ``cost_source``.
    """
    if run is None:
        return UsageData()

    input_tokens = _int_or_none(getattr(run, "prompt_tokens", None))
    output_tokens = _int_or_none(getattr(run, "completion_tokens", None))
    total_tokens = _int_or_none(getattr(run, "total_tokens", None))
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = (input_tokens or 0) + (output_tokens or 0)

    reported_cost = getattr(run, "total_cost", None)
    if isinstance(reported_cost, bool) or not isinstance(reported_cost, int | float):
        reported_cost = None

    if reported_cost is not None:
        cost: float | None = float(reported_cost)
        cost_source: str | None = "langsmith"
    else:
        cost = estimate_cost(model, input_tokens, output_tokens, _cache_read_tokens(run))
        cost_source = "estimated" if cost is not None else None

    return UsageData(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost=cost,
        cost_source=cost_source,
    )


async def collect_run_usage(run_id: str, model: str | None) -> UsageData:
    """Usage for one finished run — empty when nothing could be read."""
    return usage_from_run(await read_langsmith_run(run_id), model)


async def record_run_completion(
    run_id: str | None,
    thread_id: str,
    status: str | None,
) -> RunEntry | None:
    """File a finished run's usage and drop it from the live registry.

    Returns ``None`` for a run that was never instrumented — most runs in this
    codebase are Slack/GitHub triggered and carry no Jira telemetry, and a
    completion for one of those is not an error.
    """
    if not run_id:
        return None

    finished = active_agents.finish(run_id, status)
    metadata: RunMetadata | None = finished.metadata if finished else None

    run = await resolve_langsmith_run(run_id, metadata)
    if metadata is None:
        # The registry is in-memory: a server restart between dispatch and
        # completion loses it, and with it the correlation id — all that is
        # left to try is a direct read, which works only where the two ids
        # coincide. The run itself carries the metadata when it does.
        metadata = RunMetadata.from_metadata(run_metadata_of(run))
    if metadata is None:
        return None

    usage = usage_from_run(run, metadata.model)
    entry = usage_store.record_run(metadata, usage, run_id=run_id, status=status)

    logger.info(
        "Telemetry: run %s (%s, %s) on thread %s finished status=%s tokens=%s cost=%s (%s)",
        run_id,
        metadata.agent_role,
        metadata.jira_issue_key or "no card",
        thread_id,
        status,
        usage.total_tokens if usage.total_tokens is not None else "unknown",
        usage.cost if usage.cost is not None else "unknown",
        usage.cost_source or "no source",
    )
    await console_events.push_agent_finish(
        run_id=run_id,
        status=status,
        metadata=metadata.as_dict(),
        usage=usage.as_dict(),
    )
    return entry
