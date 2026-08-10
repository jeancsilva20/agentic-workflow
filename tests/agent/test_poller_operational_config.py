"""The poller reads shadow mode and the tick interval at tick time.

Both used to be module constants populated from the environment at import, so
changing either meant restarting the server. They now come from the file the
agent console writes, with the environment variable as the fallback when the
console has never applied anything.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent import jira_poller, operational_config


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "operational_config.json"
    monkeypatch.setenv("OPERATIONAL_CONFIG_PATH", str(path))
    return path


def _write(path: Path, **values: Any) -> None:
    path.write_text(json.dumps(values), encoding="utf-8")


def _fake_client() -> MagicMock:
    client = MagicMock()
    client.threads.get = AsyncMock(side_effect=Exception("not found"))
    client.threads.create = AsyncMock(return_value=None)
    client.threads.update = AsyncMock(return_value=None)
    return client


def test_shadow_mode_falls_back_to_the_env_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jira_poller, "JIRA_POLLER_SHADOW_MODE", True)
    assert jira_poller.is_shadow_mode() is True

    monkeypatch.setattr(jira_poller, "JIRA_POLLER_SHADOW_MODE", False)
    assert jira_poller.is_shadow_mode() is False


def test_console_config_overrides_the_env_default(
    _isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jira_poller, "JIRA_POLLER_SHADOW_MODE", False)
    _write(_isolated_config, shadow_mode=True)

    assert jira_poller.is_shadow_mode() is True


def test_a_malformed_config_file_falls_back_instead_of_raising(
    _isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jira_poller, "JIRA_POLLER_SHADOW_MODE", True)
    _isolated_config.write_text("{ not json", encoding="utf-8")

    assert jira_poller.is_shadow_mode() is True


async def test_shadow_mode_toggled_in_the_file_blocks_the_next_tick(
    _isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No restart: the same process launches, then stops launching."""
    monkeypatch.setattr(jira_poller, "JIRA_POLLER_SHADOW_MODE", False)
    monkeypatch.setattr(jira_poller, "JIRA_POLLER_PAUSED", False)
    monkeypatch.setattr(
        jira_poller,
        "_search_all_issues",
        AsyncMock(return_value={"issues": [{"key": "SSAI-1", "fields": {"labels": []}}]}),
    )
    dispatch = AsyncMock(return_value=None)
    monkeypatch.setattr(jira_poller, "dispatch_agent_run", dispatch)
    monkeypatch.setattr(jira_poller.console_events, "push_run_event", AsyncMock(return_value=None))
    monkeypatch.setattr(jira_poller.console_events, "push_log", AsyncMock(return_value=None))
    client = _fake_client()

    assert (await jira_poller._tick_step_a(client))["launched"] == 1

    _write(_isolated_config, shadow_mode=True)

    assert (await jira_poller._tick_step_a(client))["launched"] == 0
    assert dispatch.await_count == 1


def test_polling_interval_prefers_the_console_value(
    _isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jira_poller, "JIRA_POLL_INTERVAL_SECONDS", 60)
    assert jira_poller.configured_poll_interval_minutes() == 1

    _write(_isolated_config, polling_interval_minutes=30)
    assert jira_poller.configured_poll_interval_minutes() == 30


def test_an_interval_outside_the_offered_set_is_ignored(
    _isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jira_poller, "JIRA_POLL_INTERVAL_SECONDS", 300)
    _write(_isolated_config, polling_interval_minutes=7)

    assert jira_poller.configured_poll_interval_minutes() == 5


def test_reader_picks_up_a_rewritten_file(_isolated_config: Path) -> None:
    """The read is cached on the file's mtime; a rewrite has to invalidate it."""
    _write(_isolated_config, shadow_mode=True)
    assert operational_config.shadow_mode_override() is True

    _write(_isolated_config, shadow_mode=False)
    assert operational_config.shadow_mode_override() is False
