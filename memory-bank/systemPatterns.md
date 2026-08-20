# System Patterns — Arquitetura do Sistema

## 1. Cinco Grafos LangGraph

Declarados em `langgraph.json` e servidos juntos por `langgraph dev`:

| Grafo | Entrypoint | Papel |
|---|---|---|
| `agent` | `agent/server.py:1008` `get_agent` | Agente principal de codificação (Jira/Slack/Linear/GitHub) |
| `reviewer` | `agent/reviewer.py:1328` `get_reviewer_agent` | Revisor de PR read-only (findings + `publish_review`) |
| `analyzer` | `agent/analyzer.py:165` `get_analyzer` | Aprende estilo de review por repo (bootstrap/continual) |
| `chat` | `agent/chat.py:180` `get_chat_agent` | Chat sobre PR sem sandbox |
| `scheduler` | `agent/scheduler.py:38` `get_scheduler` | Orquestra cron do poller + reconcile |

O `scheduler` (`agent/scheduler.py:26-30`) roteia por `task`: `"jira_poll"` → `jira_poller.tick()`; `"reconcile"` → `reconcile_stale_runs()`. O cron do poller usa esse grafo (`agent/poller_cron.py:21-22`, `POLLER_CRON_GRAPH = "scheduler"`, input `{"task": "jira_poll"}`).

## 2. Sandbox Lifecycle

- `SANDBOX_BACKENDS` (`agent/utils/sandbox_state.py`) é um dict em processo chaveado por `thread_id`; o metadata persiste `sandbox_id` entre processos.
- `ensure_sandbox_for_thread` trata 3 casos:
  1. Sandbox em cache → ping (`echo ok`) + refresh do proxy GitHub.
  2. Metadata tem id mas sem cache → reconectar + refresh do proxy.
  3. Sem sandbox → criar e persistir o id.
- Um sandbox existente inalcançável levanta `SandboxUnreachableError` (em vez de ser substituído — substituir destruiria trabalho não commitado). O agente principal captura isso em `PrepareAgentRunMiddleware` e notifica o usuário.
- `allow_replacement=True` é passado **apenas** pelo reviewer (`agent/reviewer.py`), cujo sandbox só contém um checkout que `prepare_review_repo` re-deriva a cada run.
- Para `SANDBOX_TYPE=langsmith` (padrão), toda criação/refresh chama `_configure_github_proxy` com um token de instalação do GitHub App — o proxy injeta Basic/Bearer auth para `github.com`/`api.github.com`, permitindo `GH_TOKEN=dummy gh ...` sem armazenar tokens reais.
- Factory: `agent/utils/sandbox.py:create_sandbox` (`SANDBOX_FACTORIES`, `sandbox.py:13-19`).

## 3. Middleware Stack

### Server (agente principal) — 19 camadas (`agent/server.py:1220-1267`, ordem real)

1. `PrepareAgentRunMiddleware` (snapshot do worktree, resolução de token/modelo)
2. `DynamicToolMiddleware` (condicional)
3. `SanitizeToolInputsMiddleware`
4. `ModelCallLimitMiddleware`
5. `ToolErrorMiddleware`
6. `SubdirAgentsReadMiddleware`
7. `ToolRetryMiddleware` (retry de `task`/subagentes)
8. `PullRequestCreationGuardMiddleware`
9. `refresh_github_proxy_before_model`
10. `check_message_queue_before_model`
11. `SlackAssistantStatusMiddleware`
12. `TimeoutWrapupMiddleware`
13. `notify_step_limit_reached`
14. `notify_jira_on_unparked_termination`
15. `ModelFallbackMiddleware` (condicional)
16. `PlanModeMiddleware` (condicional)
17. `SanitizeFireworksMessagesMiddleware`
18. `SanitizeThinkingBlocksMiddleware`
19. `ModelCallTimeoutMiddleware` (innermost)

### Reviewer — 13 camadas (`agent/reviewer.py:1404-1424`, ordem real)

1. `PrepareReviewerRunMiddleware`
2. `SanitizeToolInputsMiddleware`
3. `ModelCallLimitMiddleware`
4. `ToolErrorMiddleware`
5. `refresh_github_proxy_before_model`
6. `check_message_queue_before_model`
7. `SlackAssistantStatusMiddleware`
8. `TimeoutWrapupMiddleware`
9. `SanitizeFireworksMessagesMiddleware`
10. `SanitizeThinkingBlocksMiddleware`
11. `RepairOrphanedToolCallsMiddleware`
12. `ModelCallTimeoutMiddleware`
13. `settle_review_check_on_exit`

### Middlewares definidos mas NÃO conectados

Definidos em `agent/middleware/` e exportados em `agent/middleware/__init__.py`, porém ausentes da stack do server:
- `ensure_no_empty_msg` (`agent/middleware/ensure_no_empty_msg.py:78`)
- `SandboxCircuitBreakerMiddleware` (`agent/middleware/sandbox_circuit_breaker.py:253`)
- `WorkflowPushGuardMiddleware` (`agent/middleware/workflow_push_guard.py:516`)

## 4. Model Routing

- `agent/routing` decide modelo + esforço por **papel** (`AgentRole`, `agent/routing/roles.py:15-45`): `jira_triage`, `python_harness`, `spec_author`, `spec_reviewer`, `spec_adjuster`, `coding_agent`, `code_adjuster`, `openspec_verifier`, `code_reviewer`, `diff_grouping`, `review_chat`, `style_analyzer`, `docs_agent`, `archive_agent`, `escalation_agent` (15 papéis).
- `resolve_model(role, complexity, retry_count, workflow_context)` retorna `ModelConfig(model, effort, reason)`.
- Papéis mecânicos → Haiku sem esforço; autorização/verificação → Sonnet/high; revisão/escalada → Opus/high.
- `coding_agent`/`code_adjuster` começam em Sonnet/medium e escalam para Opus/high após 2 falhas, complexidade `CRITICAL`, ou `HIGH` com sinal de risco.
- Complexidade é determinística (`agent/routing/complexity.py`, tiers `low/medium/high/critical`), sem chamada de LLM.
- Nada fora de `agent/routing` escolhe modelo. Telemetria em `agent/routing/telemetry.py`; custo agregado por card em `agent/routing/usage_store.py`.

## 5. Relações entre Componentes

```
jira_poller (60s) ──► dispatch_agent_run ──► agent (server.py)
      ▲                                          │
      │                                          ▼
      └────────── humano aprova ◄── gates ◄── PR aberto
                                                
reviewer ──consome estilo──► analyzer (bootstrap/continual)
scheduler ──orquestra──► poller (jira_poll) + reconcile (stale runs)
completion webhook (/webhooks/run-complete) ──► fecha o ciclo do run
```

- **jira_poller → dispatch → agent**: o poller detecta a coluna e despacha o run (`agent/jira_poller.py:436` → `agent/dispatch.py:189`).
- **reviewer consome estilo do analyzer**: o analyzer emite um prompt de estilo por repo (`save_review_style_prompt`), usado como apêndice no prompt do reviewer.
- **scheduler orquestra poller + reconcile**: `agent/scheduler.py:26-30` roteia `jira_poll` e `reconcile`.
- **completion webhook fecha o ciclo**: `agent/completion.py:196` registra telemetria e posta a resposta final do run.
