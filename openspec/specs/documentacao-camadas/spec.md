## ADDED Requirements

### Requirement: Um documento por camada transversal
A pasta `memory-bank/camadas/` SHALL conter um documento Markdown para cada camada transversal do sistema: `middleware.md`, `tools.md`, `routing.md`, `dashboard-console.md`, `webhooks.md`, `sandbox.md`.

#### Scenario: Seis documentos de camada
- **WHEN** a mudança é aplicada
- **THEN** `memory-bank/camadas/` contém os 6 documentos: middleware, tools, routing, dashboard-console, webhooks, sandbox

### Requirement: Documento de middleware
O documento `memory-bank/camadas/middleware.md` SHALL descrever a stack de middlewares, incluindo a ordem real em `agent/server.py` e `agent/reviewer.py`, o tipo de hook de cada um e o propósito.

#### Scenario: Ordem da stack documentada
- **WHEN** um leitor abre `memory-bank/camadas/middleware.md`
- **THEN** encontra a ordem da stack do server (19 camadas) e do reviewer (13 camadas), com o tipo de hook de cada middleware

#### Scenario: Middlewares não conectados identificados
- **WHEN** um leitor abre `memory-bank/camadas/middleware.md`
- **THEN** encontra a nota de que `ensure_no_empty_msg`, `SandboxCircuitBreakerMiddleware` e `WorkflowPushGuardMiddleware` estão definidos mas não conectados à stack real (apenas exercitados em testes)

### Requirement: Documento de tools
O documento `memory-bank/camadas/tools.md` SHALL inventariar as ~52 tools em `agent/tools/`, agrupadas por categoria (jira, openspec, linear, slack, github/pr, review, util), com propósito, entrada, saída e qual agente usa cada uma.

#### Scenario: Inventário por categoria
- **WHEN** um leitor abre `memory-bank/camadas/tools.md`
- **THEN** encontra as tools agrupadas por categoria, com propósito, entrada, saída e o agente que as usa

### Requirement: Documento de routing
O documento `memory-bank/camadas/routing.md` SHALL descrever o sistema de routing de modelos: o enum `AgentRole`, a tabela de rotas por papel, o cálculo de complexidade, a escalada e a telemetria de uso.

#### Scenario: Tabela de rotas por papel
- **WHEN** um leitor abre `memory-bank/camadas/routing.md`
- **THEN** encontra a tabela de papéis → modelo/esforço (Haiku/Sonnet/Opus) e as regras de escalada

### Requirement: Documento de dashboard-console
O documento `memory-bank/camadas/dashboard-console.md` SHALL descrever a camada de gestão: a webapp FastAPI, o dashboard (~94 rotas), o agent-console Flask e a UI React.

#### Scenario: Superfícies de gestão documentadas
- **WHEN** um leitor abre `memory-bank/camadas/dashboard-console.md`
- **THEN** encontra as três superfícies de gestão (webapp/dashboard, agent-console, UI) e suas responsabilidades

### Requirement: Documento de webhooks
O documento `memory-bank/camadas/webhooks.md` SHALL descrever os 3 webhooks (GitHub, Linear, Slack), os eventos processados e a derivação determinística de thread-ids.

#### Scenario: Webhooks e thread-ids documentados
- **WHEN** um leitor abre `memory-bank/camadas/webhooks.md`
- **THEN** encontra os 3 webhooks, os eventos que processam e as funções de derivação de thread-id

### Requirement: Documento de sandbox
O documento `memory-bank/camadas/sandbox.md` SHALL descrever o ciclo de vida do sandbox: os 6 providers, o proxy GitHub, o estado por thread e o tratamento de sandbox inalcançável.

#### Scenario: Ciclo de vida do sandbox documentado
- **WHEN** um leitor abre `memory-bank/camadas/sandbox.md`
- **THEN** encontra os 6 providers, o mecanismo de proxy GitHub, o `SANDBOX_BACKENDS` e o `SandboxUnreachableError`
