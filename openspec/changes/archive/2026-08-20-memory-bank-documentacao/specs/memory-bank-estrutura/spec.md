## ADDED Requirements

### Requirement: Estrutura de pastas do memory bank
O repositório SHALL conter uma pasta `memory-bank/` na raiz com a seguinte estrutura mínima:

```
memory-bank/
├── projectbrief.md
├── productContext.md
├── systemPatterns.md
├── techContext.md
├── activeContext.md
├── progress.md
├── agents/
└── camadas/
```

#### Scenario: Estrutura criada
- **WHEN** a mudança é aplicada
- **THEN** a pasta `memory-bank/` existe na raiz com os 6 arquivos de contexto global e as subpastas `agents/` e `camadas/`

### Requirement: Documentos de contexto global
Cada um dos 6 documentos de contexto global (`projectbrief.md`, `productContext.md`, `systemPatterns.md`, `techContext.md`, `activeContext.md`, `progress.md`) SHALL existir e conter conteúdo correspondente ao seu propósito no padrão Memory Bank.

#### Scenario: projectbrief descreve o framework
- **WHEN** um leitor abre `memory-bank/projectbrief.md`
- **THEN** encontra uma visão geral do framework (LangGraph + Deep Agents, fork Sensedia do Open SWE) com requisitos e objetivos centrais

#### Scenario: systemPatterns descreve a arquitetura
- **WHEN** um leitor abre `memory-bank/systemPatterns.md`
- **THEN** encontra a arquitetura do sistema: sandbox lifecycle, middleware stack, model routing, e relações entre componentes

#### Scenario: techContext descreve a stack
- **WHEN** um leitor abre `memory-bank/techContext.md`
- **THEN** encontra a stack tecnológica (LangGraph, Deep Agents, FastAPI, uv, ruff, basedpyright, providers de sandbox) e constraints

#### Scenario: activeContext e progress refletem o estado
- **WHEN** um leitor abre `memory-bank/activeContext.md` e `memory-bank/progress.md`
- **THEN** encontra o foco atual de desenvolvimento e o roadmap/o que funciona, respectivamente
