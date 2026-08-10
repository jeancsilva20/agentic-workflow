"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from agent.webhooks import common as webhook_common


@pytest.fixture(autouse=True)
def _no_console_operational_config(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Hide the agent console's runtime config from the suite.

    Shadow mode and the polling interval are read at call time from the file
    the console writes, which outranks the environment variable. A developer
    who left the console in shadow mode would otherwise flip the meaning of
    every launch/resume assertion in the poller tests. A test that wants a
    console-applied value writes its own file and points this variable at it.
    """
    monkeypatch.setenv("OPERATIONAL_CONFIG_PATH", str(tmp_path / "no_console_config.json"))


@pytest.fixture(autouse=True)
def _default_enable_auto_review(monkeypatch: pytest.MonkeyPatch) -> None:
    """Treat automatic reviews as enabled for every repo by default.

    The dashboard's opt-in list (loaded by :func:`agent.dashboard.enabled_repos.is_review_repo_enabled`)
    is empty in the test environment because there is no live LangGraph Store.

    Tests targeting the automatic-review gate should override this fixture or set
    ``monkeypatch.setattr(webhook_common, "is_review_repo_enabled", ...)`` to a stricter stub.
    """

    async def _enabled(_owner: str, _name: str) -> bool:
        return True

    monkeypatch.setattr(webhook_common, "is_review_repo_enabled", _enabled)
