"""GitHub fine-grained Personal Access Token (PAT) support.

Provides a single accessor for the optional ``GITHUB_PAT`` environment variable
used to authenticate Jira-triggered runs when a GitHub App installation is not
available or not appropriate.

The PAT must be a fine-grained token (not a classic token) scoped only to the
repositories the agent needs to access.  See the task documentation for the
required permission set (Contents, Pull requests, Issues, Metadata, Checks).

Security contract
-----------------
- The token value must **never** be logged, stored in thread metadata,
  serialised into LangSmith traces/configurable dicts, or echoed in prompts.
- Return the value only to trusted callsites (``resolve_github_token``,
  ``_configure_github_proxy``, local sandbox env injection).
- All other code paths receive ``None`` from ``get_github_pat`` and are
  responsible for handling the missing-token case cleanly.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_GITHUB_PAT_ENV = "GITHUB_PAT"


def get_github_pat() -> str | None:
    """Return the fine-grained PAT from the environment, or ``None``.

    Reads ``GITHUB_PAT`` from the process environment and strips surrounding
    whitespace.  Returns ``None`` when the variable is absent or blank.

    The caller is responsible for not logging or persisting the returned value.
    """
    raw = os.environ.get(_GITHUB_PAT_ENV, "")
    value = raw.strip() if raw else ""
    if not value:
        return None
    return value
