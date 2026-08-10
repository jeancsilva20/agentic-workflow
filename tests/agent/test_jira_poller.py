from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent import jira_poller

_MODULE = "agent.jira_poller"


def _fake_client(thread_metadata: dict[str, dict[str, Any] | None] | None = None) -> MagicMock:
    """A fake LangGraph client whose threads.get looks up canned metadata by thread_id."""
    thread_metadata = thread_metadata or {}

    async def fake_get(thread_id: str) -> dict[str, Any]:
        if thread_id not in thread_metadata or thread_metadata[thread_id] is None:
            raise Exception("not found")  # noqa: TRY002
        return {"metadata": thread_metadata[thread_id]}

    client = MagicMock()
    client.threads.get = AsyncMock(side_effect=fake_get)
    client.threads.create = AsyncMock(return_value=None)
    client.threads.update = AsyncMock(return_value=None)
    return client


def _issue(key: str, status: str, labels: list[str] | None = None) -> dict[str, Any]:
    return {"key": key, "fields": {"status": {"name": status}, "labels": labels or []}}


@pytest.mark.asyncio
async def test_trigger_jql_without_filter() -> None:
    with patch(f"{_MODULE}.JIRA_TRIGGER_JQL_FILTER", ""):
        assert jira_poller._trigger_jql() == 'project = SSAI AND status = "BACKLOG"'


@pytest.mark.asyncio
async def test_trigger_jql_with_filter_applied() -> None:
    with patch(f"{_MODULE}.JIRA_TRIGGER_JQL_FILTER", "issuetype = Bug"):
        assert (
            jira_poller._trigger_jql()
            == 'project = SSAI AND status = "BACKLOG" AND (issuetype = Bug)'
        )


@pytest.mark.asyncio
async def test_step_a_launches_thread_for_new_card() -> None:
    client = _fake_client({})
    with (
        patch(
            f"{_MODULE}.search_issues",
            new_callable=AsyncMock,
            return_value={"issues": [_issue("SSAI-1", "BACKLOG")]},
        ),
        patch(f"{_MODULE}.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch,
        patch(f"{_MODULE}.console_events.push_run_event", new_callable=AsyncMock) as mock_push,
        patch(f"{_MODULE}.JIRA_POLLER_SHADOW_MODE", False),
        patch(f"{_MODULE}.JIRA_POLLER_PAUSED", False),
    ):
        result = await jira_poller._tick_step_a(client)

    assert result == {"launched": 1, "skipped": 0}
    mock_dispatch.assert_awaited_once()
    client.threads.create.assert_awaited_once()
    mock_push.assert_awaited_once_with("SSAI-1", "launched", human_filed=True)
    assert mock_dispatch.await_args.kwargs["metadata"] == {
        "jira_issue_key": "SSAI-1",
        "workflow_phase": "triggered",
    }


@pytest.mark.asyncio
async def test_step_a_is_idempotent_for_a_card_that_already_owns_a_thread() -> None:
    thread_id = jira_poller.generate_thread_id_from_jira_issue("SSAI-1")
    client = _fake_client({thread_id: {"jira_issue_key": "SSAI-1"}})
    with (
        patch(
            f"{_MODULE}.search_issues",
            new_callable=AsyncMock,
            return_value={"issues": [_issue("SSAI-1", "BACKLOG")]},
        ),
        patch(f"{_MODULE}.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch,
    ):
        result = await jira_poller._tick_step_a(client)

    assert result == {"launched": 0, "skipped": 1}
    mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_step_a_detects_fa_alert_labeled_cards() -> None:
    client = _fake_client({})
    with (
        patch(
            f"{_MODULE}.search_issues",
            new_callable=AsyncMock,
            return_value={"issues": [_issue("SSAI-2", "BACKLOG", labels=["FA-Alert"])]},
        ),
        patch(f"{_MODULE}.dispatch_agent_run", new_callable=AsyncMock),
        patch(f"{_MODULE}.console_events.push_run_event", new_callable=AsyncMock) as mock_push,
    ):
        await jira_poller._tick_step_a(client)

    mock_push.assert_awaited_once_with("SSAI-2", "launched", human_filed=False)


@pytest.mark.asyncio
async def test_step_a_shadow_mode_never_launches() -> None:
    client = _fake_client({})
    with (
        patch(
            f"{_MODULE}.search_issues",
            new_callable=AsyncMock,
            return_value={"issues": [_issue("SSAI-3", "BACKLOG")]},
        ),
        patch(f"{_MODULE}.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch,
        patch(f"{_MODULE}.console_events.push_log", new_callable=AsyncMock) as mock_log,
        patch(f"{_MODULE}.JIRA_POLLER_SHADOW_MODE", True),
    ):
        result = await jira_poller._tick_step_a(client)

    mock_dispatch.assert_not_called()
    client.threads.create.assert_not_called()
    mock_log.assert_awaited_once()
    assert result == {"launched": 0, "skipped": 0}


@pytest.mark.asyncio
async def test_step_a_paused_mode_never_launches() -> None:
    client = _fake_client({})
    with (
        patch(
            f"{_MODULE}.search_issues",
            new_callable=AsyncMock,
            return_value={"issues": [_issue("SSAI-4", "BACKLOG")]},
        ),
        patch(f"{_MODULE}.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch,
        patch(f"{_MODULE}.JIRA_POLLER_SHADOW_MODE", False),
        patch(f"{_MODULE}.JIRA_POLLER_PAUSED", True),
    ):
        result = await jira_poller._tick_step_a(client)

    mock_dispatch.assert_not_called()
    assert result == {"launched": 0, "skipped": 0}


@pytest.mark.asyncio
async def test_step_b_resumes_when_column_changed() -> None:
    thread_id = jira_poller.generate_thread_id_from_jira_issue("SSAI-5")
    client = _fake_client(
        {thread_id: {"jira_parked": True, "jira_parked_column": "Em Revisão de Spec"}}
    )
    with (
        patch(
            f"{_MODULE}.search_issues",
            new_callable=AsyncMock,
            return_value={"issues": [_issue("SSAI-5", "Spec Aprovada")]},
        ),
        patch(
            f"{_MODULE}.get_comments",
            new_callable=AsyncMock,
            return_value={"comments": [{"body": "approved, go ahead"}]},
        ),
        patch(f"{_MODULE}.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch,
        patch(f"{_MODULE}.console_events.push_run_event", new_callable=AsyncMock) as mock_push,
        patch(f"{_MODULE}.JIRA_POLLER_PAUSED", False),
    ):
        result = await jira_poller._tick_step_b(client)

    assert result == {"resumed": 1, "unchanged": 0}
    mock_dispatch.assert_awaited_once()
    prompt = mock_dispatch.await_args.args[1]
    assert "Em Revisão de Spec" in prompt
    assert "Spec Aprovada" in prompt
    assert "approved, go ahead" in prompt
    assert mock_dispatch.await_args.kwargs["metadata"] == {
        "jira_issue_key": "SSAI-5",
        "workflow_phase": "resumed",
        "jira_column": "Spec Aprovada",
    }
    client.threads.update.assert_awaited_once_with(
        thread_id=thread_id, metadata={"jira_parked": False, "jira_parked_column": None}
    )
    mock_push.assert_awaited_once_with("SSAI-5", "resumed", column="Spec Aprovada")


@pytest.mark.asyncio
async def test_step_b_skips_when_column_unchanged() -> None:
    thread_id = jira_poller.generate_thread_id_from_jira_issue("SSAI-6")
    client = _fake_client(
        {thread_id: {"jira_parked": True, "jira_parked_column": "Em Code Review"}}
    )
    with (
        patch(
            f"{_MODULE}.search_issues",
            new_callable=AsyncMock,
            return_value={"issues": [_issue("SSAI-6", "Em Code Review")]},
        ),
        patch(f"{_MODULE}.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch,
    ):
        result = await jira_poller._tick_step_b(client)

    assert result == {"resumed": 0, "unchanged": 1}
    mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_step_b_skips_cards_with_no_parked_thread() -> None:
    client = _fake_client({})  # no thread at all for this issue key
    with (
        patch(
            f"{_MODULE}.search_issues",
            new_callable=AsyncMock,
            return_value={"issues": [_issue("SSAI-7", "Em Merge")]},
        ),
        patch(f"{_MODULE}.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch,
    ):
        result = await jira_poller._tick_step_b(client)

    assert result == {"resumed": 0, "unchanged": 0}
    mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_tick_runs_both_steps_and_pushes_tick_event() -> None:
    with (
        patch(f"{_MODULE}.get_client", return_value=_fake_client({})),
        patch(
            f"{_MODULE}._tick_step_a",
            new_callable=AsyncMock,
            return_value={"launched": 1, "skipped": 0},
        ),
        patch(
            f"{_MODULE}._tick_step_b",
            new_callable=AsyncMock,
            return_value={"resumed": 0, "unchanged": 2},
        ),
        patch(f"{_MODULE}.console_events.push_tick_event", new_callable=AsyncMock) as mock_push,
    ):
        result = await jira_poller.tick()

    assert result == {
        "step_a": {"launched": 1, "skipped": 0},
        "step_b": {"resumed": 0, "unchanged": 2},
    }
    mock_push.assert_awaited_once_with(
        {"launched": 1, "skipped": 0}, {"resumed": 0, "unchanged": 2}
    )


@pytest.mark.asyncio
async def test_ensure_cron_returns_existing_cron_id() -> None:
    client = MagicMock()
    client.crons.search = AsyncMock(return_value=[{"cron_id": "existing-id"}])
    client.crons.create = AsyncMock()
    with patch(f"{_MODULE}.get_client", return_value=client):
        cron_id = await jira_poller.ensure_jira_poller_cron()

    assert cron_id == "existing-id"
    client.crons.create.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_cron_creates_when_none_exists() -> None:
    client = MagicMock()
    client.crons.search = AsyncMock(return_value=[])
    client.crons.create = AsyncMock(return_value={"cron_id": "new-id"})
    with patch(f"{_MODULE}.get_client", return_value=client):
        cron_id = await jira_poller.ensure_jira_poller_cron()

    assert cron_id == "new-id"
    client.crons.create.assert_awaited_once()
    assert client.crons.create.await_args.args[0] == "scheduler"
    assert client.crons.create.await_args.kwargs["schedule"] == "* * * * *"
