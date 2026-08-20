# Camada transversal: Inventário de Tools

Todas as tools vivem em `agent/tools/` e são importadas de forma plana via
`agent/tools/__init__.py` (carregamento lazy). O conjunto é pequeno e curado —
ver README "Tools — Curated, Not Accumulated". As tools built-in do Deep Agents
são adicionadas pelo próprio `create_deep_agent` e não devem ser duplicadas.

---

## Jira (usadas pelo agente principal)

Delegam para `agent/utils/jira.py` (REST v3, Basic auth via `JIRA_BASE_URL` +
`JIRA_EMAIL` + `JIRA_API_TOKEN`).

| Tool | Arquivo | Entrada | Saída |
|---|---|---|---|
| `jira_get_issue` | `jira_get_issue.py` | `issue_key` | Detalhes da issue |
| `jira_get_comments` | `jira_get_comments.py` | `issue_key` | Comentários da issue |
| `jira_search_issues` | `jira_search_issues.py` | query/JQL | Issues encontradas |
| `jira_add_comment` | `jira_add_comment.py` | `issue_key`, texto | Confirmação |
| `jira_transition_issue` | `jira_transition_issue.py` | `issue_key`, transição | Confirmação |
| `jira_park_at_gate` | `jira_park_at_gate.py` | `issue_key`, coluna/gate | Move o card para o gate (ex.: `Em Revisão de Spec`, `Em Code Review`, `Em Merge`) |

---

## OpenSpec (agente principal)

Operam no sandbox sobre os artefatos OpenSpec.

| Tool | Arquivo | Objetivo |
|---|---|---|
| `openspec_validate` | `openspec_validate.py` | Valida a estrutura dos artefatos OpenSpec (`.openspec.yaml`, `proposal.md`, `specs/`, `tasks.md`). |
| `openspec_status` | `openspec_status.py` | Reporta o estado dos artefatos OpenSpec. |
| `openspec_archive` | `openspec_archive.py` | Arquiva o change (move para `openspec/changes/archive/`). |
| `log_openspec_event` | `log_openspec_event.py` | Emite evento de ciclo de vida OpenSpec (console). |

---

## Linear (agente principal)

Delegam para `agent/utils/linear.py` (GraphQL em `https://api.linear.app/graphql`).

| Tool | Arquivo | Objetivo |
|---|---|---|
| `linear_comment` | `linear_comment.py` | Comenta numa issue |
| `linear_create_issue` | `linear_create_issue.py` | Cria issue |
| `linear_delete_issue` | `linear_delete_issue.py` | Deleta issue |
| `linear_get_issue` | `linear_get_issue.py` | Busca issue |
| `linear_get_issue_comments` | `linear_get_issue_comments.py` | Lista comentários |
| `linear_list_teams` | `linear_list_teams.py` | Lista teams |
| `linear_search_issues` | `linear_search_issues.py` | Busca issues |
| `linear_update_issue` | `linear_update_issue.py` | Atualiza issue |

---

## Slack (agente principal)

Delegam para `agent/utils/slack.py` (`https://slack.com/api`).

| Tool | Arquivo | Objetivo |
|---|---|---|
| `slack_thread_reply` | `slack_thread_reply.py` | Responde num thread |
| `slack_read_thread_messages` | `slack_read_thread_messages.py` | Lê mensagens do thread |
| `slack_start_new_thread` | `slack_start_new_thread.py` | Inicia novo thread |
| `slack_add_reaction` | `slack_add_reaction.py` | Adiciona reação |

---

## GitHub / PR (agente principal)

| Tool | Arquivo | Objetivo |
|---|---|---|
| `open_pull_request` | `open_pull_request.py` | Abre/atualiza PR (draft conforme política). |
| `request_pr_review` | `request_pr_review.py` | Solicita revisão de PR. |
| `request_self_review` | `request_self_review.py` | Solicita auto-revisão. |

---

## Review (reviewer / analyzer / review-chat)

Usadas pelo grafo `reviewer` (e algumas pelo analyzer/chat). O reviewer também
usa `web_search`, `fetch_url`, `http_request` (compartilhadas).

| Tool | Arquivo | Objetivo |
|---|---|---|
| `fetch_review_diff` | `fetch_review_diff.py` | Busca o diff do PR para análise fresca. |
| `add_finding` | `add_finding.py` | Registra finding ancorado (`file` + `start_line`/`end_line`). |
| `update_finding` | `update_finding.py` | Atualiza finding. |
| `list_findings` | `list_findings.py` | Lista findings do modelo único em evolução. |
| `publish_review` | `publish_review.py` | Publica a revisão (comenta na linha do finding). |
| `reply_to_finding_thread` | `reply_to_finding_thread.py` | Responde a thread de finding. |
| `resolve_finding_thread` | `resolve_finding_thread.py` | Resolve thread de finding. |
| `list_review_findings` | `list_review_findings.py` | Lista findings de uma revisão. |
| `read_finding_outcomes` | `read_finding_outcomes.py` | Lê desfechos de findings (modo continual do analyzer). |
| `save_review_style` | `save_review_style.py` | Salva o prompt de estilo de revisão por repo (exportado como `save_review_style_prompt`). |

---

## Util / Plano / Rede (agente principal)

| Tool | Arquivo | Objetivo |
|---|---|---|
| `approve_plan` | `approve_plan.py` | Aprova um plano. |
| `enter_plan_mode` | `enter_plan_mode.py` | Entra em modo plano. |
| `save_plan` | `save_plan.py` | Salva um plano. |
| `save_user_instructions` | `save_user_instructions.py` | Salva instruções de usuário. |
| `save_user_skill` | `user_skills.py` | Salva skill de usuário. |
| `delete_user_skill` | `user_skills.py` | Deleta skill de usuário. |
| `schedule_thread_wakeup` | `schedule_thread_wakeup.py` | Agenda wakeup de thread. |
| `report_platform_issue` | `report_platform_issue.py` | Reporta problema de plataforma. |
| `recreate_sandbox` | `recreate_sandbox.py` | Recria o sandbox da thread. |
| `http_request` | `http_request.py` | Requisição HTTP arbitrária. |
| `fetch_url` | `fetch_url.py` | Busca conteúdo de URL. |
| `web_search` | `web_search.py` | Busca na web. |
| `read_repo_file` | `read_repo_file.py` | Lê arquivo do repo. |
| `search_repo_code` | `search_repo_code.py` | Busca código no repo. |
| `log_review_cycle` | `log_review_cycle.py` | Emite evento de ciclo de revisão (console). |

---

## Built-ins do Deep Agents

Adicionados pelo `create_deep_agent` (não duplicar em `agent/tools/`):
`delete`, `edit_file`, `execute`, `glob`, `grep`, `ls`, `read_file`, `task`
(spawn de subagente), `write_file`.

---

## Integrações dinâmicas (via `DynamicToolMiddleware`)

Carregadas sob demanda por grupo de tools (`agent/middleware/dynamic_tools.py`),
com credenciais mantidas fora do sandbox. Fontes em `agent/integrations/`:

| Integração | Arquivo | Tool(s) |
|---|---|---|
| Corridor | `corridor_mcp.py` | `analyzePlan` (MCP hospedado em `app.corridor.dev/api/mcp`). |
| Observability | `datadog_mcp.py`, `langsmith_tools.py` | Datadog + LangSmith. |
| Currents | `currents_tools.py` | Tools do Currents. |
| Notion | `notion_mcp.py` | Tools do Notion. |
| Stagehand (browser) | `stagehand_browser.py` | Automação de browser. |

---

## Referência rápida de wiring

- Agente principal (`agent/server.py`): lista `static_tools` + subagentes
  (`_general_purpose_subagent`, opcionalmente `_browser_subagent`).
- Reviewer (`agent/reviewer.py`): toolset reviewer-only + `web_search`,
  `fetch_url`, `http_request`.
- Analyzer (`agent/analyzer.py`): usa `save_review_style` (+ `read_finding_outcomes`).
