"""The bridge between a saved config change and the running LangGraph server."""

from __future__ import annotations

import asyncio

import pytest
import runtime_bridge

from agent import poller_cron


@pytest.fixture
def recorded_loops(monkeypatch) -> list[asyncio.AbstractEventLoop]:
    loops: list[asyncio.AbstractEventLoop] = []

    async def fake_reconfigure(minutes: int, client=None) -> str:
        loops.append(asyncio.get_running_loop())
        return f"cron-{minutes}"

    monkeypatch.setattr(poller_cron, "reconfigure_poller_cron", fake_reconfigure)
    return loops


def test_consecutive_changes_reuse_one_event_loop(recorded_loops) -> None:
    """Two changes in one console process: the second used to die on a closed loop."""
    assert runtime_bridge.apply_polling_interval(5) is None
    assert runtime_bridge.apply_polling_interval(10) is None

    assert len(recorded_loops) == 2
    assert recorded_loops[0] is recorded_loops[1]


def test_polling_stopped_is_reported_as_stopped_not_as_unchanged(monkeypatch) -> None:
    """The old cron is gone and the new one never landed — say so."""

    async def stopped(minutes: int, client=None) -> str:
        raise poller_cron.PollerCronStopped("no cron is installed and the poller is not ticking")

    monkeypatch.setattr(poller_cron, "reconfigure_poller_cron", stopped)

    warning = runtime_bridge.apply_polling_interval(10)

    assert warning is not None
    assert "not ticking" in warning
    assert "restart" in warning
    assert "keeps its previous interval" not in warning


def test_cron_failure_becomes_a_warning_not_an_exception(monkeypatch) -> None:
    async def fail(minutes: int, client=None) -> str:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(poller_cron, "reconfigure_poller_cron", fail)

    warning = runtime_bridge.apply_polling_interval(30)

    assert warning is not None
    assert "connection refused" in warning
    assert "30m" in warning


def test_routing_table_is_reported_without_touching_langgraph(monkeypatch) -> None:
    """Routing is local and read-only — no cron, no Store, nothing to apply."""
    table = runtime_bridge.routing_table()

    assert table, "the router must report at least one role"
    roles = {entry["role"] for entry in table}
    assert {"coding_agent", "code_reviewer", "jira_triage"} <= roles
    for entry in table:
        assert {"role", "model", "effort", "effort_supported", "active", "selected_by"} <= set(
            entry
        )
        assert entry["model"]
        assert entry["selected_by"]
        if not entry["effort_supported"]:
            assert entry["effort"] is None
    # A role no call site can reach yet must not read as a live route.
    by_role = {entry["role"]: entry for entry in table}
    assert by_role["coding_agent"]["active"] is True
    assert by_role["jira_triage"]["active"] is False
