## Why

Este repositório é um fork da Sensedia do Open SWE (LangChain) — um coding agent interno que consome Jira, gera specs OpenSpec, implementa em sandboxes isolados e abre PRs no GitHub, governado por gates de aprovação humana. O sistema é grande e distribuído: 5 grafos LangGraph, ~52 tools, 24 middlewares, 6 providers de sandbox, 6 integrações MCP, 3 webhooks, 15 papéis de routing, um dashboard FastAPI, um agent-console Flask e uma UI React.

Hoje o conhecimento sobre o sistema está espalhado em código, `AGENTS.md`, `docs/` e `openwiki/` (este último regenerado automaticamente por GitHub Actions). Não existe uma documentação estruturada e versionada que descreva, por agente, o seu objetivo, intenção, resultado, fluxo de entrada/saída, conexões e ferramentas. Isso torna difícil para novos desenvolvedores (humanos ou agentes) entenderem o sistema e para o próprio OpenCode recuperar contexto de forma consistente.

Esta mudança cria uma estrutura de **memory bank** na raiz do repositório — um padrão de documentação de mercado (popularizado pelo Cline, adotado por Microsoft/Gitpod/GitHub Copilot) — com um documento por agente e por camada, carregado pelo OpenCode via `opencode.json`.

## What Changes

- **Nova pasta `memory-bank/`** na raiz, com a estrutura clássica do Memory Bank (Cline): `projectbrief.md`, `productContext.md`, `systemPatterns.md`, `techContext.md`, `activeContext.md`, `progress.md`.
- **Pasta `memory-bank/agents/`** com um documento por agente: `main-agent.md`, `reviewer.md`, `analyzer.md`, `chat.md`, `scheduler.md`. Cada documento segue o template: **Objetivo → Intenção → Resultado → Fluxo de Entrada/Saída → Conexões → Ferramentas**.
- **Pasta `memory-bank/camadas/`** com documentos por camada transversal: `middleware.md`, `tools.md`, `routing.md`, `dashboard-console.md`, `webhooks.md`, `sandbox.md`.
- **Novo `opencode.json`** na raiz, com o campo `instructions` apontando para os arquivos do memory bank, para que o OpenCode os carregue automaticamente no contexto.
- **Atualização do `AGENTS.md`** com um índice apontando para o memory bank.

## Capabilities

### New Capabilities

- `memory-bank-estrutura`: Criar a estrutura de pastas e os documentos de contexto global do memory bank (projectbrief, productContext, systemPatterns, techContext, activeContext, progress).
- `documentacao-agentes`: Criar um documento por agente (main-agent, reviewer, analyzer, chat, scheduler) cobrindo objetivo, intenção, resultado, fluxo de entrada/saída, conexões e ferramentas.
- `documentacao-camadas`: Criar documentos por camada transversal (middleware, tools, routing, dashboard-console, webhooks, sandbox).
- `integracao-opencode`: Criar o `opencode.json` com `instructions` apontando para o memory bank e atualizar o `AGENTS.md` com um índice.

### Modified Capabilities

<!-- Nenhuma capability existente é modificada — esta é uma iniciativa de documentação greenfield -->

## Impact

- **New files**: ~18 arquivos Markdown em `memory-bank/` + 1 `opencode.json` na raiz.
- **Modified files**: `AGENTS.md` (adição de um índice/seção apontando para o memory bank).
- **Dependencies**: nenhuma nova. Não há mudança de código de runtime.
- **No breaking changes**: documentação e configuração de ferramenta de desenvolvimento apenas; nenhum comportamento de runtime é alterado.
- **Coexistência**: o memory bank coexiste com `openwiki/` (regenerado por GitHub Actions) e `docs/`; não os substitui.
