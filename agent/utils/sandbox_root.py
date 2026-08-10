"""The boundary between this project and the repository the agent works on.

The local sandbox provider runs shell commands straight on the host, so its
root directory decides which repository the agent's git commands actually
touch. Inheriting the server process's working directory points that root at
*this* checkout, which silently turns "clone the target repo, branch, commit,
push" into commits on ourselves: the clone lands inside our tree with no
``.git`` of its own, so every ``git`` command the agent runs "in the target
repo" resolves to our repository instead.

This module owns the two halves of the fix: a dedicated sandbox root outside
our tree, and a hard refusal to use any work directory inside it.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

LOCAL_SANDBOX_ROOT_ENV = "LOCAL_SANDBOX_ROOT_DIR"
SANDBOX_ROOT_DIRNAME = "open-swe-sandbox"


class SandboxRootInsideProjectError(RuntimeError):
    """A sandbox work directory resolved to somewhere inside this project."""

    def __init__(self, path: str, *, source: str) -> None:
        root = project_root()
        super().__init__(
            f"Refusing to use {path!r} as the sandbox work directory: it is inside this "
            f"project's checkout at {root!r} ({source}). The agent must operate only on "
            f"the target repository, never on the Open SWE project that runs it. Set "
            f"{LOCAL_SANDBOX_ROOT_ENV} to a directory outside {root!r} and retry."
        )
        self.path = path
        self.source = source


def project_root() -> str:
    """Absolute path of this project's checkout (the parent of ``agent/``)."""
    return str(Path(__file__).resolve().parents[2])


def is_inside_project(path: str) -> bool:
    """Whether ``path`` is this project's root or lives underneath it."""
    if not path:
        return False
    root = Path(project_root())
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        return True
    resolved = candidate.resolve()
    return resolved == root or root in resolved.parents


def assert_outside_project(path: str, *, source: str) -> str:
    """Return ``path`` unchanged, or raise if it is inside this project."""
    if is_inside_project(path):
        raise SandboxRootInsideProjectError(path, source=source)
    return path


def default_local_sandbox_root() -> str:
    """A dedicated sandbox root outside this project, used when unconfigured.

    Prefers ``~/open-swe-sandbox`` and falls back to the system temp dir when
    the home directory is missing or itself inside this project.
    """
    home = os.path.expanduser("~")
    if home and home != "~" and not is_inside_project(home):
        return str(Path(home) / SANDBOX_ROOT_DIRNAME)
    return str(Path(tempfile.gettempdir()) / SANDBOX_ROOT_DIRNAME)


def resolve_local_sandbox_root() -> str:
    """Resolve the local sandbox root, refusing any path inside this project.

    Never falls back to the process working directory: that is what put the
    target repository's clone inside our own repository in the first place.
    """
    configured = (os.getenv(LOCAL_SANDBOX_ROOT_ENV) or "").strip()
    if configured:
        return assert_outside_project(
            str(Path(configured).expanduser()), source=f"configured via {LOCAL_SANDBOX_ROOT_ENV}"
        )
    return assert_outside_project(default_local_sandbox_root(), source="default sandbox root")
