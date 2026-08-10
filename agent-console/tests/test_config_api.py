"""Backend coverage for the operational config API.

Two things are deliberately faked here: the LangGraph side effects (a cron and
a Store record, both owned by the other process — exercised for real in
``tests/agent/test_poller_cron.py``) and the config file location, which every
test points at its own tmp path so one test's persisted state can't leak into
the next.
"""

from __future__ import annotations

import json
import os
import threading
import time

import app as app_module
import config_store
import pytest
import runtime_bridge
from store import store as global_store

_KIMI = "fireworks:accounts/fireworks/models/kimi-k3"  # efforts: low/high/max only


class _BridgeCalls:
    def __init__(self) -> None:
        self.polling: list[int] = []
        self.model: list[tuple[str, str]] = []
        self.polling_warning: str | None = None
        self.model_warning: str | None = None


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = tmp_path / "operational_config.json"
    # The poller resolves the very same path from the environment, so pointing
    # it here is what makes the cross-process assertions below real.
    monkeypatch.setenv("OPERATIONAL_CONFIG_PATH", str(path))
    return path


@pytest.fixture
def bridge(monkeypatch) -> _BridgeCalls:
    calls = _BridgeCalls()

    def fake_polling(minutes: int) -> str | None:
        calls.polling.append(minutes)
        return calls.polling_warning

    def fake_model(model: str, effort: str) -> str | None:
        calls.model.append((model, effort))
        return calls.model_warning

    monkeypatch.setattr(runtime_bridge, "apply_polling_interval", fake_polling)
    monkeypatch.setattr(runtime_bridge, "apply_model_effort", fake_model)
    return calls


@pytest.fixture
def client(monkeypatch, config_path, bridge):
    monkeypatch.delenv("JIRA_POLLER_SHADOW_MODE", raising=False)
    monkeypatch.setenv("JIRA_POLL_INTERVAL_SECONDS", "60")
    monkeypatch.setattr(
        app_module, "operational_config", config_store.OperationalConfig(path=config_path)
    )
    global_store._log.clear()
    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as client:
        yield client


def _log_messages() -> list[str]:
    return [entry["message"] for entry in global_store.status()["log"]]


# --- GET ----------------------------------------------------------------


def test_get_config_returns_the_four_operational_settings(client) -> None:
    body = client.get("/api/config").get_json()

    assert body["shadow_mode"] is False
    assert isinstance(body["model"], str) and body["model"]
    assert isinstance(body["effort"], str) and body["effort"]
    assert body["polling_interval_minutes"] == 1


def test_get_config_lists_the_available_choices(client) -> None:
    body = client.get("/api/config").get_json()

    assert body["available_polling_intervals"] == [1, 5, 10, 30, 60]
    assert any(model["id"] == _KIMI for model in body["available_models"])
    assert all(
        {"id", "label", "efforts", "default_effort"} <= set(m) for m in body["available_models"]
    )
    assert "high" in body["available_efforts"]
    assert body["model"] in {model["id"] for model in body["available_models"]}


def test_get_config_exposes_no_secrets(client, monkeypatch) -> None:
    monkeypatch.setenv("JIRA_API_TOKEN", "super-secret-token")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")

    response = client.get("/api/config")
    body = response.get_json()
    raw = response.get_data(as_text=True)

    assert set(body) == {
        "shadow_mode",
        "model",
        "effort",
        "polling_interval_minutes",
        "available_models",
        "available_efforts",
        "available_polling_intervals",
    }
    assert "super-secret-token" not in raw
    assert "ops@example.com" not in raw
    assert not any(
        needle in key.lower() for key in body for needle in ("token", "secret", "password", "email")
    )


# --- shadow mode ---------------------------------------------------------


def test_put_enables_shadow_mode(client) -> None:
    response = client.put("/api/config", json={"shadow_mode": True})

    assert response.status_code == 200
    assert response.get_json()["shadow_mode"] is True
    assert client.get("/api/config").get_json()["shadow_mode"] is True


def test_put_disables_shadow_mode(client) -> None:
    client.put("/api/config", json={"shadow_mode": True})

    response = client.put("/api/config", json={"shadow_mode": False})

    assert response.get_json()["shadow_mode"] is False
    assert client.get("/api/config").get_json()["shadow_mode"] is False


def test_shadow_toggle_is_written_to_the_execution_log(client) -> None:
    client.put("/api/config", json={"shadow_mode": True})
    client.put("/api/config", json={"shadow_mode": False})

    messages = _log_messages()
    assert "config: shadow mode enabled" in messages
    assert "config: shadow mode disabled" in messages


def test_shadow_mode_from_the_api_blocks_the_poller(client) -> None:
    """The whole point of the toggle: the other process must see it."""
    from agent import jira_poller

    client.put("/api/config", json={"shadow_mode": True})
    assert jira_poller.is_shadow_mode() is True

    client.put("/api/config", json={"shadow_mode": False})
    assert jira_poller.is_shadow_mode() is False


def test_put_rejects_a_non_boolean_shadow_mode(client) -> None:
    response = client.put("/api/config", json={"shadow_mode": "yes"})

    assert response.status_code == 400
    assert "shadow_mode" in response.get_json()["error"]


# --- model and effort ----------------------------------------------------


def test_put_accepts_a_supported_model_and_effort(client, bridge) -> None:
    response = client.put("/api/config", json={"model": _KIMI, "effort": "max"})

    assert response.status_code == 200
    body = response.get_json()
    assert (body["model"], body["effort"]) == (_KIMI, "max")
    assert bridge.model == [(_KIMI, "max")]
    assert "config: model changed from" in "\n".join(_log_messages())


def test_put_rejects_an_unknown_model(client, bridge) -> None:
    response = client.put("/api/config", json={"model": "anthropic:claude-imaginary-9"})

    assert response.status_code == 400
    assert "unsupported model" in response.get_json()["error"]
    assert bridge.model == []
    assert client.get("/api/config").get_json()["model"] != "anthropic:claude-imaginary-9"


def test_put_rejects_an_effort_the_model_does_not_support(client) -> None:
    response = client.put("/api/config", json={"model": _KIMI, "effort": "medium"})

    assert response.status_code == 400
    assert "not supported by model" in response.get_json()["error"]


def test_put_rejects_an_unknown_effort(client) -> None:
    response = client.put("/api/config", json={"effort": "turbo"})

    assert response.status_code == 400


def test_model_effort_warning_is_surfaced_and_logged(client, bridge) -> None:
    bridge.model_warning = "team settings were not updated (connection refused)"

    body = client.put("/api/config", json={"model": _KIMI, "effort": "high"}).get_json()

    assert body["warnings"] == [bridge.model_warning]
    assert f"config: {bridge.model_warning}" in _log_messages()


# --- polling interval ----------------------------------------------------


@pytest.mark.parametrize("minutes", [1, 5, 10, 30, 60])
def test_put_accepts_every_offered_polling_interval(client, bridge, minutes) -> None:
    # Move away from the current value first so every interval is a real change.
    other = 30 if minutes != 30 else 5
    client.put("/api/config", json={"polling_interval_minutes": other})
    bridge.polling.clear()

    response = client.put("/api/config", json={"polling_interval_minutes": minutes})

    assert response.status_code == 200
    assert response.get_json()["polling_interval_minutes"] == minutes
    assert bridge.polling == [minutes]
    assert f"config: polling interval changed from {other}m to {minutes}m" in _log_messages()


def test_put_rejects_an_interval_that_is_not_offered(client, bridge) -> None:
    response = client.put("/api/config", json={"polling_interval_minutes": 7})

    assert response.status_code == 400
    assert bridge.polling == []


def test_unchanged_interval_does_not_touch_the_cron(client, bridge) -> None:
    """One reconfiguration per actual change — a no-op PUT must not churn crons."""
    client.put("/api/config", json={"polling_interval_minutes": 10})
    bridge.polling.clear()

    client.put("/api/config", json={"polling_interval_minutes": 10})

    assert bridge.polling == []


# --- persistence and payload hygiene -------------------------------------


def test_configuration_survives_a_restart(client, config_path) -> None:
    client.put(
        "/api/config",
        json={"shadow_mode": True, "polling_interval_minutes": 30, "model": _KIMI, "effort": "low"},
    )

    reloaded = config_store.OperationalConfig(path=config_path).get()

    assert reloaded == {
        "shadow_mode": True,
        "model": _KIMI,
        "effort": "low",
        "polling_interval_minutes": 30,
    }


def test_persisted_file_holds_only_the_four_settings(client, config_path) -> None:
    client.put("/api/config", json={"shadow_mode": True})

    stored = json.loads(config_path.read_text())

    assert set(stored) == {"shadow_mode", "model", "effort", "polling_interval_minutes"}
    assert os.environ.get("JIRA_API_TOKEN") not in stored.values()


def test_put_rejects_an_unknown_field(client, config_path) -> None:
    response = client.put("/api/config", json={"jira_api_token": "leaked"})

    assert response.status_code == 400
    assert "unknown config field" in response.get_json()["error"]
    assert not config_path.exists()


def test_put_rejects_a_non_object_body(client) -> None:
    response = client.put("/api/config", json=["shadow_mode"])

    assert response.status_code == 400


def test_a_file_changed_underneath_the_console_is_picked_up(client, config_path, bridge) -> None:
    """The file is the truth; the in-memory copy is only a cache of it.

    Reading a stale copy would report an interval the poller isn't running,
    and a PUT "back" to the real value would be treated as a no-op — leaving
    the runtime on the stale one forever.
    """
    client.put("/api/config", json={"polling_interval_minutes": 1})
    config_path.write_text(json.dumps({"polling_interval_minutes": 5}), encoding="utf-8")

    assert client.get("/api/config").get_json()["polling_interval_minutes"] == 5

    response = client.put("/api/config", json={"polling_interval_minutes": 1})

    assert response.get_json()["polling_interval_minutes"] == 1
    assert bridge.polling[-1] == 1  # the runtime was told, not skipped as a no-op


def test_concurrent_puts_never_split_the_saved_value_from_the_applied_one(
    client, config_path, monkeypatch
) -> None:
    """Two operators, two intervals, at the same moment.

    Saving and applying have to move together. If they don't, one PUT can
    persist its interval while the other's cron call lands last — the file says
    one thing, the poller runs another, and both callers were told they won.
    """
    observed: list[tuple[int, int]] = []

    def slow_apply(minutes: int) -> None:
        time.sleep(0.05)  # wide enough for the other request to slip in
        on_disk = json.loads(config_path.read_text())["polling_interval_minutes"]
        observed.append((minutes, on_disk))
        return None

    monkeypatch.setattr(runtime_bridge, "apply_polling_interval", slow_apply)

    def put(minutes: int) -> None:
        with app_module.app.test_client() as concurrent_client:
            concurrent_client.put("/api/config", json={"polling_interval_minutes": minutes})

    threads = [threading.Thread(target=put, args=(minutes,)) for minutes in (5, 30)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(observed) == 2
    # Each cron call saw its own value on disk, and the last one to run is the
    # one the file kept.
    assert all(applied == on_disk for applied, on_disk in observed)
    assert json.loads(config_path.read_text())["polling_interval_minutes"] == observed[-1][0]
