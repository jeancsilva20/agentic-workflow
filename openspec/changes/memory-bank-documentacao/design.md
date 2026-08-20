## Context

O repositório é um fork da Sensedia do Open SWE (LangChain), estendido para um workflow Jira + OpenSpec com gates de aprovação humana. A exploração inicial (5 lanes paralelas) mapeou o sistema completo:

- **5 grafos LangGraph**: `agent` (server.py), `reviewer` (reviewer.py), `analyzer` (analyzer.py), `chat` (chat.py), `scheduler` (scheduler.py).
- **~52 tools** em `agent/tools/`, **24 middlewares**, **6 providers de sandbox**, **6 integrações MCP** (Corridor, Datadog, Notion, Stagehand, Currents, LangSmith), **3 webhooks** (GitHub, Linear, Slack), **15 papéis de routing**.
- **Camada de gestão**: dashboard FastAPI (~94 rotas), agent-console Flask, UI React/TanStack.

O conhecimento está disperso. Esta mudança cria um memory bank estruturado e versionado, carregado pelo OpenCode.

## Goals / Non-Goals

**Goals:**
- Criar uma estrutura de memory bank na raiz (`memory-bank/`) seguindo o padrão de mercado (Cline), com documentos de contexto global e por agente.
- Documentar cada agente com: objetivo, intenção, resultado, fluxo de entrada/saída, conexões e ferramentas.
- Documentar cada camada transversal (middleware, tools, routing, dashboard-console, webhooks, sandbox).
- Integrar o memory bank ao OpenCode via `opencode.json` (`instructions`).
- Manter o memory bank versionado, legível por humanos e auditável em PR.

**Non-Goals:**
- Substituir `openwiki/` (regenerado por GitHub Actions) ou `docs/`.
- Alterar qualquer código de runtime do sistema.
- Criar memória vetorial/dinâmica (plugins como opencode-mem) — apenas documentação estática versionada.
- Documentar cada tool/middleware individualmente em arquivos separados (granularidade excessiva).

## Decisions

### 1. Formato: Memory Bank clássico (Cline) + pasta `agents/`

**Decision:** Adotar a estrutura clássica do Memory Bank (popularizada pelo Cline, agnóstica de ferramenta) combinada com uma pasta `agents/` para granularidade por agente.

**Rationale:**
- O padrão é de mercado e agnóstico de ferramenta — adotado por Microsoft BuildXL, Gitpod e GitHub Copilot (`awesome-copilot`).
- A hierarquia `projectbrief → productContext/systemPatterns/techContext → activeContext → progress` provê contexto global sólido.
- A pasta `agents/` atende à necessidade específica de documentar cada agente com as 6 dimensões pedidas.

**Alternatives considered:**
- **Somente docs por agente** (sem contexto global): perderia a visão sistêmica.
- **Memory Bank puro** (sem pasta agents/): não atenderia à granularidade por agente.
- **Memória vetorial** (opencode-mem, etc.): não versionada, não auditável, inadequada para documentação de framework.

### 2. Local: nova pasta `memory-bank/` na raiz

**Decision:** Criar `memory-bank/` na raiz, separada de `openwiki/` e `docs/`.

**Rationale:**
- `openwiki/` é regenerado por GitHub Actions — não deve ser editado manualmente.
- `docs/` já contém documentação de referência; o memory bank é uma camada de contexto operacional distinta.
- Uma pasta dedicada é autoexplicativa e fácil de referenciar no `opencode.json`.

### 3. Granularidade: por agente + por camada

**Decision:** Um documento por agente (5) + um documento por camada transversal (6).

**Rationale:**
- Os 5 grafos são as unidades de execução; cada um merece um documento completo.
- As camadas transversais (middleware, tools, routing, dashboard-console, webhooks, sandbox) são compartilhadas e merecem documentação própria.
- Evita granularidade excessiva (um arquivo por tool/middleware) que tornaria o memory bank difícil de navegar.

### 4. Carregamento: via `opencode.json` `instructions`

**Decision:** Criar `opencode.json` na raiz com o campo `instructions` listando os arquivos do memory bank.

**Rationale:**
- É o mecanismo nativo do OpenCode para carregar regras/documentação no contexto.
- Alternativa ao lazy-loading via referências no AGENTS.md, que exige que o agente decida ler sob demanda.

**Alternative considered:** referenciar apenas no AGENTS.md (lazy loading) — menos contexto automático, mais decisão do agente.

### 5. Template por agente (6 dimensões)

**Decision:** Cada documento de agente segue o template: **Objetivo → Intenção → Resultado → Fluxo de Entrada/Saída → Conexões → Ferramentas**.

**Rationale:**
- Cobre exatamente o que o usuário pediu.
- É o contrato de capacidade do agente — espelha a lista de tools wired em cada grafo.

## Risks / Trade-offs

- **Drift de documentação**: o memory bank pode ficar desatualizado conforme o código evolui. Mitigação: versionado em PR, revisável; o `activeContext.md` registra o estado atual.
- **Coexistência com openwiki**: o openwiki regenera páginas derivadas; o memory bank é a fonte manual. Mitigação: escopos distintos (openwiki = docs geradas; memory bank = contexto operacional por agente).
- **Volume de contexto**: carregar todos os arquivos via `instructions` aumenta o contexto inicial. Mitigação: documentos concisos e focados; pode-se ajustar a lista no `opencode.json` conforme necessário.
- **`opencode.json` inexistente hoje**: será criado; deve respeitar o schema do OpenCode.
