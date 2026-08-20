# LangSmith Telemetry + Observability API

## What & Why
Instrument every agent run with standardized metadata so tokens, costs, and routing decisions can be aggregated per Jira card. Today `agent/utils/tracing.py` only sets the LangSmith project name; no run-level metadata (jira_issue_key, agent_role, model, effort, complexity, etc.) is attached. The console's `dispatch.py` already passes `metadata={}` to `runs.create` — we need to fill that dict consistently.

The aggregation unit is **jira_issue_key + thread_id** because a single card can span multiple Human-in-the-Loop runs across different trace IDs.

## Done looks like
- Every agent execution carries a `RunMetadata` payload:  
  `{jira_issue_key, thread_id, agent_role, workflow_stage, model, effort, routing_mode="automatic", complexity_tier, routing_reason, start_time}`.
- Post-run, `input_tokens`, `output_tokens`, `total_tokens`, `cost` (or `estimated_cost`) are collected from the LangSmith run response and logged locally.
- A data-availability assessment is documented (which fields come from LangSmith directly vs need instrumentation vs unavailable) before any new instrumentation is added.
- Token and cost data are collected **after** run completion, not streamed per token.
- A local in-process cache (Python dict or lightweight store) accumulates `JiraUsageSummary` and `AgentUsageSummary` per card; this is a read-acceleration layer, not a replacement for LangSmith.
- A backend pricing table (in `agent/routing/` or `agent/dashboard/`) covers Haiku/Sonnet/Opus input/output/cache token costs with a `last_updated` date; cost estimation falls back to this when LangSmith doesn't return cost directly.
- The following API endpoints are added to `agent-console/app.py` (following existing route patterns):
  - `GET /api/observability/live` — active agent executions (what's running right now, sourced from in-memory run registry).
  - `GET /api/observability/routing` — current routing table (delegates to the routing endpoint from Task 1, or is the same route).
  - `GET /api/observability/usage` — aggregate tokens/cost for today across all models/roles.
  - `GET /api/observability/cards/<jira_issue_key>/usage` — total usage for one card (all runs aggregated by thread_id).
  - `GET /api/observability/cards/<jira_issue_key>/timeline` — ordered list of agent runs for that card with timestamps, role, model, effort, tokens, cost, status.
- LangSmith credentials (`LANGSMITH_API_KEY`) are never returned by any endpoint; the backend calls LangSmith SDK internally.
- Execution Log events are emitted for routing decisions and usage updates (e.g. `routing: spec_reviewer → Opus/high`, `usage: coding_agent 18,420 tokens`, `cost: SSAI-88 updated`) — not per-token.
- Tests cover: metadata fields present in traces, aggregation by jira_issue_key, aggregation by model, aggregation by agent_role, multi-run card, cost-unavailable fallback, no credentials leaked.

## Out of scope
- Frontend UI components (separate task).
- Streaming token counts during generation.
- Replacing or modifying LangSmith's own storage.
- Any mutation of Jira cards from observability data.

## Steps
1. **Data-availability assessment** — Before writing new code, read the LangSmith SDK docs patterns already present in `agent/utils/langsmith.py` and `agent/review/trace_context.py` to classify each required field (`jira_issue_key`, `thread_id`, `agent_role`, `model`, `effort`, `input_tokens`, `output_tokens`, `cost`, etc.) as AVAILABLE_NOW / AVAILABLE_WITH_METADATA / REQUIRES_INSTRUMENTATION / NOT_AVAILABLE. Document findings as comments in a new `agent/routing/telemetry.py` header.
2. **`RunMetadata` schema** — Define a `RunMetadata` dataclass/TypedDict in `agent/routing/telemetry.py` with all required fields. Add a builder function `build_run_metadata(agent_role, thread_id, jira_issue_key, complexity_tier, routing_config) → RunMetadata` that takes a `ModelConfig` from the router and assembles the dict for passing to LangSmith.
3. **Inject metadata into dispatch** — In `agent/dispatch.py`, update `dispatch_agent_run` to accept and forward `RunMetadata`; populate `run_config["metadata"]` from it. Ensure child runs inherit `jira_issue_key`, `thread_id`, `agent_role`, `model`, `workflow_stage` by passing them through LangGraph's `RunnableConfig` metadata propagation.
4. **Post-run usage collection** — After each run completes (in the async run-completion path already present in `dispatch.py` or `server.py`), fetch token counts from the LangSmith run result (via the SDK's `run.prompt_tokens`, `run.completion_tokens`, `run.total_tokens`, `run.total_cost` if available). Feed into the local cache.
5. **Pricing table** — Add `agent/routing/pricing.py` with a dict mapping model ID → `{input_per_mtok, output_per_mtok, cache_read_per_mtok, updated}`. Add `estimate_cost(model_id, input_tokens, output_tokens) → float | None`. This is only used when LangSmith doesn't return cost directly.
6. **Local usage cache** — In `agent/routing/usage_store.py`, implement thread-safe in-memory `UsageStore` with methods: `record_run(run_metadata, usage_data)`, `get_card_summary(jira_issue_key) → JiraUsageSummary`, `get_card_timeline(jira_issue_key) → list[RunEntry]`, `get_today_usage() → DailyUsage`. Keep a bounded window (e.g. last 500 run entries) to prevent unbounded growth.
7. **Active-agent registry** — Add a lightweight `ActiveAgentRegistry` (in `agent/routing/active_agents.py`) that tracks running executions: `start(run_id, metadata)` / `finish(run_id, status, usage)` / `list_active() → list`. Hook `start`/`finish` into the dispatch and completion paths.
8. **Observability API endpoints** — Add the five `GET /api/observability/…` routes to `agent-console/app.py`. Each endpoint reads from `UsageStore` and `ActiveAgentRegistry`; the LangSmith SDK is called only for historical backfill or timeline reconstruction, never synchronously on every browser request.
9. **Execution Log events** — Emit structured log lines through the existing Execution Log mechanism for: routing decisions, run completions with token totals, cost updates per card, and escalation events. Avoid per-token noise.
10. **Tests** — Write tests in `tests/` covering: metadata fields in trace dict, token aggregation across two runs of the same card, cost estimation fallback, no-credentials-in-response, cost-unavailable shows `null` not `0.0`.

## Relevant files
- `agent/dispatch.py`
- `agent/utils/tracing.py`
- `agent/utils/langsmith.py`
- `agent/review/trace_context.py`
- `agent/server.py`
- `agent/reviewer.py`
- `agent-console/app.py`
- `agent/dashboard/options.py`
