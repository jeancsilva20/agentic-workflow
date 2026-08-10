from __future__ import annotations

import importlib
from typing import Any

import pytest

from agent.utils import jira as jira_utils

jira_get_issue_module = importlib.import_module("agent.tools.jira_get_issue")
jira_search_issues_module = importlib.import_module("agent.tools.jira_search_issues")
jira_get_comments_module = importlib.import_module("agent.tools.jira_get_comments")
jira_add_comment_module = importlib.import_module("agent.tools.jira_add_comment")
jira_transition_issue_module = importlib.import_module("agent.tools.jira_transition_issue")


async def test_jira_get_issue_delegates_to_client(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_issue(issue_key: str) -> dict[str, Any]:
        assert issue_key == "SSAI-88"
        return {"issue": {"key": "SSAI-88"}}

    monkeypatch.setattr(jira_get_issue_module, "get_issue", fake_get_issue)

    result = await jira_get_issue_module.jira_get_issue("SSAI-88")

    assert result == {"issue": {"key": "SSAI-88"}}


async def test_jira_search_issues_delegates_to_client(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_search_issues(jql: str, **kwargs: Any) -> dict[str, Any]:
        captured["jql"] = jql
        captured.update(kwargs)
        return {"issues": [], "next_page_token": None}

    monkeypatch.setattr(jira_search_issues_module, "search_issues", fake_search_issues)

    result = await jira_search_issues_module.jira_search_issues("project = SSAI", max_results=10)

    assert result == {"issues": [], "next_page_token": None}
    assert captured == {
        "jql": "project = SSAI",
        "next_page_token": None,
        "max_results": 10,
        "fields": None,
    }


async def test_jira_get_comments_delegates_to_client(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_comments(issue_key: str) -> dict[str, Any]:
        assert issue_key == "SSAI-88"
        return {"comments": [{"id": "1"}]}

    monkeypatch.setattr(jira_get_comments_module, "get_comments", fake_get_comments)

    result = await jira_get_comments_module.jira_get_comments("SSAI-88")

    assert result == {"comments": [{"id": "1"}]}


async def test_jira_add_comment_converts_markdown_and_posts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_add_comment(issue_key: str, adf_body: dict[str, Any]) -> dict[str, Any]:
        captured["issue_key"] = issue_key
        captured["adf_body"] = adf_body
        return {"success": True, "comment": {"id": "1"}}

    monkeypatch.setattr(jira_add_comment_module, "add_comment", fake_add_comment)

    result = await jira_add_comment_module.jira_add_comment("SSAI-88", "**bold** text")

    assert result == {"success": True, "comment": {"id": "1"}}
    assert captured["issue_key"] == "SSAI-88"
    assert captured["adf_body"]["type"] == "doc"


async def test_jira_transition_issue_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_transition_to_column(issue_key: str, column_name: str) -> dict[str, Any]:
        assert issue_key == "SSAI-88"
        assert column_name == "In Progress"
        return {"success": True}

    monkeypatch.setattr(
        jira_transition_issue_module, "transition_to_column", fake_transition_to_column
    )

    result = await jira_transition_issue_module.jira_transition_issue("SSAI-88", "In Progress")

    assert result == {"success": True}


async def test_jira_transition_issue_wraps_transition_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_transition_to_column(issue_key: str, column_name: str) -> dict[str, Any]:
        raise jira_utils.JiraTransitionError("No transition to column 'Bogus'. Available: X, Y")

    monkeypatch.setattr(
        jira_transition_issue_module, "transition_to_column", fake_transition_to_column
    )

    result = await jira_transition_issue_module.jira_transition_issue("SSAI-88", "Bogus")

    assert result["success"] is False
    assert "Bogus" in result["error"]
