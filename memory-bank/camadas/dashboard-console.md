# Camada transversal: Gestão (Dashboard + Console + UI)

Quatro superfícies compõem a camada de gestão do sistema.

---

## 1. Webapp FastAPI — `agent/api/app.py`

Composição da aplicação FastAPI (`create_app`, `app.py:43-69`):

- Monta os routers: `dashboard_router`, `plan_router`,
  `workflow_approval_router`, os três webhooks (GitHub, Linear, Slack) e o
  `health_router`.
- CORS condicional via `DASHBOARD_ALLOWED_ORIGINS` (recusa `*` com
  `allow_credentials=True`).
- `lifespan` (`app.py:23-40`): valida config de sandbox e LLM local no boot e
  agenda o cron do poller Jira como background task com backoff
  (`ensure_jira_poller_cron_with_retry`), cancelado no shutdown.

---

## 2. Dashboard — `agent/dashboard/`

Router montado sob `/dashboard/api` (`routes.py` tem **94 rotas**; mais 7 em
`plan_api.py` e 3 em `workflow_approval_api.py`). Áreas cobertas:

- **OAuth**: GitHub (`oauth.py`), Slack (`slack_oauth.py`), Notion
  (`notion_oauth.py`) — login/callback/logout.
- **Perfis**: `profiles.py`, `agent_overrides.py`, `user_mappings.py`,
  `user_credentials.py`, `team_credentials.py`.
- **Admin**: `admin.py` (user-mappings, evals, cancelar threads).
- **Team settings**: `team_settings.py`.
- **Enabled repos**: `enabled_repos.py` (auto-review).
- **Review-style**: `review_styles.py`, `review_style_jobs.py`,
  `analyzer_cron.py`.
- **Agent-instructions**: `agent_instructions.py` (por repo).
- **Repo-snapshots**: `repo_snapshots.py`, `repo_cache.py`, `repo_access.py`.
- **Reviews**: `review_api.py`, `review_chat_api.py`, `pr_diff.py`.
- **Threads**: `thread_api.py` (lista, stream, turn-diff, recovery.patch,
  comandos, histórico, cancelar).
- **Schedules**: `schedules.py`.
- **Skills**: `skills.py`.
- **Usage**: `agent_usage.py` (leaderboard).
- **Plan**: `plan_api.py`, `plan_store.py`.
- **Workflow-approval**: `workflow_approval.py`, `workflow_approval_api.py`.
- **Autofix**: `autofix_state.py` (toggle `@open-swe autofix on|off`).
- **Options**: `options.py` (modelos suportados, effort).

---

## 3. Agent-console — `agent-console/`

App **Flask** na porta **5050** (`agent-console/app.py`, `http://localhost:5050`).
Mostra:

- **Shadow / live mode** do poller Jira (persistido em
  `agent-console/data/operational_config.json` via `config_store.py`).
- **Poller health**, fila de cards, runs ativos/parados/mortos e **execution
  log** ao vivo.
- Estado em memória via `ConsoleStore` (`agent-console/store.py`), com
  `RunRecord` e candidatos shadow.
- Endpoints `/api/config` (shadow mode, intervalo de poll) e
  `/api/observability/live` (`observability.py`, `runtime_bridge.py`).

---

## 4. UI — `ui/`

Frontend **TanStack Start + React 19 + shadcn/ui + Tailwind 4 + Vite** (pnpm).
Stack confirmada em `ui/package.json`: `@tanstack/react-start`,
`@tanstack/react-router`, `react ^19.2.4`, `tailwindcss ^4.2.1`, `vite ^7.3.5`.

Páginas principais (rotas em `ui/src/routes/`):

- **Profile** — `my-settings.tsx`, `login.tsx`, `integrations.tsx`.
- **Agent** — `agents.tsx`, `agents/threads.tsx`, `agents/$threadId.tsx`,
  `agents/$threadId_.plan.tsx`, `agents/skills.tsx`, `agents/automations/`,
  `agents/local/$sessionId.tsx`, `agents/instructions.tsx`,
  `agents/snapshots.tsx`.
- **Review** — `review.tsx`, `review_.repositories.$owner.tsx`,
  `review_.styles.tsx`, `agents/reviews/`.
- **Usage** — `usage.tsx`.
- **Admin** — `admin.tsx`, `admin_.evals.tsx`.
- Outros: `cloud-agents.tsx`, `index.tsx`, `$owner.$repo.pull.$number.tsx`.

---

## Fluxo de dados resumido

- O **webapp FastAPI** serve o LangGraph + API REST; o **dashboard** é a camada
  de gestão (rotas `/dashboard/api`); o **agent-console** é uma página auxiliar
  de operação do poller Jira; a **UI** consome tudo via TanStack Query/Start.
- O console espelha os mesmos stores de observabilidade a partir de dois eventos
  empurrados e serve em `GET /api/observability/...` — nunca chama LangSmith
  diretamente.
