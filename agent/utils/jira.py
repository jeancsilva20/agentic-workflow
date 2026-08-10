"""Jira Cloud REST API v3 utilities."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
from typing import Any

import httpx

from .http import DEFAULT_HTTP_TIMEOUT

logger = logging.getLogger(__name__)

JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")

_MAX_429_RETRIES = 3
_RETRY_BASE_DELAY_SECONDS = 1.0


class JiraTransitionError(RuntimeError):
    """A named column transition could not be resolved or applied."""


def jira_configured() -> bool:
    """Whether Jira credentials are present. Callers degrade gracefully when False."""
    return bool(JIRA_BASE_URL and JIRA_EMAIL and JIRA_API_TOKEN)


def _headers() -> dict[str, str]:
    credentials = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
    return {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _request(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Issue one Jira REST v3 call with 429 backoff and typed error handling.

    Returns the parsed JSON body on success (or ``{"success": True}`` for a
    204), or ``{"error": "..."}`` on any failure. Never raises for ordinary
    HTTP error responses, so callers can treat every result uniformly.
    """
    if not jira_configured():
        return {
            "error": "Jira credentials are not configured "
            "(JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN)"
        }

    url = f"{JIRA_BASE_URL}{path}"
    attempt = 0
    async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
        while True:
            attempt += 1
            try:
                response = await client.request(
                    method, url, headers=_headers(), json=json_body, params=params
                )
            except httpx.HTTPError as exc:
                return {"error": f"Jira request failed: {exc}"}

            if response.status_code == 429 and attempt <= _MAX_429_RETRIES:
                delay = _RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        pass
                logger.warning(
                    "Jira 429 rate limit on %s %s, retrying in %.1fs (attempt %d/%d)",
                    method,
                    path,
                    delay,
                    attempt,
                    _MAX_429_RETRIES,
                )
                await asyncio.sleep(delay)
                continue

            if response.status_code == 401:
                return {
                    "error": "Jira authentication failed (401) — check JIRA_EMAIL / JIRA_API_TOKEN"
                }
            if response.status_code == 404:
                return {"error": f"Jira resource not found (404): {path}"}
            if response.status_code == 400:
                return {"error": f"Jira rejected the request (400): {response.text}"}
            if response.status_code >= 400:
                return {"error": f"Jira request failed ({response.status_code}): {response.text}"}

            if response.status_code == 204 or not response.content:
                return {"success": True}
            return response.json()


async def get_issue(issue_key: str, fields: str = "*all") -> dict[str, Any]:
    """Get a Jira issue by key."""
    result = await _request("GET", f"/rest/api/3/issue/{issue_key}", params={"fields": fields})
    if "error" in result:
        return result
    return {"issue": result}


async def search_issues(
    jql: str,
    start_at: int = 0,
    max_results: int = 50,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Search issues via JQL (POST /rest/api/3/search)."""
    body: dict[str, Any] = {"jql": jql, "startAt": start_at, "maxResults": max_results}
    if fields:
        body["fields"] = fields
    result = await _request("POST", "/rest/api/3/search", json_body=body)
    if "error" in result:
        return result
    return {
        "issues": result.get("issues", []),
        "total": result.get("total", 0),
        "start_at": result.get("startAt", 0),
    }


async def get_comments(issue_key: str) -> dict[str, Any]:
    """Get comments on a Jira issue."""
    result = await _request("GET", f"/rest/api/3/issue/{issue_key}/comment")
    if "error" in result:
        return result
    return {"comments": result.get("comments", [])}


async def add_comment(issue_key: str, adf_body: dict[str, Any]) -> dict[str, Any]:
    """Add an ADF-formatted comment to a Jira issue.

    ``adf_body`` must already be a valid ADF document — see ``agent/utils/adf.py``
    to convert Markdown. The wire format wraps it as ``{"body": <adf>}``.
    """
    result = await _request(
        "POST", f"/rest/api/3/issue/{issue_key}/comment", json_body={"body": adf_body}
    )
    if "error" in result:
        return result
    return {"success": True, "comment": result}


async def get_transitions(issue_key: str) -> dict[str, Any]:
    """List the transitions currently available for an issue."""
    result = await _request("GET", f"/rest/api/3/issue/{issue_key}/transitions")
    if "error" in result:
        return result
    return {"transitions": result.get("transitions", [])}


async def transition_issue(issue_key: str, transition_id: str) -> dict[str, Any]:
    """Execute a transition by id (POST .../transitions)."""
    result = await _request(
        "POST",
        f"/rest/api/3/issue/{issue_key}/transitions",
        json_body={"transition": {"id": transition_id}},
    )
    if "error" in result:
        return result
    return {"success": True}


async def transition_to_column(issue_key: str, column_name: str) -> dict[str, Any]:
    """Move an issue to a column by name.

    Resolves ``column_name`` to a transition id via ``get_transitions`` first,
    since the transitions endpoint takes an id, not a name. Raises
    ``JiraTransitionError`` listing the available target names when the
    column does not match any transition currently offered by the issue's
    workflow state (this is how an unreachable/misconfigured column shows up,
    since the Jira workflow allows every status to reach every other one).
    """
    transitions_result = await get_transitions(issue_key)
    if "error" in transitions_result:
        raise JiraTransitionError(transitions_result["error"])

    transitions = transitions_result.get("transitions", [])
    match = next(
        (
            t
            for t in transitions
            if t.get("to", {}).get("name") == column_name or t.get("name") == column_name
        ),
        None,
    )
    if match is None:
        available = sorted(
            {t.get("to", {}).get("name", "") or t.get("name", "") for t in transitions} - {""}
        )
        raise JiraTransitionError(
            f"No transition to column {column_name!r} for issue {issue_key}. "
            f"Available targets: {', '.join(available) or '(none)'}"
        )

    result = await transition_issue(issue_key, match["id"])
    if "error" in result:
        raise JiraTransitionError(result["error"])
    return result


def generate_thread_id_from_jira_issue(issue_key: str) -> str:
    """Generate a deterministic thread ID from a Jira issue key.

    Mirrors ``generate_thread_id_from_issue`` in ``agent/webhooks/common.py``
    (the Linear equivalent) so a poller tick that re-triggers a parked thread
    reconnects to the same LangGraph thread/sandbox. The ``jira-issue:`` salt
    keeps this id space disjoint from Linear/GitHub issue ids that might share
    the same raw key string.
    """
    hash_bytes = hashlib.sha256(f"jira-issue:{issue_key}".encode()).hexdigest()
    return (
        f"{hash_bytes[:8]}-{hash_bytes[8:12]}-{hash_bytes[12:16]}-"
        f"{hash_bytes[16:20]}-{hash_bytes[20:32]}"
    )
