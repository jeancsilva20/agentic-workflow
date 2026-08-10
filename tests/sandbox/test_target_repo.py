"""The target repo clone must be a real repository pointing at the right remote."""

from __future__ import annotations

import asyncio

import pytest
from deepagents.backends.protocol import ExecuteResponse

from agent.utils.target_repo import (
    TargetRepoMismatchError,
    ensure_target_repo_clone,
    normalize_remote_url,
)

WORK_DIR = "/sandbox"
REPO_DIR = "/sandbox/sensedia-backend-case"


class _FakeBackend:
    """Answers shell probes from a scripted view of the filesystem."""

    def __init__(
        self,
        *,
        has_git: bool = True,
        path_exists: bool = True,
        toplevel: str = REPO_DIR,
        origin: str = "https://github.com/guilhermeallen/sensedia-backend-case.git",
        clone_succeeds: bool = True,
    ) -> None:
        self.has_git = has_git
        self.path_exists = path_exists
        self.toplevel = toplevel
        self.origin = origin
        self.clone_succeeds = clone_succeeds
        self.commands: list[str] = []

    @property
    def id(self) -> str:
        return "fake"

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        del timeout
        self.commands.append(command)

        def response(output: str = "", exit_code: int = 0) -> ExecuteResponse:
            return ExecuteResponse(output=output, exit_code=exit_code, truncated=False)

        if command.startswith("test -d") and command.endswith("/.git"):
            return response(exit_code=0 if self.has_git else 1)
        if command.startswith("test -e"):
            return response(exit_code=0 if self.path_exists else 1)
        if command.startswith("rm -rf"):
            self.path_exists = False
            return response()
        if "gh repo clone" in command:
            if not self.clone_succeeds:
                return response("could not resolve host", 1)
            self.has_git = True
            return response()
        if "rev-parse --show-toplevel" in command:
            return response(self.toplevel)
        if command.startswith("readlink -f"):
            return response(REPO_DIR)
        if "remote.origin.url" in command:
            return response(self.origin, 0 if self.origin else 1)
        return response(exit_code=1)


def _ensure(backend: _FakeBackend) -> str:
    return asyncio.run(
        ensure_target_repo_clone(
            backend,
            work_dir=WORK_DIR,
            owner="guilhermeallen",
            name="sensedia-backend-case",
        )
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/guilhermeallen/sensedia-backend-case.git",
        "https://github.com/guilhermeallen/sensedia-backend-case",
        "git@github.com:guilhermeallen/sensedia-backend-case.git",
        "ssh://git@github.com/guilhermeallen/sensedia-backend-case.git",
    ],
)
def test_normalize_remote_url_reduces_to_owner_name(url):
    assert normalize_remote_url(url) == "guilhermeallen/sensedia-backend-case"


def test_existing_verified_clone_is_reused():
    backend = _FakeBackend()
    assert _ensure(backend) == REPO_DIR
    assert not any("gh repo clone" in c for c in backend.commands)


def test_missing_clone_is_created():
    backend = _FakeBackend(has_git=False, path_exists=False)
    assert _ensure(backend) == REPO_DIR
    assert any("gh repo clone" in c for c in backend.commands)


def test_directory_without_its_own_git_is_replaced():
    """This is the contamination case: git there would hit the enclosing repo."""
    backend = _FakeBackend(has_git=False, path_exists=True)
    assert _ensure(backend) == REPO_DIR
    assert any(c.startswith("rm -rf") for c in backend.commands)
    assert any("gh repo clone" in c for c in backend.commands)


def test_toplevel_outside_the_repo_dir_aborts():
    backend = _FakeBackend(toplevel="/home/runner/workspace")
    with pytest.raises(TargetRepoMismatchError) as excinfo:
        _ensure(backend)
    assert "/home/runner/workspace" in str(excinfo.value)


def test_wrong_origin_aborts():
    backend = _FakeBackend(origin="https://github.com/langchain-ai/open-swe.git")
    with pytest.raises(TargetRepoMismatchError) as excinfo:
        _ensure(backend)
    assert "langchain-ai/open-swe" in str(excinfo.value)


def test_failed_clone_aborts():
    backend = _FakeBackend(has_git=False, path_exists=False, clone_succeeds=False)
    with pytest.raises(TargetRepoMismatchError):
        _ensure(backend)


def test_git_operations_always_name_the_repo_dir():
    backend = _FakeBackend()
    _ensure(backend)
    git_commands = [c for c in backend.commands if c.startswith("git ")]
    assert git_commands
    assert all(c.startswith(f"git -C {REPO_DIR} ") for c in git_commands)
