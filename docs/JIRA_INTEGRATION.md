# Jira-Driven Coding Agent

Extends Open SWE with Jira as a trigger and context source, OpenSpec as the specification layer, and a column-driven human approval workflow. See `openspec/changes/jira-openspec-coding-agent/` (proposal, design, specs, tasks) for the full design record — this document is the operator-facing "how do I run this" companion.

## 1. Jira board setup

Create (or reuse) a Jira project with these 11 columns. Three are Jira defaults kept as-is; the other eight are created for this workflow. Names are configurable (see [Environment variables](#2-environment-variables)) — the table shows the defaults.

| # | Column (env var) | Default name | Who moves it | Meaning |
|---|---|---|---|---|
| 1 | `JIRA_COLUMN_TRIGGER` | `BACKLOG` | Human | Trigger — agent starts |
| 2 | `JIRA_COLUMN_IN_PROGRESS` | `In Progress` | Agent | Agent is working |
| 3 | `JIRA_COLUMN_SPEC_REVIEW` | `Em Revisão de Spec` | Agent | Parked — waiting for spec approval |
| 4 | `JIRA_COLUMN_SPEC_APPROVED` | `Spec Aprovada` | Human | Planning approved |
| 5 | `JIRA_COLUMN_ADJUST_SPEC` | `Ajustar Spec` | Human | Spec needs adjustments |
| 6 | `JIRA_COLUMN_CODE_REVIEW` | `Em Code Review` | Agent | Parked — waiting for code review |
| 7 | `JIRA_COLUMN_CODE_APPROVED` | `Code Review Aprovado` | Human | Code approved |
| 8 | `JIRA_COLUMN_ADJUST_CODE` | `Ajustar Code` | Human | Code needs adjustments |
| 9 | `JIRA_COLUMN_MERGE` | `Em Merge` | Agent | PR open, waiting for merge |
| 10 | `JIRA_COLUMN_MERGED` | `Mergeado` | Human | PR merged |
| 11 | `JIRA_COLUMN_DONE` | `Done` | Agent | Workflow complete |

**Workflow transitions — required.** The Jira workflow MUST allow every status to transition to every other status ("Allow all statuses to transition to this one", set on each status individually). The agent's path through the board is not linear — it jumps from `In Progress` to three different targets, and several columns route back to it. Without global transitions, an out-of-sequence move gets HTTP 400 instead of succeeding.

**`BACKLOG` as the trigger is a deliberate, accepted choice** (design.md Decision 11), not an oversight: any card landing there starts a run, including cards filed for triage/discussion or by monitoring integrations. If that turns out to be noisy in practice, scope the poller's trigger JQL — see `JIRA_TRIGGER_JQL_FILTER` below — rather than adding a column.

## 2. Environment variables

Required for the Jira client (`agent/utils/jira.py`) to activate at all; omitted, every Jira tool call returns a soft `{"error": "..."}` instead of failing the run:

| Variable | Purpose |
|---|---|
| `JIRA_BASE_URL` | e.g. `https://yourorg.atlassian.net` |
| `JIRA_EMAIL` | Account email for Basic auth |
| `JIRA_API_TOKEN` | [Atlassian API token](https://id.atlassian.com/manage-profile/security/api-tokens) for that account |

Poller and column configuration (all optional, defaults shown):

| Variable | Default | Purpose |
|---|---|---|
| `JIRA_PROJECT_KEY` | `SSAI` | The Jira project the poller queries |
| `JIRA_POLL_INTERVAL_SECONDS` | `60` | Poller tick interval. LangGraph crons have minute granularity — values under 120 collapse to "every minute"; others round down to whole minutes |
| `JIRA_COLUMN_*` | see the board table above | Override any of the 11 column names. Read by both the poller (which only queries the trigger + 3 gate columns by name) and the system prompt (all 11) — override consistently, both sides pick up the same env var |
| `JIRA_TRIGGER_JQL_FILTER` | unset | Extra JQL AND-ed onto the trigger query (e.g. `issuetype = Bug`) — the Decision 11 mitigation if `BACKLOG`-as-trigger gets noisy. Off by default |
| `JIRA_FA_ALERT_LABEL` | `fa-alert` | Best-effort label used only to split human- vs. automation-filed cards in shadow-mode/volume logging — this is a guess; confirm the real label your monitoring integration uses |
| `JIRA_POLLER_SHADOW_MODE` | unset (off) | `1`/`true`/`yes` to log what the poller *would* trigger without launching any threads |
| `JIRA_POLLER_PAUSED` | unset (off) | `1`/`true`/`yes` to stop new/resumed launches without tearing down the tick itself — the fast manual brake |

Agent console (optional; see `agent-console/README.md` for the console's own setup):

| Variable | Purpose |
|---|---|
| `AGENT_CONSOLE_URL` | Base URL of a running `agent-console` instance. Unset, every push is skipped silently — the console is optional infrastructure and a run is never affected by its absence |

## 3. Complete workflow

```
TRIGGER: card enters BACKLOG (human)
  |
  v
PASSO 1  Collect Jira context (issue, description, acceptance criteria, comments)
  |
  v
PASSO 2  Prepare environment (clone, branch feat/spec-JIRA-XXXX-descricao-curta)
  |
  v
PASSO 3  Analyze code + generate OpenSpec artifacts (openspec-explore, openspec-propose skills)
  |
  v
PASSO 4  Self-review the spec (guidance: ~3 cycles, not enforced)
  |    pass or exhausted -> either way, park
  v
GATE 1   jira_park_at_gate(Em Revisão de Spec)  <-- run ends, no blocking
  |
  |  (poller notices the column change on its next tick)
  v
  Spec Aprovada (human approved)  -->  resume at PASSO 5
  Ajustar Spec (human requested changes, with a comment)  -->  resume at PASSO 3
  |
  v
PASSO 5  Implement (exit plan mode, edit/test/lint/commit)
  |
  v
PASSO 6  Self-review the code (same guidance)
  |
  v
PASSO 7  request_self_review — open at least a draft PR first (the reviewer graph
  |      needs a real PR; see design note below), then trigger it
  |    PASS -> continue      CHANGES_REQUIRED -> back to PASSO 5 (not a gate)
  v
GATE 2   jira_park_at_gate(Em Code Review)
  |
  |  (poller notices the column change)
  v
  Code Review Aprovado  -->  resume at PASSO 8
  Ajustar Code (with comment)  -->  resume at PASSO 5
  |
  v
PASSO 8  Final tests + push + finalize the PR (undraft) -> Em Merge
  |
  v
GATE 3   jira_park_at_gate(Em Merge)
  |
  |  (poller notices the column change)
  v
  Mergeado (human merged)  -->  resume at PASSO 9
  |
  v
PASSO 9  Archive OpenSpec artifacts (openspec_archive)
  |
  v
PASSO 10 Update canonical docs — separate PR, best-effort (failure doesn't block)
  |
  v
PASSO 11 Finalize: Jira comment, transition to Done, LangSmith metadata
```

**Design note on PASSO 7/8 ordering:** the reviewer graph has no path for reviewing a diff that isn't already a real GitHub PR — it fetches the diff via `base_sha`/`head_sha` from PR metadata. So in practice the agent opens at least a draft PR *before* calling `request_self_review` (PASSO 7), and PASSO 8 finalizes that same PR rather than creating a second one. See `openspec/changes/jira-openspec-coding-agent/tasks.md` §7.2 for the full reasoning.

## 4. The console (optional)

A small read-only Flask page reporting poller health, the card queue, active/parked/dead runs, and a live execution log. It's a standalone app outside the main `agent` package — see `agent-console/README.md` for setup and its own "known gaps" (no auth, no console-side pause button).

## 5. Troubleshooting

**Jira tools return `"error": "Jira credentials are not configured"` for every call.** `JIRA_BASE_URL` / `JIRA_EMAIL` / `JIRA_API_TOKEN` aren't set on the LangGraph server process. This is the intended graceful-degradation path (same pattern as Linear) — the run continues, the system prompt's Jira sections are still gated on `jira_issue_key` being present in `configurable`, independent of credentials, so a misconfigured deployment fails at the API call, not silently.

**A card sits in `BACKLOG` and nothing happens.** Check: is the poller cron actually registered and ticking? `agent-console`'s status header shows "seconds since last tick" as its primary signal — if it says `no_tick_ever` or `degraded_poller`, the cron either never registered (check server startup logs for "Failed to register the Jira poller cron") or stopped ticking. Also check `JIRA_POLLER_PAUSED` isn't set.

**A card sits at a gate (`Em Revisão de Spec` / `Em Code Review` / `Em Merge`) after the human already moved it.** The poller only re-triggers on the *next* tick (up to `JIRA_POLL_INTERVAL_SECONDS` of latency — irrelevant for a human-speed approval, but worth knowing). If it's been longer than that, check the console for `dead` status on that run: it means a runtime limit (model-call cap, or a `timeout_wrapup`-driven finish that never called `jira_park_at_gate`) ended the run without reaching a gate — the Jira comment `agent/middleware/notify_jira_unparked.py` posts names which limit fired.

**`jira_transition_issue` / `jira_park_at_gate` fails with "No transition to column '...'".** Either the column name doesn't match your board exactly (check `JIRA_COLUMN_*` overrides are consistent between the poller/prompt and the actual board), or the workflow's global transitions aren't configured (see [Jira board setup](#1-jira-board-setup)) — without them, some column-to-column moves simply don't exist as transitions. The error message lists every transition actually available from the card's current state.

**A run picked up a card nobody meant to trigger.** This is the accepted risk in design.md Decision 11 (`BACKLOG` triggers unconditionally, including triage cards and monitoring-filed bugs). Mitigate with `JIRA_TRIGGER_JQL_FILTER` (scope by issue type, label, or assignee) rather than restructuring the board — it's a configuration change, not a redesign.

**ADF / comment posting fails with `INVALID_INPUT` or HTTP 400.** `agent/utils/adf.py` normalizes curly quotes, em/en dashes, and non-breaking spaces before every comment — if this still happens, the comment body likely contains a Markdown construct outside the supported subset (headings, paragraphs, lists, code blocks, links, inline code/bold/italic); simplify the comment content.
