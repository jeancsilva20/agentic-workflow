# Exploração Arquitetural — Migração LangGraph → Langflow

> **Fase:** Explore do OpenSpec (análise pré-proposal)
> **Objetivo:** Diagnóstico arquitetural profundo para planejar a migração incremental da aplicação (LangGraph + Deep Agents) para Langflow com o menor risco possível.
> **Escopo:** Análise e auditoria do estado atual. **Não** inclui proposal nem implementação.
> **Data:** 2026-08-20

---

## 1. Resumo Executivo

O sistema é um **coding agent interno** (fork Sensedia do Open SWE) construído sobre **LangGraph + Deep Agents** (`create_deep_agent`). Ele executa um fluxo **Spec-Driven Development** acionado principalmente por cards do Jira, com 3 gates de aprovação humana, e também responde a Slack, Linear e GitHub.

**Descoberta central:** dos 5 grafos, **4 são deep agents** (`agent`, `reviewer`, `analyzer`, `chat`) — seus "nodes/edges" não são definidos no repositório, mas sim o loop interno modelo↔tool da biblioteca `deepagents`. Apenas o `scheduler` é um `StateGraph` procedural escrito à mão (`START → launch → END`). Isso muda fundamentalmente a natureza da migração: **não estamos portando grafos com nodes/edges explícitos, mas sim 4 configurações de deep agent** (tools + middleware + subagents + role de routing + prompt injetado em runtime).

**A maior lacuna de migração é a persistência:** não há banco de dados. Todo estado durável (metadata de thread, KV store, checkpointer, `sandbox_id`) é gerenciado pela plataforma LangGraph. Não existe camada de DB portátil.

**Integrações Bitbucket, Confluence e Google Drive NÃO existem no código** — zero ocorrências. São apenas menções em docs/prompts. Não há nada a migrar dessas integrações.

**Bloqueador identificado:** `jira_park_at_gate` tem não-atomicidade que pode **orfanar silenciosamente um card num gate**, perdendo o sinal de aprovação humana.

---

## 2. Mapa da Arquitetura Atual

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CAMADA DE ENTRADA (Triggers)                          │
│  Jira poller (60s) │ GitHub webhooks │ Linear webhooks │ Slack webhooks     │
│  dashboard │ scheduler cron │ reconcile                                       │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ dispatch_agent_run (langgraph_sdk)
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CAMADA DE ORQUESTRAÇÃO (5 grafos LangGraph)               │
│                                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │  agent   │  │ reviewer │  │ analyzer │  │   chat   │  │  scheduler   │  │
│  │ (deep)   │  │ (deep)   │  │ (deep)   │  │ (deep)   │  │ (procedural) │  │
│  │ server.py│  │reviewer.py│ │analyzer.py│ │ chat.py  │  │ scheduler.py │  │
│  │  :1008   │  │  :1328   │  │  :165    │  │  :180    │  │    :38       │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘  │
│       │             │             │             │               │           │
│  subagents:     subagent:     (nenhum)     subagent:      roteia por task: │
│  general-purpose browser        │        general-purpose   jira_poll /      │
│  (mesmo modelo)                 │        (read-only FS)    reconcile /      │
│                                 │                            schedule_id    │
└─────────────────────────────────┼───────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────────┐
        ▼                         ▼                             ▼
┌───────────────┐      ┌──────────────────┐          ┌──────────────────────┐
│  TOOLS (52+)  │      │  MIDDLEWARE (24) │          │  ROUTING (15 roles)  │
│ Jira/Linear/  │      │  server: 19      │          │  modelo+effort por   │
│ Slack/GitHub/ │      │  reviewer: 13    │          │  papel; escalada;    │
│ OpenSpec/     │      │  4 NÃO ligados   │          │  complexidade det.   │
│ Review/Plan   │      └──────────────────┘          └──────────────────────┘
└───────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CAMADA DE EXECUÇÃO / INFRAESTRUTURA                        │
│  Sandbox (6 providers, proxy GitHub, 3 casos) │ checkpointer (in-memory)    │
│  thread metadata + KV store (LangGraph Platform) │ turn_checkpoint (git)    │
│  completion webhook │ plan mode │ gates Jira │ workflow approval            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Inventário dos Workflows/Grafos

| Grafo | Tipo | Entrypoint | Modelo/Effort | Limites | Tools | Subagents |
|---|---|---|---|---|---|---|
| **agent** | deep agent | `server.py:1008` | role do dispatch (CODING_AGENT→Sonnet/med, escala Opus) | rec 9999, calls 5000 | 38 estáticas + 9 builtins + dinâmicas | general-purpose, browser |
| **reviewer** | deep agent | `reviewer.py:1328` | CODE_REVIEWER→Opus/high | rec 9999, calls 5000 | 10 + builtins | reviewer (1×) |
| **analyzer** | deep agent | `analyzer.py:165` | STYLE_ANALYZER→Sonnet/med | rec 9999, calls **80** | 2 + builtins | nenhum |
| **chat** | deep agent | `chat.py:180` | REVIEW_CHAT→Sonnet/med | rec 9999, calls **100** | 5 + builtins (read-only) | general-purpose (FS read-only) |
| **scheduler** | StateGraph procedural | `scheduler.py:38` | nenhum | n/a | nenhum | nenhum |

**Fluxo conceitual (todos os deep agents):**
```
entrada (config + mensagem)
  → Prepare*RunMiddleware (injeta prompt renderizado + contexto sandbox/diff)
  → loop modelo↔tool (tools + middleware ao redor de cada chamada)
  → decisões condicionais = chamadas de tool do modelo (não edges explícitas)
  → saída = mensagem sem tool call (única condição de saída)
```

**Side effects:** PRs (open_pull_request), transições Jira + gates (jira_park_at_gate), respostas Slack/Linear, commits/pushes via `execute`+`gh`, metadata de thread, snapshots turn_checkpoint, uso/telemetria.

---

## 4. Dependências Entre Camadas

```
webhooks/poller ──► dispatch ──► grafos (deep agents)
grafos ──► tools ──► utils (jira/linear/slack/github/http) ──► APIs externas
grafos ──► middleware ──► sandbox_state / thread metadata / store
grafos ──► routing ──► dashboard.options (catálogo de modelos)
sandbox ──► deepagents SandboxBackendProtocol ──► providers (langsmith/daytona/...)
completion webhook ◄── dispatch (webhook de callback)
scheduler ──► jira_poller / reconcile / schedules
```

**Acoplamentos críticos a LangGraph:**
- `langgraph.config.get_config()` — lido por quase todas as tools (thread_id, configurable)
- `langgraph_sdk.get_client()` — metadata de thread, KV store, crons, runs
- `langchain.agents.middleware` — interface de TODOS os 24 middlewares
- `deepagents.backends.sandbox.BaseSandbox` — protocolo dos 6 providers
- `langgraph.types.Command` / `InjectedState` — tools de plan mode
- checkpointer + store — toda persistência

---

## 5. Auditoria de Integridade dos Fluxos

| # | Achado | Local | Severidade | Status |
|---|---|---|---|---|
| 1 | `ensure_no_empty_msg` NÃO ligado → risco de término prematuro | stacks server/reviewer/analyzer/chat | **CORRIGIR NA MIGRAÇÃO** | PROVADO |
| 2 | Poller Step B: double-dispatch + update de metadata sem try/except | `jira_poller.py:413-424` | **CORRIGIR NA MIGRAÇÃO** | PROVADO |
| 3 | Cron delete-then-create → janela `PollerCronStopped` | `poller_cron.py:100-147` | DEPOIS | PROVADO (documentado) |
| 4 | ToolRetryMiddleware limitado, re-raise correto | `task_retry.py` | nenhum | PROVADO |
| 5 | ModelFallbackMiddleware limitado (6 tentativas) | `model_fallback.py` | nenhum | PROVADO |
| 6 | Sem ciclo agente↔agente ilimitado | `server.py:604-612` | nenhum | PROVADO |
| 7 | 3 middlewares funcionais NÃO ligados (breaker, push guard, no_empty) | `middleware/__init__.py` | **CORRIGIR NA MIGRAÇÃO** | PROVADO |
| 8 | `agent/providers` totalmente morto | `providers/__init__.py` | DEPOIS | PROVADO |
| 9 | `agent/runtime` VIVO (camada de indireção) | `runtime/*` | DEPOIS | PROVADO (não morto) |
| 10 | `agent/graphs` VIVO (entrypoints) | `graphs/*` | nenhum | PROVADO |
| 11 | `request_self_review` **É ligado** (server.py:1173) — não é morto | `server.py:1173` | nenhum | PROVADO (corrige suspeita) |
| 12 | `jira_park_at_gate` não-atomicidade → card orfanado no gate | `jira_park_at_gate.py:60-68,110` | **BLOQUEADOR** | PROVADO |
| 13 | Completion dedupe: race check-then-act menor | `completion.py:236-247` | DEPOIS | PROVADO |
| 14 | Contrato de dispatch sólido | `dispatch.py` | nenhum | PROVADO |
| 15 | Semântica de merge do turn_checkpoint | `prepare_run.py` | UNKNOWN | INVESTIGAR |
| 16 | `SANDBOX_BACKENDS` dict sem lock | `sandbox_state.py:258` | BAIXO | PROVADO (seguro em 1 loop) |
| 17 | Poller vs webhook race | `jira_poller.py` | MÉDIO | PROVADO |
| 18 | Semântica interrupt sólida | `dispatch.py` | nenhum | PROVADO |
| 19 | ActiveAgentRegistry com lock + limitado | `active_agents.py` | nenhum | PROVADO |
| 20 | Jira runs SEM timeout de wrapup por padrão | `timeout_wrapup.py:12` | **CORRIGIR NA MIGRAÇÃO** | PROVADO |
| 21 | Poller/reconcile/cron todos limitados | vários | nenhum | PROVADO |
| 22 | SandboxUnreachableError tratado corretamente | `sandbox_state.py` | nenhum | PROVADO |
| 23 | ToolErrorMiddleware sólido | `tool_error_handler.py` | nenhum | PROVADO |
| 24 | notify_jira_unparked sólido mas limitado | `notify_jira_unparked.py` | DEPOIS | PROVADO |

---

## 6. Loops e Análise das Condições de Saída

### Loop do deep agent (modelo↔tool) — **intencional e seguro (limitado), com 1 fragilidade**
- **Começa:** `create_deep_agent` (server.py:1210, etc.)
- **Condição de continuidade:** modelo emite tool call → executa → realimenta
- **Condição de saída:** modelo emite mensagem SEM tool call (única saída)
- **Limite:** recursion 9999, model calls 5000 (analyzer 80, chat 100)
- **Timeout:** 900s por chamada; wrapup 45min (mas **desabilitado para Jira**)
- **Erro:** no limite, `exit_behavior="end"` + notificações
- **Risco (PROVADO):** `ensure_no_empty_msg` desligado → se o modelo emitir texto sem tool call, o run termina sem entregar o side effect. Para Jira, `notify_jira_on_unparked_termination` só *flaggeia* o fracasso, não recupera.
- **Recomendação:** religar `ensure_no_empty_msg` OU remover como dead code — decidir deliberadamente.

### Loop do poller Jira (60s) — **intencional e seguro (limitado por tick), com gaps de idempotência**
- **Começa:** `jira_poller.py:436 tick()` → Step A + Step B
- **Limite por tick:** 20 páginas × 50 = 1000 issues
- **Risco (PROVADO):** Step B não checa `_has_active_run` e o update de metadata não é protegido → **double-dispatch** a cada 60s se o update falhar.
- **Recomendação:** guardar com active-run check + proteger update.

### Cron reconfigure (delete-then-create) — **intencional, frágil, documentado, limitado**
- Retry wrapper limitado a 5 tentativas com backoff. Janela `PollerCronStopped` deixa o polling escuro até restart.

### ToolRetry / ModelFallback — **intencionais e seguros (limitados)**

### Ciclos agente↔agente / agente↔tool — **nenhum ilimitado**

---

## 7. Gaps e Dívida Técnica

1. **BLOQUEADOR — `jira_park_at_gate` não-atomicidade:** transição Jira + metadata de thread não são atômicos; `_mark_thread_parked` engole exceções e o tool retorna `success: True` mesmo assim. Card pode ficar orfanado num gate, perdendo a aprovação humana.
2. **CORRIGIR — `ensure_no_empty_msg` desligado:** rede de segurança desativada; risco de término prematuro.
3. **CORRIGIR — Poller Step B double-dispatch:** desperdício de modelo + possível interrupção de run saudável.
4. **CORRIGIR — Jira sem timeout de wrapup:** runs longos sem checkpoint temporal.
5. **CORRIGIR — 3 middlewares funcionais não ligados:** `SandboxCircuitBreakerMiddleware` (breaker inativo), `WorkflowPushGuardMiddleware` (gate de segurança NÃO aplicado), `ensure_no_empty_msg`.
6. **DEPOIS — Persistência inexistente:** sem DB; tudo em metadata/KV/checkpointer da plataforma.
7. **DEPOIS — `agent/providers` morto, `agent/runtime` indireção circular, `request_self_review` (na verdade ligado).**

---

## 8. Classificação dos Gaps por Prioridade

| Prioridade | Gap | Momento ideal |
|---|---|---|
| **Bloqueador** | `jira_park_at_gate` não-atomicidade | Antes de migrar o fluxo Jira |
| **Corrigir na migração** | `ensure_no_empty_msg` | Durante port do agent |
| **Corrigir na migração** | Poller Step B double-dispatch | Durante port do poller |
| **Corrigir na migração** | Jira wrapup timeout | Durante port do agent |
| **Corrigir na migração** | Middlewares não ligados (breaker, push guard) | Decidir ligar ou deletar |
| **Depois** | Persistência/DB | Decisão arquitetural do Langflow |
| **Depois** | Dead code (providers, runtime indireção) | Limpeza |

---

## 9. Recomendação Langflow por Camada

| Camada | Destino | Por quê |
|---|---|---|
| **Orquestração dos 4 deep agents** | **A. Flow nativo Langflow** | O loop modelo↔tool é exatamente o que o Langflow orquestra visualmente |
| **Scheduler (procedural)** | **A. Flow nativo** | Trivial: roteia por task |
| **Tools Jira/Linear/Slack/network** | **B. Custom Component** | Lógica pura reutilizável; encapsular como componentes |
| **Tools OpenSpec** | **B. Custom Component** | Regex/validação reutilizável; trocar I/O de sandbox por FS local |
| **Tools de review (findings)** | **B. Custom Component** | Store de findings reutilizável; adaptar I/O |
| **Tools de plan mode / schedule / recreate_sandbox** | **F. Refatorar antes** | Acopladas a `Command`/`get_config`/cron LangGraph |
| **Integrações MCP (Corridor, Datadog, Notion, Currents, LangSmith, Stagehand)** | **B. Custom Component / MCP nativo** | Langflow suporta MCP; reutilizável |
| **Providers de sandbox (6)** | **C. Serviço interno** | Protocolo deepagents; manter isolado atrás de serviço |
| **Middleware (24)** | **F. Refatorar antes** | Interface `langchain.agents.middleware`; lógica interna reutilizável, hook não |
| **Routing (roles, escalada, complexidade)** | **D. Biblioteca Python compartilhada** | Quase 100% puro; reutilizar como módulo |
| **Model/LLM factory** | **D. Biblioteca compartilhada** | `make_model` baseado em langchain; Langflow também usa langchain |
| **Poller Jira** | **C. Serviço interno** | Lógica JQL/gates reutilizável; transporte LangGraph a adaptar |
| **Webhooks (GH/Linear/Slack)** | **C. Serviço interno** | Verificação de assinatura + roteamento reutilizáveis |
| **Persistence/checkpointing** | **F. Refatorar antes** | Sem DB; decisão crítica de arquitetura |
| **Dashboard/console/UI** | **E. Permanecer temporariamente** | Grande superfície; migrar por último |
| **Bitbucket/Confluence/Google Drive** | **— (não existe)** | Nada a migrar |

---

## 10. Código Reutilizável vs. a Refatorar

**Reutilizável sem alteração (🟢):** `agent/routing/` (roles, router, complexity, capabilities, pricing, usage_store, dispatch_route, active_agents), tools Jira (5), Linear (8), network (`http_request`/`fetch_url`/`web_search`), `report_platform_issue`, `log_openspec_event`, `read_finding_outcomes`, integrações MCP (6), `operational_config`, `jira_statuses`, `sandbox_paths`/`sandbox_root`, `deferred_model`, health route.

**Precisa de adapters (🟡):** tools OpenSpec (3), `open_pull_request`, Slack, review findings, `save_user_*`, `stagehand_browser`, `utils/model.py`, `gateway.py`, `telemetry`/`usage_collection` (LangSmith), `phases` (import jira_poller), turn_checkpoint, poller Jira, completion, webhooks, plan/gate/approval semantics.

**Específico de LangGraph (🔴, reimplementar):** middleware interface (24), providers de sandbox (6), `ensure_sandbox_for_thread`, dispatch (`create_durable_run`), scheduler graph, poller cron, reconcile, persistence/checkpointer, memory/message queue, tools de plan mode (`Command`/`InjectedState`), `schedule_thread_wakeup`, `recreate_sandbox`.

**Provavelmente descartado (⚫):** `agent/providers` (morto), `agent/runtime` indireção (colapsar), Bitbucket/Confluence/Drive (não existem).

**Refatorar antes:** `jira_park_at_gate` (atomicidade), middleware não ligados, persistência.

---

## 11. Fronteiras Arquiteturais Recomendadas

Para evitar trocar `acoplamento forte com LangGraph` por `acoplamento forte com Langflow`:

1. **Regras de negócio ↔ orquestração:** extrair toda lógica pura (routing, JQL/gates, validação OpenSpec, findings, verificação de assinatura) para módulos Python independentes da engine.
2. **Agents ↔ integrations:** integrar via interface de serviço/MCP, não via import direto.
3. **Agents ↔ tools:** tools como Custom Components com contrato de entrada/saída claro, sem depender de `get_config`/metadata.
4. **Providers LLM ↔ workflows:** manter `make_model` como factory única; Langflow consome via langchain.
5. **Prompts ↔ código:** prompts já são renderizados em runtime (`rendered_system_prompt`) — manter esse padrão, versionar prompts como arquivos.
6. **Estado ↔ implementação:** definir um schema de estado explícito e portável (não metadata opaco da plataforma).
7. **Orchestration ↔ execution:** sandbox como serviço interno isolado.
8. **Integrações externas ↔ domínio:** Jira/Linear/Slack/GitHub atrás de clientes reutilizáveis.

---

## 12. Estratégia de Versionamento Git/GitHub

- **Git como source of truth:** flows do Langflow são JSON exportável — versionar no Git, nunca editar só na UI.
- **Custom Components:** código Python versionado normalmente; referenciar por versão/tag.
- **Prompts:** já são arquivos (`resources/default_prompt.md`, `prompt.py`) — manter como arquivos versionados.
- **Secrets:** fora do Git — usar variáveis de ambiente / secret store do Langflow; nunca commitar tokens.
- **Ambientes:** `dev`/`prod` via config versionada + secrets por ambiente.
- **Dependências:** `pyproject.toml`/`uv.lock` já versionados.
- **Sync/deploy:** pipeline que exporta flows do Git → importa no Langflow (CI/CD), com diff/review via PR.

---

## 13. Possível Sequência Incremental de Migração

| Etapa | Alvo | Risco | Aprendizado | Rollback |
|---|---|---|---|---|
| **1** | **chat** (read-only, sem sandbox, sem side effects) | Baixo | Langflow + Custom Components + LLM + versionamento | Fácil |
| **2** | **analyzer** (2 tools, sem subagents) | Baixo | Componentes + store | Fácil |
| **3** | **reviewer** (read-only, findings) | Médio | Findings + GitHub + check runs | Médio |
| **4** | **agent** (o grande) | Alto | Tudo: sandbox, gates, PRs, middleware | Difícil |
| **5** | **poller/scheduler/webhooks** | Médio | Serviços internos + cron | Médio |
| **6** | **dashboard/console/UI** | Alto | Último, maior superfície | Difícil |

**Critério:** não escolhi o menor (chat) apenas por tamanho — chat é o melhor por combinar **baixo risco + aprendizado arquitetural relevante** (componentes, LLM, versionamento, deploy, testes) sem side effects destrutivos.

---

## 14. Primeira Fatia Vertical Candidata

**`chat` (chat sobre PR, read-only)** — `agent/chat.py:180`.

**Por que:**
- Sem sandbox, sem side effects, sem escrita — risco mínimo.
- Exercita: Langflow flow, Custom Components (`read_repo_file`, `search_repo_code`, `list_review_findings`, `web_search`, `fetch_url`), LLM (REVIEW_CHAT→Sonnet/med), versionamento, deploy, testes, rollback.
- Tem subagente (general-purpose read-only) — valida o padrão de subagentes.
- Tem `ExcludeToolsMiddleware` (read-only enforcement) — valida o conceito de permissões.
- Permite **comparação comportamental limpa** (entrada/saída textuais, sem efeitos colaterais).

---

## 15. Estratégia de Testes/Comparação LangGraph vs. Langflow

Para verificar `comportamento atual ≈ comportamento migrado`:

- **Fixtures de entrada/saída:** capturar pares (input config + mensagem → resposta final) dos runs atuais; replay no Langflow.
- **Contratos de tools:** cada Custom Component deve ter contrato de entrada/saída idêntico ao tool original (mesmos campos, mesmos erros).
- **Shadow testing:** rodar ambos em paralelo para fluxos read-only (chat, analyzer, reviewer) e comparar saídas.
- **Decisões de routing:** testar `resolve_model`/`classify_complexity` como funções puras (já são) — golden tests.
- **Side effects:** para fluxos com efeitos (agent), comparar via mocks/registros de chamadas externas (Jira/Slack/GitHub) — não executar de verdade em shadow.
- **Erros/retries/loops:** testes de limite (model call limit, timeout, fallback) replicados.
- **Testes existentes:** `tests/` já tem boa cobertura (agent, reviewer, routing, middleware, webhooks, sandbox) — reutilizar como oráculo de comportamento.

---

## 16. Riscos

**Conhecidos (demonstráveis no código):**
- `jira_park_at_gate` não-atomicidade (BLOQUEADOR).
- `ensure_no_empty_msg` desligado → término prematuro.
- Poller Step B double-dispatch.
- Jira sem timeout de wrapup.
- Middlewares funcionais não ligados (breaker, push guard).
- Persistência inteiramente na plataforma LangGraph (sem DB portátil).

**Potenciais (a validar):**
- Race poller vs webhook (Step A ghost-deletion).
- Semântica de merge do turn_checkpoint.
- Custo/qualidade do modelo ao trocar de engine de orquestração.

---

## 17. Unknowns

- **Semântica de merge do turn_checkpoint** (como arquivos revertidos são refletidos; concorrência de snapshots).
- **Topologia interna exata do `create_deep_agent`** (nodes/edges do loop vêm da lib `deepagents`, não do repo).
- **Se `interrupt_on`/checkpointer implícitos** afetam o loop do deep agent.
- **Valor real de `DEFAULT_MODEL_ID`** (vem de `dashboard/options.py`).
- **Como o Langflow representa** subagentes, middleware e o loop modelo↔tool com fidelidade equivalente.

---

## 18. Perguntas a Responder Antes do Proposal

1. **Persistência:** o Langflow vai gerenciar estado/checkpointing, ou mantemos um serviço de estado próprio (DB)? Esta é a decisão mais crítica.
2. **Sandbox:** mantemos os 6 providers como serviço interno, ou o Langflow tem equivalente nativo?
3. **Middleware:** quais dos 24 são essenciais e como traduzi-los para o modelo do Langflow? Ligar ou deletar os 3 não conectados?
4. **Routing:** o Langflow respeita o routing por papel (modelo+effort por fase), ou simplificamos?
5. **Escopo:** o `agent` completo (com sandbox, gates, PRs) cabe no Langflow, ou o Langflow orquestra e o `agent` vira serviço?
6. **Dashboard/console/UI:** migram junto ou ficam temporariamente?
7. **Jira gates:** como o Langflow representa o human-in-the-loop (pause/resume)?
8. **Versionamento:** qual o mecanismo de sync Git→Langflow (export/import CI)?
9. **Shadow testing:** quais fluxos são elegíveis para comparação paralela?
10. **Ordem:** confirmar chat → analyzer → reviewer → agent → infra como sequência.

---

## Próximo Passo

A exploração atingiu clareza suficiente nas seções 1–16. As **perguntas abertas (seção 18)** — especialmente **persistência** e **escopo do `agent`** — são decisões que precisam ser tomadas antes de escrever o proposal.

Opções de continuação:
- **(a)** aprofundar alguma área específica (ex.: viabilidade do `chat` como primeira fatia, ou o modelo de persistência do Langflow);
- **(b)** começar a rascunhar o **OpenSpec Proposal** para a primeira fatia (`chat`), incorporando estas decisões;
- **(c)** capturar estas descobertas em algum artefato (design.md / proposal.md).
