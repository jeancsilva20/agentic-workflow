"""Verify (or create) the target repository clone before the spec phase runs.

The agent is supposed to work on one repository: the one the card is about.
Nothing guarantees that on its own — a directory named after the target repo
may exist without a ``.git`` of its own, in which case every ``git`` command
run "inside it" walks up and hits whatever repository encloses it. So before
the run touches git at all, the clone is checked to be a real repository whose
``origin`` is the expected target, cloned when missing, and treated as a fatal
configuration error when it points somewhere else.
"""

from __future__ import annotations

import logging
import os
import posixpath
import re
import shlex

from deepagents.backends.protocol import SandboxBackendProtocol

logger = logging.getLogger(__name__)

CLONE_TIMEOUT_SECONDS = 240


class TargetRepoMismatchError(RuntimeError):
    """The target repo directory exists but is not the expected repository."""


def _output(result: object) -> str:
    value = getattr(result, "output", "")
    return value.strip() if isinstance(value, str) else ""


def _ok(result: object) -> bool:
    exit_code = getattr(result, "exit_code", None)
    return exit_code in (0, None)


def _gh_prefix() -> str:
    """``gh`` auth differs by provider: proxy sandboxes want a dummy token.

    The local provider authenticates ``gh`` with the real PAT already present
    in its environment, so overriding ``GH_TOKEN`` there breaks the clone.
    """
    return "" if os.getenv("SANDBOX_TYPE", "langsmith") == "local" else "GH_TOKEN=dummy "


def normalize_remote_url(url: str) -> str:
    """Reduce a git remote URL to ``owner/name`` for comparison."""
    value = url.strip()
    if not value:
        return ""
    value = re.sub(r"\.git$", "", value)
    value = re.sub(r"^git@[^:]+:", "", value)
    value = re.sub(r"^ssh://git@[^/]+/", "", value)
    value = re.sub(r"^https?://[^/]+/", "", value)
    return value.strip("/").lower()


async def _run(
    backend: SandboxBackendProtocol, command: str, *, timeout: int | None = None
) -> tuple[bool, str]:
    try:
        result = (
            await backend.aexecute(command, timeout=timeout)
            if timeout
            else await backend.aexecute(command)
        )
    except Exception:  # noqa: BLE001
        logger.warning("Target repo command failed: %s", command, exc_info=True)
        return False, ""
    return _ok(result), _output(result)


async def ensure_target_repo_clone(
    backend: SandboxBackendProtocol,
    *,
    work_dir: str,
    owner: str,
    name: str,
) -> str:
    """Return the target repo directory, cloning or repairing it as needed.

    Raises:
        TargetRepoMismatchError: the directory is a git repository whose
            ``origin`` is not ``owner/name``, or the clone could not be
            created. Both mean the run cannot safely touch git.
    """
    if not owner or not name:
        raise TargetRepoMismatchError("Target repository owner and name are required")

    repo_dir = posixpath.join(work_dir, name)
    expected = f"{owner}/{name}".lower()
    q_repo_dir = shlex.quote(repo_dir)

    has_git, _ = await _run(backend, f"test -d {q_repo_dir}/.git")
    if not has_git:
        exists, _ = await _run(backend, f"test -e {q_repo_dir}")
        if exists:
            # A directory without its own .git is exactly the contamination we
            # are guarding against: git commands in it belong to whatever
            # repository encloses it. It lives in the sandbox root, so the
            # content is re-clonable and safe to discard.
            logger.warning("Replacing %s: it exists but has no .git of its own", repo_dir)
            removed, output = await _run(backend, f"rm -rf {q_repo_dir}")
            if not removed:
                raise TargetRepoMismatchError(
                    f"{repo_dir} is not a git repository and could not be removed: {output}"
                )
        cloned, output = await _run(
            backend,
            f"{_gh_prefix()}gh repo clone {shlex.quote(expected)} {q_repo_dir}",
            timeout=CLONE_TIMEOUT_SECONDS,
        )
        if not cloned:
            raise TargetRepoMismatchError(
                f"Failed to clone {owner}/{name} into {repo_dir}: {output}"
            )

    toplevel_ok, toplevel = await _run(backend, f"git -C {q_repo_dir} rev-parse --show-toplevel")
    if not toplevel_ok or not toplevel:
        raise TargetRepoMismatchError(
            f"{repo_dir} does not resolve to a git repository of its own: {toplevel or 'no output'}"
        )
    resolved_ok, resolved_dir = await _run(backend, f"readlink -f {q_repo_dir}")
    expected_toplevel = resolved_dir if resolved_ok and resolved_dir else repo_dir
    if posixpath.normpath(toplevel) != posixpath.normpath(expected_toplevel):
        raise TargetRepoMismatchError(
            f"{repo_dir} has no .git of its own — git commands there operate on "
            f"{toplevel} instead. Refusing to run git against the wrong repository."
        )

    remote_ok, remote_url = await _run(
        backend, f"git -C {q_repo_dir} config --get remote.origin.url"
    )
    actual = normalize_remote_url(remote_url) if remote_ok else ""
    if actual != expected:
        raise TargetRepoMismatchError(
            f"{repo_dir} has origin {remote_url or '<unset>'} but this run targets "
            f"{owner}/{name}. Refusing to run git against the wrong repository."
        )

    logger.info("Target repo ready at %s (origin=%s/%s)", repo_dir, owner, name)
    return repo_dir
