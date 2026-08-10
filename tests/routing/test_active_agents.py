"""What is running right now — the one thing a finished-run store cannot say."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agent.routing.active_agents import ActiveAgentRegistry
from agent.routing.telemetry import RunMetadata, UsageData


def _metadata(thread: str = "thread-1", start_time: str | None = None) -> RunMetadata:
    return RunMetadata(
        thread_id=thread,
        agent_role="coding_agent",
        workflow_stage="Spec Aprovada",
        model="anthropic:claude-sonnet-5",
        effort="medium",
        complexity_tier="low",
        routing_reason="baseline route",
        jira_issue_key="SSAI-88",
        start_time=start_time or datetime.now(UTC).isoformat(),
    )


def test_a_started_run_is_listed_with_its_routing_decision() -> None:
    registry = ActiveAgentRegistry()
    registry.start("run-1", _metadata())

    active = registry.list_active()

    assert len(active) == 1
    assert active[0]["run_id"] == "run-1"
    assert active[0]["jira_issue_key"] == "SSAI-88"
    assert active[0]["agent_role"] == "coding_agent"
    assert active[0]["model"] == "anthropic:claude-sonnet-5"
    assert active[0]["elapsed_seconds"] >= 0


def test_a_finished_run_leaves_the_live_list() -> None:
    registry = ActiveAgentRegistry()
    registry.start("run-1", _metadata())

    finished = registry.finish("run-1", "success", UsageData(total_tokens=10))

    assert finished is not None
    assert finished.metadata.jira_issue_key == "SSAI-88"
    assert finished.usage.total_tokens == 10
    assert registry.list_active() == []


def test_finishing_an_unknown_run_is_not_an_error() -> None:
    """A completion for a run this process never dispatched is normal."""
    assert ActiveAgentRegistry().finish("run-unknown", "success") is None


def test_the_registry_cannot_grow_without_bound() -> None:
    registry = ActiveAgentRegistry(max_runs=2)
    registry.start("run-1", _metadata())
    registry.start("run-2", _metadata())
    registry.start("run-3", _metadata())

    assert [row["run_id"] for row in registry.list_active()] == ["run-2", "run-3"]


def test_a_run_whose_completion_never_arrived_can_be_swept() -> None:
    registry = ActiveAgentRegistry()
    stale = (datetime.now(UTC) - timedelta(hours=6)).isoformat()
    registry.start("run-old", _metadata(start_time=stale))
    registry.start("run-new", _metadata())

    dropped = registry.sweep_stale(max_age_seconds=3600)

    assert [entry.run_id for entry in dropped] == ["run-old"]
    assert [row["run_id"] for row in registry.list_active()] == ["run-new"]


def test_redispatching_the_same_run_id_does_not_duplicate_it() -> None:
    registry = ActiveAgentRegistry()
    registry.start("run-1", _metadata(thread="thread-1"))
    registry.start("run-1", _metadata(thread="thread-2"))

    active = registry.list_active()

    assert len(active) == 1
    assert active[0]["thread_id"] == "thread-2"
