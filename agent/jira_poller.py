"""Poller: launches a Jira-triggered agent thread per trigger-column card, and
re-triggers parked threads whose card has moved. Wired into the existing
`scheduler` graph (agent/scheduler.py) via a cron on a fixed tick, per
design.md Decision 1 and specs/column-approval-gate/spec.md.

Two independent steps per tick:
  A. New cards in the trigger column -> launch a fresh thread (idempotent:
     a card that already owns a thread is skipped, so a duplicate tick never
     double-triggers).
  B. Cards whose thread is parked at a gate -> re-trigger only if the card's
     column has actually changed since it was parked.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from langgraph_sdk import get_client

from .dispatch import dispatch_agent_run
from .utils import console_events
from .utils.jira import generate_thread_id_from_jira_issue, get_comments, search_issues

logger = logging.getLogger(__name__)

JIRA_POLL_INTERVAL_SECONDS = int(os.environ.get("JIRA_POLL_INTERVAL_SECONDS") or "60")
JIRA_PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "SSAI")

# Column names — configurable via env vars, defaults match design.md's Jira
# Column Configuration table (task 5.6). All 11 columns are covered, not just
# the ones the poller itself queries by name (COLUMN_TRIGGER and the three
# gate columns) — agent/prompt.py's JIRA_WORKFLOW_SECTION reads every one of
# these so the prompt never drifts from an operator's env-var overrides.
COLUMN_TRIGGER = os.environ.get("JIRA_COLUMN_TRIGGER", "BACKLOG")
COLUMN_IN_PROGRESS = os.environ.get("JIRA_COLUMN_IN_PROGRESS", "In Progress")
COLUMN_SPEC_REVIEW = os.environ.get("JIRA_COLUMN_SPEC_REVIEW", "Em Revisão de Spec")
COLUMN_SPEC_APPROVED = os.environ.get("JIRA_COLUMN_SPEC_APPROVED", "Spec Aprovada")
COLUMN_ADJUST_SPEC = os.environ.get("JIRA_COLUMN_ADJUST_SPEC", "Ajustar Spec")
COLUMN_CODE_REVIEW = os.environ.get("JIRA_COLUMN_CODE_REVIEW", "Em Code Review")
COLUMN_CODE_APPROVED = os.environ.get("JIRA_COLUMN_CODE_APPROVED", "Code Review Aprovado")
COLUMN_ADJUST_CODE = os.environ.get("JIRA_COLUMN_ADJUST_CODE", "Ajustar Code")
COLUMN_MERGE = os.environ.get("JIRA_COLUMN_MERGE", "Em Merge")
COLUMN_MERGED = os.environ.get("JIRA_COLUMN_MERGED", "Mergeado")
COLUMN_DONE = os.environ.get("JIRA_COLUMN_DONE", "Done")
_GATE_COLUMNS = (COLUMN_SPEC_REVIEW, COLUMN_CODE_REVIEW, COLUMN_MERGE)

# Decision 11 mitigation (task 5.10): optional JQL scoping, off by default —
# the board and the column-driven model stay intact either way. This is a
# configuration change, not a redesign.
JIRA_TRIGGER_JQL_FILTER = os.environ.get("JIRA_TRIGGER_JQL_FILTER", "")

# Best-effort label used only to split "human-filed" vs "automation-filed" in
# shadow-mode / volume logging (task 5.11 / 5.12) — configurable since the
# real label the FA Alert integration uses isn't fixed by this codebase.
JIRA_FA_ALERT_LABEL = os.environ.get("JIRA_FA_ALERT_LABEL", "fa-alert").lower()

# Task 5.11 — observe what would trigger without launching anything.
JIRA_POLLER_SHADOW_MODE = os.environ.get("JIRA_POLLER_SHADOW_MODE", "").strip().lower() in (
    "1",
    "true",
    "yes",
)

# Task 5.13 — fast manual brake: stops new/resumed launches without tearing
# down the tick itself (the tick keeps running and reporting health).
JIRA_POLLER_PAUSED = os.environ.get("JIRA_POLLER_PAUSED", "").strip().lower() in (
    "1",
    "true",
    "yes",
)

_POLLER_CRON_METADATA = {"kind": "jira_poller"}


def _langgraph_url() -> str:
    return os.environ.get("LANGGRAPH_URL") or os.environ.get(
        "LANGGRAPH_URL_PROD", "http://localhost:2024"
    )


def _trigger_jql() -> str:
    base = f'project = {JIRA_PROJECT_KEY} AND status = "{COLUMN_TRIGGER}"'
    return f"{base} AND ({JIRA_TRIGGER_JQL_FILTER})" if JIRA_TRIGGER_JQL_FILTER else base


def _parked_jql() -> str:
    columns = ", ".join(f'"{c}"' for c in _GATE_COLUMNS)
    return f"project = {JIRA_PROJECT_KEY} AND status in ({columns})"


async def _thread_metadata(client: Any, thread_id: str) -> dict[str, Any] | None:
    """Return thread metadata, or None if the thread does not exist yet."""
    try:
        thread = await client.threads.get(thread_id)
    except Exception:  # noqa: BLE001
        return None
    metadata = thread.get("metadata") if isinstance(thread, dict) else None
    return metadata if isinstance(metadata, dict) else {}


def _is_fa_alert_card(issue: dict[str, Any]) -> bool:
    labels = (issue.get("fields") or {}).get("labels") or []
    return any(JIRA_FA_ALERT_LABEL in str(label).lower() for label in labels)


def _column_name(issue: dict[str, Any]) -> str | None:
    return ((issue.get("fields") or {}).get("status") or {}).get("name")


async def _tick_step_a(client: Any) -> dict[str, Any]:
    """Launch a fresh thread for each unowned card in the trigger column."""
    result = await search_issues(_trigger_jql(), max_results=50, fields=["status", "labels"])
    if "error" in result:
        logger.warning("Jira poller: trigger search failed: %s", result["error"])
        return {"launched": 0, "skipped": 0, "error": result["error"]}

    launched = 0
    skipped = 0
    for issue in result.get("issues", []):
        issue_key = issue.get("key")
        if not issue_key:
            continue
        thread_id = generate_thread_id_from_jira_issue(issue_key)
        if await _thread_metadata(client, thread_id) is not None:
            # Already owns a thread — a duplicate tick must not double-trigger.
            skipped += 1
            continue

        human_filed = not _is_fa_alert_card(issue)
        if JIRA_POLLER_SHADOW_MODE:
            logger.info(
                "Jira poller [shadow]: would launch thread for %s (human_filed=%s)",
                issue_key,
                human_filed,
            )
            await console_events.push_log(f"[shadow] would trigger {issue_key}")
            continue
        if JIRA_POLLER_PAUSED:
            logger.info("Jira poller: paused, not launching thread for %s", issue_key)
            continue

        await client.threads.create(
            thread_id=thread_id,
            if_exists="do_nothing",
            metadata={
                "jira_issue_key": issue_key,
                "source": "jira",
                "jira_human_filed": human_filed,
            },
        )
        await dispatch_agent_run(
            thread_id,
            f"Jira issue {issue_key} entered {COLUMN_TRIGGER}. Begin PASSO 1: collect context "
            "(issue, description, acceptance criteria, comments).",
            {"source": "jira", "jira_issue_key": issue_key},
            source="jira",
            metadata={"jira_issue_key": issue_key, "workflow_phase": "triggered"},
        )
        launched += 1
        await console_events.push_run_event(issue_key, "launched", human_filed=human_filed)

    return {"launched": launched, "skipped": skipped}


async def _tick_step_b(client: Any) -> dict[str, Any]:
    """Re-trigger a parked thread whose card has moved to a different column."""
    result = await search_issues(_parked_jql(), max_results=50, fields=["status"])
    if "error" in result:
        logger.warning("Jira poller: parked search failed: %s", result["error"])
        return {"resumed": 0, "unchanged": 0, "error": result["error"]}

    resumed = 0
    unchanged = 0
    for issue in result.get("issues", []):
        issue_key = issue.get("key")
        if not issue_key:
            continue
        current_column = _column_name(issue)
        thread_id = generate_thread_id_from_jira_issue(issue_key)
        metadata = await _thread_metadata(client, thread_id)
        if not metadata or not metadata.get("jira_parked"):
            # Nothing parked here to resume — e.g. a card placed directly into
            # a gate column without ever going through the trigger column.
            continue

        parked_column = metadata.get("jira_parked_column")
        if current_column == parked_column:
            unchanged += 1
            continue

        if JIRA_POLLER_PAUSED:
            logger.info("Jira poller: paused, not resuming thread for %s", issue_key)
            continue

        comments_result = await get_comments(issue_key)
        recent = comments_result.get("comments", [])[-5:] if "comments" in comments_result else []
        comment_summary = "\n".join(str(c.get("body", "")) for c in recent) or "(no comments)"

        await dispatch_agent_run(
            thread_id,
            f"Jira issue {issue_key} moved from '{parked_column}' to '{current_column}'. "
            f"Resume the workflow from here. Recent comments:\n{comment_summary}",
            {"source": "jira", "jira_issue_key": issue_key, "jira_new_column": current_column},
            source="jira",
            metadata={
                "jira_issue_key": issue_key,
                "workflow_phase": "resumed",
                "jira_column": current_column,
            },
        )
        await client.threads.update(
            thread_id=thread_id,
            metadata={"jira_parked": False, "jira_parked_column": None},
        )
        resumed += 1
        await console_events.push_run_event(issue_key, "resumed", column=current_column)

    return {"resumed": resumed, "unchanged": unchanged}


async def tick() -> dict[str, Any]:
    """Run one poller tick: launch new threads, then resume parked ones."""
    client = get_client(url=_langgraph_url())
    step_a = await _tick_step_a(client)
    step_b = await _tick_step_b(client)
    await console_events.push_tick_event(step_a, step_b)
    return {"step_a": step_a, "step_b": step_b}


async def ensure_jira_poller_cron() -> str | None:
    """Idempotently register the recurring poller cron on the `scheduler` graph.

    LangGraph crons have minute granularity — `JIRA_POLL_INTERVAL_SECONDS`
    below 120 collapses to "every minute" (the default 60s maps exactly to
    that); values are rounded down to whole minutes above that.
    """
    client = get_client(url=_langgraph_url())
    try:
        existing = await client.crons.search(metadata=_POLLER_CRON_METADATA, limit=1)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to search for an existing Jira poller cron")
        return None
    if existing:
        first = existing[0]
        return first.get("cron_id") if isinstance(first, dict) else getattr(first, "cron_id", None)

    minutes = max(1, JIRA_POLL_INTERVAL_SECONDS // 60)
    schedule = "* * * * *" if minutes <= 1 else f"*/{minutes} * * * *"
    try:
        cron = await client.crons.create(
            "scheduler",
            schedule=schedule,
            input={"task": "jira_poll"},
            metadata=_POLLER_CRON_METADATA,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to create the Jira poller cron")
        return None
    return cron.get("cron_id") if isinstance(cron, dict) else getattr(cron, "cron_id", None)


async def ensure_jira_poller_cron_with_retry(
    *, attempts: int = 5, initial_delay_seconds: float = 2.0, max_delay_seconds: float = 30.0
) -> None:
    """Retry cron registration with backoff, for callers racing their own startup.

    `ensure_jira_poller_cron` calls back into this same server's API — during
    the ASGI lifespan `startup` phase the server isn't accepting connections
    yet, so a single attempt there always fails with a connection error. Fire
    this as a background task instead of awaiting registration directly in
    lifespan; the first attempt still needs a short delay since `startup`
    completing doesn't guarantee the listener is already up.
    """
    delay = initial_delay_seconds
    for attempt in range(1, attempts + 1):
        await asyncio.sleep(delay)
        cron_id = await ensure_jira_poller_cron()
        if cron_id is not None:
            logger.info("Jira poller cron registered (id=%s) after %d attempt(s)", cron_id, attempt)
            return
        delay = min(delay * 2, max_delay_seconds)
    logger.warning(
        "Giving up registering the Jira poller cron after %d attempts — the poller will not "
        "run until this succeeds (restart the server once it's reachable, or register the "
        "cron manually)",
        attempts,
    )
