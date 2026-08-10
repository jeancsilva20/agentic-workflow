"""Read-only route that serves the package's own `agent/skills/` directory.

Both graphs mount it: the coding agent gets the OpenSpec lifecycle and Python
engineering skills, the reviewer gets `python-review`. Keeping the route
constant and the backend factory here means the two graphs cannot drift onto
different paths — the route name is baked into the system prompts.
"""

from __future__ import annotations

from importlib import resources

from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.protocol import BackendProtocol

from .read_only_backend import ReadOnlyBackend

STATIC_SKILLS_ROUTE = "/openspec-skills/"


def make_static_skills_backend() -> BackendProtocol:
    """Serve `agent/skills/` read-only under :data:`STATIC_SKILLS_ROUTE`."""
    return ReadOnlyBackend(
        FilesystemBackend(root_dir=str(resources.files("agent.skills")), virtual_mode=True)
    )
