## 0. Jira Board and Connectivity Spike (blocking — do this first)

- [x] 0.1 Create the Jira board with the 11 columns defined in design.md — board created with 11 statuses; 3 are Jira defaults (`BACKLOG` / `In Progress` / `Done`) instead of the design's proposed names (`Pronto para Desenvolvimento` / `Em Desenvolvimento` / `Concluído`), the other 8 match exactly. Artifacts were aligned to the board, not the reverse. `BACKLOG` is the trigger column — decided (Decision 11), not open: entering the backlog is the request, no human gate, risks accepted and tracked as follow-up tasks 5.10–5.13
- [x] 0.2 Configure the workflow with global transitions — "Allow all statuses to transition to this one" on every status
- [x] 0.3 Generate a Jira API token and set `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` in a gitignored env file
- [x] 0.4 Spike: authenticate and call `GET /rest/api/3/issue/{key}` against a real card
- [x] 0.5 Spike: call `GET /rest/api/3/issue/{key}/transitions` and confirm every column is reachable from every other column
- [x] 0.6 Spike: call `POST /rest/api/3/issue/{key}/transitions` and confirm the card moves — this operation has never been exercised and all three approval gates depend on it
- [x] 0.7 Spike: post an ADF comment containing curly quotes, em-dashes and accented Portuguese; confirm no `INVALID_INPUT` / HTTP 400

## 1. Jira REST Client

- [x] 1.1 Create `agent/utils/jira.py` following the `agent/utils/linear.py` pattern — async `httpx` client, Basic auth (`JIRA_EMAIL`:`JIRA_API_TOKEN`), base URL from `JIRA_BASE_URL`
- [x] 1.2 Implement `get_issue`, `search_issues` (JQL), `get_comments`, `add_comment`, `get_transitions`, `transition_issue` against the endpoint contract in `sensedia-ai-gateway-agent-demo-*/docs/swagger_jira_custom.yaml`
- [x] 1.3 Implement `transition_to_column(key, column_name)` — resolve the column name to a transition id via `get_transitions`, then POST. Raise a descriptive error listing the available targets when the name does not resolve
- [x] 1.4 Implement thread-id derivation for Jira (deterministic ID from issue key)
- [x] 1.5 Add Jira-specific error handling: 429 with exponential backoff, 401 auth failure, 404 not found, 400 invalid transition
- [x] 1.6 **Corrected during implementation:** this said "omit Jira tools, same as Corridor/Datadog" — but that's the *other* degradation pattern in this codebase (conditional exclusion from the tool list via `DynamicToolMiddleware`), and it conflicts with §3.6/3.7 which register Jira tools unconditionally in `static_tools`, matching Linear. Went with the Linear pattern instead: tools always registered, `_request()` returns `{"error": "Jira credentials are not configured..."}` when unset, and `jira_configured()` is exported for the system prompt (§8.1) to flag the limitation

## 2. Markdown to ADF Conversion

- [x] 2.1 Create `agent/utils/adf.py` — convert Markdown (headings, paragraphs, lists, code blocks, links, inline code) to Atlassian Document Format
- [x] 2.2 Port the character normalisation already proven in the Sensedia AI Gateway project (`_pre_validate_add_comment`, `services/agent_service.py`): curly quotes, en/em dashes, non-breaking spaces
- [x] 2.3 Truncate bodies exceeding the Jira comment size limit, appending a pointer to the PR or the spec file
- [x] 2.4 Unit-test with real agent output: Portuguese text with accents, fenced code blocks, nested lists — `tests/utils/test_adf.py`, `tests/utils/test_jira.py` (24 tests)

## 3. Jira Agent Tools

- [x] 3.1 Create `agent/tools/jira_get_issue.py` — retrieve issue by key (thin wrapper, `linear_get_issue.py` pattern)
- [x] 3.2 Create `agent/tools/jira_search_issues.py` — JQL search
- [x] 3.3 Create `agent/tools/jira_get_comments.py` — retrieve issue comments
- [x] 3.4 Create `agent/tools/jira_add_comment.py` — accept Markdown, convert via `adf.py`, post
- [x] 3.5 Create `agent/tools/jira_transition_issue.py` — move issue to a target column **by name**
- [x] 3.6 Register all Jira tools in `agent/tools/__init__.py` (lazy-loading pattern)
- [x] 3.7 Add Jira tools to `static_tools` in `agent/server.py` — tests: `tests/tools/test_jira_tools.py` (6 tests)

## 4. OpenSpec as Skills + Mechanical Tools

Explore and propose are **procedures the model follows**, not file writes — they go in
`agent/skills/`, the mechanism Open SWE already serves via the `/skills/` route
(`skill_sources` in `agent/server.py`). Only genuinely mechanical operations stay tools.

- [x] 4.1 Port `.claude/skills/openspec-explore/SKILL.md` to `agent/skills/openspec-explore/`, dropping the `Requires openspec CLI` dependency — the model writes the artifacts with the existing `write_file` tool
- [x] 4.2 Port `.claude/skills/openspec-propose/SKILL.md` to `agent/skills/openspec-propose/`, same treatment, including the artifact templates the CLI used to generate — templates and per-artifact instructions inlined from the installed `@fission-ai/openspec` package's `spec-driven` schema rather than fetched via CLI
- [x] 4.3 Add the grounding rules from `prompts/spec-grounding.md` to the propose skill: card + code as sources, alert recommendations as hypotheses, product decisions escalated to the gate
- [x] 4.4 Register both skills in `skill_sources` in `agent/server.py` — added a new always-on `STATIC_SKILLS_ROUTE` (`/openspec-skills/`) backed by `FilesystemBackend` over the packaged `agent/skills/` directory, composed alongside the existing per-user `/skills/` route; required adding `agent/skills/__init__.py` so `importlib.resources.files()` resolves a real path instead of a `MultiplexedPath` (namespace package)
- [x] 4.5 Create `agent/tools/openspec_validate.py` — mechanical structural check: required files present, every requirement has at least one scenario, headers well-formed
- [x] 4.6 Create `agent/tools/openspec_archive.py` — move artifacts to `openspec/changes/archive/` and update the index — deliberately conservative: only merges a capability into `openspec/specs/` when it's genuinely new; an already-existing capability is left alone and reported under `needs_manual_merge` rather than risking an automatic MODIFIED/REMOVED merge
- [x] 4.7 Create `agent/tools/openspec_status.py` — read artifact status for a change
- [x] 4.8 Register the three tools in `agent/tools/__init__.py` and add them to `static_tools` in `agent/server.py` — tests: `tests/tools/test_openspec_tools.py` (10 tests)

## 5. Scheduler Poller and Non-Blocking Gates

- [x] 5.1 Create `agent/jira_poller.py` with a `tick()` coroutine, wired into the existing `scheduler` graph alongside `launch_scheduled_agent_run` — added a `task == "jira_poll"` branch in `agent/scheduler.py`'s `_launch`
- [x] 5.2 Register a 60s cron for the poller (`JIRA_POLL_INTERVAL_SECONDS`, default 60) — `ensure_jira_poller_cron()`, idempotent via `crons.search` by metadata. Caveat: LangGraph crons have minute granularity, so this is really "every N minutes," not true sub-minute precision. **Bug found and fixed by actually running `langgraph dev`:** the first cut awaited registration directly in `agent/api/app.py`'s lifespan `startup` hook — but registration calls back into this same server's own API, which isn't accepting connections yet during `startup`, so it failed with a connection error on every boot (confirmed live: `httpx.ConnectError: All connection attempts failed`). Fixed with `ensure_jira_poller_cron_with_retry()` (exponential backoff, 5 attempts), fired as a background `asyncio.create_task` instead of awaited inline — confirmed live afterward: registered successfully after 1 attempt once the server was actually listening. Tests: `tests/agent/test_jira_poller_cron_retry.py` (4 tests)
- [x] 5.3 Tick step A — JQL for cards in the trigger column; for each, derive the thread id from the issue key and launch a fresh agent thread if none exists
- [x] 5.4 Tick step B — JQL for cards belonging to parked threads; re-trigger the thread when its column has changed, passing the new column and any new comments as the resume prompt
- [x] 5.5 Make the tick idempotent — a card already owned by a live thread must never spawn a second one, and a duplicate tick must not double-trigger
- [x] 5.6 Implement column name configuration via environment variables with defaults — plus `JIRA_PROJECT_KEY` (default `SSAI`), for the same reason. **Corrected during section 8 work:** the first cut only covered the 5 columns the poller itself queries by name (trigger + 3 gates + Done); the other 6 (`In Progress`, `Spec Aprovada`, `Ajustar Spec`, `Code Review Aprovado`, `Ajustar Code`, `Mergeado`) were still hardcoded Portuguese strings inside `agent/prompt.py`, so an env-var override would have silently diverged from what the agent was told. All 11 are now env-configurable constants in `agent/jira_poller.py`, and `agent/prompt.py` reads every one of them at render time (not a snapshotted import) — see `tests/agent/test_jira_prompt.py::test_prompt_reflects_column_name_env_overrides`
- [x] 5.7 Create `agent/tools/jira_park_at_gate.py` — post a Jira comment, transition the card, mark the thread parked in metadata, and end the run. The agent commits before parking so the branch survives sandbox loss — "end the run" is a returned `end_run: True` signal for the model to respect, not a structural stop (no such mechanism exists to force from inside a tool call)
- [x] 5.8 Handle `SandboxUnreachableError` on resume: report to Jira, do not silently restart from scratch — found `post_sandbox_unreachable_notification` already had this exact Slack → Linear → GitHub fallback pattern with no Jira branch; added one following the same shape
- [x] 5.9 Push tick, queue, run and log events to the console (fire-and-forget, short timeout, failures swallowed) — `agent/utils/console_events.py`
- [x] 5.10 Implement the Decision 11 mitigation: optional JQL scoping in the tick (issue type, label, or assignee), off by default, toggled via `JIRA_TRIGGER_JQL_FILTER` — code exists but stays unused until someone flips it
- [x] 5.11 Ship the poller in shadow mode first: log which BACKLOG cards would trigger a run (and whether human- or FA-Alert-filed) without launching a thread, for an agreed observation window on the real SSAI board, before flipping it live — `JIRA_POLLER_SHADOW_MODE`; the FA-Alert label name is a guess (`JIRA_FA_ALERT_LABEL`, default `fa-alert`), confirm the real label before relying on the split
- [x] 5.12 Instrument trigger volume (cards picked up per tick/day, human- vs FA-Alert-filed split) in the console and LangSmith traces — turns "does this incomodar" into a number instead of a feeling, and gives 5.10 a threshold to react to — `human_filed` is pushed on every `launched` console event; a LangSmith-side rollup is not implemented (metrics land in section 10)
- [x] 5.13 Add a poller pause switch (env var or console action) that stops new thread launches without tearing down the scheduler — the fast manual brake for when the accepted risk in Decision 11 actually fires — `JIRA_POLLER_PAUSED` env var; a console *action* to flip it (vs. just the env var) is left to 5b
- [x] 5.14 Create a Jira-aware equivalent of `notify_step_limit` — an `after_agent` hook that checks whether the run ended without reaching `waiting`/done (same "Model call limits exceeded" marker check `notify_step_limit.py` uses, plus the `timeout_wrapup` case) and, if so, posts a Jira comment naming the limit that was hit and pushes a `dead` event to the console. `notify_step_limit` itself only fires when `slack_thread` is present in `configurable`, which a Jira-triggered thread never has — this closes the resulting silent-failure gap without touching the Slack path. The `timeout_wrapup` case is covered by a heuristic (ended on plain text without ever calling `jira_park_at_gate` or transitioning to Done), not a hard marker like the call-limit case — tests: `tests/agent/test_jira_poller.py`, `tests/agent/test_scheduler.py`, `tests/tools/test_jira_park_at_gate.py`, `tests/middleware/test_notify_jira_unparked.py`, `tests/middleware/test_sandbox_circuit_breaker_jira.py`, `tests/utils/test_console_events.py` (34 tests)

## 5b. Agent Console (Flask)

- [x] 5b.1 `agent-console/store.py` — in-memory state: poller health, queue, runs, log ring buffer
- [x] 5b.2 `agent-console/app.py` — `GET /api/state` and `POST /api/events/<kind>` for `tick`, `queue`, `run`, `log`
- [x] 5b.3 `agent-console/templates/index.html` — status header, four metrics, queue and active runs, execution log; 2s polling
- [x] 5b.4 Surface poller health as the primary signal: display seconds since last tick and degrade the status when it exceeds two intervals
- [x] 5b.5 Show time-parked per waiting run — the metric that exposes human bottlenecks in the workflow
- [x] 5b.6 `agent/utils/console_events.py` — the push client used by the poller and the agent
- [x] 5b.7 Document how to run it and how to point the agent at it (`AGENT_CONSOLE_URL`) — `agent-console/README.md`
- [x] 5b.8 Add the `dead` status from proposal.md to the console state machine, alongside `working`/`waiting`/`idle` — a run reported by 5.14 as ended-without-parking SHALL show `dead` instead of silently dropping out of the active-runs list — tests: `agent-console/tests/test_store.py`, `agent-console/tests/test_app.py` (15 tests). **Note:** `agent-console/` is a standalone Flask app outside the main `agent` package (per design.md's file map) — its tests live in `agent-console/tests/`, not `tests/`, and need `pip install -r agent-console/requirements.txt` in whatever environment runs them; they are not collected by the main `uv run pytest`. The poller pause switch (5.13) has no console-side action — see `agent-console/README.md`'s "Known gaps"

## 6. Auto-Review Loop (Prompt-Driven)

**Placement note:** 6.1-6.4 said `agent/prompt.py`, 8.1-8.5 said `agent/resources/default_prompt.md`. Put all of it in `agent/prompt.py` as new section constants (`JIRA_WORKFLOW_SECTION`, `JIRA_SPEC_GROUNDING_SECTION`, `JIRA_AUTO_REVIEW_SECTION`, `JIRA_REVIEWER_INTEGRATION_SECTION`, `JIRA_CANONICAL_DOCS_SECTION`), spliced into `SYSTEM_PROMPT_TEMPLATE` and gated on a new `jira_issue_key` param — `default_prompt.md` is small, user-editable, HTML-escaped custom-instruction text; this much structured content (a worked example, a branch-naming rule, five sub-sections) doesn't belong there, and `prompt.py` already has this exact pattern for Corridor (`corridor_prompt_section`, gated on a bool). Sections 6 and 8 are implemented together below.

- [x] 6.1 Add spec self-review instructions to `agent/prompt.py` (checklist: acceptance criteria, scenarios, constraints, task atomicity) — `JIRA_AUTO_REVIEW_SECTION`
- [x] 6.2 Add code self-review instructions to `agent/prompt.py` (checklist: spec fidelity, test coverage, lint, regressions, security) — `JIRA_AUTO_REVIEW_SECTION`
- [x] 6.3 Add the 3-cycle target to the prompt as **guidance**, not enforcement — do not build a counter (design.md Decision 5). Word it as "after about three passes without resolving something, hand it to a human"
- [x] 6.3b Log each self-review cycle to the console so iteration depth is observable after the fact — needed an actual callable, since the agent has no way to reach `console_events.push_log` otherwise: new tool `agent/tools/log_review_cycle.py`, also bumps a `jira_review_cycles_<phase>` thread-metadata counter for 10.1
- [x] 6.4 On cycle exhaustion, post a Jira comment listing the unresolved gaps and park in the normal gate column (`Em Revisão de Spec` / `Em Code Review`) — no dedicated fallback columns

## 7. Reviewer Graph Integration

- [x] 7.1 Create `agent/tools/request_self_review.py` — trigger existing reviewer graph on current diff — thin wrapper over `request_pr_review` (which already reads `source` generically from `configurable`, so Jira-triggered runs work with zero changes to the underlying reviewer pipeline); requires a real PR to exist first (see 7.2 note)
- [x] 7.2 Wire reviewer findings into the code review approval flow — **found a design.md ordering issue**: PASSO 7 (reviewer graph) is listed before PASSO 8 (push + create PR), but the reviewer graph has no path for reviewing a diff that isn't already a real PR (`agent/webhooks/github.py:trigger_pr_review_from_ref` needs `base_sha`/`head_sha` from PR metadata). Documented in `JIRA_REVIEWER_INTEGRATION_SECTION`: the agent opens at least a draft PR before calling `request_self_review`; PASSO 8 finalizes that same PR rather than creating a second one
- [x] 7.3 Handle CHANGES_REQUIRED status (return to implementation with findings) — prompt instruction only (no new code): re-run code self-review and `request_self_review` again, do not park at a gate for CHANGES_REQUIRED

## 8. System Prompt Updates

- [x] 8.1 Add Jira workflow section to `agent/resources/default_prompt.md` — see placement note under section 6: implemented in `agent/prompt.py` as `JIRA_WORKFLOW_SECTION` instead
- [x] 8.2 Install `prompts/spec-grounding.md` into `agent/resources/default_prompt.md` — card + code as the two sources, alert recommendations as hypotheses, read the neighbours, escalate product decisions, and the SSAI-88 worked example — `JIRA_SPEC_GROUNDING_SECTION` in `agent/prompt.py`
- [x] 8.3 Add column-driven approval flow instructions — `JIRA_WORKFLOW_SECTION`
- [x] 8.4 Add branch naming convention (`feat/spec-JIRA-XXXX-descricao-curta`) — the slug MUST pass `git check-ref-format --branch`; sanitize the Jira summary (no `:`, `~`, `^`, `?`, `*`, `[`, `\`, spaces) before building the name — `JIRA_WORKFLOW_SECTION`, PASSO 2; explicitly overrides `REPO_SETUP_SECTION`'s generic `open-swe/<slug>` convention for Jira-triggered runs
- [x] 8.5 Add auto-review loop instructions with cycle limits — `JIRA_AUTO_REVIEW_SECTION` — tests: `tests/agent/test_jira_prompt.py` (6 tests) verify gating (absent without `jira_issue_key`, present with it) and key content (branch naming, tool names)

## 9. Canonical Docs Update

- [x] 9.1 Create `agent/tools/update_canonical_docs.py` — identify and update impacted docs — **corrected the same way task 1.6 and Decision 4 already were**: "identify impacted docs" is a reasoning procedure (read the diff, find docs describing the changed behavior), not something a Python tool can do — Decision 4 already established this exact distinction for `openspec_propose`. No new tool; `JIRA_CANONICAL_DOCS_SECTION` in `agent/prompt.py` instructs the agent to use `read_file`/`grep`/`search_repo_code` (reasoning) plus the existing `open_pull_request` tool (mechanical) it already has
- [x] 9.2 Implement separate PR creation for documentation changes — reuses `open_pull_request` (already exists, generic); no new code needed
- [x] 9.3 Add docs update step to system prompt (PASSO 10) — `JIRA_CANONICAL_DOCS_SECTION`
- [x] 9.4 Handle docs update failures gracefully (report to Jira, don't block completion) — `JIRA_CANONICAL_DOCS_SECTION`

## 10. LangSmith Metrics

**Scope note:** implemented the metadata-tagging pieces that compose with what sections 5-7 already built (testable via thread-metadata assertions). Did not build a LangSmith-side rollup/dashboard — that needs a live LangSmith account to verify against, which this environment doesn't have; "final status" and "total time" specifically are not recorded anywhere yet.

- [~] 10.1 Add workflow metrics recording to `agent/server.py` (total time, review cycles, findings count, final status) — review cycles: covered via `log_review_cycle`'s `jira_review_cycles_<phase>` thread-metadata counter. Total time, findings count, and final status: **not implemented** — no run-start timestamp is captured anywhere, and nothing reads the reviewer's findings count back out. This task is genuinely incomplete, not just reworded
- [x] 10.2 Tag runs with Jira issue key and workflow phase — `agent/jira_poller.py`'s two `dispatch_agent_run` calls now pass `metadata={"jira_issue_key": ..., "workflow_phase": "triggered"|"resumed", ...}`
- [x] 10.3 Record approval gate timestamps (time spent waiting at each gate) — `jira_park_at_gate` now appends `{column, parked_at}` to a `jira_gate_history` list in thread metadata on every gate visit instead of overwriting a single timestamp. Records *entry* time per gate; does not compute a duration (nothing closes out "how long did it wait" — the poller has the resume timestamp when it detects the column changed, but doesn't currently correlate it against `jira_gate_history` to produce that number) — tests: `tests/tools/test_log_review_cycle.py`, `tests/tools/test_request_self_review.py`, plus extended assertions in the existing poller/park-at-gate tests (11 tests total across new + extended)

## 11. Testing

- [x] 11.1 Write unit tests for `agent/utils/jira.py` (mock Jira API responses) — `tests/utils/test_jira.py` (16 tests)
- [x] 11.2 Write unit tests for `agent/jira_poller.py`: launches a thread for a new card, wakes a parked thread on column change, stays idle otherwise, and is idempotent across duplicate ticks — `tests/agent/test_jira_poller.py` (13 tests)
- [x] 11.2b Write unit tests for `agent-console/store.py` (status derivation, ring buffer eviction) and for the ingest routes — `agent-console/tests/test_store.py`, `agent-console/tests/test_app.py` (15 tests, run separately per the note under §5b.8 — needs `pip install -r agent-console/requirements.txt`)
- [x] 11.3 Write unit tests for OpenSpec tools (artifact generation, validation, archival) — `tests/tools/test_openspec_tools.py` (10 tests)
- [x] 11.4 Write unit tests for Jira tools and for `adf.py` (mock HTTP responses; ADF fixtures with typographic characters) — `tests/tools/test_jira_tools.py`, `tests/utils/test_adf.py` (6 + 12 tests)
- [x] 11.5 Write unit tests for column name → transition id resolution, including the unknown-column and unreachable-column error paths — covered in `tests/utils/test_jira.py` (`test_transition_to_column_resolves_name_and_transitions`, `test_transition_to_column_raises_with_available_targets`)
- [x] 11.6 Write integration test for end-to-end workflow (Jira trigger → spec → implement → review → PR) — `tests/agent/test_jira_workflow_integration.py`: drives a full sequence (tick launches a thread → agent parks at gate 1 → poller detects the human's column change and resumes → parks at gate 2 → resumes → parks at gate 3), asserting on the real `agent-console` store's derived state and the accumulated `jira_gate_history`. Does **not** exercise a real LLM, real Jira API, or real git/PR operations — none of that infrastructure exists in this environment; it verifies the pieces this change built click together, using fakes for the Jira REST client and the LangGraph SDK client

## 12. Documentation

- [x] 12.1 Document Jira board setup: the 11 columns and the global-transitions workflow requirement — `docs/JIRA_INTEGRATION.md`
- [x] 12.2 Document required environment variables (`JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_POLL_INTERVAL_SECONDS`, column name overrides) — `docs/JIRA_INTEGRATION.md`, including the ones added along the way (`JIRA_PROJECT_KEY`, `JIRA_TRIGGER_JQL_FILTER`, `JIRA_FA_ALERT_LABEL`, `JIRA_POLLER_SHADOW_MODE`, `JIRA_POLLER_PAUSED`, `AGENT_CONSOLE_URL`)
- [x] 12.3 Document the complete workflow with ASCII diagram — `docs/JIRA_INTEGRATION.md`, including the PASSO 7/8 reordering design note
- [x] 12.4 Add troubleshooting section (common failure modes and resolutions) — `docs/JIRA_INTEGRATION.md`

## Deferred — not in the MVP

- **Sensedia AI Gateway MCP (`Jira_CRUD_Issue`)** — see design.md Decision 2 and `exploration/06-ai-gateway-sensedia.md`. Revisit if governance and observability over the agent's Jira calls become a requirement. It can be added as an extra tool source without touching the approval-gate middleware, which keeps using the direct client.
- **Jira webhook trigger** — polling/manual trigger for the MVP; a webhook lowers latency but needs a public endpoint and per-project registration.
