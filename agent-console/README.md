# Jira Agent Console

A small read-only Flask page reporting whether the Jira poller is alive, the
card queue, active/parked/dead runs, and a live execution log. It holds no
workflow state — Jira remains the system of record for column state, and
LangSmith holds the traces. If this console is down, slow, or restarted,
no run is affected: every push from the agent/poller is fire-and-forget with
a short timeout and a swallowed failure (see `agent/utils/console_events.py`).

This is a standalone app, deliberately separate from the `agent/` package
(it isn't part of the LangGraph deployment, has its own dependency — Flask —
and its directory name has a hyphen so it can't be `import`ed as a Python
package anyway).

## Running it

```bash
pip install -r agent-console/requirements.txt
python agent-console/app.py
```

Defaults to `http://localhost:5050`. Override the port with `AGENT_CONSOLE_PORT`.

## Pointing the agent at it

Set `AGENT_CONSOLE_URL` on the LangGraph server (the same process that runs
`agent/jira_poller.py` and the main agent graph) to this console's base URL:

```bash
AGENT_CONSOLE_URL=http://localhost:5050
```

Unset (the default), the agent and poller skip every push silently — the
console is entirely optional infrastructure.

## What it shows

- **Overall status** — `working` (a run is executing), `waiting` (nothing
  executing, but at least one run is parked at a gate or a card is queued),
  `idle` (nothing to do), `degraded_poller` (no tick for more than two poll
  intervals), or `no_tick_ever`.
- **Poller health** is the primary signal — seconds since the last tick is
  always shown, since a stopped poller means every parked thread stays
  parked silently.
- **Queue** — cards sitting in the trigger column that don't have a thread
  yet, with how long each has been waiting.
- **Runs** — one row per issue with a known thread: `working`, `waiting`
  (with time-parked — the metric that exposes human bottlenecks in the
  approval flow), or `dead` (a run that ended — hit a runtime limit — without
  ever reaching a gate; see `agent/middleware/notify_jira_unparked.py`).
- **Execution log** — a rolling tail of tick/run/queue events.

## API

- `GET /api/state` — the full state used to render the page.
- `POST /api/events/<kind>` — ingest one event; `kind` is `tick`, `run`,
  `queue`, or `log`. This is what `agent/utils/console_events.py` calls.

## Known gaps

- No authentication. Treat this as an internal-network-only tool.
- The poller's pause switch (`JIRA_POLLER_PAUSED`) is an environment variable
  on the LangGraph server, not a button on this page — flipping it here would
  require the poller to poll this console back every tick, which isn't
  implemented.
