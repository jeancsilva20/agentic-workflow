# Relatório de ajuste — workflow Jira → agentes → GitHub

**Data:** 10 de agosto de 2026
**Escopo:** alinhamento da implementação existente ao fluxo alvo de 11 estados do board `SSAI`
**Premissa:** ajustes incrementais. Poller, threads determinísticas, park/resume, durable execution e observabilidade permanecem intactos — nenhuma reescrita de arquitetura foi feita.

---

## 1. Como o fluxo funcionava antes

O mecanismo central já estava correto e foi preservado:

- Um cron de 60s no graph `scheduler` chama `jira_poller.tick()`.
- **Step A** procura cards em `BACKLOG` e cria uma thread nova por card. O ID da thread é derivado deterministicamente da chave do card (`generate_thread_id_from_jira_issue`), então um card que já tem thread é ignorado — é isso que garante idempotência entre ticks.
- **Step B** procura cards estacionados e retoma a thread quando a coluna muda.
- Ao chegar num gate, o agente chama `jira_park_at_gate`: comenta no Jira, move o card, grava `jira_parked` nos metadados da thread e encerra o run. O agente nunca bloqueia esperando humano.

O que estava divergente do fluxo alvo eram as bordas desse mecanismo — principalmente **o que o Step B conseguia enxergar** e **o que o prompt mandava o agente fazer depois de cada retomada**.

---

## 2. Divergências encontradas

### 2.1 Bug crítico — o poller não enxergava decisão humana nenhuma

O JQL do Step B era:

```sql
project = SSAI AND status in ("Em Revisão de Spec", "Em Code Review", "Em Merge")
```

Só as três colunas de gate. No instante em que o humano movia o card para `Spec Aprovada`, `Ajustar Spec`, `Code Review Aprovado`, `Ajustar Code` ou `Mergeado`, o card **saía da query** e o poller nunca via a decisão. A thread ficava estacionada para sempre.

Esse é o bug de maior impacto do conjunto: sem ele corrigido, o fluxo travava logo depois do primeiro gate, independentemente de qualquer instrução de prompt.

### 2.2 A busca do poller lia só a primeira página

`search_issues` pagina por `nextPageToken`, mas os dois steps pediam `max_results=50` e descartavam o token. Com o JQL restrito a três colunas isso raramente doía; com o JQL expandido para oito, dói: cards parados num gate (que não geram ação nenhuma) podem encher a primeira página enquanto o card que o humano acabou de mover fica na segunda — e nunca é retomado. Quem decide a ordem é o Jira, então o card perdido é imprevisível.

Essa divergência não estava na lista original das seis; apareceu como consequência direta do fix 2.1 e foi corrigida junto.

### 2.3 Shadow mode não cobria o Step B

`JIRA_POLLER_SHADOW_MODE` suprimia apenas o Step A. O Step B disparava resume de verdade — comentários lidos, run disparado, metadados alterados — mesmo com o shadow mode ligado. A garantia de "nenhuma ação real" era falsa.

### 2.4 Archive da OpenSpec e documentação aconteciam depois do merge

O prompt mandava arquivar a OpenSpec e atualizar docs **depois** de `Mergeado`, numa **PR separada** (Decision 6 do design original). O fluxo alvo exige o contrário: `Em Merge` significa "a automação terminou tudo", então archive e docs têm que estar na mesma branch/PR, antes do merge humano.

### 2.5 `Ajustar Code` não buscava reviews do GitHub

O resume passava só os últimos 5 comentários do Jira. O fluxo alvo diz explicitamente que **a fonte principal dos ajustes de código é o GitHub** — reviews e comentários da PR. Não havia instrução para buscá-los.

### 2.6 Fase pós-merge inadequada

Com o Step B corrigido, `Mergeado` passaria a ser detectado — mas o prompt mandava abrir uma PR nova de docs nesse ponto. O fluxo alvo define `Mergeado → Done` como fase curta e administrativa, sem alteração funcional na branch.

### 2.7 Faltava guard antes de `Em Revisão de Spec`

Nada impedia o card de ir para `Em Revisão de Spec` com a OpenSpec ainda não commitada/pushada. O card avançaria anunciando uma spec que o revisor não conseguiria abrir.

---

## 3. Arquivos modificados

| Arquivo | Mudança |
|---|---|
| `agent/jira_statuses.py` | **Novo.** Módulo central de mapeamento status Jira ↔ coluna visual; inclui resultado de auditoria da API do board SSAI |
| `agent/jira_poller.py` | JQL do Step B expandido para as 8 colunas relevantes; shadow mode aplicado ao Step B; comentários das constantes `COLUMN_*` atualizados para distinguir "status API" de "label visual" |
| `agent/prompt.py` | Diagrama de fluxo corrigido (spec phase sem `In Progress`); PASSO 1 corrigido (remove instrução de mover para `In Progress`); guard pré-spec-review atualizado; lista de transições automáticas corrigida; seção de retomada por coluna; preparação pré-merge; fechamento pós-merge; reviewer re-executa a cada entrada em `Em Code Review` |
| `openspec/changes/jira-openspec-coding-agent/design.md` | Decision 6 revisada (archive + docs na mesma PR, não em PR separada); diagrama de fluxo atualizado; seção de responsabilidade por transição |
| `docs/JIRA_INTEGRATION.md` | Diagrama operacional atualizado; quem move cada coluna; escopo real do shadow mode e do JQL do poller |
| `tests/agent/test_jira_poller.py` | +9 testes (JQL expandido, overrides, dedup, 5 decisões humanas, shadow/paused no Step B, idempotência de tick repetido) |
| `tests/agent/test_jira_prompt.py` | Teste `test_prompt_orders_the_initial_transition_before_any_spec_work` substituído por `test_prompt_spec_phase_does_not_move_card_to_in_progress` (inverte a asserção: corrige o erro do fluxo de spec); `test_prompt_makes_the_agent_own_every_non_gate_transition` atualizado (remove `BACKLOG → In Progress`) |
| `tests/agent/test_jira_workflow_integration.py` | Fluxo completo estendido até `Mergeado → Done`; +3 testes de ciclo (loop `Ajustar Spec`, loop `Ajustar Code`, retomada pós-merge) |

---

## 4. Mudanças feitas

### 4.1 Poller (`agent/jira_poller.py`)

O JQL do Step B agora cobre gates **e** pós-gates:

```sql
project = SSAI AND status in (
  "Em Revisão de Spec", "Em Code Review", "Em Merge",
  "Spec Aprovada", "Ajustar Spec", "Code Review Aprovado", "Ajustar Code", "Mergeado"
)
```

As colunas são lidas em tempo de chamada (`_gate_columns()` / `_post_gate_columns()`), então um override de `JIRA_COLUMN_*` chega à query; nomes repetidos são deduplicados.

**A idempotência não mudou de lugar.** Continua sendo a comparação `current_column == parked_column` dentro do Step B: card ainda no gate → `unchanged`, sem dispatch. Thread sem `jira_parked` → ignorada. O que mudou é apenas o conjunto de cards que a query entrega para essa comparação.

**Paginação.** Os dois steps agora percorrem todas as páginas da busca (`_search_all_issues`), seguindo o `nextPageToken` em vez de parar nos primeiros 50 resultados. Sem isso, o JQL expandido criava um jeito novo de perder card: os parados no gate ocupam a primeira página e o card recém-movido fica na segunda. Há um teto de páginas por tick — atingi-lo é logado como warning, porque significa que existem cards fora do alcance do poller. Se uma página falhar no meio, os cards já coletados continuam sendo processados e o erro é reportado junto do resultado do step; falha logo na primeira página continua abortando o step, como antes.

Shadow mode agora vale para o Step B: loga `[shadow] would resume thread for {issue_key}: {parked_column} → {current_column}`, e não lê comentários, não dispara run, não altera metadados.

### 4.2 Prompt (`agent/prompt.py`) — rodada anterior

Cinco blocos novos/reescritos, todos com nomes de coluna vindos das env vars:

- **Matriz de transições automáticas** — deixa explícito que o humano só move o card em três pontos e que as demais transições são do agente.
- **Guard pré-`Em Revisão de Spec`** — commit, push e confirmação da branch remota antes de chamar `jira_park_at_gate`.
- **Seção de retomada por coluna** — o que fazer ao voltar em cada um dos cinco pós-gates.
- **Pré-merge e pós-merge** — archive e docs na mesma branch/PR; self-review do diff pré-merge.

A instrução de PR separada de docs foi removida.

### 4.3 Módulo central de statuses (`agent/jira_statuses.py`) — adicionado nesta rodada

Novo módulo com fonte de verdade para o mapeamento completo das 11 etapas do workflow:

- `TransitionInitiator` — enum que distingue quem move o card para cada coluna: `HUMAN`, `AGENT_AUTO`, `AGENT_GATE`.
- `WorkflowStep` — dataclass com `jira_status` (string da API), `column_label` (label visual), `env_var`, `poller_constant`, `transition_initiator` e `description`.
- `WORKFLOW_STEPS` — tupla com todos os 11 passos documentados, incluindo a nota crítica de que a fase de spec corre inteiramente com o card em `BACKLOG`.
- Resultado da auditoria da API do board SSAI: **nenhuma divergência** — os defaults de `jira_poller.py` são exatamente os nomes de status retornados pelo endpoint de transições.
- Funções auxiliares: `get_workflow_step`, `gate_steps`, `post_gate_steps`.

### 4.4 Correção do fluxo da fase de spec no prompt — adicionado nesta rodada

Dois erros estruturais corrigidos:

**Erro 1 — PASSO 1 mandava o agente mover o card para `In Progress` antes de qualquer trabalho de spec.**

O prompt anterior tinha em PASSO 1 a instrução `jira_transition_issue({issue}, "In Progress")`, fazendo o card aparecer em "Em Desenvolvimento" enquanto o agente ainda escrevia a spec. O fluxo correto é: o card permanece em `BACKLOG` durante toda a fase de spec; a primeira mudança de status é o estacionamento em `Em Revisão de Spec` via `jira_park_at_gate`. `In Progress` só aparece quando o agente retoma de `Spec Aprovada` para iniciar a implementação.

Mudanças específicas:
- Diagrama de fluxo: `{col_trigger} -> {col_in_progress} -> [self-review] -> {col_spec_review}` corrigido para `{col_trigger} -> [spec work + self-review] -> {col_spec_review}`.
- PASSO 1 reescrito: remove a instrução de transição, adiciona nota explícita de que o card fica em `{col_trigger}` durante todo o spec.
- "Every automatic move" corrigido: remove `{col_trigger}` → `{col_in_progress}` da lista (não é mais uma transição do agente na fase de spec).
- "Guard before `Em Revisão de Spec`": corrigido de "card still in `{col_in_progress}`" para "card still in `{col_trigger}`".
- "Gates" section: corrigido de "moves into `{col_in_progress}` in PASSO 1 and PASSO 5" para "move into `{col_in_progress}` in PASSO 5 when resuming from `{col_spec_approved}`".

**Erro 2 — constantes `COLUMN_*` do poller sem distinção explícita entre "status API" e "label visual".**

Os comentários do bloco `COLUMN_*` em `jira_poller.py` foram atualizados para deixar explícita a diferença conceitual entre status (enviado à API, usado em JQL) e label de coluna (exibido para humanos). A distinção completa com os 11 passos vive em `agent/jira_statuses.py`.

### 4.5 Atualização dos testes — adicionado nesta rodada

- `test_prompt_orders_the_initial_transition_before_any_spec_work` substituído por `test_prompt_spec_phase_does_not_move_card_to_in_progress`, que inverte as asserções: agora verifica que PASSO 1 **não** contém a transição para `In Progress` e que a spec phase mantém o card no trigger.
- `test_prompt_makes_the_agent_own_every_non_gate_transition`: removeu `BACKLOG → In Progress` da lista de transições esperadas; adicionou asserção negativa explícita.

---

## 5. Máquina de estados final

| # | Coluna | Tipo | Quem move o card para lá |
|---|---|---|---|
| 1 | `BACKLOG` | Gatilho | Humano (ou integração de monitoramento) |
| 2 | `In Progress` | **Automático** | Agente |
| 3 | `Em Revisão de Spec` | **Human in the Loop** | Agente (estaciona) |
| 4 | `Spec Aprovada` | Decisão humana | Humano |
| 5 | `Ajustar Spec` | Decisão humana | Humano |
| 6 | `Em Code Review` | Reviewer automático, **depois** Human in the Loop | Agente (estaciona) |
| 7 | `Code Review Aprovado` | Decisão humana | Humano |
| 8 | `Ajustar Code` | Decisão humana | Humano |
| 9 | `Em Merge` | **Human in the Loop** | Agente (estaciona) |
| 10 | `Mergeado` | Decisão humana (merge já feito no GitHub) | Humano |
| 11 | `Done` | **Automático** | Agente |

**Transições do agente:** `BACKLOG`→`In Progress`, `In Progress`→`Em Revisão de Spec`, `Spec Aprovada`→`In Progress`, `Ajustar Spec`→`Em Revisão de Spec`, `In Progress`→`Em Code Review`, `Ajustar Code`→`Em Code Review`, `Code Review Aprovado`→`Em Merge`, `Mergeado`→`Done`.

**Transições do humano:** sair de `Em Revisão de Spec` (→ `Spec Aprovada` ou `Ajustar Spec`), sair de `Em Code Review` (→ `Code Review Aprovado` ou `Ajustar Code`), sair de `Em Merge` (→ `Mergeado`, depois de fazer o merge no GitHub).

O agente **nunca** move para `Code Review Aprovado`, **nunca** move para `Mergeado` e **nunca** faz merge de PR.

---

## 6. Como o poller detecta cada retomada

Todo tick roda dois passos independentes. Os dois percorrem **todas as páginas** da busca antes de processar qualquer card.

**Step A** — `status = "BACKLOG"`. Para cada card, calcula o thread ID determinístico; se a thread já existe, pula (`skipped`). Só cria e dispara quando não existe.

**Step B** — as 8 colunas do JQL expandido. Para cada card:

1. Calcula o mesmo thread ID determinístico → sempre a **mesma** thread, nunca uma nova.
2. Lê os metadados. Sem `jira_parked` → ignora (ex.: card colocado direto num gate sem nunca ter passado pelo trigger).
3. Compara `current_column` com `jira_parked_column`. Iguais → `unchanged`, nada acontece.
4. Diferentes → busca os comentários recentes, dispara `dispatch_agent_run` na thread existente com as duas colunas no prompt, e limpa `jira_parked`.

Limpar `jira_parked` no passo 4 é o que torna o tick seguinte inofensivo: o card ainda aparece na query, mas a thread não está mais estacionada, então ele cai no passo 2 e é ignorado. Um tick repetido nunca reprocessa.

**Estacionamento e retomada.** `jira_park_at_gate` grava `jira_parked: True`, `jira_parked_column`, `jira_parked_at` e acrescenta uma entrada em `jira_gate_history` — o histórico é acumulativo, então duas passagens pelo mesmo gate aparecem como duas entradas (é assim que os ciclos ficam auditáveis). A retomada usa o thread ID derivado da chave do card, reconectando ao mesmo sandbox e ao mesmo contexto.

---

## 7. Os dois loops

**Loop `Ajustar Spec`:** `Em Revisão de Spec` → humano move para `Ajustar Spec` → poller detecta e retoma a mesma thread → agente lê os comentários (ou, se não houver, faz revisão crítica própria) → ajusta a OpenSpec na mesma branch → commit + push → `jira_park_at_gate("Em Revisão de Spec")`. Repetível N vezes.

**Loop `Ajustar Code`:** `Em Code Review` → humano move para `Ajustar Code` → poller retoma → agente busca reviews/comentários da PR **no GitHub** → lista os pontos pendentes → corrige na mesma branch → testes + self-review → commit + push (a PR atualiza) → `jira_park_at_gate("Em Code Review")` → o reviewer roda de novo sobre a nova versão da PR. Repetível N vezes.

Em ambos os casos a branch e a PR são sempre as mesmas — nenhuma branch ou PR nova é criada por ciclo.

---

## 8. Momentos-chave

| Evento | Quando acontece |
|---|---|
| OpenSpec commitada e pushada | Antes de mover para `Em Revisão de Spec` (guard obrigatório) |
| PR aberta (draft) | Antes do `request_self_review`, ainda em `In Progress` |
| Reviewer graph executa | A cada entrada em `Em Code Review`, inclusive em cada volta do loop `Ajustar Code` |
| OpenSpec arquivada | Na preparação pré-merge, depois de `Code Review Aprovado`, antes de `Em Merge` |
| Documentação atualizada | No mesmo ponto, na mesma branch/PR |
| Merge da PR | Ação humana no GitHub, durante o gate `Em Merge` |
| Fechamento (comentário final, `Done`) | Na retomada em `Mergeado`, sem alteração funcional na branch |

---

## 9. Resultado dos testes

```
tests/agent + tests/tools + tests/utils + tests/middleware   519 passed
suíte específica de Jira                                      86 passed
suíte completa (tests/)                          1791 passed, 16 failed
```

As 16 falhas estão em `tests/models/` e `tests/dashboard/` e são **pré-existentes** — verificado rodando a mesma seleção com as alterações revertidas (mesmas 16 falhas, mesmos nomes). São testes do catálogo de modelos, sem relação com o fluxo Jira.

Cobertura nova, item por item do checklist de validação:

| Item pedido | Teste |
|---|---|
| JQL expandido cobre todos os pós-gate | `test_parked_jql_covers_gates_and_every_post_gate_column` |
| Card movido além da primeira página é retomado | `test_step_b_resumes_a_card_that_falls_beyond_the_first_page`, `test_step_a_launches_a_card_that_falls_beyond_the_first_page` |
| Paginação tem teto e sobrevive a página com erro | `test_pagination_stops_at_the_page_cap`, `test_a_failing_page_keeps_the_issues_already_collected`, `test_step_b_reports_a_partial_failure_without_dropping_the_tick` |
| JQL respeita overrides / não duplica | `test_parked_jql_follows_column_name_overrides`, `test_parked_jql_has_no_duplicate_columns` |
| Shadow mode no Step B | `test_step_b_shadow_mode_logs_but_never_resumes` |
| Idempotência de polling | `test_step_b_second_tick_after_resume_does_not_reprocess` |
| Retomada da mesma thread (5 decisões) | `test_step_b_resumes_for_every_human_decision` (parametrizado) |
| Loop `Ajustar Spec` | `test_adjust_spec_loop_reparks_the_same_thread_each_cycle` |
| Loop `Ajustar Code` | `test_adjust_code_loop_reparks_at_code_review_for_a_fresh_reviewer_pass` |
| Reviewer re-executa a cada `Em Code Review` | mesmo teste acima (duas entradas no `jira_gate_history`) + `test_prompt_runs_the_reviewer_on_every_code_review_entry` |
| `Em Merge` não faz merge automático | `test_full_workflow_through_all_three_gates`, `test_prompt_never_auto_merges_or_self_approves` |
| `Mergeado` é pós-merge | `test_merged_resume_carries_the_post_merge_context`, `test_prompt_post_merge_phase_is_administrative_only` |
| Docs e archive antes de `Em Merge` | `test_prompt_puts_archive_and_docs_before_the_merge_gate` |
| Guard pré-`Em Revisão de Spec` | `test_prompt_guards_spec_review_move_on_a_pushed_remote_branch` |
| Agente move todas as colunas que são dele | `test_prompt_makes_the_agent_own_every_non_gate_transition` |
| Transição inicial ordenada antes da spec | `test_prompt_orders_the_initial_transition_before_any_spec_work` |
| Commits pré-merge são revisados antes do gate | `test_prompt_reviews_the_pre_merge_commits_before_parking_at_the_merge_gate` |

**Observação sobre os testes existentes.** `test_jira_workflow_integration.py` estava falhando **antes** desta mudança neste ambiente, porque `JIRA_POLLER_SHADOW_MODE=1` está setado e o teste lia a constante do módulo (populada a partir do env no import). Os arquivos de teste do poller agora fixam os dois freios (`SHADOW_MODE`, `PAUSED`) via fixture, ficando independentes do ambiente.

---

## 10. O que não foi validado

Nada aqui foi exercitado contra um LLM real, o board Jira real ou o GitHub real — esta é a mesma limitação registrada em `.agents/memory/` e em `instruções replit.md`. As mudanças de poller estão cobertas por teste de comportamento; as mudanças de prompt estão cobertas por testes de conteúdo (o texto certo chega ao prompt renderizado), o que **não** é o mesmo que garantir que o modelo obedeça. A primeira execução real de um card ponta a ponta continua sendo o teste que falta.
