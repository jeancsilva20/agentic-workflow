# Camada transversal: Stack de Middlewares

Os middlewares rodam ao redor de cada chamada de modelo/tool do agente. A ordem
é significativa: o primeiro da lista é o **mais externo** (roda primeiro na
entrada, último na saída) e o último é o **mais interno**.

Tipos de hook usados nesta stack:

- `awrap_model_call` — envolve a chamada ao modelo (async).
- `awrap_tool_call` / `wrap_tool_call` — envolve a chamada a uma tool.
- `before_model` — roda antes da chamada ao modelo.
- `after_model` — roda depois da chamada ao modelo.
- `before_agent` — roda antes do agente iniciar.
- `after_agent` — roda depois do agente terminar.

---

## Server — `agent/server.py:1220-1266` (mais externo → mais interno)

| # | Middleware | Arquivo | Hook | Objetivo |
|---|---|---|---|---|
| 1 | `PrepareAgentRunMiddleware` | `agent/middleware/prepare_run.py` | `awrap_model_call` | Prepara a execução: resolve token GitHub, garante/cria o sandbox da thread, aplica `git config --global`, snapshot do worktree em `refs/open-swe/turns/<msg-id>`. Recebe `thread_id`, `config`, `profile_login`, `model_id`, `effort`, `source`, `user_email`, `linear_project_id`, `linear_issue_number`, `create_prs`, `draft_prs`, `plan_mode`, `corridor_enabled`, `jira_issue_key`. |
| 2 | `DynamicToolMiddleware` *(opcional)* | `agent/middleware/dynamic_tools.py` | `awrap_model_call`, `awrap_tool_call` | Carrega tools de integração dinâmica (grupos de tools) somente quando solicitado, via `load_integration_tools`. Só entra na lista se `dynamic_tool_middleware` existir. |
| 3 | `SanitizeToolInputsMiddleware` | `agent/middleware/sanitize_tool_inputs.py` | `awrap_tool_call` | Normaliza/limpa entradas das tools antes que cheguem à tool. |
| 4 | `ModelCallLimitMiddleware` | (do `langchain.agents.middleware`) | — | Limita chamadas de modelo a `MODEL_CALL_RECURSION_LIMIT` (~metade de `DEFAULT_RECURSION_LIMIT`), com `exit_behavior="end"`. |
| 5 | `ToolErrorMiddleware` | `agent/middleware/tool_error_handler.py` | `awrap_tool_call` | Captura exceções de tools e as transforma em mensagens de tool. |
| 6 | `SubdirAgentsReadMiddleware` | `agent/middleware/subdir_agents.py` | `awrap_tool_call` | Anexa `AGENTS.md` ancestrais aplicáveis aos resultados de `read_file`, uma vez por run. |
| 7 | `ToolRetryMiddleware` | `agent/middleware/task_retry.py` | — | Re-tenta a tool `task` (subagentes) até 2 vezes (`max_retries=2`), com `retry_on`/`on_failure` e backoff `initial_delay=1.0`/`max_delay=10.0`. |
| 8 | `PullRequestCreationGuardMiddleware` | `agent/middleware/pr_creation_guard.py` | `wrap_tool_call`, `awrap_tool_call` | Guarda a criação de PR (política Always Create PRs / aprovação de workflow). |
| 9 | `refresh_github_proxy_before_model` | `agent/middleware/refresh_github_proxy.py` | `before_model` | Atualiza o proxy GitHub do sandbox (token de instalação do GitHub App) antes de cada chamada de modelo. |
| 10 | `check_message_queue_before_model` | `agent/middleware/check_message_queue.py` | `before_model` | Puxa comentários Linear / mensagens Slack que chegaram durante o run da fila da thread e os injeta como mensagens de usuário. É o que permite "mensagear o agente enquanto ele trabalha". |
| 11 | `SlackAssistantStatusMiddleware` | `agent/middleware/refresh_slack_status.py` | `awrap_model_call`, `awrap_tool_call` | Mantém o status "assistant está digitando" do Slack atualizado ao redor das chamadas. |
| 12 | `TimeoutWrapupMiddleware` | `agent/middleware/timeout_wrapup.py` | `awrap_model_call` | Encerramento/aviso em caso de timeout; recebe `is_jira_run=(source == "jira")`. |
| 13 | `notify_step_limit_reached` | `agent/middleware/notify_step_limit.py` | `after_agent` | Publica resposta no Slack quando o agente atinge o limite de passos. |
| 14 | `notify_jira_on_unparked_termination` | `agent/middleware/notify_jira_unparked.py` | `after_agent` | Notifica no Jira quando um run termina sem ter parado num gate (unparked). |
| 15 | `ModelFallbackMiddleware` *(opcional)* | `agent/middleware/model_fallback.py` | `awrap_model_call` | Fallback para modelo secundário; só entra se `LLM_FALLBACK_MODEL_ID` ou o fallback padrão do modelo diferir do primário (`*fallback_middleware`). |
| 16 | `PlanModeMiddleware` | `agent/middleware/plan_mode.py` | `before_agent`, `awrap_model_call` | Modo plano (aprovar plano antes de codificar); entra via `*plan_mode_middleware`. |
| 17 | `SanitizeFireworksMessagesMiddleware` | `agent/middleware/sanitize_fireworks_messages.py` | `awrap_model_call` | Sanitiza mensagens específicas do provedor Fireworks. |
| 18 | `SanitizeThinkingBlocksMiddleware` | `agent/middleware/sanitize_thinking_blocks.py` | `awrap_model_call` | Remove blocos de thinking Anthropic malformados/vazios imediatamente antes da chamada ao provedor. |
| 19 | `ModelCallTimeoutMiddleware` | `agent/middleware/model_call_timeout.py` | `awrap_model_call` | **Mais interno.** Limita uma única chamada de modelo a `OPEN_SWE_MODEL_CALL_TIMEOUT_SECONDS` (padrão 15 min); o timeout escala para fora até o `ModelFallbackMiddleware`. |

---

## Reviewer — `agent/reviewer.py:1404-1425` (mais externo → mais interno)

| # | Middleware | Arquivo | Hook | Objetivo |
|---|---|---|---|---|
| 1 | `PrepareReviewerRunMiddleware` | `agent/middleware/prepare_run.py` | `awrap_model_call` | Variante do reviewer: garante sandbox com `allow_replacement=True` e re-deriva o checkout via `prepare_review_repo`. Recebe `thread_id`, `config`, `use_gateway`. |
| 2 | `SanitizeToolInputsMiddleware` | `sanitize_tool_inputs.py` | `awrap_tool_call` | Idem server. |
| 3 | `ModelCallLimitMiddleware` | (langchain) | — | Idem server. |
| 4 | `ToolErrorMiddleware` | `tool_error_handler.py` | `awrap_tool_call` | Idem server. |
| 5 | `refresh_github_proxy_before_model` | `refresh_github_proxy.py` | `before_model` | Idem server. |
| 6 | `check_message_queue_before_model` | `check_message_queue.py` | `before_model` | Idem server. |
| 7 | `SlackAssistantStatusMiddleware` | `refresh_slack_status.py` | `awrap_model_call`, `awrap_tool_call` | Idem server. |
| 8 | `TimeoutWrapupMiddleware` | `timeout_wrapup.py` | `awrap_model_call` | Idem server (sem `is_jira_run`). |
| 9 | `SanitizeFireworksMessagesMiddleware` | `sanitize_fireworks_messages.py` | `awrap_model_call` | Idem server. |
| 10 | `SanitizeThinkingBlocksMiddleware` | `sanitize_thinking_blocks.py` | `awrap_model_call` | Idem server. |
| 11 | `RepairOrphanedToolCallsMiddleware` | `agent/middleware/repair_orphaned_tool_calls.py` | `awrap_model_call` | Repara chamadas de tool órfãs (resultado perdido) no fluxo do reviewer. |
| 12 | `ModelCallTimeoutMiddleware` | `model_call_timeout.py` | `awrap_model_call` | Mais interno. Idem server. |
| 13 | `settle_review_check_on_exit` | `agent/middleware/settle_review_check.py` | `after_agent` | Finaliza o check run de revisão no GitHub ao sair. |

---

## Definidos mas NÃO conectados à stack real (apenas testes)

Estes middlewares existem no código mas não estão na lista de `middleware` de
nenhum agente — são exercitados apenas por testes:

| Middleware | Arquivo | Hook | Por que não está ligado |
|---|---|---|---|
| `ensure_no_empty_msg` | `agent/middleware/ensure_no_empty_msg.py` | `after_model` | Re-injetaria um tool call sintético quando o modelo emite mensagem sem tool call. Substituído pela combinação "system prompt pede tool a cada turno" + `ensure_no_empty_msg` não usado na stack real. |
| `SandboxCircuitBreakerMiddleware` | `agent/middleware/sandbox_circuit_breaker.py` | `before_model` | Tiraria o agente de falhas repetidas de sandbox. Não está na stack atual. |
| `WorkflowPushGuardMiddleware` | `agent/middleware/workflow_push_guard.py` | `awrap_tool_call` | Guarda pushes de workflow (aprovação). Não está na stack atual. |

> Nota: `ExcludeToolsMiddleware` (`agent/middleware/exclude_tools.py`) também
> existe mas não é ligado ao agente padrão.
