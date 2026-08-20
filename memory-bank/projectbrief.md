# Project Brief — Open SWE (fork Sensedia)

## Visão Geral

Este repositório é um **fork da Sensedia do Open SWE (LangChain)** — um coding agent interno construído sobre **LangGraph + Deep Agents** (`deepagents.create_deep_agent`). Ele roda como um app LangGraph: cada thread possui seu próprio sandbox isolado em nuvem, e o agente é acionado a partir de Jira, Slack, Linear ou GitHub (comentários de PR e auto-review em `opened` / `ready-for-review`).

O fluxo central é **Spec-Driven Development (SDD)**: o agente consome cards do Jira, gera specs OpenSpec, implementa em sandboxes isolados e abre PRs no GitHub — tudo governado por **gates de aprovação humana** via transições de colunas no Jira.

## Objetivos Centrais

1. **Consumir Jira** — um poller monitora colunas e despacha runs conforme o card avança.
2. **Gerar specs OpenSpec** — antes de qualquer código, o agente produz `proposal.md`, `specs/`, `tasks.md` e `design.md` (skills OpenSpec vendorizadas em `openspec/`).
3. **Implementar em sandbox** — cada thread tem um sandbox isolado (proxy GitHub injeta credenciais sem armazenar tokens reais).
4. **Abrir PRs no GitHub** — o agente commita, faz push e abre/atualiza o PR draft.
5. **3 gates de aprovação humana** — o agente pausa o card no Jira e espera um humano aprovar antes de prosseguir.

## Os 3 Gates (colunas do Jira)

| Gate | Coluna Jira | Condição para parar |
|---|---|---|
| 1 | **Em Revisão de Spec** | Artefatos OpenSpec commitados e pushados (proposal, specs, tasks, design) |
| 2 | **Em Code Review** | `openspec-verify` sem findings CRITICAL pendentes |
| 3 | **Em Merge** | `openspec-archive` concluído (change movida para `archive/`) |

As constantes de coluna vivem em `agent/jira_poller.py` (ex.: `COLUMN_SPEC_REVIEW`, `COLUMN_CODE_REVIEW`, `COLUMN_MERGE`), expostas ao prompt em `agent/prompt.py:512-522`.

## Stack

- **Python ≥ 3.11** (`requires-python = ">=3.11"`; `langgraph.json` fixa o runtime em 3.12)
- **FastAPI** (app `agent.webapp:app`)
- **uv** (gerenciador de dependências)
- **pytest** (testes, `asyncio_mode = "auto"`)
- **ruff** (lint/format, line-length 100, target py311)
- **basedpyright** (type checking, `typeCheckingMode = "standard"`)

## Grafos LangGraph (declarados em `langgraph.json`)

| Grafo | Entrypoint | Propósito |
|---|---|---|
| `agent` | `agent/server.py:get_agent` | Agente principal de codificação (Jira/Slack/Linear/GitHub) |
| `reviewer` | `agent/reviewer.py:get_reviewer_agent` | Revisor de PR read-only |
| `analyzer` | `agent/analyzer.py:get_analyzer` | Aprende estilo de review por repositório |
| `chat` | `agent/chat.py:get_chat_agent` | Chat sobre PR sem sandbox |
| `scheduler` | `agent/scheduler.py:get_scheduler` | Orquestra cron do poller + reconcile |

## Referências-chave

- `agent/server.py:1008` — `get_agent(config)`, factory do grafo principal
- `agent/reviewer.py:1328` — `get_reviewer_agent(config)`
- `agent/analyzer.py:165` — `get_analyzer(config)`
- `agent/chat.py:180` — `get_chat_agent(config)`
- `agent/scheduler.py:38` — `get_scheduler(config)`
- `agent/jira_poller.py:436` — `tick()`, o passo do poller
- `agent/dispatch.py:189` — `dispatch_agent_run`, dispara runs
- `agent/completion.py:196` — `handle_run_completion`, webhook que fecha o ciclo
