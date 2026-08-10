# Jira Agent Console

A small Flask page reporting whether the Jira poller is alive, the card queue,
active/parked/dead runs, and a live execution log — and the one place to change
the agent's operational settings without a redeploy (see below). It holds no
workflow state — Jira remains the system of record for column state, and
LangSmith holds the traces. If this console is down, slow, or restarted,
no run is affected: every push from the agent/poller is fire-and-forget with
a short timeout and a swallowed failure (see `agent/utils/console_events.py`),
and the poller reads its configuration from disk rather than from this app.

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
- `GET /api/config` — the operational configuration in effect, plus the
  choices available for each field.
- `PUT /api/config` — change one or more of them. Partial payloads are fine;
  an invalid value is rejected with `400` and nothing is applied.

## Operational configuration

Four settings can be changed here without restarting the LangGraph server:

| Field | Values | Applied by |
| --- | --- | --- |
| `shadow_mode` | `true` / `false` | the poller, on its next tick |
| `model` | any id in `available_models` | new Jira runs (team defaults) |
| `effort` | an effort the chosen model supports | new Jira runs (team defaults) |
| `polling_interval_minutes` | `1`, `5`, `10`, `30`, `60` | the poller cron |

The values are seeded from `JIRA_POLLER_SHADOW_MODE` /
`JIRA_POLL_INTERVAL_SECONDS` and the team default model, then persisted to
`agent-console/data/operational_config.json` — so a change survives a page
refresh and a restart of either process. The `.env` file is never rewritten;
once a value has been set here, the console's copy wins over the environment.

That file is also how the poller learns about shadow mode: it reads it on each
tick rather than being pushed to, so a console that is down never delays or
blocks a run. The other two settings do need the LangGraph server — the
polling interval replaces the poller's cron (deleting the old one first, so
there is never a second cron double-ticking), and the model/effort pair is
written to the team settings in the LangGraph Store. If either push fails, the
value is still saved and the response carries a `warnings` entry saying the
runtime has not taken it yet. The cron is replaced by deleting before creating,
so if the creation is the part that fails the poller is left with no cron at
all — the warning says so rather than claiming the old interval survived.
Restarting the LangGraph server is the recovery: on startup it compares the
installed cron against the saved interval and reinstalls it when they differ.

Every change is written to the execution log (`config: shadow mode enabled`,
`config: polling interval changed from 1m to 10m`, …).

## Known gaps

- No authentication, and `PUT /api/config` now changes how the agent behaves.
  Treat this as an internal-network-only tool.
- The poller's pause switch (`JIRA_POLLER_PAUSED`) is still an environment
  variable on the LangGraph server, not a field on this page.
