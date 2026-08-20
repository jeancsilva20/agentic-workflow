# Agente Principal (`main-agent`)

Arquivo-fonte: `agent/server.py` — factory `get_agent` (linha 1008).

## Objetivo

Executar o fluxo Jira + OpenSpec (spec authoring, implementação, ajustes, arquivamento) e responder a disparos de Slack, Linear, GitHub e dashboard. É **stateless**: todo o estado por-thread vive no sandbox + metadados do thread.

## Intenção

Um único deep agent por despacho. Não abre PR automaticamente — ele mesmo faz commit, push e abre/atualiza o PR draft. Respeita os gates de aprovação (SDD) e transiciona o card Jira apenas quando os artefatos exigidos estão commitados e enviados ao remoto.

## Resultado

Respostas no canal de origem (Slack/Linear/GitHub/dashboard), commits, push, PR draft, transições Jira, metadados gravados no thread e telemetria de roteamento.

## Fluxo de Entrada/Saída

- **Entrada**: `config.configurable` (`thread_id`, `source`, `repo`, `jira_issue_key`, `plan_mode`, `user_email`), mensagens de usuário e `routing_signals`.
- **Saída**: respostas, PRs, comentários, transições Jira e telemetria.

## Conexões

Chamado por `dispatch_agent_run`, webhooks, dashboard e `jira_poller`. Chama `ensure_sandbox_for_thread` e subagentes `_general_purpose_subagent` e `_browser_subagent` (server.py:1214-1217).

## Ferramentas

**Estáticas** (server.py:1142-1181): `http_request`, `fetch_url`, `web_search`, `approve_plan`, `enter_plan_mode`, `save_plan`, `save_user_instructions`, `save_user_skill`, `delete_user_skill`, `jira_add_comment`, `jira_get_comments`, `jira_get_issue`, `jira_park_at_gate`, `jira_search_issues`, `jira_transition_issue`, `linear_*`, `log_openspec_event`, `log_review_cycle`, `open_pull_request`, `openspec_archive`/`status`/`validate`, `request_pr_review`, `request_self_review`, `recreate_sandbox`, `report_platform_issue`, `schedule_thread_wakeup`, `slack_*`.

**Integrações dinâmicas** (server.py:1183-1188): Corridor, Observability, Currents, Notion (via `DynamicToolMiddleware`).

**Built-ins** (do `create_deep_agent`): `read_file`, `write_file`, `edit_file`, `delete`, `ls`, `glob`, `grep`, `execute`, `task`.

**Middleware** (server.py:1220-1266): `PrepareAgentRun`, `DynamicTool`, `SanitizeToolInputs`, `ModelCallLimit`, `ToolError`, `SubdirAgents`, `ToolRetry`, `PullRequestCreationGuard`, `refresh_github_proxy`, `check_message_queue`, `SlackAssistantStatus`, `TimeoutWrapup`, `notify_step_limit`, `notify_jira_unparked`, `ModelFallback`, `PlanMode`, `SanitizeFireworks`, `SanitizeThinking`, `ModelCallTimeout`.

**Modelo**: `resolve_model(CODING_AGENT)` → Sonnet/medium, escala para Opus/high após 2 falhas ou complexidade alta.
