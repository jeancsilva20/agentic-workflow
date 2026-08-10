"""The observability API: what ran, what it cost, and what it must never leak."""

from __future__ import annotations

import json
from typing import Any

import observability
import pytest
from app import app as flask_app
from store import store as global_store


@pytest.fixture
def client():
    global_store._runs.clear()
    global_store._queue.clear()
    global_store._log.clear()
    global_store._last_tick_at = None
    observability.reset()
    flask_app.config.update(TESTING=True)
    with flask_app.test_client() as client:
        yield client
    observability.reset()


def _metadata(
    *,
    card: str | None = "SSAI-88",
    thread: str = "thread-1",
    role: str = "coding_agent",
    model: str = "anthropic:claude-sonnet-5",
    effort: str | None = "medium",
    stage: str = "Spec Aprovada",
    start_time: str | None = "2026-08-10T10:00:00+00:00",
    escalation_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "jira_issue_key": card,
        "thread_id": thread,
        "agent_role": role,
        "workflow_stage": stage,
        "model": model,
        "effort": effort,
        "routing_mode": "automatic",
        "complexity_tier": "low",
        "routing_reason": "baseline route for the role",
        "escalation_reason": escalation_reason,
        "start_time": start_time,
    }


def _usage(total: int | None = 2000, cost: float | None = 0.5) -> dict[str, Any]:
    if total is None:
        return {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "cost": cost,
            "cost_source": "langsmith" if cost is not None else None,
        }
    return {
        "input_tokens": int(total * 0.6),
        "output_tokens": total - int(total * 0.6),
        "total_tokens": total,
        "cost": cost,
        "cost_source": "langsmith" if cost is not None else None,
    }


def _start(client, run_id: str, **kwargs: Any):
    return client.post(
        "/api/events/agent_start", json={"run_id": run_id, "metadata": _metadata(**kwargs)}
    )


def _finish(client, run_id: str, usage: dict[str, Any] | None = None, **kwargs: Any):
    return client.post(
        "/api/events/agent_finish",
        json={
            "run_id": run_id,
            "status": "success",
            "metadata": _metadata(**kwargs),
            "usage": usage if usage is not None else _usage(),
        },
    )


# --- live -------------------------------------------------------------------


def test_live_lists_what_is_executing_right_now(client) -> None:
    _start(client, "run-1")

    active = client.get("/api/observability/live").get_json()["active"]

    assert len(active) == 1
    assert active[0]["run_id"] == "run-1"
    assert active[0]["jira_issue_key"] == "SSAI-88"
    assert active[0]["agent_role"] == "coding_agent"
    assert active[0]["model"] == "anthropic:claude-sonnet-5"
    assert active[0]["effort"] == "medium"


def test_a_finished_run_is_no_longer_live(client) -> None:
    _start(client, "run-1")
    _finish(client, "run-1")

    assert client.get("/api/observability/live").get_json()["active"] == []


def test_an_event_without_a_run_id_is_rejected(client) -> None:
    response = client.post("/api/events/agent_start", json={"metadata": _metadata()})

    assert response.status_code == 400


def test_an_event_without_telemetry_metadata_is_rejected(client) -> None:
    response = client.post("/api/events/agent_start", json={"run_id": "run-1", "metadata": {}})

    assert response.status_code == 400


# --- aggregation ------------------------------------------------------------


def test_a_card_aggregates_every_run_across_every_thread(client) -> None:
    """One card, three runs, two threads — the console reports one total."""
    _finish(client, "run-1", _usage(1000, 0.25), thread="thread-1", role="spec_author")
    _finish(client, "run-2", _usage(2000, 0.50), thread="thread-1", role="coding_agent")
    _finish(client, "run-3", _usage(500, 0.10), thread="thread-2", role="code_adjuster")

    summary = client.get("/api/observability/cards/SSAI-88/usage").get_json()

    assert summary["jira_issue_key"] == "SSAI-88"
    assert summary["runs"] == 3
    assert summary["total_tokens"] == 3500
    assert summary["cost"] == 0.85
    assert summary["threads"] == ["thread-1", "thread-2"]
    by_role = {row["agent_role"]: row["total_tokens"] for row in summary["by_agent"]}
    assert by_role == {"spec_author": 1000, "coding_agent": 2000, "code_adjuster": 500}


def test_a_card_splits_usage_by_model(client) -> None:
    _finish(client, "run-1", _usage(1000, 1.0), model="anthropic:claude-opus-5")
    _finish(client, "run-2", _usage(3000, 0.3), model="anthropic:claude-sonnet-5")

    by_model = {
        row["model"]: row
        for row in client.get("/api/observability/cards/SSAI-88/usage").get_json()["by_model"]
    }

    assert by_model["anthropic:claude-opus-5"]["cost"] == 1.0
    assert by_model["anthropic:claude-sonnet-5"]["total_tokens"] == 3000


def test_another_card_is_not_included(client) -> None:
    _finish(client, "run-1", _usage(1000, 0.1), card="SSAI-1")
    _finish(client, "run-2", _usage(2000, 0.2), card="SSAI-2")

    assert client.get("/api/observability/cards/SSAI-1/usage").get_json()["total_tokens"] == 1000


def test_an_unknown_card_reports_zero_runs(client) -> None:
    summary = client.get("/api/observability/cards/SSAI-404/usage").get_json()

    assert summary["runs"] == 0
    assert summary["cost"] is None


def test_an_unpriced_run_reports_null_cost_not_zero(client) -> None:
    _finish(client, "run-1", _usage(1000, None))

    summary = client.get("/api/observability/cards/SSAI-88/usage").get_json()

    assert summary["total_tokens"] == 1000
    assert summary["cost"] is None
    assert summary["runs_missing_cost"] == 1
    # The literal matters: a client rendering `0.0` would show a free run.
    assert '"cost": null' in json.dumps(summary, indent=1).replace("\n ", " ")


def test_timeline_is_ordered_and_carries_the_route_and_the_usage(client) -> None:
    _finish(
        client,
        "run-2",
        _usage(2000, 0.5),
        role="coding_agent",
        start_time="2026-08-10T12:00:00+00:00",
    )
    _finish(
        client,
        "run-1",
        _usage(1000, 0.2),
        role="spec_author",
        start_time="2026-08-10T09:00:00+00:00",
    )

    timeline = client.get("/api/observability/cards/SSAI-88/timeline").get_json()

    assert timeline["jira_issue_key"] == "SSAI-88"
    assert [row["run_id"] for row in timeline["runs"]] == ["run-1", "run-2"]
    first = timeline["runs"][0]
    assert first["agent_role"] == "spec_author"
    assert first["model"] == "anthropic:claude-sonnet-5"
    assert first["effort"] == "medium"
    assert first["status"] == "success"
    assert first["total_tokens"] == 1000
    assert first["cost"] == 0.2
    assert first["start_time"] == "2026-08-10T09:00:00+00:00"


def test_today_usage_covers_every_card(client) -> None:
    from datetime import UTC, datetime

    today = datetime.now(UTC).isoformat()
    _finish(client, "run-1", _usage(1000, 0.1), card="SSAI-1", start_time=today)
    _finish(client, "run-2", _usage(2000, 0.2), card="SSAI-2", start_time=today)
    _finish(
        client, "run-3", _usage(3000, 0.3), card="SSAI-2", start_time="2020-01-01T00:00:00+00:00"
    )

    usage = client.get("/api/observability/usage").get_json()

    assert usage["runs"] == 2
    assert usage["total_tokens"] == 3000
    assert usage["cost"] == pytest.approx(0.3)
    assert usage["cards"] == ["SSAI-1", "SSAI-2"]


# --- routing ----------------------------------------------------------------


def test_routing_endpoint_reports_the_same_table_as_the_config_route(client) -> None:
    observability_view = client.get("/api/observability/routing").get_json()

    assert observability_view == client.get("/api/config/routing").get_json()
    assert observability_view["routing"], "the routing table must not be empty"


# --- execution log ----------------------------------------------------------


def test_a_routing_decision_is_written_to_the_execution_log(client) -> None:
    _start(client, "run-1", role="spec_reviewer", model="anthropic:claude-opus-5", effort="high")

    messages = [entry["message"] for entry in client.get("/api/state").get_json()["log"]]

    assert any("routing: SSAI-88 spec_reviewer → Opus/high" == message for message in messages)


def test_an_escalation_is_reported_as_its_own_event(client) -> None:
    _start(client, "run-1", escalation_reason="2 failed attempts")

    messages = [entry["message"] for entry in client.get("/api/state").get_json()["log"]]

    assert any(message.startswith("escalation: SSAI-88") for message in messages)


def test_usage_and_cost_are_logged_once_per_run_not_per_token(client) -> None:
    _finish(client, "run-1", _usage(18420, 0.5))

    messages = [entry["message"] for entry in client.get("/api/state").get_json()["log"]]

    assert "usage: coding_agent 18,420 tokens" in messages
    assert sum(message.startswith("cost: SSAI-88") for message in messages) == 1


def test_an_unavailable_cost_says_so_in_the_log(client) -> None:
    _finish(client, "run-1", _usage(1000, None), model="some-provider:mystery")

    messages = [entry["message"] for entry in client.get("/api/state").get_json()["log"]]

    assert any("cost: SSAI-88 unavailable" in message for message in messages)


# --- credentials ------------------------------------------------------------


def test_no_endpoint_returns_a_langsmith_credential(client, monkeypatch) -> None:
    """The console never calls LangSmith; nothing it serves may carry a key."""
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_pt_sentinel_value")
    _start(client, "run-1")
    _finish(client, "run-1")

    for path in (
        "/api/observability/live",
        "/api/observability/routing",
        "/api/observability/usage",
        "/api/observability/cards/SSAI-88/usage",
        "/api/observability/cards/SSAI-88/timeline",
        "/api/state",
    ):
        body = client.get(path).get_data(as_text=True)
        lowered = body.lower()
        assert "lsv2_pt_sentinel_value" not in body, path
        assert "lsv2_" not in lowered, path
        assert "api_key" not in lowered, path
        assert "apikey" not in lowered, path
        assert "endpoint" not in lowered, path
