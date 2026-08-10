import asyncio
from typing import cast

import pytest

import agent.integrations.local as local_mod
from agent.utils.sandbox_root import SandboxRootInsideProjectError, project_root


class _StubLocalShellBackend:
    def __init__(self, *, root_dir, virtual_mode, inherit_env, env=None):
        self.root_dir = root_dir
        self.virtual_mode = virtual_mode
        self.inherit_env = inherit_env
        self.env = env


def test_create_local_sandbox_creates_missing_root_dir(monkeypatch, tmp_path):
    root = tmp_path / "nested" / "openswe-sandbox"
    monkeypatch.setenv("LOCAL_SANDBOX_ROOT_DIR", str(root))
    monkeypatch.setattr(local_mod, "LocalShellBackend", _StubLocalShellBackend)

    backend = asyncio.run(local_mod.create_local_sandbox())

    assert root.is_dir()
    stub = cast(_StubLocalShellBackend, backend)
    assert stub.root_dir == str(root)
    assert stub.virtual_mode is True
    assert stub.inherit_env is True


def test_create_local_sandbox_does_not_read_cwd_when_root_is_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_SANDBOX_ROOT_DIR", str(tmp_path))
    monkeypatch.setattr(local_mod, "LocalShellBackend", _StubLocalShellBackend)

    def fail_getcwd():
        raise AssertionError("getcwd should not be called for a configured root")

    monkeypatch.setattr(local_mod.os, "getcwd", fail_getcwd)

    backend = asyncio.run(local_mod.create_local_sandbox())

    stub = cast(_StubLocalShellBackend, backend)
    assert stub.root_dir == str(tmp_path)


def test_create_local_sandbox_default_root_is_outside_this_project(monkeypatch, tmp_path):
    """Unconfigured, the sandbox roots itself outside our checkout -- never at cwd."""
    monkeypatch.delenv("LOCAL_SANDBOX_ROOT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(local_mod, "LocalShellBackend", _StubLocalShellBackend)

    backend = asyncio.run(local_mod.create_local_sandbox())

    stub = cast(_StubLocalShellBackend, backend)
    assert stub.root_dir != str(tmp_path)
    assert not stub.root_dir.startswith(project_root())
    assert stub.virtual_mode is True


def test_create_local_sandbox_refuses_root_inside_this_project(monkeypatch):
    """A root inside our checkout stops the run instead of contaminating us."""
    refused = f"{project_root()}/sensedia-backend-case"
    monkeypatch.setenv("LOCAL_SANDBOX_ROOT_DIR", refused)
    monkeypatch.setattr(local_mod, "LocalShellBackend", _StubLocalShellBackend)

    with pytest.raises(SandboxRootInsideProjectError) as excinfo:
        asyncio.run(local_mod.create_local_sandbox())

    assert refused in str(excinfo.value)


def test_create_local_sandbox_injects_pat_as_gh_token(monkeypatch, tmp_path):
    """When GITHUB_PAT is set, GH_TOKEN is injected into the sandbox env."""
    monkeypatch.setenv("LOCAL_SANDBOX_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv("GITHUB_PAT", "ghp_test_local_pat")
    monkeypatch.setattr(local_mod, "LocalShellBackend", _StubLocalShellBackend)

    backend = asyncio.run(local_mod.create_local_sandbox())

    stub = cast(_StubLocalShellBackend, backend)
    assert stub.env is not None
    assert stub.env["GH_TOKEN"] == "ghp_test_local_pat"


def test_create_local_sandbox_no_env_when_pat_absent(monkeypatch, tmp_path):
    """When GITHUB_PAT is absent, no extra env dict is passed to the backend."""
    monkeypatch.setenv("LOCAL_SANDBOX_ROOT_DIR", str(tmp_path))
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    monkeypatch.setattr(local_mod, "LocalShellBackend", _StubLocalShellBackend)

    backend = asyncio.run(local_mod.create_local_sandbox())

    stub = cast(_StubLocalShellBackend, backend)
    assert stub.env is None


def test_create_local_sandbox_pat_overrides_inherited_gh_token(monkeypatch, tmp_path):
    """GITHUB_PAT replaces any GH_TOKEN already in the environment."""
    monkeypatch.setenv("LOCAL_SANDBOX_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv("GH_TOKEN", "old_inherited_token")
    monkeypatch.setenv("GITHUB_PAT", "ghp_new_pat")
    monkeypatch.setattr(local_mod, "LocalShellBackend", _StubLocalShellBackend)

    backend = asyncio.run(local_mod.create_local_sandbox())

    stub = cast(_StubLocalShellBackend, backend)
    # env dict passed to the backend explicitly sets GH_TOKEN to the PAT value,
    # overriding the inherited one.
    assert stub.env is not None
    assert stub.env["GH_TOKEN"] == "ghp_new_pat"
