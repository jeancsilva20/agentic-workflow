"""Instrumentation of a dispatched run, end to end: tag it, then read it back."""

from __future__ import annotations

import importlib
from collections.abc import AsyncIterator
from typing import Any

import pytest
from langsmith.utils import LangSmithNotFoundError

from agent.routing.active_agents import active_agents
from agent.routing.roles import AgentRole
from agent.routing.router import HAIKU_MODEL_ID, SONNET_MODEL_ID, resolve_model
from agent.routing.telemetry import build_dispatch_metadata, build_run_metadata
from agent.routing.usage_collection import (
    collect_run_usage,
    record_run_completion,
    usage_from_run,
)
from agent.routing.usage_store import usage_store
from agent.utils.tracing import AGENT_TRACING_PROJECT, REVIEW_TRACING_PROJECT

dispatch = importlib.import_module("agent.dispatch")
jira_poller = importlib.import_module("agent.jira_poller")


@pytest.fixture(autouse=True)
def _clean_stores(monkeypatch: pytest.MonkeyPatch) -> Any:
    # The console push is a real HTTP call whenever AGENT_CONSOLE_URL is set, as
    # it is in a dev workspace: left alone, this suite would file fake runs into
    # the console a developer is looking at.
    monkeypatch.setattr("agent.utils.console_events.AGENT_CONSOLE_URL", "")
    active_agents.clear()
    usage_store.clear()
    yield
    active_agents.clear()
    usage_store.clear()


class _FakeRuns:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    async def create(self, thread_id: str, assistant_id: str, **kwargs: Any) -> dict[str, str]:
        self.created.append({"thread_id": thread_id, "assistant_id": assistant_id, **kwargs})
        return {"run_id": "run-1"}


class _FakeClient:
    def __init__(self) -> None:
        self.runs = _FakeRuns()


class _FakeLangSmithRun:
    """The subset of ``langsmith.schemas.Run`` the collector reads."""

    def __init__(
        self,
        *,
        prompt_tokens: int | None = 1200,
        completion_tokens: int | None = 800,
        total_tokens: int | None = 2000,
        total_cost: float | None = None,
        prompt_token_details: dict[str, int] | None = None,
        # Instrumented by default: that marker is how the collector tells one of
        # our traces from an unrelated run that happens to answer to the same id.
        metadata: dict[str, Any] | None = None,
    ) -> None:
        metadata = {"telemetry_version": 1} if metadata is None else metadata
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.total_cost = total_cost
        self.prompt_token_details = prompt_token_details
        self.metadata = metadata


def _metadata(role: AgentRole = AgentRole.CODING_AGENT, card: str | None = "SSAI-88"):
    route = resolve_model(role)
    return build_run_metadata(
        route.role,
        "thread-1",
        card,
        route.complexity,
        route,
        workflow_stage="Spec Aprovada",
        dispatch_id="dispatch-1",
    )


# --- dispatch: the run is tagged before it starts ---------------------------


async def test_dispatch_puts_the_telemetry_on_the_runs_config_metadata() -> None:
    """Config metadata is what LangGraph propagates to every child run."""
    client = _FakeClient()

    await dispatch.dispatch_agent_run(
        "thread-1",
        "go",
        {"source": "jira", "jira_new_column": "Spec Aprovada"},
        source="jira",
        metadata={"jira_issue_key": "SSAI-88"},
        client=client,
    )

    metadata = client.runs.created[0]["config"]["metadata"]
    assert metadata["jira_issue_key"] == "SSAI-88"
    assert metadata["thread_id"] == "thread-1"
    assert metadata["agent_role"] == AgentRole.CODING_AGENT.value
    assert metadata["model"] == SONNET_MODEL_ID
    assert metadata["workflow_stage"] == "Spec Aprovada"
    assert metadata["routing_mode"] == "automatic"
    assert metadata["routing_reason"]
    assert metadata["start_time"]


async def test_dispatch_keeps_the_callers_own_metadata() -> None:
    client = _FakeClient()

    await dispatch.dispatch_agent_run(
        "thread-1",
        "go",
        {"source": "jira"},
        source="jira",
        metadata={"workflow_phase": "resumed"},
        client=client,
    )

    assert client.runs.created[0]["config"]["metadata"]["workflow_phase"] == "resumed"


async def test_dispatch_registers_the_run_as_active() -> None:
    client = _FakeClient()

    await dispatch.dispatch_agent_run("thread-1", "go", {}, source="jira", client=client)

    assert [row["run_id"] for row in active_agents.list_active()] == ["run-1"]


async def test_a_dispatch_with_no_card_is_still_measured() -> None:
    """A Slack run has no card, but it spends the same tokens as one that has."""
    client = _FakeClient()

    await dispatch.dispatch_agent_run("thread-1", "go", {}, source="slack", client=client)

    metadata = client.runs.created[0]["config"]["metadata"]
    assert metadata["jira_issue_key"] is None
    assert metadata["agent_role"] == AgentRole.CODING_AGENT.value
    assert metadata["model"] == SONNET_MODEL_ID
    # Nothing better is known about where it sits than what triggered it.
    assert metadata["workflow_stage"] == "slack"
    assert [row["run_id"] for row in active_agents.list_active()] == ["run-1"]


async def test_a_review_run_is_tagged_as_review_not_as_coding_work() -> None:
    """The single-purpose graphs route themselves; the tag has to say the same."""
    client = _FakeClient()

    await dispatch.dispatch_agent_run(
        "thread-1", "go", {}, source="github", assistant_id="reviewer", client=client
    )

    metadata = client.runs.created[0]["config"]["metadata"]
    assert metadata["agent_role"] == AgentRole.CODE_REVIEWER.value
    assert metadata["model"] == resolve_model(AgentRole.CODE_REVIEWER).model


async def test_a_direct_durable_run_is_tagged_and_registered() -> None:
    """Scheduled jobs and analyzer jobs bypass dispatch_agent_run entirely."""
    client = _FakeClient()

    await dispatch.create_durable_run(
        "thread-1",
        "analyzer",
        input={"messages": []},
        source="review-style-continual",
        config={"configurable": {"thread_id": "thread-1"}},
        client=client,
    )

    metadata = client.runs.created[0]["config"]["metadata"]
    assert metadata["agent_role"] == AgentRole.STYLE_ANALYZER.value
    assert metadata["workflow_stage"] == "review-style-continual"
    assert [row["run_id"] for row in active_agents.list_active()] == ["run-1"]


async def test_a_jira_run_dispatched_directly_is_tagged_with_its_card() -> None:
    """Derived from the run's own dicts, so a caller cannot forget to pass it."""
    client = _FakeClient()

    await dispatch.dispatch_agent_run(
        "thread-1",
        "go",
        {"source": "jira", "jira_issue_key": "SSAI-88", "jira_new_column": "Ajustar Code"},
        source="jira",
        client=client,
    )

    metadata = client.runs.created[0]["config"]["metadata"]
    assert metadata["jira_issue_key"] == "SSAI-88"
    assert metadata["workflow_stage"] == "Ajustar Code"
    assert metadata["agent_role"] == AgentRole.CODE_ADJUSTER.value


# --- the tag matches the route the graph factory will build -----------------


@pytest.mark.parametrize(
    "column",
    [
        None,
        "BACKLOG",
        "Spec Aprovada",
        "Ajustar Spec",
        "Ajustar Code",
        "Code Review Aprovado",
        "Mergeado",
    ],
)
def test_the_recorded_role_is_the_role_the_run_will_be_built_with(column: str | None) -> None:
    """Telemetry that names a different model from the one that ran is worse than none."""
    from agent import server

    metadata: dict[str, Any] = {"jira_issue_key": "SSAI-88"}
    configurable: dict[str, Any] = {"source": "jira", "jira_issue_key": "SSAI-88"}
    if column is not None:
        metadata["jira_column"] = column
        configurable["jira_new_column"] = column

    recorded = build_dispatch_metadata(
        "thread-1", "agent", source="jira", metadata=metadata, configurable=configurable
    )
    built = server._dispatch_role({"metadata": metadata}, configurable)

    assert recorded.agent_role == built.value


def test_a_launch_is_recorded_as_the_phase_it_was_dispatched_at() -> None:
    """A launch carries no column, so it routes as coding work — the stage says why."""
    recorded = build_dispatch_metadata(
        "thread-1",
        "agent",
        source="jira",
        metadata={"jira_issue_key": "SSAI-88", "workflow_phase": "triggered"},
        configurable={"source": "jira", "jira_issue_key": "SSAI-88"},
    )

    assert recorded.workflow_stage == "triggered"
    assert recorded.agent_role == AgentRole.CODING_AGENT.value
    assert recorded.jira_issue_key == "SSAI-88"


async def test_the_pollers_launch_and_resume_are_both_tagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The poller passes no telemetry of its own; the dispatch path derives it."""
    client = _FakeClient()

    await dispatch.dispatch_agent_run(
        "thread-1",
        f"Jira issue SSAI-88 entered {jira_poller.COLUMN_TRIGGER}.",
        {"source": "jira", "jira_issue_key": "SSAI-88"},
        source="jira",
        metadata={"jira_issue_key": "SSAI-88", "workflow_phase": "triggered"},
        client=client,
    )
    await dispatch.dispatch_agent_run(
        "thread-1",
        "Jira issue SSAI-88 moved to 'Ajustar Spec'.",
        {"source": "jira", "jira_issue_key": "SSAI-88", "jira_new_column": "Ajustar Spec"},
        source="jira",
        metadata={
            "jira_issue_key": "SSAI-88",
            "workflow_phase": "resumed",
            "jira_column": "Ajustar Spec",
        },
        client=client,
    )

    launch, resume = (run["config"]["metadata"] for run in client.runs.created)
    assert launch["jira_issue_key"] == resume["jira_issue_key"] == "SSAI-88"
    assert launch["workflow_stage"] == "triggered"
    assert resume["workflow_stage"] == "Ajustar Spec"
    assert resume["agent_role"] == AgentRole.SPEC_ADJUSTER.value


# --- post-run collection ----------------------------------------------------


def test_langsmiths_own_cost_wins() -> None:
    usage = usage_from_run(_FakeLangSmithRun(total_cost=0.4242), SONNET_MODEL_ID)

    assert usage.cost == 0.4242
    assert usage.cost_source == "langsmith"
    assert (usage.input_tokens, usage.output_tokens, usage.total_tokens) == (1200, 800, 2000)


def test_cost_falls_back_to_the_pricing_table() -> None:
    usage = usage_from_run(_FakeLangSmithRun(total_cost=None), SONNET_MODEL_ID)

    assert usage.cost_source == "estimated"
    assert usage.cost == pytest.approx(1200 * 3.0 / 1e6 + 800 * 15.0 / 1e6)


def test_cached_input_tokens_lower_the_estimate() -> None:
    plain = usage_from_run(_FakeLangSmithRun(), SONNET_MODEL_ID)
    cached = usage_from_run(
        _FakeLangSmithRun(prompt_token_details={"cache_read": 1000}), SONNET_MODEL_ID
    )
    assert plain.cost is not None and cached.cost is not None

    assert cached.cost < plain.cost


def test_an_unpriceable_run_reports_no_cost_rather_than_a_free_one() -> None:
    usage = usage_from_run(_FakeLangSmithRun(total_cost=None), "some-provider:mystery")

    assert usage.total_tokens == 2000
    assert usage.cost is None
    assert usage.cost_source is None


def test_missing_totals_are_derived_but_never_invented() -> None:
    usage = usage_from_run(_FakeLangSmithRun(total_tokens=None), HAIKU_MODEL_ID)
    assert usage.total_tokens == 2000

    nothing = usage_from_run(
        _FakeLangSmithRun(prompt_tokens=None, completion_tokens=None, total_tokens=None),
        HAIKU_MODEL_ID,
    )
    assert nothing.total_tokens is None
    assert nothing.cost is None


async def test_without_credentials_usage_is_unknown_not_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)

    usage = await collect_run_usage("run-1", SONNET_MODEL_ID)

    assert usage.as_dict() == {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "cost": None,
        "cost_source": None,
    }


async def test_completion_files_the_run_and_clears_it_from_the_live_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_read(run_id: str) -> Any:
        return _FakeLangSmithRun(total_cost=0.5)

    monkeypatch.setattr("agent.routing.usage_collection.read_langsmith_run", fake_read)
    active_agents.start("run-1", _metadata())

    entry = await record_run_completion("run-1", "thread-1", "success")

    assert entry is not None
    assert active_agents.list_active() == []
    summary = usage_store.get_card_summary("SSAI-88").as_dict()
    assert summary["runs"] == 1
    assert summary["total_tokens"] == 2000
    assert summary["cost"] == 0.5


async def test_completion_recovers_the_metadata_from_the_trace_after_a_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The in-memory registry is lost on restart; the run itself still carries the tag."""

    async def fake_read(run_id: str) -> Any:
        return _FakeLangSmithRun(total_cost=0.25, metadata=_metadata().as_metadata())

    monkeypatch.setattr("agent.routing.usage_collection.read_langsmith_run", fake_read)

    entry = await record_run_completion("run-1", "thread-1", "success")

    assert entry is not None
    assert usage_store.get_card_summary("SSAI-88").as_dict()["runs"] == 1


async def test_an_uninstrumented_run_is_not_filed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_read(run_id: str) -> Any:
        return _FakeLangSmithRun(metadata={"source": "slack"})

    monkeypatch.setattr("agent.routing.usage_collection.read_langsmith_run", fake_read)

    assert await record_run_completion("run-1", "thread-1", "success") is None
    assert usage_store.entries() == []


async def test_a_run_with_no_card_still_lands_in_the_daily_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slack and scheduled work costs money too; it just belongs to no card."""

    async def fake_read(run_id: str) -> Any:
        return _FakeLangSmithRun(total_cost=0.3)

    monkeypatch.setattr("agent.routing.usage_collection.read_langsmith_run", fake_read)
    active_agents.start("run-1", _metadata(card=None))

    await record_run_completion("run-1", "thread-1", "success")

    from datetime import UTC, datetime

    today = usage_store.get_today_usage(today=datetime.now(UTC).date().isoformat()).as_dict()
    assert today["runs"] == 1
    assert today["total_tokens"] == 2000
    assert today["cards"] == []


class _FakeLangSmithClient:
    """LangSmith as it behaves for a run dispatched through LangGraph.

    ``read_run`` is given the *LangGraph* run id, which LangSmith has never
    seen: it raises, exactly as the real client does for an unknown id. The
    trace is only reachable through the metadata the dispatch stamped on it.
    """

    def __init__(self, run: Any, dispatch_id: str, project: str) -> None:
        self._run = run
        self._dispatch_id = dispatch_id
        self._project = project
        self.queries: list[tuple[str, str, bool]] = []

    async def read_run(self, run_id: str) -> Any:
        raise LangSmithNotFoundError(f"Run {run_id} not found")

    async def list_runs(
        self, *, project_name: str, filter: str, is_root: bool = False, limit: int = 1
    ) -> AsyncIterator[Any]:
        self.queries.append((project_name, filter, is_root))
        if project_name == self._project and self._dispatch_id in filter:
            yield self._run


async def test_the_trace_is_found_by_the_id_the_dispatch_stamped_on_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A LangGraph run id is not a LangSmith run id; the metadata is the bridge."""
    metadata = _metadata()
    dispatch_id = metadata.dispatch_id or ""
    fake = _FakeLangSmithClient(
        _FakeLangSmithRun(total_cost=0.5), dispatch_id, metadata.tracing_project
    )
    monkeypatch.setattr("agent.routing.usage_collection._client", lambda: fake)
    active_agents.start("langgraph-run-1", metadata)

    entry = await record_run_completion("langgraph-run-1", "thread-1", "success")

    assert entry is not None
    assert entry.usage.total_tokens == 2000
    assert entry.usage.cost == 0.5
    project, query, is_root = fake.queries[0]
    assert project == AGENT_TRACING_PROJECT
    assert "telemetry_dispatch_id" in query and dispatch_id in query
    assert is_root is True
    assert usage_store.get_card_summary("SSAI-88").as_dict()["total_tokens"] == 2000


async def test_a_review_run_is_looked_up_in_the_review_project() -> None:
    """Each graph traces into one project; the wrong one would find nothing."""
    reviewer = build_dispatch_metadata("thread-1", "reviewer", source="github")
    coding = build_dispatch_metadata("thread-1", "agent", source="jira")

    assert reviewer.tracing_project == REVIEW_TRACING_PROJECT
    assert coding.tracing_project == AGENT_TRACING_PROJECT


async def test_usage_stays_unknown_when_the_trace_cannot_be_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No trace is not free work: the run is filed, with nulls, not zeros."""
    metadata = _metadata()
    fake = _FakeLangSmithClient(_FakeLangSmithRun(), "some-other-dispatch", "some-other-project")
    monkeypatch.setattr("agent.routing.usage_collection._client", lambda: fake)
    active_agents.start("langgraph-run-1", metadata)

    entry = await record_run_completion("langgraph-run-1", "thread-1", "success")

    assert entry is not None
    assert entry.usage.total_tokens is None
    assert entry.usage.cost is None
    summary = usage_store.get_card_summary("SSAI-88").as_dict()
    assert summary["cost"] is None
    assert summary["runs_missing_cost"] == 1


async def test_a_run_read_back_under_a_colliding_id_is_not_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A direct read that returns somebody else's run must not be filed as ours."""

    async def fake_read(run_id: str) -> Any:
        return _FakeLangSmithRun(total_cost=9.99, metadata={"source": "unrelated"})

    monkeypatch.setattr("agent.routing.usage_collection.read_langsmith_run", fake_read)
    monkeypatch.setattr(
        "agent.routing.usage_collection.find_run_by_dispatch_id",
        _no_run,
    )
    active_agents.start("langgraph-run-1", _metadata())

    entry = await record_run_completion("langgraph-run-1", "thread-1", "success")

    assert entry is not None
    assert entry.usage.cost is None


async def _no_run(dispatch_id: str, project: str) -> Any:
    return None


async def test_a_failed_run_is_still_accounted_for(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tokens spent before an error are spent."""

    async def fake_read(run_id: str) -> Any:
        return _FakeLangSmithRun(total_cost=0.1)

    monkeypatch.setattr("agent.routing.usage_collection.read_langsmith_run", fake_read)
    active_agents.start("run-1", _metadata())

    entry = await record_run_completion("run-1", "thread-1", "error")

    assert entry is not None and entry.status == "error"
    assert usage_store.get_card_summary("SSAI-88").as_dict()["runs"] == 1
