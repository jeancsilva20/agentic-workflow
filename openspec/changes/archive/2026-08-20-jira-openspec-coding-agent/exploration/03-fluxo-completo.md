# Fluxo Completo do Agente

## Visão Geral

O agente é triggerado quando um card Jira entra na coluna "BACKLOG". A partir daí, executa 11 passos com 3 pontos de aprovação humana e 2 loops de auto-revisão.

## Diagrama do Fluxo

```
TRIGGER: Card em "BACKLOG"
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│ PASSO 1: COLETAR CONTEXTO DO JIRA                                │
│                                                                  │
│ • Ler issue (key, título, descrição, critérios de aceite)        │
│ • Ler comentários, anexos, links                                 │
│ • Mover card para "In Progress"                                  │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│ PASSO 2: PREPARAR AMBIENTE                                       │
│                                                                  │
│ • Clonar repo no sandbox                                         │
│ • Criar branch: feat/spec-JIRA-XXXX-descricao-curta              │
│ • Carregar AGENTS.md + docs canônicos do repo                    │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│ PASSO 3: ANALISAR + GERAR SPEC (PLAN MODE)                       │
│                                                                  │
│ Agente em plan mode:                                             │
│ • Explora código relevante (grep, glob, read)                    │
│ • Identifica arquivos, dependências, impacto                     │
│ • Gera artifacts OpenSpec:                                       │
│   - proposal.md                                                  │
│   - design.md                                                    │
│   - specs/<capability>/spec.md                                   │
│   - tasks.md                                                     │
│ • Salva no branch feat/spec-JIRA-XXXX                            │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│ PASSO 4: AUTO-REVIEW DA SPEC (LOOP, ~3 CICLOS)                   │
│                                                                  │
│ Checklist de auto-review:                                        │
│ ☐ Todos os critérios de aceite do Jira estão cobertos?           │
│ ☐ Cenários felizes, tristes e borda estão documentados?          │
│ ☐ Constraints e regras de negócio estão explícitos?              │
│ ☐ Dependências e breaking changes identificados?                 │
│ ☐ Tasks são atômicas e implementáveis?                           │
│                                                                  │
│ Se encontrar gaps → volta ao PASSO 3 (corrigir spec)             │
│ Após ~3 ciclos sem resolver → comenta os gaps no Jira e segue    │
│ APROVAÇÃO 1 mesmo assim (sem coluna dedicada)                    │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
╔══════════════════════════════════════════════════════════════════╗
║ APROVAÇÃO 1: REVISÃO DA SPEC                                     ║
║                                                                  ║
║ Agente move card para "Em Revisão de Spec"                       ║
║ Aguarda humano:                                                  ║
║   • "Spec Aprovada" → PASSO 5                                    ║
║   • "Ajustar Spec" → PASSO 3 (com feedback do comentário)        ║
╚══════════════════════════════════════════════════════════════════╝
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│ PASSO 5: IMPLEMENTAR                                             │
│                                                                  │
│ Agente sai do plan mode:                                         │
│ • Executa tasks do OpenSpec sequencialmente                      │
│ • Para cada task:                                                │
│   - Edita/cria arquivos                                          │
│   - Cria/altera testes unitários                                 │
│   - Executa lint                                                 │
│   - Executa testes da task                                       │
│   - Commit atômico                                               │
│   - Marca task como [x] no tasks.md                              │
│ • Executa testes de integração (se existirem)                    │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│ PASSO 6: AUTO-REVIEW DO CÓDIGO (LOOP, ~3 CICLOS)                 │
│                                                                  │
│ Checklist de auto-review:                                        │
│ ☐ O código implementa toda a spec?                               │
│ ☐ Todos os critérios de aceite foram atendidos?                  │
│ ☐ Cobertura de testes adequada?                                  │
│ ☐ Lint passa? Build passa?                                       │
│ ☐ Possíveis regressões?                                          │
│ ☐ Problemas de segurança?                                        │
│ ☐ Tratamento de erros adequado?                                  │
│ ☐ Código desnecessário ou duplicado?                             │
│                                                                  │
│ Se encontrar problemas → volta ao PASSO 5 (corrigir)             │
│ Após ~3 ciclos sem resolver → comenta os problemas e vai         │
│ direto para APROVAÇÃO 2 (sem coluna dedicada)                    │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│ PASSO 7: REVIEWER AUTOMÁTICO (REVIEWER GRAPH DO OPEN SWE)        │
│                                                                  │
│ Agente separado, read-only:                                      │
│ • Analisa git diff                                               │
│ • Valida contra spec do OpenSpec                                 │
│ • Procura bugs, regressões, segurança                            │
│ • Gera findings estruturados                                     │
│                                                                  │
│ Status: PASS ou CHANGES_REQUIRED                                 │
│                                                                  │
│ Se CHANGES_REQUIRED → volta ao PASSO 5 (corrigir findings)       │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
╔══════════════════════════════════════════════════════════════════╗
║ APROVAÇÃO 2: CODE REVIEW HUMANO                                  ║
║                                                                  ║
║ Agente move card para "Em Code Review"                           ║
║ Aguarda humano:                                                  ║
║   • "Code Review Aprovado" → PASSO 8                             ║
║   • "Ajustar Code" → PASSO 5 (com feedback do comentário)        ║
╚══════════════════════════════════════════════════════════════════╝
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│ PASSO 8: TESTES FINAIS + PUSH + PR                               │
│                                                                  │
│ • Executa suite completa de testes (unit + integration)          │
│ • Push da branch feat/spec-JIRA-XXXX                             │
│ • Cria PR no GitHub (draft)                                      │
│ • Body da PR gerado automaticamente:                             │
│   - Link Jira                                                    │
│   - Resumo da spec                                               │
│   - Lista de alterações                                          │
│   - Resultado dos testes                                         │
│   - Resultado do reviewer automático                             │
│ • Publica link da PR no Jira                                     │
│ • Move card para "Em Merge"                                      │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
╔══════════════════════════════════════════════════════════════════╗
║ APROVAÇÃO 3: MERGE                                               ║
║                                                                  ║
║ Agente monitora CI da PR (CI auto-fix do Open SWE atua)          ║
║ Aguarda humano:                                                  ║
║   • Mergeia a PR                                                 ║
║   • Move card para "Mergeado"                                    ║
║                                                                  ║
║ Se review humano na PR pedir mudanças → PASSO 5                  ║
╚══════════════════════════════════════════════════════════════════╝
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│ PASSO 9: ARCHIVE DA SPEC                                         │
│                                                                  │
│ • Executa openspec archive JIRA-XXXX                             │
│ • Move artifacts para openspec/changes/archive/                  │
│ • Atualiza índice de changes                                     │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│ PASSO 10: ATUALIZAR DOCS CANÔNICOS                               │
│                                                                  │
│ • Identifica docs impactados pela mudança                        │
│ • Atualiza docs canônicos no repositório:                        │
│   - specs/<capability>/spec.md (spec viva, pós-implementação)    │
│   - AGENTS.md (se novas convenções surgiram)                     │
│   - README ou docs/ (se APIs públicas mudaram)                   │
│ • Cria branch separada e PR para docs                            │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│ PASSO 11: FINALIZAR                                              │
│                                                                  │
│ • Publica resumo final no Jira                                   │
│ • Move card para "Done"                                          │
│ • Registra métricas no LangSmith:                                │
│   - Tempo total                                                  │
│   - Ciclos de auto-review (spec + code)                          │
│   - Findings do reviewer                                         │
│   - Status final                                                 │
└──────────────────────────────────────────────────────────────────┘
```

## Estados do Agente

Não há state machine dentro do agente. O estado vive em dois lugares: a **coluna do card**
no Jira e uma marca de "parked" nos metadados da thread. O agente só tem dois modos —
está rodando, ou o run acabou.

```
TICK (60s, graph scheduler)
│
├── A) cards em "BACKLOG"
│      sem thread? → cria thread (thread_id derivado da issue key)
│
└── B) cards de threads marcadas como parked
       coluna mudou? → re-dispara a thread com a nova coluna + comentários novos
```

Ciclo de vida de um gate:

```
agente trabalhando
   │
   ├─ commita o trabalho
   ├─ comenta no Jira
   ├─ move o card para a coluna do gate
   ├─ marca a thread como parked nos metadados
   └─ ENCERRA O RUN                       ← nada consumindo tempo daqui em diante
          │
          ⋮  (humano decide, pode levar horas)
          │
   tick detecta mudança de coluna
   re-dispara a thread → reconecta no mesmo sandbox → continua
```

Consequência: uma aprovação pode levar horas sem estourar o `timeout_wrapup` de 45 min,
porque não existe run vivo durante a espera. O custo é até 60s de latência entre o humano
mover o card e o agente retomar.

O caso "auto-review esgotado" não tem estado próprio: o agente comenta o que não
conseguiu resolver e entra no mesmo estado de espera do caminho feliz. Quem lê o
comentário decide se aprova mesmo assim ou manda ajustar — e o comportamento de
retomada é idêntico nos dois casos.

## Colunas do Jira

| # | Coluna | Quem Move | Significado |
|---|---|---|---|
| 1 | BACKLOG | Humano | Trigger inicial |
| 2 | In Progress | Agente | Agente está trabalhando |
| 3 | Em Revisão de Spec | Agente | Parado, aguardando aprovação da spec |
| 4 | Spec Aprovada | Humano | Planejamento aprovado |
| 5 | Ajustar Spec | Humano | Spec precisa de ajustes |
| 6 | Em Code Review | Agente | Parado, aguardando code review |
| 7 | Code Review Aprovado | Humano | Código aprovado |
| 8 | Ajustar Code | Humano | Código precisa de ajustes |
| 9 | Em Merge | Agente | PR aberta, aguardando merge |
| 10 | Mergeado | Humano | PR mergeada |
| 11 | Done | Agente | Fluxo finalizado |

**Transições globais obrigatórias.** O workflow do Jira precisa permitir que qualquer
status vá para qualquer outro ("Allow all statuses to transition to this one" em cada
status). O fluxo não é linear — o agente sai de "In Progress" para três destinos
diferentes e cinco colunas voltam para lá. Sem transições globais, o `POST /transitions`
devolve 400 num salto ilegal.

**Colunas removidas.** A versão anterior tinha 15 colunas, incluindo `Necessita
Complemento da Spec`, `Spec Complementada`, `Necessita Revisão Humana` e `Orientações
Fornecidas`. Foram cortadas: o comportamento de retomada delas era idêntico ao das
colunas de ajuste, então não codificavam estado nenhum — só registravam quem tomou a
iniciativa, o que cabe num comentário.

## Variáveis de Ambiente

| Variável | Default | Descrição |
|---|---|---|
| `JIRA_BASE_URL` | (requerido) | Ex.: `https://sensedia.atlassian.net` |
| `JIRA_EMAIL` | (requerido) | E-mail Atlassian usado no Basic auth |
| `JIRA_API_TOKEN` | (requerido) | API token pessoal (id.atlassian.com → Security) |
| `JIRA_POLL_INTERVAL_SECONDS` | `60` | Intervalo do tick do poller em segundos |
| `AGENT_CONSOLE_URL` | (opcional) | Base URL do console; sem ela, os eventos não são enviados |
| `JIRA_COLUMN_READY` | `BACKLOG` | Coluna de trigger |
| `JIRA_COLUMN_DEV` | `In Progress` | Coluna de trabalho |
| `JIRA_COLUMN_SPEC_REVIEW` | `Em Revisão de Spec` | Coluna de aprovação 1 |
| `JIRA_COLUMN_SPEC_APPROVED` | `Spec Aprovada` | Spec aprovada |
| `JIRA_COLUMN_SPEC_ADJUST` | `Ajustar Spec` | Spec precisa ajustes |
| `JIRA_COLUMN_CODE_REVIEW` | `Em Code Review` | Coluna de aprovação 2 |
| `JIRA_COLUMN_CODE_APPROVED` | `Code Review Aprovado` | Código aprovado |
| `JIRA_COLUMN_CODE_ADJUST` | `Ajustar Code` | Código precisa ajustes |
| `JIRA_COLUMN_MERGE` | `Em Merge` | Coluna de aprovação 3 |
| `JIRA_COLUMN_MERGED` | `Mergeado` | PR mergeada |
| `JIRA_COLUMN_DONE` | `Done` | Fluxo finalizado |
