# Model Router Backend + Agent Roles

## What & Why
Replace the current global model/effort configuration (a single `model` + `effort` pair stored in `OperationalConfig` and driven by the console UI) with a centralized automatic Model Router that assigns the right model and effort to each named agent role. This is a prerequisite for both observability and correct multi-model execution.

Currently `config_store.py` holds `("shadow_mode", "model", "effort", "polling_interval_minutes")` as `CONFIG_FIELDS`, and `server.py`/`reviewer.py` read per-thread `configurable["agent_model_id"]`/`["agent_effort"]` or team defaults. The console UI exposes a global Model and Effort selector. All of this becomes obsolete once routing is per-role.

## Done looks like
- A single `agent/routing/` package exposes `resolve_model(agent_role, complexity, retry_count, workflow_context) → ModelConfig(model, effort, reason)`.
- Agent roles are defined as a shared enum/constants (e.g. `jira_triage`, `python_harness`, `spec_author`, `spec_reviewer`, `spec_adjuster`, `coding_agent`, `code_adjuster`, `openspec_verifier`, `code_reviewer`, `docs_agent`, `archive_agent`, `escalation_agent`).
- A `model_capabilities` registry records which models support effort and which valid effort levels exist; `resolve_model` never sends effort to a model that doesn't support it.
- A `complexity_classifier` returns `LOW | MEDIUM | HIGH | CRITICAL` using deterministic signals (files affected, migration, auth, retry count, etc.) without spending an LLM call.
- Default routing per role:
  - `jira_triage`, `python_harness`, `archive_agent`: Haiku, no effort
  - `spec_author`, `spec_adjuster`: Sonnet, high
  - `spec_reviewer`: Opus, high
  - `coding_agent`, `code_adjuster`: Sonnet, medium (escalates to high or Opus per retry/complexity)
  - `openspec_verifier`: Sonnet, high
  - `code_reviewer`: Opus, high
  - `docs_agent`: Haiku for mechanical operations, Sonnet for semantic review
  - `escalation_agent`: Opus, high
- Escalation logic: `coding_agent` and `code_adjuster` escalate to Opus after 2 failed attempts or when `complexity >= HIGH` with specific signals (auth, concurrency, migration, security); `escalation_reason` is always recorded.
- `server.py` and `reviewer.py` call `resolve_model` instead of reading from `configurable["agent_model_id"]`/`["agent_effort"]` or OperationalConfig.
- `config_store.py` `CONFIG_FIELDS` drops `model` and `effort`; `_validate` no longer validates them; `app.py`/`runtime_bridge.py` no longer call `apply_model_effort`.
- Existing per-thread `configurable` keys `agent_model_id`/`agent_effort` are removed from the code paths that set/read them (no dead config).
- A new read-only GET `/api/config/routing` endpoint (or equivalent following the existing API naming pattern) returns the full routing table so the frontend can render it.
- Unit tests cover every role mapping, escalation thresholds, complexity signals, model capability guards, and missing-effort scenarios.

## Out of scope
- Frontend UI changes (separate task).
- LangSmith telemetry instrumentation (separate task).
- Any manual override mechanism (explicitly deferred per requirements).
- Changing the LangGraph graph topology.

## Steps
1. **Create `agent/routing/` package** — Define `AgentRole` (string enum or typed constants), `ComplexityTier` enum, and `ModelConfig` dataclass with fields `model`, `effort`, `reason`. Keep imports minimal to avoid circular deps.
2. **Model capabilities registry** — In `agent/routing/capabilities.py`, derive per-model capability facts (effort support, available efforts) from the existing `agent/dashboard/options.py` catalog so there is one source of truth; add a helper that returns the safe effort for a given model (or `None` if unsupported).
3. **Complexity classifier** — In `agent/routing/complexity.py`, implement deterministic `classify_complexity(signals: dict) → ComplexityTier` using signals: files_changed, has_migration, has_auth_change, has_security, retry_count, review_return_count, etc. No LLM call.
4. **Model Router** — In `agent/routing/router.py`, implement `resolve_model(agent_role, complexity, retry_count, workflow_context) → ModelConfig`. Encode the default table per role; apply escalation rules for `coding_agent`/`code_adjuster`; guard effort against `model_capabilities`; return a `reason` string for every decision.
5. **Wire into `server.py`** — Replace the `configurable["agent_model_id"]`/`["agent_effort"]` read path in `get_agent` (around lines 1046-1065) and team-default resolution with a `resolve_model(AgentRole.CODING_AGENT, ...)` call. Pass complexity signals gathered from thread metadata (retry counts, previous failures).
6. **Wire into `reviewer.py`** — Replace `reviewer_model_id`/`reviewer_reasoning_effort` reads (lines 1336-1364) and grouping model resolution (lines 864-889) with `resolve_model` calls for `spec_reviewer`, `code_reviewer`, etc.
7. **Wire into `scheduler.py`/`analyzer.py`** — Ensure any triage or harness invocations use `resolve_model` for `jira_triage` / `python_harness` roles; remove direct model references if present.
8. **Remove global model/effort from OperationalConfig** — Drop `"model"` and `"effort"` from `CONFIG_FIELDS` in `config_store.py`; remove validation, seeding, and serialization of those two fields; update `app.py` to stop reading/writing them; remove `apply_model_effort` from `runtime_bridge.py`.
9. **Routing table endpoint** — Add `GET /api/config/routing` (following the existing route prefix pattern in `agent-console/app.py`) that calls `resolve_model` for each role at baseline complexity/zero retries and returns a JSON list of `{role, model, effort, effort_supported}`.
10. **Tests** — Write unit tests in `tests/` covering: each role's default mapping, escalation on `retry_count >= 2`, `complexity=HIGH` escalation signals, effort guarded when model doesn't support it, `effort=None` returned as `None` not a string.

## Relevant files
- `agent-console/config_store.py`
- `agent-console/app.py`
- `agent-console/runtime_bridge.py`
- `agent/dashboard/options.py`
- `agent/utils/model.py`
- `agent/server.py`
- `agent/reviewer.py`
- `agent/scheduler.py`
- `agent/utils/tracing.py`
