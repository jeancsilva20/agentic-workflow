# Tasks — Memory Bank de Documentação

## 1. Estrutura do memory bank

- [x] 1.1 Criar a pasta `memory-bank/` na raiz com as subpastas `agents/` e `camadas/`
- [x] 1.2 Criar `memory-bank/projectbrief.md` — visão geral do framework (LangGraph + Deep Agents, fork Sensedia do Open SWE), requisitos e objetivos centrais
- [x] 1.3 Criar `memory-bank/productContext.md` — por que o projeto existe, problema que resolve, casos de uso (Jira/Slack/Linear/GitHub)
- [x] 1.4 Criar `memory-bank/systemPatterns.md` — arquitetura: sandbox lifecycle, middleware stack, model routing, relações entre componentes
- [x] 1.5 Criar `memory-bank/techContext.md` — stack tecnológica, setup, constraints, dependências
- [x] 1.6 Criar `memory-bank/activeContext.md` — foco atual de desenvolvimento, mudanças recentes, próximos passos
- [x] 1.7 Criar `memory-bank/progress.md` — o que funciona, o que falta, issues conhecidas

## 2. Documentação por agente

- [x] 2.1 Criar `memory-bank/agents/main-agent.md` — agente principal (server.py): objetivo, intenção, resultado, fluxo I/O, conexões, ferramentas
- [x] 2.2 Criar `memory-bank/agents/reviewer.md` — revisor de PR read-only (reviewer.py): objetivo, intenção, resultado, fluxo I/O, conexões, ferramentas
- [x] 2.3 Criar `memory-bank/agents/analyzer.md` — analista de estilo de review (analyzer.py): objetivo, intenção, resultado, fluxo I/O, conexões, ferramentas
- [x] 2.4 Criar `memory-bank/agents/chat.md` — chat sobre PR sem sandbox (chat.py): objetivo, intenção, resultado, fluxo I/O, conexões, ferramentas
- [x] 2.5 Criar `memory-bank/agents/scheduler.md` — orquestrador de cron (scheduler.py): objetivo, intenção, resultado, fluxo I/O, conexões, ferramentas

## 3. Documentação por camada transversal

- [x] 3.1 Criar `memory-bank/camadas/middleware.md` — stack de middlewares (ordem real em server.py e reviewer.py, tipos de hook, propósito, não-conectados)
- [x] 3.2 Criar `memory-bank/camadas/tools.md` — inventário das ~52 tools por categoria (jira, openspec, linear, slack, github/pr, review, util)
- [x] 3.3 Criar `memory-bank/camadas/routing.md` — sistema de routing de modelos (AgentRole, tabela de rotas, complexidade, escalada, telemetria)
- [x] 3.4 Criar `memory-bank/camadas/dashboard-console.md` — webapp FastAPI, dashboard (~94 rotas), agent-console Flask, UI React
- [x] 3.5 Criar `memory-bank/camadas/webhooks.md` — webhooks GitHub/Linear/Slack, eventos, derivação de thread-ids
- [x] 3.6 Criar `memory-bank/camadas/sandbox.md` — ciclo de vida do sandbox (6 providers, proxy GitHub, SANDBOX_BACKENDS, SandboxUnreachableError)

## 4. Integração com OpenCode

- [x] 4.1 Criar `opencode.json` na raiz com o campo `instructions` listando os arquivos do memory bank
- [x] 4.2 Atualizar `AGENTS.md` com uma seção/índice apontando para o memory bank
- [x] 4.3 Validar que o `opencode.json` é JSON bem-formado e compatível com o schema do OpenCode

## 5. Verificação

- [x] 5.1 Verificar que todos os arquivos do memory bank existem e seguem o template de 6 dimensões (agentes) e o propósito (camadas)
- [x] 5.2 Verificar que o conteúdo é fiel ao código (referências de arquivo:linha corretas)
- [x] 5.3 Rodar `openspec validate` para garantir que os artefatos desta change estão completos
