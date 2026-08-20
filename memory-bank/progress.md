# Progress — O que Funciona, o que Falta

## O que Funciona

- **Workflow Jira completo com 3 gates** — poller (60s) → dispatch → agente (spec → implementa → PR) → pausa nos gates `Em Revisão de Spec`, `Em Code Review`, `Em Merge` → retomada por transição humana.
- **Reviewer graph** — revisor de PR read-only com findings ancorados inline e `publish_review` (`agent/reviewer.py`).
- **Analyzer de estilo** — aprende o estilo de review por repositório (modos bootstrap e continual) e alimenta o prompt do reviewer (`agent/analyzer.py`).
- **Chat** — chat sobre PR sem sandbox (`agent/chat.py`).
- **Poller de 60s** — `agent/jira_poller.py:436` (`tick()`), com cron via grafo `scheduler` (`agent/poller_cron.py`).
- **Scheduler** — orquestra `jira_poll` e `reconcile` de runs órfãos/stale (`agent/scheduler.py:26-30`).
- **Dashboard** — webapp FastAPI com rotas de perfil, repos habilitados, review-style e observabilidade (`agent/dashboard/`).
- **Agent-console** — console de operação (Flask) para acompanhar/controlar runs.
- **Completion webhook** — `/webhooks/run-complete` garante que todo run termine com sinal e registra telemetria (`agent/completion.py:196`).
- **Workflow OpenSpec** — change `jira-openspec-coding-agent` com **84/85 tasks concluídas**.

## O que Falta / Issues Conhecidas

- **3 middlewares definidos mas não conectados** à stack do server:
  - `ensure_no_empty_msg` (`agent/middleware/ensure_no_empty_msg.py:78`)
  - `SandboxCircuitBreakerMiddleware` (`agent/middleware/sandbox_circuit_breaker.py:253`)
  - `WorkflowPushGuardMiddleware` (`agent/middleware/workflow_push_guard.py:516`)
- **Documentação estruturada por agente** — esta iniciativa de memory bank ainda em andamento (change `openspec/changes/memory-bank-documentacao/`): falta documentação por agente (`agents/`) e por camada (`camadas/`), além de `opencode.json` e índice no `AGENTS.md`.
- **1 task pendente** no change `jira-openspec-coding-agent` (84/85).

## Próximos Marcos

1. Concluir a documentação global do memory bank (este conjunto de 6 arquivos).
2. Criar `memory-bank/agents/*.md` (main-agent, reviewer, analyzer, chat, scheduler).
3. Criar `memory-bank/camadas/*.md` (middleware, tools, routing, dashboard-console, webhooks, sandbox).
4. Criar `opencode.json` e atualizar `AGENTS.md` com índice.
