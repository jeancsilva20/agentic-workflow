# Exploração Inicial: Contexto e Fontes

## Documentos analisados

### 1. The Agentic Development Playbook
Framework de adoção de desenvolvimento agentivo. Principais contribuições para este projeto:

- **Agentic SDLC**: 5 estágios — Define, Shape, Build, Validate, Run
- **Princípio central**: "Humans own intent and judgment; agents own execution and coverage"
- **Specification-driven development**: A spec é o novo source code. Pipeline: PRD → Specification → Architecture Plan → Epic → User Story → Ticket
- **Quality Gates**: Spec completeness, Architecture review, Automated test coverage, Code review, Security & compliance, Release readiness
- **Maturity Curve**: 5 níveis (Non-adopters → Individual → Standardized → AI-Augmented → AI-Native)
- **Novos papéis**: Agentic Architect, Agent Coach, Agentic Validation Architect
- **Agent Bench**: Coleção curada de agentes especializados por domínio
- **Métricas**: Speed, Quality, Agent Autonomy, Cost (não atividade: tokens, linhas de código)
- **Context Debt**: Decisões informais que nunca voltam para os artifacts formais

### 2. langgraph-coding-agent-open-swe-arquitetura.md
Proposta de arquitetura técnica para um coding agent. Principais contribuições:

- **3 agentes especializados**: Planner, Implementer, Reviewer
- **LangGraph StateGraph** com `interrupt()` para human-in-the-loop
- **Jira via Atlassian Rovo MCP** + `langchain-mcp-adapters`
- **GitHub**: Git local no sandbox (implementação) + GitHub CLI/MCP (controle)
- **OpenSpec** como camada de especificação formal
- **8 fases de implementação** progressivas
- **State do LangGraph**: `CodingState` com campos para Jira, Git, OpenSpec, implementação, testes, review, delivery

### 3. Open SWE (código real)
Framework open source da LangChain, base escolhida para o projeto. Características:

- **Single Deep Agent** (não multi-agente) via `deepagents.create_deep_agent`
- **Plan mode**: `enter_plan_mode` / `approve_plan` (tools, não agentes separados)
- **Sandbox isolado**: Modal, Daytona, Runloop, E2B, LangSmith
- **Middleware stack**: 12 camadas (Sanitize, ModelCallLimit, ToolError, SubdirAgents, MessageQueue, SlackStatus, EmptyMsg, StepLimit, CircuitBreaker, Fallback, ThinkingBlocks, Timeout)
- **Triggers**: Slack, Linear, GitHub (webhooks + thread-id derivation)
- **Subagentes**: General purpose + Browser (via `task` tool)
- **Reviewer graph**: Agente separado, read-only, findings model, aprende estilo do repo
- **CI auto-fix**: "PR babysitting" com confidence-gated fix runs
- **Dashboard**: OAuth, perfis, team settings, review styles
- **Tools**: ~30 tools curadas (Linear, Slack, GitHub, HTTP, web search, plan, etc.)
- **Integrações**: Corridor MCP, Datadog MCP, LangSmith tools, Currents, Notion, Stagehand Browser

### 4. Sensedia AI Gateway (`sensedia-ai-gateway-agent-demo-*`)
App Flask que já integra Jira via MCP publicado pelo AI Gateway. Investigado como
possível camada de acesso ao Jira — avaliado e adiado; ver `06-ai-gateway-sensedia.md`.
Contribuições aproveitadas:

- `docs/swagger_jira_custom.yaml` — contrato dos 6 endpoints Jira REST v3 usados
- Normalização de ADF (`_pre_validate_add_comment`) — texto de LLM quebra o Jira
- Confirmação de que `transitionIssue` exige transition id, não nome de coluna
- `AtlassianTokenService` — referência de OAuth 3LO headless, caso seja necessário depois

### 5. Board SSAI em `sensedia.atlassian.net`
Projeto `Sensedia AI Day`, criado para este workflow. 11 status, transições globais em
todos. Três nomes são defaults do Jira mantidos como estão (`BACKLOG`, `In Progress`,
`Done`); os outros oito foram criados para o fluxo. Validado pelo spike — ver
`07-spike-validacao.md`.

### 6. Repositório sob teste: `guilhermeallen/sensedia-backend-case`
Backend FastAPI que o card `SSAI-88` reporta. Branch padrão é **`master`**, não `main`.
É o primeiro caso real de ponta a ponta, e é bem instrumentado: o card traz traceback
apontando arquivo e linha, logs nos comentários, e uma ambiguidade de produto genuína
que o agente precisa escalar em vez de resolver. Ver o exemplo trabalhado em
`../prompts/spec-grounding.md`.

## Premissas estabelecidas

1. **Open SWE é a fundação** — não se reescreve o núcleo, apenas se estende
2. **Jira é o trigger primário** — board `SSAI` em `sensedia.atlassian.net`, 11 colunas
   com transições globais, já criado e validado
3. **`BACKLOG` é a coluna de trigger** — card que cai lá inicia o fluxo, sem gesto
   separado de "pronto para desenvolvimento" (Decisão 11)
4. **OpenSpec é obrigatório** — camada de especificação estruturada
5. **Aprovação humana via colunas do Jira** — agente move o card e **encerra o run**;
   um poller retoma a thread quando o humano avança o card (Decisão 1)
6. **Branch naming**: `feat/spec-JIRA-XXXX-descricao-curta` — sem dois-pontos, o slug
   precisa passar em `git check-ref-format`
7. **Spec ancorada em duas fontes** — dados do card e código do repo (Decisão 12)
8. **Métricas via LangSmith** — já integrado no Open SWE
