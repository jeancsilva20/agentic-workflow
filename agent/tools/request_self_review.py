"""Tool: ``request_self_review``. Trigger the existing reviewer graph on the
current PR for a Jira-driven run (PASSO 7 in design.md's workflow).

Thin wrapper over ``request_pr_review`` — the reviewer graph has no path for
reviewing an uncommitted or un-PR'd diff (it fetches the diff via
``base_sha``/``head_sha`` from real PR metadata: see
``agent/webhooks/github.py:trigger_pr_review_from_ref``), so this requires a
PR to already exist. Design.md's workflow places this step (PASSO 7) before
"push + create PR" (PASSO 8) — reconciled by having the agent open at least a
draft PR before calling this tool; PASSO 8 then finalizes that same PR
(undrafts it, final push) rather than creating a second one.
"""

from __future__ import annotations

from typing import Any

from .request_pr_review import request_pr_review


async def request_self_review(pr_url: str) -> dict[str, Any]:
    """Start the reviewer agent for this Jira issue's pull request.

    Args:
        pr_url: The GitHub PR URL. Open one (a draft is fine) with
            `open_pull_request` before calling this — the reviewer graph has
            no path for reviewing a diff that isn't already a real PR.

    Returns:
        Whatever `request_pr_review` returns: success plus reviewer-run
        details, or `success: False` and an `error` if the URL didn't parse.
    """
    return await request_pr_review(pr_url)
