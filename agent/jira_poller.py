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

from . import operational_config
from .dispatch import dispatch_agent_run
from .poller_cron import (
    cron_id_of,
    cron_schedule_for_minutes,
    cron_schedule_of,
    list_poller_crons,
    reconfigure_poller_cron,
)
from .utils import console_events
from .utils.jira import generate_thread_id_from_jira_issue, get_comments, search_issues

logger = logging.getLogger(__name__)

JIRA_POLL_INTERVAL_SECONDS = int(os.environ.get("JIRA_POLL_INTERVAL_SECONDS") or "60")
JIRA_PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "SSAI")

# Jira status strings — these are the *API-level status names* sent to the
# Jira transitions endpoint and used in JQL queries (e.g. `status = "BACKLOG"`).
# They also happen to equal the visual column labels on the SSAI board, but
# the two concepts are distinct:
#
#   Jira status (API term)  → what jira_transition_issue / JQL receive
#   Column label (UI term)  → what a human sees on the board
#
# Configurable via env vars; defaults match the SSAI board audit documented
# in agent/jira_statuses.py. All 11 statuses are covered, not just the ones
# the poller queries directly — agent/prompt.py reads every one so the prompt
# never drifts from an operator's env-var override.
#
# Naming note: "COLUMN_*" is a historical name; these constants hold *status*
# strings (the API identifier), not visual column labels (the UI term). See
# agent/jira_statuses.py for the full mapping with the distinction made
# explicit.
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


def _gate_columns() -> tuple[str, ...]:
    """The three columns the agent parks a thread at, read at call time."""
    return (COLUMN_SPEC_REVIEW, COLUMN_CODE_REVIEW, COLUMN_MERGE)


def _post_gate_columns() -> tuple[str, ...]:
    """The columns a human moves a parked card *to*.

    Step B's query has to cover these as well as the gate columns themselves:
    once a human moves the card out of a gate, the card no longer matches a
    gate-only query, so a poller that watched only the gates would never see
    the decision it exists to detect.
    """
    return (
        COLUMN_SPEC_APPROVED,
        COLUMN_ADJUST_SPEC,
        COLUMN_CODE_APPROVED,
        COLUMN_ADJUST_CODE,
        COLUMN_MERGED,
    )


# Decision 11 mitigation (task 5.10): optional JQL scoping, off by default —
# the board and the column-driven model stay intact either way. This is a
# configuration change, not a redesign.
JIRA_TRIGGER_JQL_FILTER = os.environ.get("JIRA_TRIGGER_JQL_FILTER", "")

# Best-effort label used only to split "human-filed" vs "automation-filed" in
# shadow-mode / volume logging (task 5.11 / 5.12) — configurable since the
# real label the FA Alert integration uses isn't fixed by this codebase.
JIRA_FA_ALERT_LABEL = os.environ.get("JIRA_FA_ALERT_LABEL", "fa-alert").lower()

# Task 5.11 — observe what would trigger without launching anything. This is
# only the *default*: the agent console can override it at runtime, so read the
# effective value through `is_shadow_mode()` rather than this constant.
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

# Page size per Jira search request, and the ceiling on how many pages a single
# tick will walk. The cap only exists so a misconfigured project key or an
# unexpectedly huge board can't make one tick run forever; hitting it is logged
# as a warning because it means cards are going unpolled.
_SEARCH_PAGE_SIZE = 50
_MAX_SEARCH_PAGES = 20


def _langgraph_url() -> str:
    return os.environ.get("LANGGRAPH_URL") or os.environ.get(
        "LANGGRAPH_URL_PROD", "http://localhost:2024"
    )


def is_shadow_mode() -> bool:
    """Whether this tick may only observe, read at tick time, not import time.

    The agent console writes the operator's choice to a file both processes
    share (``agent.operational_config``), so flipping shadow mode takes effect
    on the next tick without restarting the LangGraph server. With no console
    override the environment default (`JIRA_POLLER_SHADOW_MODE`) still governs.
    """
    override = operational_config.shadow_mode_override()
    return JIRA_POLLER_SHADOW_MODE if override is None else override


def configured_poll_interval_minutes() -> int:
    """Effective tick interval in whole minutes: console override, else env."""
    override = operational_config.polling_interval_minutes_override()
    if override is not None:
        return override
    return max(1, JIRA_POLL_INTERVAL_SECONDS // 60)


def _trigger_jql() -> str:
    base = f'project = {JIRA_PROJECT_KEY} AND status = "{COLUMN_TRIGGER}"'
    return f"{base} AND ({JIRA_TRIGGER_JQL_FILTER})" if JIRA_TRIGGER_JQL_FILTER else base


def _parked_jql() -> str:
    """JQL for Step B: every column a parked thread can legitimately sit in.

    Both the gate columns (card still parked, nothing to do) and the post-gate
    columns a human moves it to (the decision this step exists to detect).
    Querying both in one JQL keeps the "did the column actually change?"
    comparison — and therefore idempotency — inside Step B itself.
    """
    seen: list[str] = []
    for column in (*_gate_columns(), *_post_gate_columns()):
        if column and column not in seen:
            seen.append(column)
    columns = ", ".join(f'"{c}"' for c in seen)
    return f"project = {JIRA_PROJECT_KEY} AND status in ({columns})"


async def _search_all_issues(jql: str, *, fields: list[str]) -> dict[str, Any]:
    """Collect every page of a JQL search, not just the first.

    A single page silently drops cards once the result set is larger than
    ``_SEARCH_PAGE_SIZE``, and Step B's query spans eight columns: parked
    cards sitting at a gate can fill the first page while the one card a
    human actually moved is on page two, so it would never be resumed. The
    number of pages is capped so a runaway query can't stall the tick.

    Returns ``{"issues": [...]}``, plus an ``error`` key if a page failed —
    the issues collected before the failure are still returned, since acting
    on the cards we did see beats dropping the whole tick.
    """
    issues: list[dict[str, Any]] = []
    next_page_token: str | None = None
    for _ in range(_MAX_SEARCH_PAGES):
        result = await search_issues(
            jql,
            next_page_token=next_page_token,
            max_results=_SEARCH_PAGE_SIZE,
            fields=fields,
        )
        if "error" in result:
            return {"issues": issues, "error": result["error"]}
        issues.extend(result.get("issues", []))
        next_page_token = result.get("next_page_token")
        if not next_page_token:
            break
    else:
        logger.warning(
            "Jira poller: stopped paginating %r after %d pages (%d issues) — cards beyond "
            "this point are not being polled this tick",
            jql,
            _MAX_SEARCH_PAGES,
            len(issues),
        )
    return {"issues": issues}


async def _thread_metadata(client: Any, thread_id: str) -> dict[str, Any] | None:
    """Return thread metadata, or None if the thread does not exist yet."""
    try:
        thread = await client.threads.get(thread_id)
    except Exception:  # noqa: BLE001
        return None
    metadata = thread.get("metadata") if isinstance(thread, dict) else None
    return metadata if isinstance(metadata, dict) else {}


_ACTIVE_RUN_STATUSES: frozenset[str] = frozenset({"running", "pending", "enqueued"})


async def _has_active_run(client: Any, thread_id: str) -> bool:
    """Return True if the thread has at least one run in an active state.

    Covers ``running``, ``pending`` and ``enqueued`` so that scheduler ticks
    drained after a server restart are treated as "active" and don't cause
    duplicate launches.  On any SDK error we err on the side of caution and
    return True (assume active) to avoid deleting a thread that is actually
    doing work.
    """
    try:
        runs = await client.runs.list(thread_id, limit=10)
    except Exception:  # noqa: BLE001
        return True
    return any(
        (r.get("status") if isinstance(r, dict) else None) in _ACTIVE_RUN_STATUSES
        for r in (runs or [])
    )


def _is_fa_alert_card(issue: dict[str, Any]) -> bool:
    labels = (issue.get("fields") or {}).get("labels") or []
    return any(JIRA_FA_ALERT_LABEL in str(label).lower() for label in labels)


def _column_name(issue: dict[str, Any]) -> str | None:
    return ((issue.get("fields") or {}).get("status") or {}).get("name")


async def _tick_step_a(client: Any) -> dict[str, Any]:
    """Launch a fresh thread for each unowned card in the trigger column."""
    result = await _search_all_issues(_trigger_jql(), fields=["status", "labels"])
    error = result.get("error")
    if error and not result["issues"]:
        logger.warning("Jira poller: trigger search failed: %s", error)
        return {"launched": 0, "skipped": 0, "shadow_candidates": [], "error": error}

    launched = 0
    skipped = 0
    shadow_candidates: list[str] = []
    for issue in result.get("issues", []):
        issue_key = issue.get("key")
        if not issue_key:
            continue
        thread_id = generate_thread_id_from_jira_issue(issue_key)
        metadata = await _thread_metadata(client, thread_id)
        if metadata is not None:
            # Thread exists — decide whether it is legitimately owned or stuck.
            if metadata.get("jira_parked") or await _has_active_run(client, thread_id):
                # Parked at a gate (waiting on a human) or a run is in flight
                # (including scheduler ticks drained after a server restart) —
                # this card is not ours to re-launch.
                skipped += 1
                continue
            # Interrupted run: thread exists but nothing is running and it is
            # not parked at a gate.  Delete the ghost thread so we can relaunch
            # cleanly, as if the card were brand-new.
            logger.warning(
                "Jira poller: thread %s for %s has no active run and is not parked "
                "— deleting ghost thread and relaunching",
                thread_id,
                issue_key,
            )
            try:
                await client.threads.delete(thread_id)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Jira poller: failed to delete ghost thread %s for %s — skipping",
                    thread_id,
                    issue_key,
                )
                skipped += 1
                continue
            # Fall through to the normal launch path below.

        human_filed = not _is_fa_alert_card(issue)
        if is_shadow_mode():
            shadow_candidates.append(issue_key)
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
        launch_configurable = {
            "source": "jira",
            "jira_issue_key": issue_key,
            "jira_new_column": COLUMN_TRIGGER,
            "jira_column": COLUMN_TRIGGER,
        }
        launch_metadata = {"jira_issue_key": issue_key, "workflow_phase": "triggered"}
        await dispatch_agent_run(
            thread_id,
            f"Jira issue {issue_key} entered {COLUMN_TRIGGER}. Begin PASSO 1: collect context "
            "(issue, description, acceptance criteria, comments).",
            launch_configurable,
            source="jira",
            metadata=launch_metadata,
        )
        launched += 1
        await console_events.push_run_event(issue_key, "launched", human_filed=human_filed)

    summary = {
        "launched": launched,
        "skipped": skipped,
        "shadow_candidates": shadow_candidates,
    }
    if error:
        # Partial page failure: report it, but keep the work already done.
        logger.warning("Jira poller: trigger search failed mid-pagination: %s", error)
        summary["error"] = error
    return summary


async def _tick_step_b(client: Any) -> dict[str, Any]:
    """Re-trigger a parked thread whose card has moved to a different column."""
    result = await _search_all_issues(_parked_jql(), fields=["status"])
    error = result.get("error")
    if error and not result["issues"]:
        logger.warning("Jira poller: parked search failed: %s", error)
        return {"resumed": 0, "unchanged": 0, "error": error}

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

        if is_shadow_mode():
            # Shadow mode's guarantee is "no real action" — that has to cover
            # resumes too, not just fresh launches.
            logger.info(
                "Jira poller [shadow]: would resume thread for %s: %s -> %s",
                issue_key,
                parked_column,
                current_column,
            )
            await console_events.push_log(
                f"[shadow] would resume thread for {issue_key}: {parked_column} → {current_column}"
            )
            continue

        if JIRA_POLLER_PAUSED:
            logger.info("Jira poller: paused, not resuming thread for %s", issue_key)
            continue

        comments_result = await get_comments(issue_key)
        recent = comments_result.get("comments", [])[-5:] if "comments" in comments_result else []
        comment_summary = "\n".join(str(c.get("body", "")) for c in recent) or "(no comments)"

        resume_configurable = {
            "source": "jira",
            "jira_issue_key": issue_key,
            "jira_new_column": current_column,
        }
        resume_metadata = {
            "jira_issue_key": issue_key,
            "workflow_phase": "resumed",
            "jira_column": current_column,
        }
        await dispatch_agent_run(
            thread_id,
            f"Jira issue {issue_key} moved from '{parked_column}' to '{current_column}'. "
            f"Resume the workflow from here. Recent comments:\n{comment_summary}",
            resume_configurable,
            source="jira",
            metadata=resume_metadata,
        )
        await client.threads.update(
            thread_id=thread_id,
            metadata={"jira_parked": False, "jira_parked_column": None},
        )
        resumed += 1
        await console_events.push_run_event(issue_key, "resumed", column=current_column)

    summary = {"resumed": resumed, "unchanged": unchanged}
    if error:
        # Partial page failure: report it, but keep the work already done.
        logger.warning("Jira poller: parked search failed mid-pagination: %s", error)
        summary["error"] = error
    return summary


async def tick() -> dict[str, Any]:
    """Run one poller tick: launch new threads, then resume parked ones."""
    client = get_client(url=_langgraph_url())
    step_a = await _tick_step_a(client)
    step_b = await _tick_step_b(client)
    await console_events.push_tick_event(step_a, step_b)
    return {"step_a": step_a, "step_b": step_b}


async def ensure_jira_poller_cron() -> str | None:
    """Register the recurring poller cron on the `scheduler` graph, reconciling.

    LangGraph crons have minute granularity — `JIRA_POLL_INTERVAL_SECONDS`
    below 120 collapses to "every minute" (the default 60s maps exactly to
    that); values are rounded down to whole minutes above that. An interval the
    operator picked in the console outranks the env var, so a restart keeps the
    interval they chose instead of silently reverting to the deployment default.

    "A cron exists" is therefore not good enough to return early: the console
    can save an interval whose push to this server failed, and a stale cron
    left at the old schedule would make that saved value a lie forever. So the
    existing cron is compared against the configured one and replaced when it
    disagrees — which also makes a restart the documented recovery path for a
    failed reconfiguration.
    """
    client = get_client(url=_langgraph_url())
    schedule = cron_schedule_for_minutes(configured_poll_interval_minutes())
    try:
        existing = await list_poller_crons(client)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to search for an existing Jira poller cron")
        return None

    if len(existing) == 1 and cron_schedule_of(existing[0]) == schedule:
        return cron_id_of(existing[0])

    if existing:
        logger.info(
            "Reconciling %d Jira poller cron(s) to the configured schedule %s",
            len(existing),
            schedule,
        )

    try:
        return await reconfigure_poller_cron(configured_poll_interval_minutes(), client=client)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to install the Jira poller cron at schedule %s", schedule)
        return None


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
