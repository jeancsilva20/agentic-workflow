"""The boundary between this project and the repository the agent works on."""

from __future__ import annotations

import pytest

from agent.utils.sandbox_root import (
    SandboxRootInsideProjectError,
    assert_outside_project,
    default_local_sandbox_root,
    is_inside_project,
    project_root,
    resolve_local_sandbox_root,
)


def test_project_root_is_this_checkout():
    root = project_root()
    assert (root + "/agent/utils/sandbox_root.py").startswith(root)
    assert is_inside_project(root)


@pytest.mark.parametrize(
    "path",
    [
        "/sensedia-backend-case",
        "/agent",
        "/harness/SSAI-90-harness-report.md",
        "",
    ],
)
def test_paths_under_the_project_are_inside(path):
    assert is_inside_project(project_root() + path) is True


def test_paths_outside_the_project_are_allowed(tmp_path):
    assert is_inside_project(str(tmp_path)) is False
    assert assert_outside_project(str(tmp_path), source="test") == str(tmp_path)


def test_relative_paths_are_treated_as_inside():
    """A relative path resolves against the process cwd -- i.e. against us."""
    assert is_inside_project("sensedia-backend-case") is True


def test_assert_outside_project_names_the_refused_path():
    refused = project_root() + "/sensedia-backend-case"
    with pytest.raises(SandboxRootInsideProjectError) as excinfo:
        assert_outside_project(refused, source="resolved sandbox work directory")
    message = str(excinfo.value)
    assert refused in message
    assert "resolved sandbox work directory" in message
    assert "LOCAL_SANDBOX_ROOT_DIR" in message


def test_default_sandbox_root_is_outside_the_project():
    assert not is_inside_project(default_local_sandbox_root())


def test_resolve_uses_configured_root(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_SANDBOX_ROOT_DIR", str(tmp_path))
    assert resolve_local_sandbox_root() == str(tmp_path)


def test_resolve_falls_back_to_default_not_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCAL_SANDBOX_ROOT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    resolved = resolve_local_sandbox_root()
    assert resolved == default_local_sandbox_root()
    assert resolved != str(tmp_path)


def test_resolve_refuses_configured_root_inside_the_project(monkeypatch):
    monkeypatch.setenv("LOCAL_SANDBOX_ROOT_DIR", project_root())
    with pytest.raises(SandboxRootInsideProjectError):
        resolve_local_sandbox_root()
