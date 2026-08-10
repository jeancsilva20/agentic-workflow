import asyncio
import os

from deepagents.backends import LocalShellBackend


async def create_local_sandbox(sandbox_id: str | None = None):
    """Create a local shell sandbox with no isolation.

    WARNING: This runs commands directly on the host machine with no sandboxing.
    Only use for local development with human-in-the-loop enabled.

    The root directory defaults to the current working directory and can be
    overridden via the LOCAL_SANDBOX_ROOT_DIR environment variable. It is
    created if it does not already exist.

    When ``GITHUB_PAT`` is set in the environment it is injected as ``GH_TOKEN``
    so that git operations inside the sandbox authenticate with the PAT.  Any
    ``GH_TOKEN`` inherited from the parent process is replaced.

    Args:
        sandbox_id: Ignored for local sandboxes; accepted for interface compatibility.

    Returns:
        LocalShellBackend instance implementing SandboxBackendProtocol.
    """
    from ..utils.github_pat import get_github_pat

    root_dir = os.getenv("LOCAL_SANDBOX_ROOT_DIR", os.getcwd())
    await asyncio.to_thread(os.makedirs, root_dir, exist_ok=True)

    extra_env: dict[str, str] | None = None
    pat = get_github_pat()
    if pat:
        extra_env = {"GH_TOKEN": pat}

    return LocalShellBackend(
        root_dir=root_dir,
        virtual_mode=True,
        inherit_env=True,
        env=extra_env,
    )
