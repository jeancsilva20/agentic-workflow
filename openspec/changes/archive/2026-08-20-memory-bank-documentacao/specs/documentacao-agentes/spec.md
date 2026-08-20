## ADDED Requirements

### Requirement: Um documento por agente
A pasta `memory-bank/agents/` SHALL conter um documento Markdown para cada um dos 5 grafos/agentes do sistema: `main-agent.md`, `reviewer.md`, `analyzer.md`, `chat.md`, `scheduler.md`.

#### Scenario: Cinco documentos de agente
- **WHEN** a mudança é aplicada
- **THEN** `memory-bank/agents/` contém exatamente os 5 documentos: main-agent, reviewer, analyzer, chat, scheduler

### Requirement: Template de 6 dimensões por agente
Cada documento de agente SHALL seguir o template com as 6 dimensões: **Objetivo**, **Intenção**, **Resultado**, **Fluxo de Entrada/Saída**, **Conexões**, **Ferramentas**.

#### Scenario: Todas as dimensões presentes
- **WHEN** um leitor abre qualquer documento em `memory-bank/agents/`
- **THEN** encontra as 6 seções: Objetivo, Intenção, Resultado, Fluxo de Entrada/Saída, Conexões, Ferramentas

#### Scenario: Objetivo descreve o propósito
- **WHEN** um leitor lê a seção Objetivo de um agente
- **THEN** encontra por que o agente existe, qual problema resolve e quando é acionado

#### Scenario: Intenção descreve limites
- **WHEN** um leitor lê a seção Intenção de um agente
- **THEN** encontra os princípios de comportamento e limites (ex.: reviewer é read-only, nunca abre PR)

#### Scenario: Resultado descreve artefatos
- **WHEN** um leitor lê a seção Resultado de um agente
- **THEN** encontra os artefatos produzidos (findings, PR, spec, relatório) e critérios de sucesso

#### Scenario: Fluxo de Entrada/Saída descreve I/O
- **WHEN** um leitor lê a seção Fluxo de Entrada/Saída de um agente
- **THEN** encontra as entradas (eventos que o disparam, metadados de thread, config) e saídas (mensagens, PRs, comentários, artefatos persistidos)

#### Scenario: Conexões descreve interações
- **WHEN** um leitor lê a seção Conexões de um agente
- **THEN** encontra os outros agentes com que interage e os stores compartilhados (sandbox, thread metadata, LangSmith, dashboard)

#### Scenario: Ferramentas lista as tools
- **WHEN** um leitor lê a seção Ferramentas de um agente
- **THEN** encontra a lista exata de ferramentas expostas àquele agente, espelhando o wiring real em `agent/server.py`, `agent/reviewer.py`, `agent/analyzer.py`, `agent/chat.py`

### Requirement: Conteúdo fiel ao código
O conteúdo de cada documento de agente SHALL ser fiel ao código real, com referências de arquivo:linha quando relevante, e refletir o mapeamento feito na exploração inicial.

#### Scenario: Referências de arquivo
- **WHEN** um documento descreve o agente main-agent
- **THEN** referencia `agent/server.py` (factory `get_agent`) e o wiring real de tools/middleware/modelo

#### Scenario: Reviewer documentado como read-only
- **WHEN** um leitor lê `memory-bank/agents/reviewer.md`
- **THEN** encontra que o reviewer é read-only (sem commit/push/abrir PR) e usa o modelo Opus/high
