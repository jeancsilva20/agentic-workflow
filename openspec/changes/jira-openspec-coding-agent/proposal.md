## Why

Engineering teams need a coding agent that consumes Jira issues, generates structured specifications via OpenSpec, implements code in isolated sandboxes, and submits pull requests — all governed by human approval gates mapped to Jira column transitions. The Open SWE framework already provides sandbox infrastructure, GitHub integration, middleware, and a reviewer graph. This change extends it with Jira as the primary trigger and context source, OpenSpec as the specification layer, and a column-driven approval workflow that keeps humans in control at three checkpoints: spec review, code review, and merge.

## What Changes

- **Jira REST Integration**: Add a Jira Cloud REST v3 client (Basic auth) plus thin agent tools for get issue, JQL search, comments and column transitions, following the existing `agent/utils/linear.py` + `agent/tools/linear_*.py` pattern.
- **OpenSpec Integration**: Add tools for generating, validating, and archiving OpenSpec artifacts (`proposal.md`, `design.md`, `specs/*/spec.md`, `tasks.md`) directly from the sandbox.
- **Column-Driven Approval Workflow**: A 60s poller in the existing `scheduler` graph launches a thread per card in the trigger column and re-triggers parked threads when their column changes. The agent ends its run at each gate rather than blocking, so a human approval can take hours without burning the run's time budget.
- **Agent Console**: A small Flask page showing whether the agent is working, waiting on a human, or dead — plus the card queue and a live execution log.
- **Auto-Review Loops**: The agent performs self-review of specs and code before requesting human approval. The prompt targets about 3 correction cycles, but this is guidance rather than an enforced limit — what is required is that the agent always hands over with a comment naming what it could not resolve.
- **Reviewer Graph Integration**: The existing Open SWE reviewer graph is invoked after implementation to produce structured findings before human code review.
- **Canonical Docs Update**: After merge, the agent updates living specification docs and creates a separate PR for documentation changes.
- **LangSmith Metrics**: All workflow metrics (total time, review cycles, findings, final status) are recorded in LangSmith traces.
- **Branch Convention**: Feature branches follow `feat/spec-JIRA-XXXX-descricao-curta`.

## Capabilities

### New Capabilities

- `jira-integration`: Connect to Jira Cloud via its REST v3 API, read issues and comments, transition cards between columns by name, and post ADF-formatted updates.
- `openspec-workflow`: Generate, validate, and archive OpenSpec artifacts (proposal, design, specs, tasks) within the agent sandbox.
- `column-approval-gate`: Detect trigger cards and resume parked threads by polling Jira column state on a 60s tick, covering three human approval checkpoints (spec review, code review, merge) without blocking a run.
- `agent-console`: A read-only Flask page reporting agent status, poller health, the card queue, active runs with time-parked, and a live execution log.
- `auto-review-loop`: Self-review specs and code, iterating a small number of times as guided by the prompt, and always handing over with a summary of what remains unresolved.
- `canonical-docs-update`: After merge, update living specification documents and create a separate PR for documentation changes.

### Modified Capabilities

<!-- No existing specs to modify — this is a greenfield extension of Open SWE -->

## Impact

- **New files**: ~15 new Python modules across `agent/tools/`, `agent/utils/` and `agent/`, plus a standalone `agent-console/` Flask app (3 files)
- **Modified files**: ~9 existing files including `agent/server.py`, `agent/scheduler.py`, `agent/tools/__init__.py`, `agent/prompt.py`, and `agent/resources/default_prompt.md`
- **Dependencies**: none new in Open SWE — `httpx` is already used by `agent/utils/linear.py`. The console needs `flask`. Requires `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` and `AGENT_CONSOLE_URL` (environment variables)
- **No breaking changes**: All additions follow existing Open SWE patterns; no existing functionality is removed or altered
- **Jira board**: Requires 11 columns and a workflow configured with global transitions (documented in design.md). The board does not exist yet and will be created for this workflow.
