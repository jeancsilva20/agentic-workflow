from __future__ import annotations

import asyncio

import pytest

from agent.utils import auth


def test_leave_failure_comment_posts_generic_token_free_slack_notice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slack auth failures post a generic notice, never the (possibly sensitive) message."""
    monkeypatch.setenv("DASHBOARD_BASE_URL", "https://app.example.com")
    thread_called: dict[str, str] = {}

    async def fake_post_slack_thread_reply(channel_id: str, thread_ts: str, message: str) -> bool:
        thread_called["channel_id"] = channel_id
        thread_called["thread_ts"] = thread_ts
        thread_called["message"] = message
        return True

    monkeypatch.setattr(auth, "post_slack_thread_reply", fake_post_slack_thread_reply)
    monkeypatch.setattr(
        auth,
        "get_config",
        lambda: {
            "configurable": {
                "slack_thread": {
                    "channel_id": "C123",
                    "thread_ts": "1.2",
                    "triggering_user_id": "U123",
                }
            }
        },
    )

    # Pass a message that embeds a per-user auth URL; it must NOT be echoed publicly.
    asyncio.run(auth.leave_failure_comment("slack", "Click https://auth.example/secret-token"))

    assert thread_called["channel_id"] == "C123"
    assert thread_called["thread_ts"] == "1.2"
    assert "secret-token" not in thread_called["message"]
    assert "https://app.example.com/my-settings" in thread_called["message"]


def _slack_config(github_login: str | None = "mason-gh") -> dict:
    configurable: dict = {
        "source": "slack",
        "user_email": "mason@example.com",
        "thread_id": "t1",
    }
    if github_login is not None:
        configurable["github_login"] = github_login
    return {"configurable": configurable}


def _stub_dashboard_store(
    monkeypatch: pytest.MonkeyPatch,
    *,
    token: str | None,
    expires_at: str | None = "2099-01-01T00:00:00Z",
    cached: tuple[str | None, str | None] = (None, None),
) -> None:
    from agent.dashboard import profiles

    async def fake_get_from_thread(thread_id: str):
        return cached

    async def fake_get_valid(login: str):
        return token

    async def fake_get_value(namespace, key):
        return {"token_expires_at": expires_at}

    monkeypatch.setattr(auth, "get_github_token_from_thread", fake_get_from_thread)
    monkeypatch.setattr(profiles, "get_valid_access_token", fake_get_valid)
    monkeypatch.setattr(profiles, "_get_value", fake_get_value)


def test_resolve_github_token_slack_uses_dashboard_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_dashboard_store(monkeypatch, token="user-tok")
    monkeypatch.setattr(auth, "is_bot_token_only_mode", lambda: False)

    token, expires_at = asyncio.run(auth.resolve_github_token(_slack_config(), "t1"))

    assert token == "user-tok"
    assert expires_at == "2099-01-01T00:00:00Z"


def test_resolve_github_token_slack_ignores_stale_thread_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Slack thread ids are shared, so a prior user's cached token must NOT be
    # returned. Resolution always goes by github_login via the dashboard store.
    _stub_dashboard_store(
        monkeypatch,
        token="bob-token",
        cached=("alice-token", "2099-01-01T00:00:00Z"),
    )
    monkeypatch.setattr(auth, "is_bot_token_only_mode", lambda: False)

    token, _ = asyncio.run(auth.resolve_github_token(_slack_config(), "t1"))

    assert token == "bob-token"


def test_resolve_github_token_slack_no_token_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_dashboard_store(monkeypatch, token=None)
    monkeypatch.setattr(auth, "is_bot_token_only_mode", lambda: False)

    with pytest.raises(auth.GitHubUserAuthRequired):
        asyncio.run(auth.resolve_github_token(_slack_config(), "t1"))


def test_resolve_github_token_per_user_wins_over_bot_only_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_dashboard_store(monkeypatch, token="user-tok")
    monkeypatch.setattr(auth, "is_bot_token_only_mode", lambda: True)

    async def fail_bot(thread_id: str):
        raise AssertionError("bot token must not be used when a user token exists")

    monkeypatch.setattr(auth, "_resolve_bot_installation_token", fail_bot)

    token, _ = asyncio.run(auth.resolve_github_token(_slack_config(), "t1"))
    assert token == "user-tok"


def test_resolve_github_token_slack_no_token_falls_back_to_bot_in_bot_only_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_dashboard_store(monkeypatch, token=None)
    monkeypatch.setattr(auth, "is_bot_token_only_mode", lambda: True)

    async def fake_bot(thread_id: str):
        return ("bot-tok", None)

    monkeypatch.setattr(auth, "_resolve_bot_installation_token", fake_bot)

    token, expires_at = asyncio.run(auth.resolve_github_token(_slack_config(), "t1"))
    assert (token, expires_at) == ("bot-tok", None)


def _linear_config(github_login: str | None = "mason-gh") -> dict:
    configurable: dict = {
        "source": "linear",
        "user_email": "mason@example.com",
        "thread_id": "t1",
    }
    if github_login is not None:
        configurable["github_login"] = github_login
    return {"configurable": configurable}


def test_resolve_github_token_linear_uses_dashboard_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_dashboard_store(monkeypatch, token="user-tok")
    monkeypatch.setattr(auth, "is_bot_token_only_mode", lambda: False)

    token, expires_at = asyncio.run(auth.resolve_github_token(_linear_config(), "t1"))

    assert token == "user-tok"
    assert expires_at == "2099-01-01T00:00:00Z"


def test_resolve_github_token_linear_no_token_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_dashboard_store(monkeypatch, token=None)
    monkeypatch.setattr(auth, "is_bot_token_only_mode", lambda: False)

    with pytest.raises(auth.GitHubUserAuthRequired):
        asyncio.run(auth.resolve_github_token(_linear_config(), "t1"))


def test_resolve_github_token_linear_no_token_falls_back_to_bot_in_bot_only_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_dashboard_store(monkeypatch, token=None)
    monkeypatch.setattr(auth, "is_bot_token_only_mode", lambda: True)

    async def fake_bot(thread_id: str):
        return ("bot-tok", None)

    monkeypatch.setattr(auth, "_resolve_bot_installation_token", fake_bot)

    token, expires_at = asyncio.run(auth.resolve_github_token(_linear_config(), "t1"))
    assert (token, expires_at) == ("bot-tok", None)


@pytest.mark.parametrize("source", ["github"])
def test_resolve_github_token_bot_only_mode_non_slack_uses_bot(
    monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    monkeypatch.setattr(auth, "is_bot_token_only_mode", lambda: True)

    async def fake_bot(thread_id: str):
        return ("bot-tok", None)

    monkeypatch.setattr(auth, "_resolve_bot_installation_token", fake_bot)

    config = {"configurable": {"source": source, "github_login": "octo", "thread_id": "t1"}}
    token, _ = asyncio.run(auth.resolve_github_token(config, "t1"))
    assert token == "bot-tok"


# ---------------------------------------------------------------------------
# Jira PAT tests
# ---------------------------------------------------------------------------


def _jira_config(issue_key: str = "PROJ-1") -> dict:
    return {"configurable": {"source": "jira", "jira_issue_key": issue_key}}


def test_resolve_github_token_jira_with_pat_returns_pat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When GITHUB_PAT is set and source is jira, the PAT is returned directly."""
    monkeypatch.setattr(auth, "get_github_pat", lambda: "ghp_test_pat")
    monkeypatch.setattr(auth, "is_bot_token_only_mode", lambda: False)

    token, expires_at = asyncio.run(auth.resolve_github_token(_jira_config(), "t-jira"))

    assert token == "ghp_test_pat"
    assert expires_at is None


def test_resolve_github_token_jira_without_pat_falls_back_to_bot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When GITHUB_PAT is absent for source=jira, bot-token fallback is used."""
    monkeypatch.setattr(auth, "get_github_pat", lambda: None)
    monkeypatch.setattr(auth, "is_bot_token_only_mode", lambda: True)

    async def fake_bot(thread_id: str):
        return ("bot-tok", None)

    monkeypatch.setattr(auth, "_resolve_bot_installation_token", fake_bot)

    token, expires_at = asyncio.run(auth.resolve_github_token(_jira_config(), "t-jira"))

    assert token == "bot-tok"
    assert expires_at is None


def test_resolve_github_token_jira_pat_takes_precedence_over_bot_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When both App and PAT are configured, PAT is used for jira source."""
    monkeypatch.setattr(auth, "get_github_pat", lambda: "ghp_pat_value")
    monkeypatch.setattr(auth, "is_bot_token_only_mode", lambda: True)

    async def fail_bot(thread_id: str):
        raise AssertionError("bot token must not be used when PAT is configured for jira")

    monkeypatch.setattr(auth, "_resolve_bot_installation_token", fail_bot)

    token, _ = asyncio.run(auth.resolve_github_token(_jira_config(), "t-jira"))
    assert token == "ghp_pat_value"


def test_leave_failure_comment_jira_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """leave_failure_comment('jira', ...) must never raise ValueError."""
    monkeypatch.setattr(
        auth,
        "get_config",
        lambda: {"configurable": {"jira_issue_key": "PROJ-99"}},
    )
    # Stub add_comment so we don't hit the real Jira API.
    comments_posted: list[str] = []

    async def fake_add_comment(issue_key: str, adf_body: object) -> dict:
        comments_posted.append(issue_key)
        return {"success": True}

    import agent.utils.jira as jira_mod

    monkeypatch.setattr(jira_mod, "add_comment", fake_add_comment)

    # Must not raise, even with a Jira issue key present.
    asyncio.run(auth.leave_failure_comment("jira", "Something went wrong"))

    assert comments_posted == ["PROJ-99"]


def test_leave_failure_comment_jira_no_key_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """leave_failure_comment('jira', ...) without jira_issue_key just logs."""
    monkeypatch.setattr(
        auth,
        "get_config",
        lambda: {"configurable": {}},
    )
    # Should silently succeed with no comment posted.
    asyncio.run(auth.leave_failure_comment("jira", "No Jira key available"))


def test_resolve_github_token_slack_unaffected_by_pat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting GITHUB_PAT must not change the token resolution for slack source."""
    monkeypatch.setattr(auth, "get_github_pat", lambda: "ghp_should_be_ignored")
    _stub_dashboard_store(monkeypatch, token="slack-user-tok")
    monkeypatch.setattr(auth, "is_bot_token_only_mode", lambda: False)

    token, _ = asyncio.run(auth.resolve_github_token(_slack_config(), "t1"))
    assert token == "slack-user-tok"


def test_resolve_github_token_linear_unaffected_by_pat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting GITHUB_PAT must not change the token resolution for linear source."""
    monkeypatch.setattr(auth, "get_github_pat", lambda: "ghp_should_be_ignored")
    _stub_dashboard_store(monkeypatch, token="linear-user-tok")
    monkeypatch.setattr(auth, "is_bot_token_only_mode", lambda: False)

    token, _ = asyncio.run(auth.resolve_github_token(_linear_config(), "t1"))
    assert token == "linear-user-tok"
