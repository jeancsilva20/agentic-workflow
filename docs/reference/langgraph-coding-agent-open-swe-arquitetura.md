# Proposta de Arquitetura — Coding Agent com LangGraph, Jira MCP, GitHub e OpenSpec

## Recomendação

Para este projeto, a base mais aderente é o **Open SWE**, da LangChain:

- Repositório: https://github.com/langchain-ai/open-swe
- Clone:

```bash
git clone https://github.com/langchain-ai/open-swe.git
cd open-swe
```

O Open SWE é um framework open source para construir coding agents internos e utiliza LangGraph/Deep Agents como parte de sua arquitetura.

Ele já resolve grande parte da infraestrutura necessária para um agente que:

- recebe uma demanda;
- acessa um repositório;
- entende o código existente;
- executa comandos;
- modifica arquivos;
- executa testes;
- revisa alterações;
- trabalha com branches;
- e publica o resultado no GitHub.

A proposta é **não usar o workflow padrão do Open SWE sem alterações**. O ideal é aproveitar seu runtime, sandbox, ferramentas de código e integração com GitHub, adicionando por cima um workflow LangGraph explicitamente controlado.

---

## Objetivo do agente

O agente deverá consumir três fontes principais de contexto:

1. **Jira**
   - Issue.
   - Descrição.
   - Critérios de aceite.
   - Comentários.
   - Links e informações relacionadas.

2. **GitHub**
   - Repositório da aplicação.
   - Código-fonte.
   - Histórico Git quando necessário.
   - Branches.
   - Pull Requests.

3. **OpenSpec**
   - Especificações existentes.
   - Proposal da alteração.
   - Design.
   - Tasks.
   - Estado do planejamento.

O agente deverá executar um ciclo controlado:

```text
Jira
  ↓
Carregar repositório
  ↓
Analisar código
  ↓
OpenSpec
  ↓
Planejamento
  ↓
AGUARDAR APROVAÇÃO HUMANA
  ↓
"OK"
  ↓
Implementação
  ↓
Testes
  ↓
Code Review
  ↓
Correções, se necessário
  ↓
Testes finais
  ↓
Pull Request
  ↓
Atualização do Jira
```

---

# Arquitetura proposta

```text
                         JIRA
                          │
                    Atlassian MCP
                          │
                          ▼
                 ┌─────────────────┐
                 │  Jira Context   │
                 │ issue/comments  │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │ Clone GitHub    │
                 │ Repo / Branch   │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │    OpenSpec     │
                 │ context/specs   │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │ Planner Agent   │
                 │                 │
                 │ proposal        │
                 │ design          │
                 │ specs           │
                 │ tasks           │
                 └────────┬────────┘
                          │
                          ▼
                ╔═══════════════════╗
                ║ LANGGRAPH         ║
                ║ interrupt()       ║
                ║                   ║
                ║ Plano pronto.     ║
                ║ Implementar?      ║
                ╚═════════╤═════════╝
                          │
                 ┌────────┴────────┐
                 │                 │
              AJUSTAR             OK
                 │                 │
                 └──► Planner      ▼
                              ┌─────────────┐
                              │ Implementer │
                              │ Agent       │
                              └──────┬──────┘
                                     │
                                     ▼
                              alterar código
                                     │
                                     ▼
                              executar testes
                                     │
                                     ▼
                              ┌─────────────┐
                              │ Reviewer    │
                              │ Agent       │
                              └──────┬──────┘
                                     │
                                     ▼
                              Review Result
                                 │       │
                    CHANGES_REQUIRED    PASS
                                 │       │
                                 ▼       ▼
                          Implementer   PR
```

---

# Por que LangGraph

O LangGraph é especialmente adequado para esse fluxo porque permite combinar:

- passos determinísticos;
- decisões baseadas em LLM;
- persistência de estado;
- execução durável;
- human-in-the-loop;
- checkpoints;
- retomada de uma execução interrompida.

O ponto principal será utilizar `interrupt()`.

Exemplo conceitual:

```python
from langgraph.types import interrupt

def approval_node(state):
    decision = interrupt({
        "type": "plan_approval",
        "message": "O planejamento foi concluído.",
        "plan": state["plan"],
        "question": "Deseja implementar?"
    })

    return {
        "planning_approved": decision == "OK"
    }
```

O workflow poderá parar nesse ponto.

Quando o usuário responder:

```text
OK
```

o graph será retomado a partir do checkpoint persistido.

Isso é importante porque o usuário pode aprovar o plano minutos, horas ou até posteriormente, sem precisar reconstruir manualmente todo o contexto da execução.

---

# Base: Open SWE

A recomendação é fazer um fork do:

```text
langchain-ai/open-swe
```

Clone:

```bash
git clone https://github.com/langchain-ai/open-swe.git
cd open-swe
```

Repositório:

https://github.com/langchain-ai/open-swe

O projeto foi desenhado para customização. A documentação do projeto aponta `agent/server.py` e a montagem do agente como um dos principais pontos de extensão.

A ideia é aproveitar principalmente:

- runtime de coding agent;
- sandbox;
- acesso ao filesystem;
- execução de shell;
- leitura de arquivos;
- edição de arquivos;
- busca no código;
- execução de testes;
- subagentes;
- integração com Git/GitHub;
- infraestrutura já existente do projeto.

E substituir/adaptar os triggers e integrações que não forem necessárias.

---

# Jira via MCP

Para Jira, a recomendação é utilizar o **Atlassian Rovo MCP Server**.

Documentação:

https://support.atlassian.com/atlassian-rovo-mcp-server/docs/getting-started-with-the-atlassian-remote-mcp-server/

O MCP pode fornecer ao agente operações relacionadas a Jira e Confluence conforme as permissões disponibilizadas.

Uma camada possível seria:

```text
LangGraph
   │
   ▼
langchain-mcp-adapters
   │
   ▼
Atlassian Rovo MCP
   │
   ▼
Jira
```

A biblioteca oficial de adaptação MCP da LangChain está em:

https://github.com/langchain-ai/langchain-mcp-adapters

Instalação:

```bash
pip install langchain-mcp-adapters
```

Ela permite carregar ferramentas MCP para utilização por agentes LangChain/LangGraph.

Exemplo conceitual:

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({
    "jira": {
        "transport": "streamable_http",
        "url": "<MCP_URL>"
    }
})

tools = await client.get_tools()
```

O conjunto final pode expor capacidades como:

```text
jira_search
jira_get_issue
jira_get_comments
jira_add_comment
jira_transition_issue
```

As ferramentas efetivamente disponíveis dependerão das permissões e configuração do servidor MCP.

---

# GitHub

Há duas formas de trabalhar com GitHub.

## 1. Git local no sandbox — recomendado para implementação

O código deve ser realmente clonado para o sandbox do agente.

```text
GitHub
   │
   ▼
git clone
   │
   ▼
Sandbox
   │
   ├── grep
   ├── find
   ├── git diff
   ├── editar arquivos
   ├── executar testes
   ├── lint
   └── build
```

Exemplo:

```bash
git clone git@github.com:empresa/projeto.git
cd projeto

git checkout -b feature/JIRA-1234
```

Durante o desenvolvimento:

```bash
git status
git diff
pytest
ruff check .
```

Depois:

```bash
git add .
git commit -m "feat: implement JIRA-1234"
git push origin feature/JIRA-1234
```

Esse é o mecanismo recomendado para o **coding agent**, porque ele terá acesso a um checkout real da aplicação.

---

## 2. GitHub MCP — opcional

Existe também o servidor MCP oficial do GitHub:

https://github.com/github/github-mcp-server

Ele pode ser utilizado para operações de controle como:

- buscar informações do repositório;
- consultar issues;
- consultar commits;
- consultar PRs;
- criar ou atualizar PRs;
- automações relacionadas ao GitHub.

Minha recomendação é:

```text
Código / build / testes
        ↓
 Git local no sandbox

Controle GitHub / metadata / PR
        ↓
 GitHub CLI ou GitHub MCP
```

---

# OpenSpec

O OpenSpec será responsável pela camada de especificação e planejamento.

Site:

https://openspec.dev/

Documentação:

https://openspec.dev/docs

Agent Contract:

https://openspec.dev/docs/reference/agents

As specs podem viver dentro do próprio repositório:

```text
projeto/
│
├── src/
├── tests/
│
└── openspec/
    ├── specs/
    │   ├── auth/
    │   │   └── spec.md
    │   └── payments/
    │       └── spec.md
    │
    └── changes/
```

O Agent Contract do OpenSpec disponibiliza saídas machine-readable, inclusive em JSON.

Exemplos relevantes:

```bash
openspec status --json
openspec validate --json
openspec instructions <artifact> --json
openspec instructions apply --json
```

Isso permite que o LangGraph tome decisões usando dados estruturados em vez de tentar inferir o estado do planejamento apenas lendo texto livre.

---

# Fluxo OpenSpec + LangGraph

```text
Jira Issue
    │
    ▼
Planner
    │
    ▼
OpenSpec
    │
    ├── proposal
    ├── specs
    ├── design
    └── tasks
    │
    ▼
openspec status --json
    │
    ▼
planningComplete?
    │
    ├── NÃO ─────► Planner
    │
    └── SIM
          │
          ▼
      interrupt()
          │
          ▼
       AGUARDA
          │
         "OK"
          │
          ▼
openspec instructions apply --json
          │
          ▼
     Implementer
```

---

# Separação de agentes

Minha recomendação é utilizar pelo menos três papéis.

## 1. Planner Agent

Responsabilidades:

```text
Jira
 +
Código atual
 +
OpenSpec existente
        │
        ▼
     Planner
        │
        ├── analisar impacto
        ├── identificar arquivos envolvidos
        ├── identificar dependências
        ├── definir arquitetura
        ├── definir testes
        └── gerar plano de implementação
```

Saídas:

```text
proposal
design
specs
tasks
```

O Planner **não implementa código**.

---

# Gate de aprovação

Depois do planejamento:

```text
Planner
   │
   ▼
OpenSpec
   │
   ▼
interrupt()
   │
   ▼

Plano:

1. alterar service X
2. adicionar adapter Y
3. alterar endpoint Z
4. criar testes A/B/C

Deseja implementar?

[OK]
[AJUSTAR]
[CANCELAR]
```

Somente `OK` libera o próximo node.

---

# 2. Implementer Agent

Entrada:

```text
OpenSpec aprovado
+
repositório
+
tasks
```

Responsabilidades:

- criar branch;
- editar código;
- executar tarefas do OpenSpec;
- criar ou alterar testes;
- executar lint;
- executar build;
- executar testes;
- atualizar progresso das tasks.

Fluxo:

```text
Implementer
     │
     ├── Task 1
     ├── Task 2
     ├── Task 3
     │
     ▼
   Tests
```

---

# 3. Reviewer Agent

O Reviewer deve ser separado do Implementer.

Entrada:

```text
OpenSpec
+
git diff
+
arquivos modificados
+
resultado dos testes
```

Responsabilidades:

- validar os critérios do Jira;
- validar a implementação contra a especificação;
- procurar regressões;
- identificar bugs;
- identificar problemas de arquitetura;
- verificar segurança;
- verificar tratamento de erros;
- verificar cobertura de testes;
- procurar código desnecessário;
- verificar breaking changes.

Resultado estruturado:

```json
{
  "status": "CHANGES_REQUIRED",
  "findings": [
    {
      "severity": "high",
      "file": "src/service.py",
      "description": "Missing validation for ..."
    }
  ]
}
```

ou:

```json
{
  "status": "PASS",
  "findings": []
}
```

---

# Loop Implementer / Reviewer

```text
Implementer
     │
     ▼
Tests
     │
     ▼
Reviewer
     │
     ├──── PASS ────────────────┐
     │                           │
     └──── CHANGES_REQUIRED      │
                │                │
                ▼                │
           Implementer           │
                │                │
                ▼                │
              Tests              │
                │                │
                └──► Reviewer    │
                                 │
                                 ▼
                            Final Tests
                                 │
                                 ▼
                                PR
```

Pode ser definido um limite máximo de ciclos para evitar loops infinitos.

Exemplo:

```python
MAX_REVIEW_CYCLES = 3
```

Se exceder:

```text
NEEDS_HUMAN_REVIEW
```

---

# State do LangGraph

Uma estrutura inicial poderia ser:

```python
from typing import TypedDict


class CodingState(TypedDict):

    # Jira
    jira_issue_key: str
    jira_context: dict

    # Git
    repo_owner: str
    repo_name: str
    repo_path: str
    base_branch: str
    working_branch: str

    # OpenSpec
    openspec_change: str
    plan: dict
    planning_complete: bool
    planning_approved: bool

    # Implementation
    changed_files: list[str]

    # Tests
    test_results: dict

    # Review
    review_cycle: int
    review_findings: list[dict]
    review_status: str

    # Delivery
    pr_url: str | None
```

---

# Nodes iniciais recomendados

Para o primeiro MVP, eu criaria estes nodes:

```text
START
  │
  ▼
jira_context
  │
  ▼
prepare_repo
  │
  ▼
load_openspec_context
  │
  ▼
planner
  │
  ▼
validate_openspec
  │
  ▼
approval
  │
  ├── AJUSTAR ──────► planner
  │
  ├── CANCELAR ─────► END
  │
  └── OK
       │
       ▼
   implement
       │
       ▼
     tests
       │
       ▼
     review
       │
       ├── CHANGES_REQUIRED
       │         │
       │         ▼
       │     implement
       │
       └── PASS
             │
             ▼
        final_tests
             │
             ▼
         create_pr
             │
             ▼
         update_jira
             │
             ▼
            END
```

---

# Estrutura sugerida

Uma estrutura possível no fork:

```text
open-swe/
│
├── agent/
│   │
│   ├── graph/
│   │   ├── state.py
│   │   ├── workflow.py
│   │   └── routing.py
│   │
│   ├── nodes/
│   │   ├── jira_context.py
│   │   ├── prepare_repo.py
│   │   ├── openspec_context.py
│   │   ├── planner.py
│   │   ├── approval.py
│   │   ├── implementer.py
│   │   ├── tests.py
│   │   ├── reviewer.py
│   │   ├── create_pr.py
│   │   └── update_jira.py
│   │
│   ├── integrations/
│   │   ├── jira_mcp.py
│   │   ├── github.py
│   │   └── openspec.py
│   │
│   ├── prompts/
│   │   ├── planner.md
│   │   ├── implementer.md
│   │   └── reviewer.md
│   │
│   └── server.py
│
├── tests/
│
└── ...
```

---

# Workflow conceitual

```python
from langgraph.graph import StateGraph, START, END

builder = StateGraph(CodingState)

builder.add_node("jira_context", jira_context)
builder.add_node("prepare_repo", prepare_repo)
builder.add_node("openspec_context", openspec_context)
builder.add_node("planner", planner)
builder.add_node("approval", approval)
builder.add_node("implementer", implementer)
builder.add_node("tests", run_tests)
builder.add_node("reviewer", reviewer)
builder.add_node("final_tests", final_tests)
builder.add_node("create_pr", create_pr)
builder.add_node("update_jira", update_jira)

builder.add_edge(START, "jira_context")
builder.add_edge("jira_context", "prepare_repo")
builder.add_edge("prepare_repo", "openspec_context")
builder.add_edge("openspec_context", "planner")
builder.add_edge("planner", "approval")

# conditional edges:
#
# approval:
#   OK -> implementer
#   AJUSTAR -> planner
#   CANCELAR -> END
#
# reviewer:
#   PASS -> final_tests
#   CHANGES_REQUIRED -> implementer

builder.add_edge("implementer", "tests")
builder.add_edge("tests", "reviewer")
builder.add_edge("final_tests", "create_pr")
builder.add_edge("create_pr", "update_jira")
builder.add_edge("update_jira", END)

graph = builder.compile(...)
```

---

# Pull Request

Quando o Reviewer retornar `PASS`, o agente executa os testes finais e abre a PR.

Exemplo com GitHub CLI:

```bash
gh pr create \
  --base main \
  --head feature/JIRA-1234 \
  --title "JIRA-1234 - Implement feature" \
  --body-file pr-description.md
```

A descrição da PR pode ser produzida automaticamente:

```markdown
## Jira

JIRA-1234

## Objetivo

Implementar ...

## Alterações

- ...
- ...
- ...

## Testes

- Unit tests
- Integration tests

## OpenSpec

Change: JIRA-1234

## Review

Automated reviewer: PASS
```

Depois da criação:

```text
PR URL
   │
   ▼
Jira MCP
   │
   ├── adicionar comentário
   └── opcionalmente alterar status
```

---

# Segurança

Como o agente terá capacidade de executar comandos e modificar código, as operações deverão acontecer em um ambiente isolado.

Evitar executar o agente diretamente no host em produção.

Recomendações:

- sandbox/container isolado;
- tokens de curta duração quando possível;
- princípio de menor privilégio;
- branch exclusiva por execução;
- nunca permitir push direto em `main`;
- exigir PR;
- proteger operações destrutivas;
- manter human-in-the-loop em ações críticas.

Uma separação razoável:

```text
READ
Jira
GitHub
OpenSpec
      │
      ▼
permitido automaticamente


WRITE LOCAL
filesystem
branch
tests
      │
      ▼
permitido no sandbox


WRITE REMOTE
Jira
GitHub PR
      │
      ▼
policy control / approval quando necessário
```

---

# MVP recomendado

Eu começaria sem tentar construir uma plataforma genérica.

Primeiro MVP:

```text
jira_context
      ↓
prepare_repo
      ↓
openspec_plan
      ↓
approval
      ↓
implement
      ↓
test
      ↓
review
      ↓
create_pr
```

Os oito nodes já entregam o ciclo completo.

---

# Ordem de implementação

## Fase 1

Fork/clone do Open SWE.

```bash
git clone https://github.com/langchain-ai/open-swe.git
```

Objetivo:

- executar localmente;
- entender sandbox;
- entender lifecycle do agente;
- executar uma tarefa simples em um repo de testes.

---

## Fase 2

Jira MCP.

Adicionar:

```text
jira_context
```

Objetivo:

```text
JIRA-1234
     ↓
LangGraph
     ↓
context estruturado
```

---

## Fase 3

OpenSpec.

Adicionar:

```text
planner
+
openspec
```

Gerar:

```text
proposal
specs
design
tasks
```

---

## Fase 4

Human-in-the-loop.

Adicionar:

```text
interrupt()
```

Fluxo:

```text
PLAN
 ↓
WAITING_APPROVAL
 ↓
OK
 ↓
IMPLEMENT
```

---

## Fase 5

Implementer.

Reutilizar a infraestrutura de coding agent do Open SWE.

---

## Fase 6

Reviewer independente.

Adicionar:

```text
Implementer
    ↓
Reviewer
    ↓
PASS / CHANGES_REQUIRED
```

---

## Fase 7

GitHub PR.

Adicionar:

```text
final_tests
      ↓
commit
      ↓
push
      ↓
PR
```

---

## Fase 8

Atualização do Jira.

```text
PR criada
   │
   ▼
Jira
   │
   ├── comentário com PR
   └── atualização de status
```

---

# Stack final

```text
Python
   │
   ├── LangGraph
   │
   ├── Deep Agents / Open SWE
   │
   ├── langchain-mcp-adapters
   │
   ├── OpenSpec
   │
   ├── Git
   │
   └── GitHub CLI / GitHub MCP
   │
   ▼

Integrations

Atlassian Rovo MCP
        │
        ▼
       Jira


Git / GitHub
     │
     ▼
repository + PR


OpenSpec
     │
     ▼
spec-driven development
```

---

# Repositórios e documentação

## Base principal

Open SWE:

https://github.com/langchain-ai/open-swe

Clone:

```bash
git clone https://github.com/langchain-ai/open-swe.git
```

---

## MCP para LangChain/LangGraph

LangChain MCP Adapters:

https://github.com/langchain-ai/langchain-mcp-adapters

---

## Jira MCP

Atlassian Rovo MCP:

https://support.atlassian.com/atlassian-rovo-mcp-server/docs/getting-started-with-the-atlassian-remote-mcp-server/

---

## GitHub MCP

GitHub MCP Server:

https://github.com/github/github-mcp-server

---

## OpenSpec

Site:

https://openspec.dev/

Docs:

https://openspec.dev/docs

Agent Contract:

https://openspec.dev/docs/reference/agents

---

## LangGraph Interrupts

https://docs.langchain.com/oss/python/langgraph/interrupts

---

## LangGraph Persistence

https://docs.langchain.com/oss/python/langgraph/persistence

---

# Decisão final

A arquitetura recomendada é:

```text
Open SWE
   +
LangGraph StateGraph
   +
LangGraph interrupts
   +
Atlassian Rovo MCP
   +
langchain-mcp-adapters
   +
OpenSpec
   +
Git/GitHub
```

Com o fluxo:

```text
JIRA
  ↓
CONTEXT
  ↓
REPOSITORY
  ↓
OPENSPEC
  ↓
PLANNER
  ↓
HUMAN APPROVAL
  ↓
IMPLEMENTER
  ↓
TESTS
  ↓
REVIEWER
  ↓
CORREÇÕES
  ↓
FINAL TESTS
  ↓
PULL REQUEST
  ↓
JIRA UPDATE
```

O Open SWE deve ser tratado como **engine/base do coding agent**, e o `StateGraph` customizado deve controlar o ciclo de vida da tarefa.

Dessa forma, a autonomia do agente fica limitada por estados claros, e a implementação só começa depois de uma aprovação humana explícita.
