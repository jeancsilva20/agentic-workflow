# Tech Context — Stack Tecnológica

## Linguagem e Runtime

- **Python ≥ 3.11** (`requires-python = ">=3.11"`); `langgraph.json` fixa o runtime em **3.12**.
- **Async-only**: o app roda exclusivamente assíncrono; não há implementações sync/async duplicadas.

## Framework Principal

- **LangGraph** — orquestração de grafos; cada thread tem seu próprio grafo/sandbox.
- **Deep Agents** (`deepagents.create_deep_agent`) — construção do agente com ferramentas curadas e middleware.
- **langgraph-sdk** — cliente usado para disparar/streamar runs a partir dos webhooks.

## Servidor / API

- **FastAPI** — app `agent.webapp:app` (rotas custom + dashboard montado via `include_router`).
- **Uvicorn** — servidor ASGI (`make run`).

## Clientes HTTP e Segurança

- **httpx** — cliente HTTP assíncrono.
- **PyJWT** — tokens JWT (ex.: token de instalação do GitHub App, `agent/utils/github_app.py`).
- **cryptography** — criptografia de tokens OAuth em repouso (`agent/encryption.py`, `MultiFernet`).

## LLM / Observabilidade

- **langchain** — base de integração.
- **langsmith** — sandbox padrão (`SANDBOX_TYPE=langsmith`) e telemetria de tokens/custo.
- **langchain-anthropic / langchain-openai / langchain-fireworks** — provedores de modelo.
- **exa-py** — busca web (`web_search`).
- **langchain-mcp-adapters** — adaptadores MCP (integrações MCP).
- **stagehand** — automação de browser (quando aplicável).

## Setup e Comandos

```bash
make install       # uv sync --extra dev (pytest, ruff, …)
make dev           # uv run langgraph dev — serve os 5 grafos + FastAPI
make run           # uvicorn agent.webapp:app --reload --port 8000
make test          # uv run pytest -vvv tests/
make lint          # ruff check + ruff format --diff
make format        # ruff format + ruff check --fix
make typecheck     # basedpyright agent tests
```

## Constraints

- **Async-only** — implementar apenas a variante async (`awrap_*`, `_arun`); a sync nunca é invocada.
- **ruff** — line-length 100, target py311.
- **basedpyright** — `typeCheckingMode = "standard"`.
- Testes unit-only por padrão em `tests/`; integração em `tests/integration_tests/`.

## Providers de Sandbox

Selecionados via `SANDBOX_TYPE`; factory em `agent/utils/sandbox.py:create_sandbox` (`SANDBOX_FACTORIES`, `sandbox.py:13-19`):

| Provider | Creator |
|---|---|
| `langsmith` (padrão) | `agent.integrations.langsmith:create_langsmith_sandbox` |
| `daytona` | `agent.integrations.daytona:create_daytona_sandbox` |
| `modal` | `agent.integrations.modal:create_modal_sandbox` |
| `runloop` | `agent.integrations.runloop:create_runloop_sandbox` |
| `e2b` | `agent.integrations.e2b:create_e2b_sandbox` |
| `local` | `agent.integrations.local:create_local_sandbox` |

Somente `langsmith` configura o proxy GitHub (Basic/Bearer auth para `github.com`/`api.github.com`); os demais pulam essa etapa.

## Escopo do Sistema (da proposta `memory-bank-documentacao`)

- 5 grafos LangGraph, ~52 tools, 24 middlewares, 6 providers de sandbox, 6 integrações MCP, 3 webhooks, 15 papéis de routing, dashboard FastAPI, agent-console Flask e UI React.
