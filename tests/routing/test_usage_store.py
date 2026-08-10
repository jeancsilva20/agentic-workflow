"""Aggregating a card's usage across the several runs it takes to finish one."""

from __future__ import annotations

from agent.routing.roles import AgentRole
from agent.routing.telemetry import RunMetadata, UsageData
from agent.routing.usage_store import UsageStore


def _metadata(
    *,
    card: str | None = "SSAI-88",
    thread: str = "thread-1",
    role: AgentRole = AgentRole.CODING_AGENT,
    model: str = "anthropic:claude-sonnet-5",
    start_time: str = "2026-08-10T10:00:00+00:00",
) -> RunMetadata:
    return RunMetadata(
        thread_id=thread,
        agent_role=role.value,
        workflow_stage="Spec Aprovada",
        model=model,
        effort="medium",
        complexity_tier="low",
        routing_reason="baseline route",
        jira_issue_key=card,
        start_time=start_time,
    )


def _usage(total: int | None = 1000, cost: float | None = 0.5) -> UsageData:
    if total is None:
        return UsageData(cost=cost, cost_source="langsmith" if cost is not None else None)
    return UsageData(
        input_tokens=int(total * 0.8),
        output_tokens=total - int(total * 0.8),
        total_tokens=total,
        cost=cost,
        cost_source="langsmith" if cost is not None else None,
    )


def test_a_card_totals_every_run_it_spans() -> None:
    """One card, two human-in-the-loop runs on two threads: one number."""
    store = UsageStore()
    store.record_run(_metadata(thread="thread-1"), _usage(1000, 0.5))
    store.record_run(_metadata(thread="thread-2", role=AgentRole.CODE_ADJUSTER), _usage(500, 0.25))

    summary = store.get_card_summary("SSAI-88").as_dict()

    assert summary["runs"] == 2
    assert summary["total_tokens"] == 1500
    assert summary["cost"] == 0.75
    assert summary["threads"] == ["thread-1", "thread-2"]


def test_usage_is_split_by_agent_role() -> None:
    store = UsageStore()
    store.record_run(_metadata(role=AgentRole.SPEC_AUTHOR), _usage(300, 0.1))
    store.record_run(_metadata(role=AgentRole.CODING_AGENT), _usage(700, 0.4))
    store.record_run(_metadata(role=AgentRole.CODING_AGENT), _usage(100, 0.1))

    by_role = {
        row["agent_role"]: row for row in store.get_card_summary("SSAI-88").as_dict()["by_agent"]
    }

    assert by_role[AgentRole.SPEC_AUTHOR.value]["runs"] == 1
    assert by_role[AgentRole.CODING_AGENT.value]["runs"] == 2
    assert by_role[AgentRole.CODING_AGENT.value]["total_tokens"] == 800
    assert by_role[AgentRole.CODING_AGENT.value]["cost"] == 0.5


def test_usage_is_split_by_model() -> None:
    store = UsageStore()
    store.record_run(_metadata(model="anthropic:claude-opus-5"), _usage(200, 1.0))
    store.record_run(_metadata(model="anthropic:claude-sonnet-5"), _usage(800, 0.2))

    by_model = {
        row["model"]: row for row in store.get_card_summary("SSAI-88").as_dict()["by_model"]
    }

    assert by_model["anthropic:claude-opus-5"]["cost"] == 1.0
    assert by_model["anthropic:claude-sonnet-5"]["total_tokens"] == 800


def test_cards_do_not_bleed_into_each_other() -> None:
    store = UsageStore()
    store.record_run(_metadata(card="SSAI-1"), _usage(100, 0.1))
    store.record_run(_metadata(card="SSAI-2"), _usage(900, 0.9))

    assert store.get_card_summary("SSAI-1").as_dict()["total_tokens"] == 100
    assert store.get_card_summary("SSAI-2").as_dict()["total_tokens"] == 900


def test_a_card_with_no_runs_reports_zero_not_an_error() -> None:
    summary = UsageStore().get_card_summary("SSAI-404").as_dict()

    assert summary["runs"] == 0
    # Nothing was measured, so nothing is claimed about cost.
    assert summary["cost"] is None
    assert summary["by_agent"] == []


def test_an_unpriced_run_leaves_the_total_unknown_not_zero() -> None:
    store = UsageStore()
    store.record_run(_metadata(), _usage(1000, None))

    summary = store.get_card_summary("SSAI-88").as_dict()

    assert summary["cost"] is None
    assert summary["runs_missing_cost"] == 1
    assert summary["total_tokens"] == 1000


def test_a_priced_run_next_to_an_unpriced_one_reports_both_facts() -> None:
    store = UsageStore()
    store.record_run(_metadata(), _usage(1000, 0.5))
    store.record_run(_metadata(), _usage(1000, None))

    summary = store.get_card_summary("SSAI-88").as_dict()

    assert summary["cost"] == 0.5
    assert summary["runs_missing_cost"] == 1


def test_a_run_with_no_usage_at_all_is_still_on_the_timeline() -> None:
    """A run LangSmith could not be asked about still happened."""
    store = UsageStore()
    store.record_run(_metadata(), UsageData(), run_id="run-1", status="success")

    summary = store.get_card_summary("SSAI-88").as_dict()

    assert summary["runs"] == 1
    assert summary["runs_missing_tokens"] == 1
    assert summary["total_tokens"] == 0
    assert summary["cost"] is None


def test_timeline_is_ordered_and_carries_the_routing_decision() -> None:
    store = UsageStore()
    store.record_run(
        _metadata(start_time="2026-08-10T12:00:00+00:00", role=AgentRole.CODE_ADJUSTER),
        _usage(500, 0.2),
        run_id="run-2",
        status="success",
    )
    store.record_run(
        _metadata(start_time="2026-08-10T09:00:00+00:00", role=AgentRole.SPEC_AUTHOR),
        _usage(300, 0.1),
        run_id="run-1",
        status="success",
    )

    timeline = [entry.as_dict() for entry in store.get_card_timeline("SSAI-88")]

    assert [row["run_id"] for row in timeline] == ["run-1", "run-2"]
    first = timeline[0]
    assert first["agent_role"] == AgentRole.SPEC_AUTHOR.value
    assert first["model"] and first["effort"] == "medium"
    assert first["status"] == "success"
    assert first["total_tokens"] == 300
    assert first["cost"] == 0.1


def test_today_usage_ignores_other_days() -> None:
    store = UsageStore()
    store.record_run(_metadata(start_time="2026-08-10T01:00:00+00:00"), _usage(100, 0.1))
    store.record_run(_metadata(start_time="2026-08-09T23:00:00+00:00"), _usage(900, 0.9))

    today = store.get_today_usage(today="2026-08-10").as_dict()

    assert today["date"] == "2026-08-10"
    assert today["runs"] == 1
    assert today["total_tokens"] == 100
    assert today["cards"] == ["SSAI-88"]
    assert [row["model"] for row in today["by_model"]] == ["anthropic:claude-sonnet-5"]


def test_the_window_is_bounded() -> None:
    """Memory is bounded on purpose; LangSmith keeps the durable copy."""
    store = UsageStore(max_entries=3)
    for index in range(10):
        store.record_run(_metadata(), _usage(100, 0.1), run_id=f"run-{index}")

    assert [entry.run_id for entry in store.entries()] == ["run-7", "run-8", "run-9"]


def test_runs_without_a_card_are_kept_out_of_card_totals() -> None:
    store = UsageStore()
    store.record_run(_metadata(card=None), _usage(100, 0.1))

    assert store.get_card_summary("SSAI-88").as_dict()["runs"] == 0
    assert store.get_today_usage(today="2026-08-10").as_dict()["cards"] == []
