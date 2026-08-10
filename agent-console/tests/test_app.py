from __future__ import annotations

import pytest
from app import app as flask_app
from store import store as global_store


@pytest.fixture
def client():
    global_store._runs.clear()
    global_store._queue.clear()
    global_store._log.clear()
    global_store._last_tick_at = None
    flask_app.config.update(TESTING=True)
    with flask_app.test_client() as client:
        yield client


def test_index_page_renders(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert b"Sensedia Agentic Workflow" in response.data


def test_get_state_reflects_ingested_events(client) -> None:
    client.post("/api/events/tick", json={"step_a": {"launched": 1}, "step_b": {}})
    client.post("/api/events/run", json={"issue_key": "SSAI-1", "action": "launched"})

    response = client.get("/api/state")
    data = response.get_json()

    assert data["overall_status"] == "working"
    assert data["metrics"]["working"] == 1


def test_post_run_event_requires_issue_key_and_action(client) -> None:
    response = client.post("/api/events/run", json={"issue_key": "SSAI-1"})

    assert response.status_code == 400


def test_post_queue_event_requires_issue_key(client) -> None:
    response = client.post("/api/events/queue", json={})

    assert response.status_code == 400


def test_post_log_event_appends_to_log(client) -> None:
    response = client.post("/api/events/log", json={"message": "hello"})
    assert response.status_code == 200

    state = client.get("/api/state").get_json()
    assert any(entry["message"] == "hello" for entry in state["log"])


def test_unknown_event_kind_returns_404(client) -> None:
    response = client.post("/api/events/bogus", json={})

    assert response.status_code == 404
