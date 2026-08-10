"""Cron reconfiguration: exactly one poller cron, at the requested interval."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent import poller_cron


def _fake_client(existing: list[dict[str, Any]] | None = None) -> MagicMock:
    client = MagicMock()
    client.crons.search = AsyncMock(return_value=list(existing or []))
    client.crons.delete = AsyncMock(return_value=None)
    client.crons.create = AsyncMock(return_value={"cron_id": "cron-new"})
    return client


@pytest.mark.parametrize(
    ("minutes", "schedule"),
    [
        (1, "* * * * *"),
        (5, "*/5 * * * *"),
        (10, "*/10 * * * *"),
        (30, "*/30 * * * *"),
        # `*/60` is out of range for the minute field, so an hourly tick has to
        # move into the hour field instead.
        (60, "0 * * * *"),
        (120, "0 */2 * * *"),
    ],
)
def test_schedule_for_each_offered_interval(minutes: int, schedule: str) -> None:
    assert poller_cron.cron_schedule_for_minutes(minutes) == schedule


async def test_reconfigure_replaces_the_existing_cron() -> None:
    client = _fake_client([{"cron_id": "cron-old"}])

    cron_id = await poller_cron.reconfigure_poller_cron(10, client=client)

    client.crons.delete.assert_awaited_once_with("cron-old")
    client.crons.create.assert_awaited_once()
    assert client.crons.create.await_args.kwargs["schedule"] == "*/10 * * * *"
    assert client.crons.create.await_args.kwargs["metadata"] == poller_cron.POLLER_CRON_METADATA
    assert cron_id == "cron-new"


async def test_reconfigure_leaves_exactly_one_cron_when_duplicates_exist() -> None:
    client = _fake_client([{"cron_id": "cron-a"}, {"cron_id": "cron-b"}])

    await poller_cron.reconfigure_poller_cron(5, client=client)

    assert [call.args[0] for call in client.crons.delete.await_args_list] == ["cron-a", "cron-b"]
    assert client.crons.create.await_count == 1


async def test_reconfigure_creates_the_cron_when_none_exists() -> None:
    client = _fake_client([])

    await poller_cron.reconfigure_poller_cron(30, client=client)

    client.crons.delete.assert_not_awaited()
    assert client.crons.create.await_args.kwargs["schedule"] == "*/30 * * * *"


async def test_reconfigure_deletes_before_creating() -> None:
    """Never two live crons: the old one has to be gone before the new one exists."""
    order: list[str] = []
    client = _fake_client([{"cron_id": "cron-old"}])
    client.crons.delete = AsyncMock(side_effect=lambda _id: order.append("delete"))
    client.crons.create = AsyncMock(
        side_effect=lambda *_a, **_k: order.append("create") or {"cron_id": "cron-new"}
    )

    await poller_cron.reconfigure_poller_cron(5, client=client)

    assert order == ["delete", "create"]


async def test_reconfigure_raises_when_the_server_rejects_it() -> None:
    """A failure must reach the operator — a silently unchanged interval is worse."""
    client = _fake_client([])
    client.crons.create = AsyncMock(side_effect=RuntimeError("connection refused"))

    with pytest.raises(RuntimeError) as failure:
        await poller_cron.reconfigure_poller_cron(5, client=client)

    # Nothing was deleted, so the previous state (no cron) is intact — this is
    # not the "polling stopped" case.
    assert not isinstance(failure.value, poller_cron.PollerCronStopped)


async def test_failing_to_recreate_after_deleting_reports_polling_stopped() -> None:
    """Delete-then-create has a window where the poller has no cron at all.

    If creation fails inside it, the poller is not ticking — telling the
    operator it "kept the previous interval" would hide an outage.
    """
    client = _fake_client([{"cron_id": "cron-old"}])
    client.crons.create = AsyncMock(side_effect=RuntimeError("connection refused"))

    with pytest.raises(poller_cron.PollerCronStopped) as failure:
        await poller_cron.reconfigure_poller_cron(5, client=client)

    client.crons.delete.assert_awaited_once_with("cron-old")
    assert "not ticking" in str(failure.value)
    assert "connection refused" in str(failure.value)


def test_client_is_reused_across_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(poller_cron, "_client_cache", None)
    created: list[str] = []
    monkeypatch.setattr(
        poller_cron,
        "get_client",
        lambda url: created.append(url) or MagicMock(),
    )

    first = poller_cron.cron_client()
    second = poller_cron.cron_client()

    assert first is second
    assert len(created) == 1
