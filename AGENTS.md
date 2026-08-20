# AGENTS.md

This file provides guidance to Coding Agents when working with code in this repository.

## Memory Bank

Documentação estruturada do sistema por agente e por camada em [`memory-bank/`](memory-bank/). Cada agente é documentado com objetivo, intenção, resultado, fluxo de entrada/saída, conexões e ferramentas. Veja `memory-bank/projectbrief.md` para a visão geral.

## Project

Open SWE is an open-source coding-agent framework built on **LangGraph** + **Deep Agents** (`deepagents.create_deep_agent`). It runs as a LangGraph app: each thread spawns its own isolated cloud sandbox, and the agent is invoked from Slack, Linear, or GitHub (PR comments, plus auto-review on opened / ready-for-review).

A separate **reviewer** graph runs read-only code reviews on PRs, and a **review-style analyzer** graph learns per-repo review style from historical PRs.

## Commands

Dependencies are managed with **uv**. Tests use pytest (`asyncio_mode = "auto"`). Lint/format is **ruff** (line-length 100, target py311). Type checking is **basedpyright** (`typeCheckingMode = "standard"`). `requires-python = ">=3.11"`; `langgraph.json` pins the runtime to 3.12.

```bash
make install            # uv sync --extra dev (pytest, ruff, …)
make dev                # uv run langgraph dev — serves all three graphs + the FastAPI app from langgraph.json
make run                # uvicorn agent.webapp:app --reload --port 8000 (FastAPI only, no LangGraph runtime)
make test               # uv run pytest -vvv tests/
make test TEST_FILE=tests/github/test_open_pull_request.py    # single test file
uv run pytest -vvv tests/github/test_open_pull_request.py::test_name  # single test
make lint               # ruff check + ruff format --diff
make format             # ruff format + ruff check --fix
make typecheck          # basedpyright agent tests
```

`langgraph.json` declares three graph entrypoints and the FastAPI app, all served together by `langgraph dev`:

| Graph | Entrypoint | Purpose |
|---|---|---|
| `agent` | `agent.server:get_agent` | Main coding agent (Slack/Linear/GitHub-triggered). |
| `reviewer` | `agent.reviewer:get_reviewer_agent` | Read-only PR reviewer. Findings model + `publish_review`. |
| `analyzer` | `agent.analyzer:get_analyzer` | Learns per-repo reviewer style from historical PRs and this reviewer's own finding outcomes. |
| `ci_monitor` | `agent.ci_monitor:get_ci_monitor` | Polling fallback for CI auto-fix: each tick sweeps open agent-authored PRs for failing checks / merge conflicts via `agent.ci_autofix.sweep_open_prs`. |

The FastAPI app is `agent.webapp:app`.

CI auto-fix ("PR babysitting") lives in `agent/ci_autofix.py`: when a CI check fails (webhook `check_run` / `check_suite` / `workflow_run` / `status`) or a reviewer leaves actionable feedback on a PR Open SWE opened, it locates the originating agent thread (by `pr_url` metadata) and dispatches a confidence-gated fix run on the `agent` graph. Gated by the per-user `auto_fix_ci` profile flag, the enabled-repos opt-in, and a per-PR `@open-swe autofix on|off` toggle (`agent/dashboard/autofix_state.py`). Skip-rules (base-branch failures, human commits, same-head dedupe, batching while runs are active, loop cap) all live in `ci_autofix.py`.

## Architecture

### Entrypoints

- **`agent/server.py` → `get_agent(config)`** — main graph factory. Called per-thread. Resolves the GitHub token, gets-or-creates the sandbox for the thread, resolves the team/profile/per-thread model + effort, then constructs a fresh `create_deep_agent(...)` with the curated tool list and middleware stack. The agent itself is stateless — all per-thread state lives in the sandbox + thread metadata.
- **`agent/reviewer.py` → `get_reviewer_agent(config)`** — reviewer graph factory. Shares `ensure_sandbox_for_thread` with the main agent but wires a reviewer-only toolset (`add_finding`, `update_finding`, `list_findings`, `publish_review`, `web_search`, `fetch_url`, `http_request`) and a different system prompt that pins the single-evolving-findings model and the diff-anchored bar for filing a finding. Read-only: no commit/push/PR-opening tools.
- **`agent/analyzer.py` → `get_analyzer(config)`** — small graph that emits a per-repo style prompt via the `save_review_style_prompt` tool, consumed by the reviewer as a "repository-specific review style" appendix. It runs in one of two modes (`analyzer_mode` in `configurable`): **bootstrap** (cold-start: crawl historical PR reviews) and **continual** (nightly: refine using this reviewer's own finding outcomes via `read_finding_outcomes`). Each mode's procedure lives in a deepagents **skill** (`agent/skills/bootstrap-repo-analysis/`, `agent/skills/continual-learning/`) served as virtual files via a `CompositeBackend` `/skills/` route + `StateBackend` (seeded into the run's `files` channel by the launcher — never written to the sandbox). Launchers and the per-repo nightly cron live in `agent/dashboard/review_style_jobs.py` and `agent/dashboard/analyzer_cron.py`; the cron is registered when bootstrap completes.
- **`agent/webapp.py`** — custom FastAPI routes mounted alongside the LangGraph server. Webhooks land here (GitHub, Linear, Slack). Each webhook resolves a deterministic `thread_id` (so follow-up messages route to the same agent run) and triggers/streams a run via the `langgraph_sdk` client. Also auto-reviews PRs on `opened` / `ready_for_review` events when the repo+author opt in.
- **`agent/dashboard/`** — `router` mounted under the FastAPI app at startup (`app.include_router(dashboard_router)`). Owns GitHub OAuth, per-user profiles, admin endpoints, team defaults, enabled-repo lists, review-style management, and the Agents chat thread API used by the UI in `ui/`.

### Sandbox lifecycle (the tricky part)

`SANDBOX_BACKENDS` (in `agent/utils/sandbox_state.py`) is an in-process dict keyed by `thread_id`. Thread metadata persists `sandbox_id` across processes. `ensure_sandbox_for_thread` handles three cases:

1. Sandbox cached in memory → ping it (`echo ok`), then refresh the GitHub proxy.
2. Metadata has an id but no cache → reconnect, then refresh the GitHub proxy.
3. No sandbox at all → create one and persist the id.

Only case 3 creates. An existing sandbox that can't be reached raises `SandboxUnreachableError` (`agent/utils/sandbox_state.py`) rather than being replaced: a replacement is empty, so swapping one in would destroy uncommitted work while looking like a recovery. The main agent catches that in `PrepareAgentRunMiddleware` and notifies the user via `post_sandbox_unreachable_notification`.

`allow_replacement=True` opts out of that protection and is passed **only** by the reviewer (`agent/reviewer.py:_ensure_reviewer_sandbox_for_thread`), whose sandbox holds nothing but a checkout `prepare_review_repo` re-derives every run. Reviewer threads are one-per-PR and outlive their sandbox, so without this a deleted sandbox bricks reviews on that PR permanently.

For `SANDBOX_TYPE=langsmith` (default), every sandbox creation/refresh also calls `_configure_github_proxy` with a fresh GitHub App installation token (`get_github_app_installation_token`). The proxy injects Basic auth for `github.com` git traffic and Bearer auth for `api.github.com` so sandbox commands can use `GH_TOKEN=dummy gh ...` without storing real tokens in the sandbox. Other providers (modal, daytona, runloop, e2b, local) skip the proxy step. Provider is selected via `SANDBOX_TYPE`; factory is `agent/utils/sandbox.py:create_sandbox` (`SANDBOX_FACTORIES` maps each provider name to a creator in `agent/integrations/`).

Every run re-applies `git config --global user.name/email` for the bot identity, because reused/reconnected sandboxes can lose `--global` config and Vercel preview deploys reject commits whose author email doesn't resolve to a GitHub account.

`PrepareAgentRunMiddleware` also snapshots the worktree into `refs/open-swe/turns/<user-message-id>` at run start (`utils/turn_checkpoint.py`), recording the refs in thread metadata. `GET /threads/{id}/turn-diff` reads them back so the dashboard's changed-files views come from git rather than from replaying edit tool calls — which is the only way to catch edits made through `execute` and to drop files that were later reverted.

### Middleware stack (order matters)

Configured in `agent/server.py:get_agent`, runs around every model call (in this order):

1. `SanitizeToolInputsMiddleware` — strips/normalizes tool inputs before they reach tools.
2. `ModelCallLimitMiddleware` (from `langchain.agents.middleware`) — caps model calls at `MODEL_CALL_RECURSION_LIMIT` (~half of `DEFAULT_RECURSION_LIMIT`); `exit_behavior="end"`.
3. `ToolErrorMiddleware` — catches tool exceptions and surfaces them as tool messages.
4. `SubdirAgentsReadMiddleware` — appends applicable ancestor `AGENTS.md` instructions to `read_file` results once per run, so scoped rules are visible before edits.
5. `check_message_queue_before_model` — pulls Linear comments / Slack messages that arrived mid-run from the thread queue and injects them as user messages before the next LLM call. This is what makes "message the agent while it's working" work.
6. `SlackAssistantStatusMiddleware` — keeps the Slack "assistant is typing"-style status up to date around model calls.
7. `ensure_no_empty_msg` — after-model hook; when the model emits a message with no tool call (and hasn't already messaged the user or confirmed completion) it re-injects a synthetic `no_op` / `confirming_completion` tool call so the run continues instead of ending prematurely.
8. `notify_step_limit_reached` — after-agent hook that posts a Slack reply when the agent hits the step limit, so the user gets a clear signal instead of silence.
9. `SandboxCircuitBreakerMiddleware` — trips the agent out of repeated sandbox failures instead of looping.
10. `ModelFallbackMiddleware` (optional) — added only when `LLM_FALLBACK_MODEL_ID` or the per-model default fallback differs from the primary model.
11. `SanitizeThinkingBlocksMiddleware` — strips malformed empty Anthropic thinking blocks immediately before provider calls.
12. `ModelCallTimeoutMiddleware` — innermost. Caps a single model call at `OPEN_SWE_MODEL_CALL_TIMEOUT_SECONDS` (default 15 min) so a stalled provider connection raises instead of parking the run; the timeout escalates outward to `ModelFallbackMiddleware`. Complements the per-request `timeout` `agent/utils/model.py` sets on every provider. Subagents compile into their own graphs, so each `SubAgent` spec carries its own instance (`_subagent_model_timeout_middleware`) — parent middleware never wraps a delegated `task`'s model calls, and a wedged one escalates via `ToolRetryMiddleware`'s `task` retry.

The system prompt instructs the agent to call a tool every turn, and `ensure_no_empty_msg` re-injects a tool call when it doesn't — together these keep runs from stopping partway through a task.

Other middleware exists in `agent/middleware/` (`ExcludeToolsMiddleware`) but isn't wired into the default agent. The reviewer uses a leaner stack: `SanitizeToolInputsMiddleware`, `ModelCallLimitMiddleware`, `ToolErrorMiddleware`, `SlackAssistantStatusMiddleware`, `SanitizeThinkingBlocksMiddleware`.

There is intentionally no after-agent safety net that opens a PR for the agent. The agent itself is responsible for committing, pushing, opening/updating the draft PR, and replying in the source channel — all via `GH_TOKEN=dummy gh` and `slack_thread_reply` / `linear_comment`.

### Tools

All tools live in `agent/tools/` and are flat-imported via `agent/tools/__init__.py`. The set is intentionally small and curated — see README "Tools — Curated, Not Accumulated".

Wired into `get_agent`:
`http_request`, `fetch_url`, `web_search`, `approve_plan`, `enter_plan_mode`, `save_plan`, `save_user_instructions`, `linear_comment`, `linear_create_issue`, `linear_delete_issue`, `linear_get_issue`, `linear_get_issue_comments`, `linear_list_teams`, `linear_search_issues`, `linear_update_issue`, `open_pull_request`, `request_pr_review`, `report_platform_issue`, `schedule_thread_wakeup`, `slack_add_reaction`, `slack_read_thread_messages`, `slack_start_new_thread`, `slack_thread_reply`.

Reviewer-only tools (in `agent/reviewer.py`): `add_finding`, `update_finding`, `list_findings`, `publish_review`. The review-style analyzer uses `save_review_style` (exported as `save_review_style_prompt`).

Built-in deepagents tools (`read_file`, `write_file`, `edit_file`, `delete`, `ls`, `glob`, `grep`, `execute`, `task` for subagent spawning, …) are added by `create_deep_agent` itself; don't duplicate them.

### Model routing

Model + reasoning effort are **not** configurable per run. `agent/routing` decides
both from the agent role: `resolve_model(role, complexity, retry_count, workflow_context)`
returns a `ModelConfig(model, effort, reason)`. Roles are the `AgentRole` enum
(`jira_triage`, `spec_author`, `coding_agent`, `code_reviewer`, `docs_agent`, …).

- Cheap, mechanical roles run Haiku with no effort; authoring and verification run
  Sonnet/high; reviewing and escalation run Opus/high.
- `coding_agent` / `code_adjuster` start at Sonnet/medium and escalate to Opus/high
  after two failed attempts, at `CRITICAL` complexity, or at `HIGH` complexity with a
  risk signal (auth, migration, security, concurrency). The `escalation_reason` is
  always recorded on the decision.
- Complexity is deterministic (`agent/routing/complexity.py`) — file counts, risk
  signals, retries and review returns. No LLM call.
- Effort is guarded against `agent/routing/capabilities.py`, derived from the model
  catalog: a model that does not advertise the routed effort gets none rather than a
  substituted level.

Which role a run is routed as is decided once per dispatch, from the Jira column the
poller resumed the card at (`agent/routing/phases.py`): the trigger column is spec
authoring, the adjust columns are the matching adjuster, the pre-merge column is
OpenSpec verification, and a merged card is archiving. A run with no Jira column —
dashboard, Slack, Linear, PR comment — is `coding_agent`. The reviewer selects
`code_reviewer` and `diff_grouping` itself; the PR review chat runs as
`review_chat` and the review-style analyzer as `style_analyzer`. Nothing outside
`agent/routing` may pick a model: not a request field, not a dashboard profile,
not a team default.

Because the workflow is one deep agent per dispatch rather than one graph node per
phase, some roles in the enum are not selected by anything yet (`jira_triage`,
`python_harness`, `spec_reviewer`, `docs_agent`, `escalation_agent`) — those phases
happen inside another role's run. `GET /api/config/routing` marks each row `active`
and says what selects it, so the table is never read as more than it is.

There is no override: not per thread, not per profile, not per team, not from the
console. Dashboard profile model fields still exist for display, but they no longer
steer a run.

Every dispatched run carries that decision into LangSmith as trace metadata
(`agent/routing/telemetry.py`): card, thread, role, workflow stage, model, effort,
complexity tier, routing reason. Tokens and cost are read back from the completed
run — after it finishes, never per token — and aggregated per Jira card across all
of its threads (`agent/routing/usage_store.py`), with `agent/routing/pricing.py` as
the cost fallback when LangSmith reports none. An unpriceable run reports `null`,
not `0.0`. The console mirrors the same stores from two pushed events and serves
them at `GET /api/observability/…`; it never calls LangSmith itself.

Custom instructions are layered into the system prompt from two stores: per-repo (`agent/dashboard/agent_instructions.py`, edited on the Repository Instructions page) and per-user (`agent/dashboard/user_instructions.py`, edited in the dashboard Profile tab or by the agent itself via `save_user_instructions`). Repo instructions and `AGENTS.md` win over user-level ones on conflict.

Supported model IDs and per-model effort/reasoning rules live in `agent/dashboard/options.py`. Profile flags also drive run behavior — e.g. `profile_create_prs` enables the opt-in Always Create PRs policy. Model construction goes through `agent/utils/model.py` (`make_model`, `provider_model_kwargs`, `fallback_model_id_for`).

### Auth

- **GitHub**: dual-mode. User OAuth tokens are encrypted at rest in the dashboard OAuth store and cached only in process during a run (`utils/auth.py:resolve_github_token`, `utils/github_token.py`). When no user token is available, falls back to a GitHub App installation token (`utils/github_app.py`). The installation token is also what configures the LangSmith sandbox's GitHub proxy.
- **Webhooks**: GitHub signatures verified in `utils/github_comments.py:verify_github_signature`; Slack/Linear handled in their respective utils.
- **Dashboard / UI**: GitHub OAuth login lives in `agent/dashboard/oauth.py` and `routes.py` (`/auth/login`, `/auth/callback`, `/auth/logout`, `/me`).

### Thread-id derivation

Webhooks compute deterministic thread ids so the same Linear issue / Slack thread / PR routes back to the same running agent. See `utils/github_comments.py:get_thread_id_from_branch` and the equivalents in `utils/linear.py` / `utils/slack.py`. Reviewer threads have their own deterministic ids and are tagged with `REVIEWER_THREAD_KIND` metadata so the FastAPI side can find them.

## Conventions

- Tests are unit-only by default (`tests/`). Integration tests would go under `tests/integration_tests/` (currently empty — `make integration_tests` no-ops if missing).
- New sandbox providers: add a module under `agent/integrations/` and wire it into `SANDBOX_FACTORIES` in `agent/utils/sandbox.py`. See `docs/CUSTOMIZATION.md`.
- New tools: add to `agent/tools/`, export from `agent/tools/__init__.py`, add to the `tools=[...]` list in `server.py:get_agent` (or `reviewer.py` for reviewer-only tools).
- New middleware: add to `agent/middleware/`, export from `agent/middleware/__init__.py`, add to the `middleware=[...]` list in `server.py:get_agent` — order is significant (see the stack above).
- Async-only: this app runs exclusively async, so do not add sync/async dual implementations. Implement only the async variant (`awrap_*`, `_arun`, etc.); the sync counterpart is never invoked. Omit the sync method entirely when the interface allows it (e.g. `AgentMiddleware` already raises `NotImplementedError` on the sync path). Only when a type/ABC requires the sync method to exist (e.g. `BaseTool._run` is abstract), define it with a bare `raise NotImplementedError` rather than a real sync implementation.
- New dashboard endpoints: add to `agent/dashboard/routes.py`. The router is auto-mounted on the FastAPI app.
- New graphs: register the entrypoint in `langgraph.json` under `graphs`.
- Minimal-to-no code comments — only when the *why* isn't obvious from the code.

## SDD Mandatory Gates (Jira-triggered runs)

Spec-Driven Development is the development standard for every Jira-triggered run, not a
recommendation. **The rules below take precedence over any default agent behavior**, including
any instinct to start coding once the problem looks clear. A run that produces code before it
produces a spec has already failed, regardless of whether the code is correct.

The OpenSpec instructions the agent follows are **vendored, never fetched at runtime**. Provenance
(upstream source, version, commit, fetch date, vendored files) is recorded in
`openspec/openspec-version.yaml`; pristine upstream copies live under
`openspec/vendor/openspec-skills/`. Refresh them explicitly with
`scripts/sync-openspec-skills.sh --commit <SHA> [--version <tag>]` — it fails loudly without a
pinned commit and never pulls `main`. The four skills actually served to the agent (route
`/openspec-skills/`) are CLI-free ports of the upstream ones: `openspec-explore`,
`openspec-propose`, `openspec-verify`, `openspec-archive`. `openspec/config.yaml` carries the
target-repo context and the per-artifact rules those skills must satisfy.

### Step 0 — Python Harness Engineer (before any exploration or code)

On a Python repository the run has one mandatory step before SDD starts. The order is:

```
repository cloned / branch created (PASSO 2)
  -> Run Python Harness Engineer   (agent/skills/python-harness/SKILL.md)
  -> OpenSpec Explore (PASSO 3) -> OpenSpec Propose -> ... -> implementation
```

The harness is read-only apart from installing the project's own declared dependencies. It
detects the Python version, the dependency manager, the install / run / test / lint /
type-check / migration commands, the framework, the architecture layers and the required
environment variables, and emits a **Harness Report**: as a fenced block in the thread *and*
saved to `<working_dir>/harness/<ISSUE-KEY>-harness-report.md`, outside the repo clone so it
never reaches `git status` or the PR. The saved copy is why the detection is not repeated on
every model call — later steps and runs resumed after a gate read the file.

The Harness Report is context for both the OpenSpec proposal (its Impact section and the
lint/test entries in `tasks.md`) and the implementation (every command it runs). The agent MUST
NOT edit a source file before the report exists.

Two hard rules the skill enforces: if a safe test command cannot be determined, the harness
asks on the Jira card and ends the turn (`HARNESS BLOCKED`) rather than guessing; and it never
installs tooling the project has not declared — that is a separate, proposed decision (see
`python-quality`).

### Gate 1 — before `Em Revisão de Spec`

The agent MUST NOT call `jira_park_at_gate` for `Em Revisão de Spec` until all of these exist,
are **committed**, and are **pushed to the remote branch** (confirmed via
`git ls-remote --heads origin <branch>` or the equivalent `gh api` call):

- `openspec/changes/<change>/.openspec.yaml`
- `openspec/changes/<change>/proposal.md`
- at least one `openspec/changes/<change>/specs/<capability>/spec.md`
- `openspec/changes/<change>/tasks.md`
- `design.md` whenever a product decision is unresolved — an unresolved decision belongs in its
  Open Questions section, never in the code

Implementation does not begin before this gate is passed by a human. If the commit or the push
fails, comment the failure on the card and end the turn with the card still in `In Progress`.

### Gate 2 — before `Em Code Review`

The agent MUST NOT call `jira_park_at_gate` for `Em Code Review` until the `openspec-verify`
skill has run against the current committed state and left **no unresolved CRITICAL finding**.
Verification is a reasoning + code-reading step (`grep`, `read_file`, `execute`), not a tool
call: `openspec_validate` only checks artifact structure. If self-review guidance is exhausted
with a CRITICAL still standing, park anyway — but the gate comment MUST enumerate every
unresolved finding. Parking silently on a known divergence is the failure this gate exists to
prevent.

### Gate 3 — before `Em Merge`

The agent MUST NOT call `jira_park_at_gate` for `Em Merge` until the `openspec-archive` skill
has completed: the change moved to `openspec/changes/archive/<change>/`, every
`needs_manual_merge` capability reconciled by hand, an entry appended to
`openspec/changes/archive/index.md`, and the archive plus documentation updates committed and
pushed to the **same branch and same PR** as the implementation. Nothing is deferred to after
the merge, and no second PR is opened for docs (design.md Decision 6, revised).

### Observability

Emit a console log line at each OpenSpec lifecycle point using the existing `console_events`
pattern (`agent/utils/console_events.py`; `log_review_cycle` is the tool-side example of pushing
one). The four points and their message shapes:

| Point | Message |
|---|---|
| Skills loaded at run start | `openspec: version <version> loaded` |
| Artifacts written (PASSO 3) | `openspec: proposal generated` |
| `openspec-verify` clean (Gate 2) | `openspec: verification passed` |
| `openspec-archive` complete (Gate 3) | `openspec: archived` |

These are fire-and-forget pushes: a console that is down or slow must never affect a run.

## Python Skill Loading (contextual, not always-on)

Six Python skills live in `agent/skills/` and are served read-only to the agent under
`/openspec-skills/` alongside the four OpenSpec ones. `SkillsMiddleware` lists every skill's
name and description at run start; the agent reads a `SKILL.md` **only when the phase below
calls for it**, so context cost is proportional to what the task actually needs. Loading all
six on every run is the failure mode this table exists to prevent.

| Phase | Skills to load | Why |
|---|---|---|
| After clone / before Explore (Step 0) | `python-harness` | Produces the Harness Report every later phase reads. Nothing else runs first. |
| Explore / Propose (PASSO 3) | `python-engineering` + the Harness Report | Judge feasibility, layering and blast radius against the project's real conventions; no framework detail needed to write a spec. |
| Implementation (PASSO 5) | `python-engineering`, `fastapi-engineering`, `python-testing` | The always-on trio for writing code on a FastAPI repo. Skip `fastapi-engineering` when the harness detected another framework or none. |
| Implementation touching models / queries / schema | + `python-database` | Load only when the change touches persistence. Its rule — every schema change ships an Alembic migration in the same commit — is a gate on that kind of change. |
| Quality gates (end of PASSO 5, and PASSO 6) | + `python-quality` | Detect the project's declared gates, run them, and report honestly before parking. |
| Review / Verify (PASSO 6, before `Em Code Review`) | `python-quality` + `openspec-verify` | The code-vs-spec check and the gate run, together. |
| Pre-merge (PASSO 8) | `openspec-archive` | Python skills are no longer needed; the diff is archive + docs. |

Rules that hold across all phases:

- Load a skill when you reach its phase, not preemptively, and do not re-read a `SKILL.md` you
  already read in this run.
- `python-engineering` is the base; the others assume it and do not repeat it.
- Every one of them defers to the Harness Report for commands and to the target repository's
  existing conventions for style. A skill never overrides what the repo already does.

## Reviewer Independence

The `reviewer` graph is a **separate agent from the coding agent**, and the separation is the
point: two runs of the same model agreeing with each other is not a review. The rules:

- The reviewer performs **fresh analysis on the PR diff**. It reads the diff (via
  `fetch_review_diff`) and the code the diff touches, and derives its own conclusions from
  them.
- The coding agent's self-assessment is **untrusted input**, not a finding of fact. The PR
  description, the commit messages, the author trace and any self-review comment are claims to
  verify. "The author says it is tested" is not a test; "the author says no schema changed" is
  not a schema check. The reviewer never reproduces or endorses those conclusions as its own.
- **The reviewer's findings supersede the coding agent's self-assessment.** When the two
  disagree, the review is what stands, and the coding agent fixes the code rather than arguing
  the summary.
- Findings are **anchored inline**: `add_finding` with `file` + `start_line`/`end_line` inside
  the diff, so `publish_review` posts a comment on the offending line. A top-level summary
  alone is not a review.
- On a Python diff the reviewer loads `agent/skills/python-review/SKILL.md` (served on the
  `/openspec-skills/` route, same as the coding agent's skills) and works its seven passes:
  Correctness, Python, FastAPI, Database, Security, Tests, OpenSpec adherence. The OpenSpec
  pass is what keeps the SDD contract honest at review time — implemented behaviour must trace
  to a requirement, `design.md` decisions are binding, and a `- [x]` in `tasks.md` whose work
  is not in the diff is a finding.

<!-- OPENWIKI:START -->

## OpenWiki

This repository uses OpenWiki for recurring code documentation. Start with `openwiki/quickstart.md`, then follow its links to architecture, workflows, domain concepts, operations, integrations, testing guidance, and source maps.

The scheduled OpenWiki GitHub Actions workflow refreshes the repository wiki. Do not hand-edit generated OpenWiki pages unless explicitly asked; prefer updating source code/docs and letting OpenWiki regenerate.

<!-- OPENWIKI:END -->
