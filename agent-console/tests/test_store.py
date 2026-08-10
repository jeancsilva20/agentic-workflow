from __future__ import annotations

from store import _LOG_RING_BUFFER_SIZE, ConsoleStore


def test_no_tick_ever_before_any_tick_recorded() -> None:
    store = ConsoleStore(poll_interval_seconds=60)
    status = store.status()

    assert status["overall_status"] == "no_tick_ever"
    assert status["poller"]["last_tick_at"] is None
    assert status["poller"]["healthy"] is False


def test_idle_after_a_healthy_tick_with_nothing_to_do() -> None:
    store = ConsoleStore(poll_interval_seconds=60)
    store.record_tick({"launched": 0}, {"resumed": 0})

    status = store.status()

    assert status["overall_status"] == "idle"
    assert status["poller"]["healthy"] is True


def test_working_when_a_run_is_launched() -> None:
    store = ConsoleStore(poll_interval_seconds=60)
    store.record_tick({}, {})
    store.record_run_event("SSAI-1", "launched", human_filed=True)

    status = store.status()

    assert status["overall_status"] == "working"
    assert status["metrics"]["working"] == 1
    run = status["runs"][0]
    assert run["issue_key"] == "SSAI-1"
    assert run["status"] == "working"
    assert run["human_filed"] is True


def test_waiting_when_a_run_is_parked_with_time_parked_reported() -> None:
    store = ConsoleStore(poll_interval_seconds=60)
    store.record_tick({}, {})
    store.record_run_event("SSAI-2", "launched")
    store.record_run_event("SSAI-2", "parked", column="Em Revisão de Spec")

    status = store.status()

    assert status["overall_status"] == "waiting"
    assert status["metrics"]["waiting"] == 1
    run = status["runs"][0]
    assert run["status"] == "waiting"
    assert run["column"] == "Em Revisão de Spec"
    assert run["time_parked_seconds"] is not None
    assert run["time_parked_seconds"] >= 0


def test_waiting_when_only_the_queue_is_non_empty() -> None:
    store = ConsoleStore(poll_interval_seconds=60)
    store.record_tick({}, {})
    store.record_queue_event("SSAI-3")

    status = store.status()

    assert status["overall_status"] == "waiting"
    assert status["metrics"]["queued"] == 1
    assert status["queue"][0]["issue_key"] == "SSAI-3"
    assert status["queue"][0]["waiting_seconds"] >= 0


def test_launching_a_run_removes_it_from_the_queue() -> None:
    store = ConsoleStore(poll_interval_seconds=60)
    store.record_tick({}, {})
    store.record_queue_event("SSAI-4")
    store.record_run_event("SSAI-4", "launched")

    status = store.status()

    assert status["queue"] == []
    assert status["metrics"]["working"] == 1


def test_dead_run_is_reported_distinctly_and_not_dropped() -> None:
    store = ConsoleStore(poll_interval_seconds=60)
    store.record_tick({}, {})
    store.record_run_event("SSAI-5", "launched")
    store.record_run_event("SSAI-5", "dead", reason="model call limit")

    status = store.status()

    assert status["metrics"]["dead"] == 1
    run = next(r for r in status["runs"] if r["issue_key"] == "SSAI-5")
    assert run["status"] == "dead"
    assert run["reason"] == "model call limit"


def test_degraded_poller_when_tick_is_stale() -> None:
    store = ConsoleStore(poll_interval_seconds=1)
    store.record_tick({}, {})
    store._last_tick_at -= 10  # simulate a tick from 10s ago with a 1s interval

    status = store.status()

    assert status["overall_status"] == "degraded_poller"
    assert status["poller"]["healthy"] is False


def test_log_ring_buffer_evicts_oldest_entries() -> None:
    store = ConsoleStore()
    for i in range(_LOG_RING_BUFFER_SIZE + 10):
        store.record_log(f"entry {i}")

    status = store.status()
    # status() only returns the most recent 100, but the underlying buffer
    # itself must not exceed its configured size.
    assert len(store._log) == _LOG_RING_BUFFER_SIZE
    assert store._log[-1]["message"] == f"entry {_LOG_RING_BUFFER_SIZE + 9}"
    assert len(status["log"]) == 100
