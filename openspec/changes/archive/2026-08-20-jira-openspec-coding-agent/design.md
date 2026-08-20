## Context

Open SWE (`open-swe/`) is a production-grade coding agent framework built on LangGraph + Deep Agents. It provides sandbox isolation, GitHub OAuth, a curated toolset, a middleware stack, subagent orchestration, a reviewer graph, and Slack/Linear/GitHub triggers. This change extends Open SWE to support a Jira-driven, OpenSpec-guided workflow with human approval gates mapped to Jira column transitions.

The architecture is guided by two reference documents:
- **The Agentic Development Playbook**: Defines the 5-stage Agentic SDLC (Define → Shape → Build → Validate → Run), the principle that "humans own intent and judgment; agents own execution and coverage," and the maturity curve from ad-hoc AI usage to agent-native organizations.
- **langgraph-coding-agent-open-swe-arquitetura.md**: Proposes a LangGraph StateGraph with Planner, Implementer, and Reviewer agents, Jira MCP integration, OpenSpec as the specification layer, and `interrupt()` for human-in-the-loop.

Key constraints:
- Open SWE is the foundation — adapt, don't rewrite
- Jira is the primary trigger and context source (`sensedia.atlassian.net` is available; the board for this workflow does not exist yet and will be created for it)
- OpenSpec is mandatory for structured specification
- Human approval happens via Jira column transitions (agent moves the card and ends its run; a poller resumes the thread once a human advances the card)
- Branch naming: `feat/spec-JIRA-XXXX-descricao-curta`
- Metrics go to LangSmith (already integrated)

## Goals / Non-Goals

**Goals:**
- Add Jira as a first-class trigger and context source alongside existing Linear/Slack/GitHub
- Integrate OpenSpec for structured specification generation, validation, and archival
- Implement a column-driven approval workflow with three human checkpoints
- Add auto-review loops (spec and code) guided toward a small number of correction cycles
- Leverage the existing Open SWE reviewer graph for automated code review
- Update canonical docs post-merge via a separate PR
- Record workflow metrics in LangSmith

**Non-Goals:**
- Removing or replacing Linear/Slack/GitHub triggers (they remain functional)
- Implementing LangGraph `interrupt()` for persistent pauses (the scheduler poller achieves the same with infrastructure that already exists)
- Jira webhooks (the 60s poller is sufficient for the MVP)
- Creating separate Planner/Implementer agent graphs (the existing plan mode is evolved instead)
- Building a generic Jira integration platform (tightly scoped to this workflow)
- Modifying the Open SWE middleware stack architecture (only additions, no rewrites)

## Decisions

### 1. Scheduler Poller with Non-Blocking Gates

**Decision:** A cron tick every 60s drives a poller in the existing `scheduler` graph. The poller does two things per tick: launch a fresh agent thread for each card in the trigger column, and re-trigger any parked thread whose card has moved. **The agent never blocks waiting for a human** — on reaching a gate it posts to Jira, moves the card, and ends its run.

**Rationale:**
- Three Open SWE limits run on wall-clock time, not work done: `timeout_wrapup.py` injects a "wrap up immediately" instruction at 45 minutes, `model_call_timeout.py` caps a single model call at 900s, and `ModelCallLimitMiddleware` ends the run at its call cap. A gate that sleeps inside the agent loop burns that budget while idle, and the merge gate — a human merging a PR — is routinely measured in hours.
- Uncommitted work lives in the sandbox, and an unreachable sandbox raises `SandboxUnreachableError` rather than being replaced (replacing it would destroy that work while looking like a recovery). Blocking for hours widens that window for no benefit.
- The `scheduler` graph already exists for exactly this shape — `agent/scheduler.py` fans cron ticks into fresh agent threads via `launch_scheduled_agent_run`.
- Thread ids are derived deterministically from the issue key, so a re-triggered thread reconnects to the same sandbox and continues where it stopped. This is the same mechanism that already routes Linear and Slack follow-ups back to a running agent.
- Trigger detection and gate resumption are the same query shape, so one component covers both.

**Cost:** up to 60s of latency between a human moving a card and the agent resuming. Irrelevant for human approval.

**Alternatives considered:**
- **Blocking middleware polling every 15s** — the original decision, reversed. Its stated precedent was wrong: `check_message_queue_before_model` is a `@before_model` hook that reads the store once and returns; it does not poll or wait. Nothing in Open SWE blocks inside the agent loop.
- **`interrupt()`** — requires LangGraph Platform or a self-hosted checkpointer with persistence. The poller achieves the same pause with infrastructure that already exists.
- **`schedule_thread_wakeup`** — a one-shot cron re-trigger of the current thread (min 60s, max 24h), already in the toolset. Viable and kept as a fallback: it lets a thread wake itself without the poller. Not chosen as the primary mechanism because the poller has to exist anyway for trigger detection, and one component beats two.
- **Jira webhooks** — lower latency, but needs a public endpoint and per-project registration. Deferred.

### 2. Jira via Direct REST API (not MCP)

**Decision:** Call the Jira Cloud REST API v3 directly from `agent/utils/jira.py` using Basic auth (email + API token), following the pattern of `agent/utils/linear.py`. Thin tools in `agent/tools/jira_*.py` wrap the client, following `agent/tools/linear_get_issue.py`.

**Rationale:**
- The scheduler poller must query Jira **outside** the agent entirely — it runs on a cron tick, with no LLM in the loop. MCP tools are built for LLM invocation; the poller would have to re-establish an MCP session every 60s just to run two JQL queries.
- Open SWE already has this exact pattern for Linear: a 383-line HTTP client in `utils/`, plus 8 thin tools that delegate to it (`linear_get_issue.py` is 15 lines).
- Basic auth with a Jira API token is a single static credential — no OAuth flow, no refresh rotation, no token expiry mid-run.
- The credential lives in the LangGraph server process and never reaches the sandbox — the same guarantee MCP would provide, so token safety does not discriminate between the options.
- `transitionIssue` has never been exercised in any existing integration. The three approval gates depend on it either way; direct REST minimises the layers between the agent and that call.

**Alternatives considered:**
- **Sensedia AI Gateway MCP (`Jira_CRUD_Issue`)** — evaluated in depth, see `exploration/06-ai-gateway-sensedia.md`. It exposes exactly the six operations this workflow needs and already solves headless Atlassian OAuth. Rejected for the MVP because it stacks two independently rotating auth layers (gateway OAuth2 client_credentials + Atlassian 3LO), an MCP session handshake, a synchronous client inside an async agent, and a hard runtime dependency on both the gateway and a Flask service. Its swagger is reused as the endpoint contract and its ADF normalisation logic is ported.
- **Atlassian Rovo MCP** — the original proposal. Requires interactive OAuth, which a webhook- or cron-triggered agent cannot complete.
- **`atlassian-python-api` SDK** — a new dependency for calls that are a few lines of `httpx` each.

**Deferred, not discarded:** if governance over Jira calls becomes a requirement, the gateway MCP can be added later as an additional tool source without touching the middleware, which keeps using the direct client.

### 3. OpenSpec as Sandbox Tools (not External Service)

**Decision:** OpenSpec artifacts live in the sandbox under `/workspace/openspec/`. The **explore** and **propose** procedures are deepagents **skills** (`agent/skills/`, served through the `/skills/` route Open SWE already has); only mechanical operations — validate, archive, status — are tools, following the `save_plan.py` pattern.

**Why skills and not tools for propose:** authoring a proposal is a reasoning procedure, not a file write. A Python tool cannot write a `design.md`; at best it stamps a template. The `.claude/skills/openspec-propose/SKILL.md` in this repo is already that procedure, and Open SWE already serves skills to the agent (`skill_sources` in `agent/server.py`, as used by `bootstrap-repo-analysis`). Porting the skill reuses both. Note the shipped skill declares `compatibility: Requires openspec CLI` — that dependency is dropped in the port; the model writes artifacts with the existing `write_file` tool.

**Rationale:**
- Keeps specs versioned in the same repo (branch `feat/spec-JIRA-XXXX`)
- No external service dependency — the agent is self-contained
- The `save_plan` tool already demonstrates reading/writing Markdown from the sandbox
- Specs travel with the PR, providing context for reviewers

**Alternatives considered:**
- OpenSpec CLI as external process: Would require installing OpenSpec in the sandbox snapshot; adds maintenance burden
- Separate spec repository: Adds complexity; specs should live with the code they describe

### 4. Single Agent with Evolved Plan Mode (not Multi-Agent)

**Decision:** Extend the existing plan mode rather than creating separate Planner/Implementer agent graphs.

**Rationale:**
- Open SWE's plan mode already restricts tools (`PLAN_MODE_EXCLUDED_TOOLS`) and supports `enter_plan_mode`/`approve_plan`
- A single agent maintains context continuity — no serialization between planning and implementation
- The existing middleware stack, model resolution, and sandbox lifecycle work unchanged
- Subagents (`task` tool) already provide parallelism when needed

**Alternatives considered:**
- Separate Planner/Implementer/Reviewer graphs: Better separation of concerns but doubles LLM calls, requires cross-graph state management, and duplicates middleware configuration

### 5. Auto-Review as Prompt-Driven Loops (not Structural Gates)

**Decision:** Implement spec and code self-review as prompt-driven loops. The "maximum of 3 cycles" is **guidance in the system prompt, not an enforced limit** — this is accepted deliberately.

**What "not enforced" means:** nothing counts the cycles. The model is asked to stop after three and is expected to comply approximately. It may do two, or five. Since a run now ends and resumes at each gate (Decision 1), a counter would also have to survive the run ending — which a prompt cannot do. The number is a nudge toward "iterate a bit, then hand over", not a contract.

**Rationale:**
- Consistent with Open SWE's prompt-driven validation philosophy
- No new infrastructure needed — the agent iterates within the same run
- The invariant that actually matters is not the count: it is that the agent **always parks with a comment naming what it could not resolve**. That is specified in `column-approval-gate` and is observable, unlike a cycle number.
- Runaway iteration is already bounded structurally by the runtime, independent of this prompt: `ModelCallLimitMiddleware` ends the run at its call cap, `timeout_wrapup.py` forces wrap-up at 45 minutes, and `notify_step_limit` reports when the step limit is hit. These — not the number 3 — are what prevent an infinite loop.
- Drift is observable rather than silent: the agent logs each cycle to the console, so "it looped seven times on SSAI-412" is visible in the execution log even though nothing stopped it.

**Accepted consequence:** self-review depth varies per issue and is not reproducible. If cycle count later proves to matter — for example if it becomes a quality metric worth trusting — it has to move into agent state, which reverses this decision.

**Alternatives considered:**
- **Enforced counter in agent state** (the `LinearNotifyState` / `linear_messages_sent_count` pattern): deterministic and survives the run ending, but contradicts the prompt-driven philosophy and adds state plumbing for a bound the runtime already provides.
- **Structural quality gates (separate validation agents)**: more robust, but requires new graphs and infrastructure; better suited to a later maturity level.

### 6. Canonical Docs and OpenSpec Archive Ship With the Implementation PR

**Decision (revised — supersedes the original "separate PR after merge"):** the OpenSpec archive and every documentation update the change requires happen **before** the card reaches `Em Merge`, on the same branch and the same PR as the implementation. There is no post-merge docs PR.

**Rationale:**
- `Em Merge` is defined as "the automation has finished everything it needs to do and this PR is ready for a human to merge". Work that still has to happen after the merge contradicts that definition and leaves the delivery incomplete at the moment a human is asked to accept it.
- The reviewer and the approving human see the docs and the archive in the same diff they approve, instead of approving code whose documentation lands later and unreviewed.
- The post-merge phase becomes purely administrative (confirm the merge, record the result, comment, move to `Done`), which is what makes it safe to run without touching the branch.
- A second PR opened after the merge is a second review cycle, a second set of checks, and a second thing that can be forgotten — with no reviewer left watching the card.

**Superseded rationale (the original decision):** keeping the implementation PR focused on code, letting docs be reviewed independently, and avoiding premature doc updates if the implementation PR needs revision. The first two are real but minor next to shipping an incomplete delivery; the third is answered by the fact that pre-merge preparation only starts after `Code Review Aprovado`, when the implementation is already settled.

**Cost:** the implementation PR carries doc and archive commits, so its diff is larger. Accepted.

### 7. Branch Naming Convention

**Decision:** `feat/spec-JIRA-XXXX-descricao-curta`

**Rationale:**
- `feat/` prefix follows conventional commit taxonomy
- `spec-` indicates this branch carries OpenSpec artifacts
- `JIRA-XXXX` provides traceability to the originating issue
- `descricao-curta` gives human-readable context

**Constraint:** The separator MUST NOT be a colon. Git forbids `:` in ref names
(`git check-ref-format --branch "feat/spec:JIRA-1234-x"` fails), so an earlier
`feat/spec:JIRA-XXXX` proposal was invalid. The only hard rule is the `feat/`
prefix; the rest of the name must satisfy `git check-ref-format --branch`.

## Jira Column Configuration

The workflow requires these 11 columns in the Jira project:

| # | Column | Who Moves | Meaning |
|---|---|---|---|
| 1 | BACKLOG | Human | Trigger — agent starts |
| 2 | In Progress | Agent | Agent is working |
| 3 | Em Revisão de Spec | Agent | Parked — waiting for spec approval |
| 4 | Spec Aprovada | Human | Planning approved |
| 5 | Ajustar Spec | Human | Spec needs adjustments |
| 6 | Em Code Review | Agent | Parked — waiting for code review |
| 7 | Code Review Aprovado | Human | Code approved |
| 8 | Ajustar Code | Human | Code needs adjustments |
| 9 | Em Merge | Agent | PR open, waiting for merge |
| 10 | Mergeado | Human | PR merged |
| 11 | Done | Agent | Workflow complete |

These are the names as actually configured in the `SSAI` project on `sensedia.atlassian.net`, verified by the spike. Three of them (`BACKLOG`, `In Progress`, `Done`) are Jira defaults kept as-is; the other eight were created for this workflow.

**Workflow transitions.** The Jira workflow MUST allow every status to transition to every other status ("Allow all statuses to transition to this one", set on each status). The flow is not linear — the agent moves from `In Progress` to three different targets, and five columns route back to it. Global transitions remove the transition matrix entirely and prevent HTTP 400 on an illegal jump. **Verified on the SSAI board:** all 11 statuses reach all 11.

**`BACKLOG` is the trigger — a deliberate choice.** Any card landing in `BACKLOG` starts the workflow; there is no separate "ready for development" gesture. The team accepts that entering the backlog *is* the request. Consequences to be aware of:

- Every card created in the project starts an agent run on the next tick, including cards filed for triage or discussion.
- Cards produced by monitoring integrations (the FA Alert flow already files bugs into this project) are picked up automatically with no human in between.

If this becomes noisy, the narrowest fix that keeps the column-driven model is to scope the poller's trigger JQL — by issue type, label, or assignee — rather than adding a column. That is a configuration change to `agent/jira_poller.py`, not a redesign.

**Removed columns.** An earlier draft had 15 columns, adding `Necessita Complemento da Spec`, `Spec Complementada`, `Necessita Revisão Humana` and `Orientações Fornecidas` for the auto-review-exhausted case. They were dropped: when auto-review exhausts its cycles the agent parks in the same gate column it would otherwise use (`Em Revisão de Spec` / `Em Code Review`) and posts a comment explaining what it could not resolve. The resume behaviour is byte-for-byte identical to the adjust path, so those four columns encoded no distinct state — only a distinction of who initiated, which belongs in a comment.

## Complete Agent Workflow

```
TRIGGER: Card in "BACKLOG"
  │
  ▼
PASSO 1: Collect Jira context (issue, description, acceptance criteria, comments)
  │
  ▼
PASSO 2: Prepare environment (clone repo, create branch feat/spec-JIRA-XXXX-*)
  │
  ▼
PASSO 3: Analyze code + generate OpenSpec (plan mode)
  │         → proposal.md, design.md, specs/*/spec.md, tasks.md
  │
  ▼
PASSO 4: Auto-review spec (loop, ~3 cycles — guidance)
  │         ├── Pass → move to "Em Revisão de Spec"
  │         └── Exhausted → comment unresolved gaps, move to "Em Revisão de Spec"
  │
  ▼
APPROVAL 1: Human reviews spec
  │         ├── "Spec Aprovada" → PASSO 5
  │         └── "Ajustar Spec" → PASSO 3 with feedback
  │
  ▼
PASSO 5: Implement (exit plan mode, execute tasks sequentially)
  │         → Edit files, write tests, lint, commit atomically
  │
  ▼
PASSO 6: Auto-review code (loop, ~3 cycles — guidance)
  │         ├── Pass → PASSO 7
  │         └── Exhausted → comment blockers, skip to "Em Code Review"
  │
  ▼
PASSO 7: Reviewer graph (automated, read-only)
  │         ├── PASS → move to "Em Code Review"
  │         └── CHANGES_REQUIRED → PASSO 5
  │
  ▼
APPROVAL 2: Human reviews code
  │         ├── "Code Review Aprovado" → PASSO 8
  │         └── "Ajustar Code" → PASSO 5 with feedback
  │
  ▼
PASSO 8: Pre-merge preparation — SAME branch, SAME PR (Decision 6, revised)
  │         → Final checks + tests
  │         → Archive OpenSpec (openspec_archive)
  │         → Identify and update impacted canonical docs
  │         → Commit + push
  │         → Self-review the pre-merge diff (it lands after the human's
  │           approval, so it is the one part of the PR nobody reviewed)
  │         → Confirm the PR is consistent and merge-ready
  │         → Move to "Em Merge"
  │
  ▼
APPROVAL 3: Human merges the PR on GitHub, then moves the card
  │         → "Mergeado"   (the agent never merges and never sets this column)
  │
  ▼
PASSO 9: Post-merge closing — administrative only, no functional changes
  │         → Confirm the PR is actually merged
  │         → Record the final result, update existing metadata/metrics
  │         → Final Jira comment, move to "Done"
```

**Transition ownership.** The human moves the card at exactly three points — out of `Em Revisão de Spec`, out of `Em Code Review`, and out of `Em Merge`. Every other transition on the board is the agent's, made automatically and only after the underlying step actually succeeded: no move to `Em Revisão de Spec` without a pushed remote branch carrying the OpenSpec, no move to `Em Code Review` without a created/updated PR, no move to `Em Merge` without a successful archive + docs + checks, no move to `Done` without a confirmed merge. On failure the agent comments the reason on the card and leaves it where it is.

## File Map

### New Files (~15)

```
agent/utils/jira.py                     # Jira REST v3 client (Basic auth) + thread-id derivation
agent/utils/adf.py                      # Markdown -> Atlassian Document Format converter
agent/tools/jira_get_issue.py           # Get Jira issue by key
agent/tools/jira_search_issues.py       # Search issues via JQL
agent/tools/jira_get_comments.py        # Get issue comments
agent/tools/jira_add_comment.py         # Add comment (Markdown -> ADF)
agent/tools/jira_transition_issue.py    # Move issue to a target column by name
agent/tools/openspec_propose.py         # Generate OpenSpec artifacts
agent/tools/openspec_status.py          # Read OpenSpec status
agent/tools/openspec_validate.py        # Validate spec completeness
agent/tools/openspec_archive.py         # Archive completed spec
agent/tools/request_self_review.py      # Trigger reviewer graph
agent/tools/update_canonical_docs.py    # Update docs post-merge
agent/jira_poller.py                    # 60s tick: launch new threads, wake parked ones
agent/tools/jira_park_at_gate.py        # Comment, move card, end the run at a gate
agent/utils/console_events.py           # Push tick/queue/run/log events to the console
agent-console/app.py                    # Flask console: state, queue, execution log
agent-console/store.py                  # In-memory state + log ring buffer
agent-console/templates/index.html      # Single page, 2s polling
```

### Modified Files (~8)

```
agent/server.py                         # Add Jira + OpenSpec tools, middleware
agent/tools/__init__.py                 # Register new tools
agent/middleware/__init__.py            # Register new middleware
agent/prompt.py                         # Add workflow instructions
agent/resources/default_prompt.md       # Add OpenSpec + Jira workflow sections
agent/graphs/agent.py                   # No changes needed (delegates to server.py)
langgraph.json                          # No changes needed (same agent graph)
pyproject.toml                          # No changes needed (deps already present)
```

## Risks / Trade-offs

- **Polling latency**: up to 60s between a human moving a card and the agent resuming. Accepted — the gate is a human decision, not a real-time interaction.
- **Jira API rate limits**: the poller issues two JQL queries per tick regardless of load. Mitigation: bounded, predictable call volume; exponential backoff on 429.
- **Poller is a single point of failure**: if the tick stops, every parked thread stays parked silently. Mitigation: the console surfaces "last tick Ns ago" as its primary health signal, and the tick timestamp is the one thing it always displays.
- **Sandbox loss across a long gate**: a thread parked for hours may find its sandbox gone on resume. Mitigation: the agent commits before parking, so the branch survives; on `SandboxUnreachableError` the run reports to Jira instead of silently restarting.
- **Jira credential availability**: If `JIRA_EMAIL` / `JIRA_API_TOKEN` are unset, the Jira tools are omitted from the toolset and the system prompt states that Jira integration is unavailable. Mitigation: same graceful-degradation pattern as Corridor/Datadog.
- **Markdown is not a valid Jira comment body**: Jira REST v3 requires ADF (Atlassian Document Format), not Markdown. LLM-generated Portuguese text reliably contains curly quotes, em-dashes and non-breaking spaces that Jira rejects with `INVALID_INPUT` / HTTP 400 — a failure already observed and worked around in the Sensedia AI Gateway project. Mitigation: `agent/utils/adf.py` converts Markdown to ADF and normalises those characters before every comment call.
- **Transition resolution**: `POST /rest/api/3/issue/{key}/transitions` takes a transition **id**, not a column name, so every move is two calls (`GET transitions` → resolve → `POST`). Mitigation: resolution lives inside the client; the agent and middleware address columns by name. Global workflow transitions (see Column Configuration) keep the resolution total.
- **Console is an extra service**: the agent pushes events to it over HTTP. Mitigation: every push is fire-and-forget with a short timeout and a swallowed failure — a console that is down or slow must never affect a run. The console holds no workflow state; Jira remains the system of record and LangSmith holds the traces.
- **OpenSpec artifact drift**: Specs generated during planning may diverge from actual implementation. Mitigation: Auto-review loop validates implementation against spec; reviewer graph cross-references.
- **Column name coupling**: The middleware depends on exact Jira column names. Mitigation: Column names are configurable via environment variables with documented defaults.
- **Single agent context window**: Large codebases may exceed context limits during combined planning + implementation. Mitigation: Subagents (`task` tool) for parallel work; plan mode encourages focused scope.
