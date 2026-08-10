# Sensedia Agentic Workflow — Agent Console

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

- **Header** — the official Sensedia logo, the application name, and the mode
  the agent is actually in: an amber `SHADOW MODE / Monitoring only` badge or a
  green `LIVE EXECUTION / Agents can execute` one, driven by `GET /api/config`
  and never by anything the page keeps to itself. The supplied SVG is stored at
  `static/sensedia-logo.svg` (see `static/README.md`); a neutral fallback slot
  remains available if the asset cannot be loaded.
- **Agent Configuration** — the operational settings below as a toggle and a
  dropdown, filled from the API. A change disables the controls, shows
  `Saving…`, and either confirms or reverts: the panel only ever shows a value
  the backend accepted (see "Operational configuration"). Model and effort are
  not here: the router picks them per agent role (see "Model routing").
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
  `queue`, `log`, `agent_start` or `agent_finish`. This is what
  `agent/utils/console_events.py` calls.
- `GET /api/config` — the operational configuration in effect, plus the
  choices available for each field.
- `PUT /api/config` — change one or more of them. Partial payloads are fine;
  an invalid value is rejected with `400` and nothing is applied.
- `GET /api/config/routing` — the model router's table: which model and effort
  each agent role runs on. Read-only; there is no `PUT` counterpart.
- `GET /api/observability/live` — the agent runs executing right now.
- `GET /api/observability/routing` — the same table as `/api/config/routing`.
- `GET /api/observability/usage` — today's tokens and cost, by model and role.
- `GET /api/observability/cards/<key>/usage` — one card's total, every run of it.
- `GET /api/observability/cards/<key>/timeline` — that card's runs in order.

## Operational configuration

Two settings can be changed here without restarting the LangGraph server:

| Field | Values | Applied by |
| --- | --- | --- |
| `shadow_mode` | `true` / `false` | the poller, on its next tick |
| `polling_interval_minutes` | `1`, `5`, `10`, `30`, `60` | the poller cron |

The values are seeded from `JIRA_POLLER_SHADOW_MODE` /
`JIRA_POLL_INTERVAL_SECONDS`, then persisted to
`agent-console/data/operational_config.json` — so a change survives a page
refresh and a restart of either process. The `.env` file is never rewritten;
once a value has been set here, the console's copy wins over the environment.

That file is also how the poller learns about shadow mode: it reads it on each
tick rather than being pushed to, so a console that is down never delays or
blocks a run. The polling interval does need the LangGraph server — it replaces
the poller's cron (deleting the old one first, so there is never a second cron
double-ticking). If that push fails, the
value is still saved and the response carries a `warnings` entry saying the
runtime has not taken it yet. The cron is replaced by deleting before creating,
so if the creation is the part that fails the poller is left with no cron at
all — the warning says so rather than claiming the old interval survived.
Restarting the LangGraph server is the recovery: on startup it compares the
installed cron against the saved interval and reinstalls it when they differ.

Every change is written to the execution log (`config: shadow mode enabled`,
`config: polling interval changed from 1m to 10m`, …).

## Model routing

Which model each step of the workflow runs on is not an operator setting. The
router in `agent/routing` decides it from the agent role — triage and archiving
on Haiku, spec authoring on Sonnet, spec and code review on Opus — escalating
the coding roles to Opus after two failed attempts or on a risky change (auth,
migration, security, concurrency). Which role a run is is decided from the Jira
column the poller resumed it at, so a card in `Ajustar Spec` and a card in
`Aprovado Code` do not run on the same model.

Every other LLM entrypoint is routed the same way — PR review chat and the
review-style analyzer included — so no request field, profile or team default
picks a model anywhere.

`GET /api/config/routing` reports the whole table so the console can show what a
role will run on and why. Each row also carries `active` and `selected_by`: a few
roles in the enum are phases that happen inside another role's run and nothing
selects them yet, and the table says so instead of implying they are live.

## Observability

Every agent run is tagged, on dispatch, with the routing decision behind it —
Jira card, thread, agent role, workflow stage, model, effort, complexity tier
and the reason the router picked that pair. The tag rides along in LangSmith
trace metadata, so a trace can be read back later without this console being
involved at all.

Tokens and cost are collected **after** a run finishes, from the completed
LangSmith run, never streamed per token. The trace is found by the correlation
id the dispatch stamped on it, not by the LangGraph run id — those are two
different systems' identifiers, and the metadata is what bridges them. LangSmith's own `total_cost` is used
when it has one; otherwise the fallback table in `agent/routing/pricing.py`
estimates it and the entry is marked `estimated`. A model neither of them can
price reports `cost: null` — never `0.0`, which would read as a free run — and
the card's total says how many of its runs are missing a cost.

The aggregation unit is the **card**, not the run or the thread: one card is
worked across several human-in-the-loop runs on different threads, and the
totals sum all of them.

The console keeps its own copy of that data, in the same store classes the
agent uses, filled from two pushed events (`agent_start`, `agent_finish`). It
never calls LangSmith — it holds no LangSmith credential to call it with — so a
page refresh costs nothing outside this process, and no endpoint can leak one.
The cost is that a console restart empties the window and it refills from
subsequent events; LangSmith remains the durable record either way, and the
window is bounded (the most recent runs) so neither process grows without end.

Each event also writes to the execution log, one line per run rather than per
token: `routing: SSAI-88 spec_reviewer → Opus/high`,
`usage: coding_agent 18,420 tokens`, `cost: SSAI-88 updated to $1.2340`.

## Tests

```bash
pytest agent-console/tests            # backend + server-rendered page
npm run test:frontend                 # the page's behaviour, in jsdom
```

The jsdom suite loads `templates/index.html` itself and stubs `fetch`, so the
loading/error/rollback assertions exercise the code the browser runs. `pytest`
shells out to it too (`tests/test_frontend.py`) and skips that one test when
Node or the `jsdom` dev dependency is missing.

## Known gaps

- No authentication, and `PUT /api/config` now changes how the agent behaves.
  Treat this as an internal-network-only tool.
- The poller's pause switch (`JIRA_POLLER_PAUSED`) is still an environment
  variable on the LangGraph server, not a field on this page.
