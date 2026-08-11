from __future__ import annotations

import json
import os
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


@pytest.fixture(autouse=True)
def _flags_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin both poller brakes off.

    They default to environment variables read at import time, so a deployment
    env with `JIRA_POLLER_SHADOW_MODE=1` set would otherwise make every "does
    it launch/resume?" test assert the opposite of its name. Shadow mode's
    other source — the file the agent console writes — is neutralised suite-wide
    in `tests/conftest.py`. Tests that want a brake on re-patch it themselves.
    """
    monkeypatch.setattr(jira_poller, "JIRA_POLLER_SHADOW_MODE", False)
    monkeypatch.setattr(jira_poller, "JIRA_POLLER_PAUSED", False)


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
async def test_parked_jql_covers_gates_and_every_post_gate_column() -> None:
    """Step B must see the card *after* a human moves it out of a gate.

    Regression: the query listed only the three gate columns, so the moment a
    human moved a card to `Spec Aprovada` / `Ajustar Spec` / `Code Review
    Aprovado` / `Ajustar Code` / `Mergeado` the card fell out of the query and
    the decision was never detected.
    """
    jql = jira_poller._parked_jql()

    assert jql.startswith("project = SSAI AND status in (")
    for column in (
        jira_poller.COLUMN_SPEC_REVIEW,
        jira_poller.COLUMN_CODE_REVIEW,
        jira_poller.COLUMN_MERGE,
        jira_poller.COLUMN_SPEC_APPROVED,
        jira_poller.COLUMN_ADJUST_SPEC,
        jira_poller.COLUMN_CODE_APPROVED,
        jira_poller.COLUMN_ADJUST_CODE,
        jira_poller.COLUMN_MERGED,
    ):
        assert f'"{column}"' in jql


@pytest.mark.asyncio
async def test_parked_jql_follows_column_name_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jira_poller, "COLUMN_ADJUST_CODE", "Corrigir Código")

    assert '"Corrigir Código"' in jira_poller._parked_jql()


@pytest.mark.asyncio
async def test_parked_jql_has_no_duplicate_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two env vars pointed at the same status must not double-list it."""
    monkeypatch.setattr(jira_poller, "COLUMN_ADJUST_SPEC", jira_poller.COLUMN_SPEC_REVIEW)

    jql = jira_poller._parked_jql()

    assert jql.count(f'"{jira_poller.COLUMN_SPEC_REVIEW}"') == 1


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

    assert result == {"launched": 1, "skipped": 0, "shadow_candidates": []}
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

    assert result == {"launched": 0, "skipped": 1, "shadow_candidates": []}
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
        patch(f"{_MODULE}.JIRA_POLLER_SHADOW_MODE", False),
        patch(f"{_MODULE}.JIRA_POLLER_PAUSED", False),
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
    assert result == {"launched": 0, "skipped": 0, "shadow_candidates": ["SSAI-3"]}


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
    assert result == {"launched": 0, "skipped": 0, "shadow_candidates": []}


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


@pytest.mark.parametrize(
    ("parked_column", "moved_to"),
    [
        ("Em Revisão de Spec", "Spec Aprovada"),
        ("Em Revisão de Spec", "Ajustar Spec"),
        ("Em Code Review", "Code Review Aprovado"),
        ("Em Code Review", "Ajustar Code"),
        ("Em Merge", "Mergeado"),
    ],
)
@pytest.mark.asyncio
async def test_step_b_resumes_for_every_human_decision(parked_column: str, moved_to: str) -> None:
    """Each of the five human decisions must resume the SAME parked thread."""
    thread_id = jira_poller.generate_thread_id_from_jira_issue("SSAI-50")
    client = _fake_client({thread_id: {"jira_parked": True, "jira_parked_column": parked_column}})
    with (
        patch(
            f"{_MODULE}.search_issues",
            new_callable=AsyncMock,
            return_value={"issues": [_issue("SSAI-50", moved_to)]},
        ),
        patch(f"{_MODULE}.get_comments", new_callable=AsyncMock, return_value={"comments": []}),
        patch(f"{_MODULE}.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch,
        patch(f"{_MODULE}.console_events.push_run_event", new_callable=AsyncMock),
    ):
        result = await jira_poller._tick_step_b(client)

    assert result == {"resumed": 1, "unchanged": 0}
    assert mock_dispatch.await_args.args[0] == thread_id
    prompt = mock_dispatch.await_args.args[1]
    assert parked_column in prompt
    assert moved_to in prompt
    assert mock_dispatch.await_args.kwargs["metadata"]["jira_column"] == moved_to


@pytest.mark.asyncio
async def test_step_b_shadow_mode_logs_but_never_resumes() -> None:
    """Shadow mode's guarantee is "no real action" — resumes included."""
    thread_id = jira_poller.generate_thread_id_from_jira_issue("SSAI-51")
    client = _fake_client(
        {thread_id: {"jira_parked": True, "jira_parked_column": "Em Code Review"}}
    )
    with (
        patch(
            f"{_MODULE}.search_issues",
            new_callable=AsyncMock,
            return_value={"issues": [_issue("SSAI-51", "Ajustar Code")]},
        ),
        patch(f"{_MODULE}.get_comments", new_callable=AsyncMock) as mock_comments,
        patch(f"{_MODULE}.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch,
        patch(f"{_MODULE}.console_events.push_log", new_callable=AsyncMock) as mock_log,
        patch(f"{_MODULE}.JIRA_POLLER_SHADOW_MODE", True),
    ):
        result = await jira_poller._tick_step_b(client)

    assert result == {"resumed": 0, "unchanged": 0}
    mock_dispatch.assert_not_called()
    mock_comments.assert_not_called()
    client.threads.update.assert_not_called()
    mock_log.assert_awaited_once()
    message = mock_log.await_args.args[0]
    assert "[shadow]" in message
    assert "SSAI-51" in message
    assert "Em Code Review" in message
    assert "Ajustar Code" in message


@pytest.mark.asyncio
async def test_step_b_paused_mode_never_resumes() -> None:
    thread_id = jira_poller.generate_thread_id_from_jira_issue("SSAI-52")
    client = _fake_client({thread_id: {"jira_parked": True, "jira_parked_column": "Em Merge"}})
    with (
        patch(
            f"{_MODULE}.search_issues",
            new_callable=AsyncMock,
            return_value={"issues": [_issue("SSAI-52", "Mergeado")]},
        ),
        patch(f"{_MODULE}.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch,
        patch(f"{_MODULE}.JIRA_POLLER_PAUSED", True),
    ):
        result = await jira_poller._tick_step_b(client)

    assert result == {"resumed": 0, "unchanged": 0}
    mock_dispatch.assert_not_called()
    client.threads.update.assert_not_called()


@pytest.mark.asyncio
async def test_step_b_second_tick_after_resume_does_not_reprocess() -> None:
    """Idempotency: the resume clears `jira_parked`, so a repeated tick over
    the same post-gate column is a no-op instead of a second dispatch."""
    issue_key = "SSAI-53"
    thread_id = jira_poller.generate_thread_id_from_jira_issue(issue_key)
    metadata: dict[str, Any] = {"jira_parked": True, "jira_parked_column": "Em Revisão de Spec"}

    async def fake_get(requested_id: str) -> dict[str, Any]:
        assert requested_id == thread_id
        return {"metadata": metadata}

    async def fake_update(*, thread_id: str, metadata: dict[str, Any]) -> None:  # noqa: ARG001
        metadata_store.update(metadata)

    metadata_store = metadata
    client = MagicMock()
    client.threads.get = AsyncMock(side_effect=fake_get)
    client.threads.update = AsyncMock(side_effect=fake_update)

    with (
        patch(
            f"{_MODULE}.search_issues",
            new_callable=AsyncMock,
            return_value={"issues": [_issue(issue_key, "Spec Aprovada")]},
        ),
        patch(f"{_MODULE}.get_comments", new_callable=AsyncMock, return_value={"comments": []}),
        patch(f"{_MODULE}.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch,
        patch(f"{_MODULE}.console_events.push_run_event", new_callable=AsyncMock),
    ):
        first = await jira_poller._tick_step_b(client)
        second = await jira_poller._tick_step_b(client)

    assert first == {"resumed": 1, "unchanged": 0}
    assert second == {"resumed": 0, "unchanged": 0}
    assert mock_dispatch.await_count == 1


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
async def test_ensure_cron_keeps_an_existing_cron_on_the_configured_schedule() -> None:
    client = MagicMock()
    client.crons.search = AsyncMock(
        return_value=[{"cron_id": "existing-id", "schedule": "* * * * *"}]
    )
    client.crons.create = AsyncMock()
    client.crons.delete = AsyncMock()
    with patch(f"{_MODULE}.get_client", return_value=client):
        cron_id = await jira_poller.ensure_jira_poller_cron()

    assert cron_id == "existing-id"
    client.crons.create.assert_not_called()
    client.crons.delete.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_cron_replaces_a_cron_left_on_a_stale_schedule(tmp_path) -> None:
    """Startup is the recovery path for a console change the server never took.

    The operator saved 30 minutes, the push to this server failed, and the old
    every-minute cron stayed behind. Returning it unchanged would leave the
    saved interval permanently untrue.
    """
    config_file = tmp_path / "operational_config.json"
    config_file.write_text(json.dumps({"polling_interval_minutes": 30}), encoding="utf-8")

    client = MagicMock()
    client.crons.search = AsyncMock(return_value=[{"cron_id": "stale-id", "schedule": "* * * * *"}])
    client.crons.delete = AsyncMock()
    client.crons.create = AsyncMock(return_value={"cron_id": "fresh-id"})
    with (
        patch.dict(os.environ, {"OPERATIONAL_CONFIG_PATH": str(config_file)}),
        patch(f"{_MODULE}.get_client", return_value=client),
    ):
        cron_id = await jira_poller.ensure_jira_poller_cron()

    assert cron_id == "fresh-id"
    client.crons.delete.assert_awaited_once_with("stale-id")
    assert client.crons.create.await_args.kwargs["schedule"] == "*/30 * * * *"


@pytest.mark.asyncio
async def test_ensure_cron_collapses_duplicate_crons_to_one() -> None:
    client = MagicMock()
    client.crons.search = AsyncMock(
        return_value=[
            {"cron_id": "one", "schedule": "* * * * *"},
            {"cron_id": "two", "schedule": "* * * * *"},
        ]
    )
    client.crons.delete = AsyncMock()
    client.crons.create = AsyncMock(return_value={"cron_id": "only"})
    with patch(f"{_MODULE}.get_client", return_value=client):
        cron_id = await jira_poller.ensure_jira_poller_cron()

    assert cron_id == "only"
    assert [call.args[0] for call in client.crons.delete.await_args_list] == ["one", "two"]
    client.crons.create.assert_awaited_once()


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


# --- Pagination -------------------------------------------------------------
#
# Step B's query spans eight columns, so a real board easily exceeds one page.
# A single unpaginated request drops whatever sits past the page boundary, and
# Jira decides the ordering — so the card a human just moved can be the one
# that never gets resumed.


def _paged_search(pages: list[list[dict[str, Any]]]) -> AsyncMock:
    """Fake `search_issues` that hands out `pages` one request at a time."""
    calls: list[str | None] = []

    async def fake(
        jql: str,
        next_page_token: str | None = None,
        max_results: int = 50,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        calls.append(next_page_token)
        index = 0 if next_page_token is None else int(next_page_token)
        issues = pages[index]
        token = str(index + 1) if index + 1 < len(pages) else None
        return {"issues": issues, "next_page_token": token}

    mock = AsyncMock(side_effect=fake)
    mock.page_tokens = calls  # type: ignore[attr-defined]
    return mock


@pytest.mark.asyncio
async def test_step_b_resumes_a_card_that_falls_beyond_the_first_page() -> None:
    """The moved card is last, behind a full page of cards still at their gate."""
    parked_at_gate = [_issue(f"SSAI-{n}", jira_poller.COLUMN_SPEC_REVIEW) for n in range(100, 150)]
    moved = _issue("SSAI-999", jira_poller.COLUMN_SPEC_APPROVED)

    metadata: dict[str, dict[str, Any] | None] = {
        jira_poller.generate_thread_id_from_jira_issue(issue["key"]): {
            "jira_parked": True,
            "jira_parked_column": jira_poller.COLUMN_SPEC_REVIEW,
        }
        for issue in [*parked_at_gate, moved]
    }
    client = _fake_client(metadata)
    search = _paged_search([parked_at_gate, [moved]])

    with (
        patch(f"{_MODULE}.search_issues", search),
        patch(f"{_MODULE}.get_comments", new_callable=AsyncMock, return_value={"comments": []}),
        patch(f"{_MODULE}.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch,
        patch("agent.utils.console_events.AGENT_CONSOLE_URL", None),
    ):
        result = await jira_poller._tick_step_b(client)

    assert result == {"resumed": 1, "unchanged": 50}
    mock_dispatch.assert_awaited_once()
    assert mock_dispatch.await_args.args[0] == jira_poller.generate_thread_id_from_jira_issue(
        "SSAI-999"
    )
    # Page one, then page two via the token Jira handed back.
    assert search.page_tokens == [None, "1"]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_step_a_launches_a_card_that_falls_beyond_the_first_page() -> None:
    older = [_issue(f"SSAI-{n}", "BACKLOG") for n in range(200, 250)]
    newcomer = _issue("SSAI-777", "BACKLOG")
    metadata: dict[str, dict[str, Any] | None] = {
        jira_poller.generate_thread_id_from_jira_issue(issue["key"]): {"jira_issue_key": "x"}
        for issue in older
    }
    client = _fake_client(metadata)

    with (
        patch(f"{_MODULE}.search_issues", _paged_search([older, [newcomer]])),
        patch(f"{_MODULE}.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch,
        patch("agent.utils.console_events.AGENT_CONSOLE_URL", None),
    ):
        result = await jira_poller._tick_step_a(client)

    assert result == {"launched": 1, "skipped": 50, "shadow_candidates": []}
    mock_dispatch.assert_awaited_once()


@pytest.mark.asyncio
async def test_pagination_stops_at_the_page_cap() -> None:
    """A query that never stops paginating must not stall the tick forever."""
    endless = AsyncMock(
        return_value={"issues": [_issue("SSAI-1", "BACKLOG")], "next_page_token": "more"}
    )
    with patch(f"{_MODULE}.search_issues", endless):
        result = await jira_poller._search_all_issues("project = SSAI", fields=["status"])

    assert endless.await_count == jira_poller._MAX_SEARCH_PAGES
    assert len(result["issues"]) == jira_poller._MAX_SEARCH_PAGES


@pytest.mark.asyncio
async def test_a_failing_page_keeps_the_issues_already_collected() -> None:
    """Losing page two shouldn't discard the cards found on page one."""
    calls = {"n": 0}

    async def fake(
        jql: str,
        next_page_token: str | None = None,
        max_results: int = 50,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] == 1:
            return {"issues": [_issue("SSAI-1", "BACKLOG")], "next_page_token": "2"}
        return {"error": "Jira 503"}

    with patch(f"{_MODULE}.search_issues", AsyncMock(side_effect=fake)):
        result = await jira_poller._search_all_issues("project = SSAI", fields=["status"])

    assert [i["key"] for i in result["issues"]] == ["SSAI-1"]
    assert result["error"] == "Jira 503"


@pytest.mark.asyncio
async def test_step_b_reports_a_partial_failure_without_dropping_the_tick() -> None:
    moved = _issue("SSAI-5", jira_poller.COLUMN_ADJUST_CODE)
    client = _fake_client(
        {
            jira_poller.generate_thread_id_from_jira_issue("SSAI-5"): {
                "jira_parked": True,
                "jira_parked_column": jira_poller.COLUMN_CODE_REVIEW,
            }
        }
    )

    async def fake(
        jql: str,
        next_page_token: str | None = None,
        max_results: int = 50,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        if next_page_token is None:
            return {"issues": [moved], "next_page_token": "2"}
        return {"error": "Jira 503"}

    with (
        patch(f"{_MODULE}.search_issues", AsyncMock(side_effect=fake)),
        patch(f"{_MODULE}.get_comments", new_callable=AsyncMock, return_value={"comments": []}),
        patch(f"{_MODULE}.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch,
        patch("agent.utils.console_events.AGENT_CONSOLE_URL", None),
    ):
        result = await jira_poller._tick_step_b(client)

    mock_dispatch.assert_awaited_once()
    assert result == {"resumed": 1, "unchanged": 0, "error": "Jira 503"}


@pytest.mark.asyncio
async def test_step_b_still_reports_a_first_page_failure_as_a_dead_tick() -> None:
    client = _fake_client({})
    with patch(
        f"{_MODULE}.search_issues", new_callable=AsyncMock, return_value={"error": "Jira 401"}
    ):
        result = await jira_poller._tick_step_b(client)

    assert result == {"resumed": 0, "unchanged": 0, "error": "Jira 401"}
