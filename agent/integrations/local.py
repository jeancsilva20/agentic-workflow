import asyncio
import base64
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

    configured_root_dir = os.getenv("LOCAL_SANDBOX_ROOT_DIR")
    if configured_root_dir:
        root_dir = configured_root_dir
    else:
        # LangGraph's blockbuster guard rejects synchronous filesystem calls
        # on the ASGI event loop.  Keep the fallback compatible with the
        # existing behavior, but resolve it off-loop.
        root_dir = await asyncio.to_thread(os.getcwd)
    await asyncio.to_thread(os.makedirs, root_dir, exist_ok=True)

    extra_env: dict[str, str] | None = None
    pat = get_github_pat()
    if pat:
        # Encode as Basic auth: x-access-token:<PAT>
        _b64 = base64.b64encode(f"x-access-token:{pat}".encode()).decode()
        extra_env = {
            "GH_TOKEN": pat,
            # The Replit host sets GIT_ASKPASS=replit-git-askpass which hangs
            # on git push because the proxy is not available inside the sandbox.
            # Override with empty string so git ignores it and falls through to
            # the http.extraheader we inject below.
            "GIT_ASKPASS": "",
            "GIT_TERMINAL_PROMPT": "0",
            # Inject PAT as HTTP Basic auth for all github.com git operations.
            # GIT_CONFIG_* vars are supported since git 2.31 and take precedence
            # over credential helpers and askpass — no config file is touched.
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {_b64}",
        }

    return LocalShellBackend(
        root_dir=root_dir,
        virtual_mode=True,
        inherit_env=True,
        env=extra_env,
    )
