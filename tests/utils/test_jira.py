from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from agent.utils import jira


class _FakeAsyncClient:
    """Minimal async-context-manager stand-in for httpx.AsyncClient."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.request = AsyncMock(side_effect=self._next_response)

    async def _next_response(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        return self._responses.pop(0)

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False


def _configure_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jira, "JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setattr(jira, "JIRA_EMAIL", "bot@example.com")
    monkeypatch.setattr(jira, "JIRA_API_TOKEN", "token123")


def _patch_client(monkeypatch: pytest.MonkeyPatch, *responses: httpx.Response) -> _FakeAsyncClient:
    fake_client = _FakeAsyncClient(list(responses))
    monkeypatch.setattr(jira.httpx, "AsyncClient", lambda **_kwargs: fake_client)
    return fake_client


async def test_request_returns_error_when_credentials_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(jira, "JIRA_BASE_URL", "")
    monkeypatch.setattr(jira, "JIRA_EMAIL", "")
    monkeypatch.setattr(jira, "JIRA_API_TOKEN", "")

    result = await jira.get_issue("SSAI-1")

    assert "error" in result
    assert "not configured" in result["error"]
    assert jira.jira_configured() is False


async def test_get_issue_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_credentials(monkeypatch)
    _patch_client(
        monkeypatch,
        httpx.Response(200, json={"id": "10001", "key": "SSAI-88", "fields": {"summary": "Bug"}}),
    )

    result = await jira.get_issue("SSAI-88")

    assert result == {"issue": {"id": "10001", "key": "SSAI-88", "fields": {"summary": "Bug"}}}


async def test_search_issues_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_credentials(monkeypatch)
    fake_client = _patch_client(
        monkeypatch,
        httpx.Response(
            200,
            json={"issues": [{"key": "SSAI-1"}]},
        ),
    )

    result = await jira.search_issues("project = SSAI AND status = BACKLOG")

    assert result == {"issues": [{"key": "SSAI-1"}], "next_page_token": None}
    call = fake_client.calls[0]
    assert call["url"].endswith("/rest/api/3/search/jql")
    assert call["json"] == {"jql": "project = SSAI AND status = BACKLOG", "maxResults": 50}


async def test_search_issues_paginates_with_next_page_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_credentials(monkeypatch)
    fake_client = _patch_client(
        monkeypatch,
        httpx.Response(
            200,
            json={"issues": [{"key": "SSAI-2"}], "nextPageToken": "tok-2"},
        ),
    )

    result = await jira.search_issues(
        "project = SSAI", next_page_token="tok-1", max_results=1, fields=["status"]
    )

    assert result == {"issues": [{"key": "SSAI-2"}], "next_page_token": "tok-2"}
    assert fake_client.calls[0]["json"] == {
        "jql": "project = SSAI",
        "maxResults": 1,
        "nextPageToken": "tok-1",
        "fields": ["status"],
    }


async def test_get_comments_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_credentials(monkeypatch)
    _patch_client(
        monkeypatch,
        httpx.Response(200, json={"comments": [{"id": "1", "body": "hi"}]}),
    )

    result = await jira.get_comments("SSAI-88")

    assert result == {"comments": [{"id": "1", "body": "hi"}]}


async def test_add_comment_wraps_adf_body(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_credentials(monkeypatch)
    fake_client = _patch_client(monkeypatch, httpx.Response(201, json={"id": "999"}))

    adf_body = {"type": "doc", "version": 1, "content": []}
    result = await jira.add_comment("SSAI-88", adf_body)

    assert result == {"success": True, "comment": {"id": "999"}}
    assert fake_client.calls[0]["json"] == {"body": adf_body}


async def test_get_transitions_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_credentials(monkeypatch)
    _patch_client(
        monkeypatch,
        httpx.Response(
            200,
            json={
                "transitions": [
                    {"id": "31", "name": "Start Progress", "to": {"name": "In Progress"}}
                ]
            },
        ),
    )

    result = await jira.get_transitions("SSAI-88")

    assert result["transitions"][0]["to"]["name"] == "In Progress"


async def test_transition_issue_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_credentials(monkeypatch)
    fake_client = _patch_client(monkeypatch, httpx.Response(204))

    result = await jira.transition_issue("SSAI-88", "31")

    assert result == {"success": True}
    assert fake_client.calls[0]["json"] == {"transition": {"id": "31"}}


async def test_transition_to_column_resolves_name_and_transitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_credentials(monkeypatch)
    _patch_client(
        monkeypatch,
        httpx.Response(
            200,
            json={
                "transitions": [
                    {"id": "31", "name": "Start Progress", "to": {"name": "In Progress"}},
                    {"id": "41", "name": "Done", "to": {"name": "Done"}},
                ]
            },
        ),
        httpx.Response(204),
    )

    result = await jira.transition_to_column("SSAI-88", "In Progress")

    assert result == {"success": True}


async def test_transition_to_column_raises_with_available_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_credentials(monkeypatch)
    _patch_client(
        monkeypatch,
        httpx.Response(
            200,
            json={
                "transitions": [
                    {"id": "31", "name": "Start Progress", "to": {"name": "In Progress"}}
                ]
            },
        ),
    )

    with pytest.raises(jira.JiraTransitionError) as exc:
        await jira.transition_to_column("SSAI-88", "Nonexistent Column")

    assert "Nonexistent Column" in str(exc.value)
    assert "In Progress" in str(exc.value)


async def test_401_returns_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_credentials(monkeypatch)
    _patch_client(monkeypatch, httpx.Response(401))

    result = await jira.get_issue("SSAI-88")

    assert "error" in result
    assert "401" in result["error"]


async def test_404_returns_not_found_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_credentials(monkeypatch)
    _patch_client(monkeypatch, httpx.Response(404))

    result = await jira.get_issue("SSAI-999")

    assert "error" in result
    assert "404" in result["error"]


async def test_400_returns_invalid_transition_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_credentials(monkeypatch)
    _patch_client(monkeypatch, httpx.Response(400, text="invalid transition id"))

    result = await jira.transition_issue("SSAI-88", "bad-id")

    assert "error" in result
    assert "400" in result["error"]


async def test_429_retries_with_backoff_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_credentials(monkeypatch)
    monkeypatch.setattr(jira.asyncio, "sleep", AsyncMock())
    fake_client = _patch_client(
        monkeypatch,
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json={"transitions": []}),
    )

    result = await jira.get_transitions("SSAI-88")

    assert result == {"transitions": []}
    assert len(fake_client.calls) == 2
    jira.asyncio.sleep.assert_awaited_once()


def test_thread_id_derivation_is_deterministic() -> None:
    first = jira.generate_thread_id_from_jira_issue("SSAI-88")
    second = jira.generate_thread_id_from_jira_issue("SSAI-88")

    assert first == second
    assert len(first) == 36  # UUID-shaped: 8-4-4-4-12


def test_thread_id_derivation_differs_by_issue_key() -> None:
    assert jira.generate_thread_id_from_jira_issue(
        "SSAI-1"
    ) != jira.generate_thread_id_from_jira_issue("SSAI-2")
