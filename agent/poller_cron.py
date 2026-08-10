"""Lifecycle of the LangGraph cron that drives the Jira poller tick.

Split out of ``agent.jira_poller`` because the console needs to *reconfigure*
the cron (when an operator changes the polling interval) without importing the
poller's Jira/dispatch machinery, and because "exactly one poller cron exists"
is a rule worth stating in one place: two live crons double every tick, which
means two searches, two launch attempts per card, and a doubled model bill.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from langgraph_sdk import get_client

logger = logging.getLogger(__name__)

POLLER_CRON_METADATA: dict[str, Any] = {"kind": "jira_poller"}
POLLER_CRON_GRAPH = "scheduler"
POLLER_CRON_INPUT: dict[str, Any] = {"task": "jira_poll"}

# Ceiling on how many poller crons one reconfiguration will clean up. There
# should only ever be one; a higher number means something already went wrong,
# and the limit keeps a runaway search bounded.
_MAX_POLLER_CRONS = 100

_client_cache: tuple[str, Any] | None = None


def _langgraph_url() -> str:
    return os.environ.get("LANGGRAPH_URL") or os.environ.get(
        "LANGGRAPH_URL_PROD", "http://localhost:2024"
    )


def cron_client() -> Any:
    """One LangGraph client per URL, reused across calls.

    ``get_client`` builds an HTTP client (and its connection pool) per call, so
    a fresh one on every reconfiguration would leak connections for what is a
    once-in-a-while admin action.
    """
    global _client_cache

    url = _langgraph_url()
    if _client_cache is None or _client_cache[0] != url:
        _client_cache = (url, get_client(url=url))
    return _client_cache[1]


def cron_schedule_for_minutes(minutes: int) -> str:
    """Cron expression for an "every N minutes" tick.

    LangGraph crons have minute granularity, so anything below a minute
    collapses to "every minute". Sixty minutes and above cannot be expressed in
    the minute field (`*/60` is out of range) and become an hourly schedule.
    """
    minutes = max(1, int(minutes))
    if minutes <= 1:
        return "* * * * *"
    if minutes < 60:
        return f"*/{minutes} * * * *"
    hours = max(1, minutes // 60)
    return "0 * * * *" if hours == 1 else f"0 */{hours} * * *"


class PollerCronStopped(RuntimeError):
    """The old cron was removed and its replacement could not be created.

    Distinct from any other reconfiguration failure because the consequence is
    different in kind: the poller is not ticking at all, rather than ticking at
    the previous interval. Callers must say so instead of reassuring the
    operator that the old schedule is still running.
    """


def cron_id_of(cron: Any) -> str | None:
    if isinstance(cron, dict):
        cron_id = cron.get("cron_id")
    else:
        cron_id = getattr(cron, "cron_id", None)
    return cron_id if isinstance(cron_id, str) else None


def cron_schedule_of(cron: Any) -> str | None:
    schedule = cron.get("schedule") if isinstance(cron, dict) else getattr(cron, "schedule", None)
    return schedule if isinstance(schedule, str) else None


async def list_poller_crons(client: Any | None = None) -> list[Any]:
    """Every cron tagged as the Jira poller's."""
    client = client or cron_client()
    return list(
        await client.crons.search(metadata=POLLER_CRON_METADATA, limit=_MAX_POLLER_CRONS) or []
    )


async def reconfigure_poller_cron(
    new_interval_minutes: int, client: Any | None = None
) -> str | None:
    """Replace every existing poller cron with exactly one at the new interval.

    Deletes first and creates afterwards: overlapping the two would leave the
    old and the new cron both firing, and a duplicated tick is precisely what
    the poller's idempotency is not there to absorb. The price of that ordering
    is a window where no cron exists, so a failed creation after a successful
    deletion raises :class:`PollerCronStopped` — polling has stopped, and
    saying "it kept the old interval" there would be a lie. Recovery is either
    another attempt or a server restart, which reconciles the cron against the
    configured interval.
    """
    client = client or cron_client()
    schedule = cron_schedule_for_minutes(new_interval_minutes)

    deleted = 0
    for cron in await list_poller_crons(client):
        cron_id = cron_id_of(cron)
        if cron_id is None:
            continue
        await client.crons.delete(cron_id)
        deleted += 1
        logger.info("Deleted Jira poller cron %s before reconfiguring", cron_id)

    try:
        created = await client.crons.create(
            POLLER_CRON_GRAPH,
            schedule=schedule,
            input=POLLER_CRON_INPUT,
            metadata=POLLER_CRON_METADATA,
        )
    except Exception as exc:
        if deleted:
            raise PollerCronStopped(
                f"the poller cron could not be created ({exc}) and the previous one was already "
                f"removed — no cron is installed and the poller is not ticking"
            ) from exc
        raise
    cron_id = cron_id_of(created)
    logger.info(
        "Jira poller cron reconfigured to %s (every %s minute(s), id=%s)",
        schedule,
        new_interval_minutes,
        cron_id,
    )
    return cron_id
