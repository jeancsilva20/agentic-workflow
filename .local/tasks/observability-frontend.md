# Observability Frontend – Console UI

## What & Why
The current Agent Console has a global Model `<select>` (line 229-232 in `index.html`) and Effort `<select>` (lines 233-236) that become obsolete once the Model Router backend is live. These controls must be removed and replaced with read-only observability panels: MODEL ROUTING table, ACTIVE AGENTS live view, MODEL USAGE, AGENT USAGE, and JIRA CARD USAGE (with timeline). All data comes from the new `/api/observability/*` endpoints added in the telemetry task.

The console is a single-file Jinja template (`agent-console/templates/index.html`) with no build step. Changes take effect after a workflow/server restart. Existing elements to preserve: Sensedia logo, Shadow Mode toggle, Jira Polling selector, Working/Waiting on Human/Queued/Dead queue view, Runs table, Execution Log.

## Done looks like
- The Model `<select>` and Effort `<select>` are removed from the configuration panel.
- The configuration section contains only: Shadow Mode toggle, Jira Polling interval selector, and a read-only **MODEL ROUTING** table.
- MODEL ROUTING table shows each agent role, its assigned model, and its effort (or "N/A" when the model doesn't support effort); data is fetched from `GET /api/config/routing` on page load and on a periodic refresh (e.g. every 60s — no per-render polling).
- An **ACTIVE AGENTS** panel is added below the queue cards, showing a live row per running execution with: Jira Card, Agent Role, Model, Effort, Complexity, elapsed duration, Status. Fetched from `GET /api/observability/live` on a short interval (≈5s), reusing the existing SSE/polling mechanism already in the console.
- A **USAGE OVERVIEW** section (collapsible or tab) shows today's aggregate: total LLM calls, tokens (Haiku/Sonnet/Opus breakdown), and cost (actual or estimated, labeled accordingly; never "$0.00" when data is missing). Fetched from `GET /api/observability/usage`.
- Clicking a card in the Queue or Runs table opens a **Card Detail** sidebar/section showing:
  - Status, Current Agent, Current Model, Effort, Complexity, Routing Reason.
  - TOTAL USAGE: LLM calls, input/output/total tokens, total cost.
  - BY MODEL: Haiku/Sonnet/Opus token + cost breakdown.
  - BY AGENT: each role's token + cost.
  - TIMELINE: chronological list of completed agent runs with time, role, model, tokens, cost, status.
  - Data fetched from `GET /api/observability/cards/<key>/usage` and `.../timeline`.
- When a run is escalated (Sonnet → Opus), the ACTIVE AGENTS row and Card Detail display an "ESCALATED" badge with the reason.
- Cost values labeled as "Estimated" when derived from the backend pricing table; shown as "Cost unavailable" when no data exists; never "$0.00" when unknown.
- No LangSmith credentials, API keys, or secrets are ever embedded in the HTML or JavaScript.
- The JS changes for removed model/effort controls are clean: no dead event listeners or fetch calls referencing those selects remain.
- The template continues to work as a single-file template; no build tooling is added.

## Out of scope
- Backend routing logic and API endpoints (Task 1 and Task 2).
- Any chart/graph library addition (tables and text badges only; no decorative charts).
- Mobile layout changes.
- Agent selection manual override UI.

## Steps
1. **Remove obsolete controls** — Delete the Model `<select>` (lines ~229-232), Effort `<select>` (lines ~233-236), and their associated JS (model populate/change handlers around lines 424-441, 523-535). Remove the `apply_model_effort` fetch call in `app.js`/inline JS. Verify no remaining code references `cfg-model` or `cfg-effort` element IDs.
2. **MODEL ROUTING table** — In the config section (where Model/Effort used to be), add a read-only HTML table with columns Agent | Model | Effort. Populate via a `fetchRoutingTable()` JS function that calls `GET /api/config/routing` and renders rows. Call on page load; re-fetch every 60 seconds.
3. **ACTIVE AGENTS panel** — Add a new collapsible section between the queue summary cards and the Runs table. Each row shows: card key, agent role, model · effort, complexity badge, elapsed time (updated client-side from `started_at`), status badge. Fetch from `GET /api/observability/live`; update on the same interval as the existing queue refresh (≈5s) to reuse the existing polling cycle without adding a new `setInterval`.
4. **Escalation badge** — When a row in ACTIVE AGENTS or Card Detail has `escalated: true`, render a distinct "ESCALATED ↑" badge with the `routing_reason` as a tooltip/subtitle.
5. **USAGE OVERVIEW section** — Add a collapsible "Usage Today" summary bar (or section at the bottom of the config panel). Show total tokens and cost for Haiku, Sonnet, Opus as three labeled columns. Fetch from `GET /api/observability/usage` on page load and refresh every 30s. Format costs as "$X.XXXX" when known, "Estimated $X.XXXX" when estimated, "—" when unavailable.
6. **Card Detail panel** — When the user clicks a card row in the Runs table (or Queue), open a `<details>` or slide-in panel showing the TOTAL USAGE, BY MODEL, BY AGENT, and TIMELINE subsections. Fetch data lazily (only when opened) from the observability endpoints. Render timeline as an ordered list: `HH:MM · Role · Model · tokens · cost · status`. Show a loading state while fetching.
7. **CSS polish** — Add minimal scoped styles for: routing table, active-agent rows, escalation badge (amber), complexity badges (LOW=gray, MEDIUM=blue, HIGH=orange, CRITICAL=red), cost labels. Do not introduce a CSS framework; extend existing inline styles.
8. **Clean up dead config JS** — Audit remaining JS for any references to model/effort config fields; remove handlers that called `PUT /api/config` with model/effort payloads. Ensure `PUT /api/config` now only sends `shadow_mode` and `polling_interval_minutes`.
9. **Tests** — Update `agent-console/tests/` DOM tests to: assert model and effort selects are absent, assert routing table is present, assert active-agents section exists, assert card-detail panel renders usage data. Follow the existing test pattern (load template, assert DOM nodes).

## Relevant files
- `agent-console/templates/index.html`
- `agent-console/app.py`
- `agent-console/config_store.py`
- `agent-console/tests/`
- `agent-console/static/`
