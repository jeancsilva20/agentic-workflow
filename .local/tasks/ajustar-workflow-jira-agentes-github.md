# Ajustar Workflow Jira → Agentes → GitHub

## What & Why

O arquivo `attached_assets/Pasted-Quero-revisar-e-ajustar-o-workflow-Jira-agentes-GitHub-_1786328542918.txt` define o fluxo alvo com 11 estados Jira e regras precisas de responsabilidade, idempotência e tratamento de falhas. A análise da implementação atual revelou seis divergências concretas em relação a esse fluxo. Este task corrige essas divergências incrementalmente, preservando a arquitetura existente (poller + threads determinísticas + park/resume + durable execution).

### Divergências confirmadas

**1. Bug crítico no JQL de Step B (poller não detecta decisões humanas)**

O JQL de Step B é `status in ("Em Revisão de Spec", "Em Code Review", "Em Merge")`. Quando o humano move o card para `Spec Aprovada`, `Ajustar Spec`, `Code Review Aprovado`, `Ajustar Code` ou `Mergeado`, o card sai das colunas gate e desaparece da query. O poller nunca detecta a decisão humana. Fix: expandir o JQL de Step B para incluir todos os status pós-gate.

**2. Shadow mode não suprime Step B**

`JIRA_POLLER_SHADOW_MODE` suprime apenas Step A (novos cards). Step B (resumo de threads estacionadas) executa mesmo em shadow mode — violando a garantia de "nenhuma ação real em shadow mode". Fix: aplicar shadow mode ao Step B também (log observacional sem dispatch).

**3. Archivamento da OpenSpec e atualização de docs ocorrem após o merge, não antes**

O fluxo alvo exige que OpenSpec archive e documentação relevante sejam feitos ANTES de mover para `Em Merge` (na mesma branch/PR). A implementação atual faz archivamento e docs após `Mergeado` (PASSO 9/10 pós-merge). Fix: reorganizar o prompt para incluir preparação pré-merge (archive + docs na branch) antes de estacionar em `Em Merge`.

**4. Ajustar Code busca apenas comentários do Jira, não reviews do GitHub**

O fluxo alvo diz: "A fonte principal dos ajustes de código deve ser o GitHub." O resume dispatch atual inclui só os últimos 5 comentários do Jira. Quando o agente retoma a partir de `Ajustar Code`, ele precisa buscar ativamente os reviews e comentários da PR no GitHub. Fix: adicionar instrução explícita no prompt para, ao retomar de `Ajustar Code`, chamar a tool de busca de PR reviews/comments do GitHub e usá-los como fonte primária dos ajustes.

**5. Fluxo pós-Mergeado inadequado**

Com o fix do JQL (#1), o poller passará a detectar `Mergeado`. Mas o prompt atual tenta criar uma PR separada de docs após o merge — o que conflita com o fluxo alvo, que define `Mergeado → Done` como uma fase curta e administrativa (confirmar PR merged, registrar resultado, comentar, mover para Done). Fix: ajustar instruções do prompt para o resume em `Mergeado`.

**6. Falta guard explícito para mover para `Em Revisão de Spec`**

O fluxo alvo diz: "O card não pode ser movido para 'Em Revisão de Spec' se a OpenSpec não tiver sido persistida, commitada e enviada para o GitHub com sucesso." O prompt atual não torna isso explícito. Fix: adicionar instrução de guard no prompt — o `jira_park_at_gate` para `Em Revisão de Spec` só deve ser chamado após confirmar que a branch remota com a OpenSpec existe.

## Done looks like

- O poller detecta cards movidos para `Spec Aprovada`, `Ajustar Spec`, `Code Review Aprovado`, `Ajustar Code` e `Mergeado` sem perda de idempotência
- Em shadow mode, Step B loga o que "faria" mas não dispara nenhum resume real
- O agente executa archive da OpenSpec e docs relevantes na branch antes de mover para `Em Merge`
- Ao retomar de `Ajustar Code`, o agente busca reviews/comentários da PR no GitHub como fonte primária
- Ao retomar de `Mergeado`, o agente executa somente tarefas administrativas de fechamento e move para `Done`
- Guard no prompt impede mover para `Em Revisão de Spec` antes de confirmar branch remota com OpenSpec
- Testes existentes continuam passando; novos testes cobrem as transições do fluxo alvo (loop Ajustar Spec, loop Ajustar Code, idempotência de polling, reviewer re-execução, guard pre-Em Revisão de Spec, preparação pré-merge, fluxo Mergeado → Done)
- Sem reescrita da arquitetura: poller, threads determinísticas, park/resume e durable execution permanecem intactos

## Out of scope

- Substituição ou remoção dos triggers existentes (Linear/Slack/GitHub)
- Webhooks Jira (o poller de 60s permanece como mecanismo primário)
- Autenticação no agent-console
- Mudança nos grafos LangGraph (reviewer graph não é alterado estruturalmente)
- Resolução do conflito entre os dois `agent-console/` (Task #4, cancelada — contexto separado)
- Configuração de sandbox segura (Task #10, em paralelo)
- Qualquer mudança no board Jira real (o board SSAI já tem as 11 colunas configuradas)

## Steps

1. **Corrigir JQL de Step B** — expandir `_parked_jql()` em `agent/jira_poller.py` para incluir todos os status pós-gate: `Spec Aprovada`, `Ajustar Spec`, `Code Review Aprovado`, `Ajustar Code` e `Mergeado`. O Step B deve encontrar cards estacionados independentemente de qual coluna o humano os moveu. Garantir que a lógica de comparação `current_column == parked_column` (sem mudança → ignora) e a lógica de skip (thread não parked → ignora) continuem intactas para preservar idempotência.

2. **Aplicar shadow mode ao Step B** — em `agent/jira_poller.py`, após a expansão do JQL, adicionar verificação de `JIRA_POLLER_SHADOW_MODE` no loop de Step B: em shadow mode, logar o que seria retomado (`[shadow] would resume thread for {issue_key}: {parked_column} → {current_column}`) sem emitir dispatch real. Emitir evento de console observacional idêntico ao que seria emitido, mas marcado como shadow.

3. **Reorganizar o prompt de preparação pré-merge** — em `agent/prompt.py` (e/ou `agent/resources/default_prompt.md`), mover as instruções de archivamento da OpenSpec e atualização de documentação relevante para ANTES de estacionar em `Em Merge`. O agente deve: executar checks e testes finais → arquivar OpenSpec (`openspec_archive`) → identificar e atualizar docs impactadas na mesma branch → commitar e fazer push → confirmar PR consistente → mover para `Em Merge`. Remover instruções que criam PR separada de docs (Decision 6 do design.md é sobrescrita pelo fluxo alvo).

4. **Adicionar guard pré-`Em Revisão de Spec`** — no prompt, tornar explícito que `jira_park_at_gate` para `Em Revisão de Spec` só deve ser chamado após confirmar que a branch remota com os artefatos da OpenSpec existe (branch pushed com sucesso). Se o push falhar, registrar o erro de forma observável (comentar no Jira se possível) e não mover o card.

5. **Instruções de Ajustar Code com fonte GitHub** — no prompt, adicionar instrução explícita para o caso de retomada de `Ajustar Code`: o agente deve identificar a PR associada, buscar ativamente reviews e comentários da PR no GitHub (usando as tools disponíveis), e usá-los como fonte primária dos ajustes antes de consultar os comentários do Jira. Listar os pontos pendentes de ajuste de forma estruturada antes de iniciar as correções.

6. **Instruções de Mergeado → Done (fase pós-merge curta)** — no prompt, adicionar instrução clara para o caso de retomada de `Mergeado`: confirmar que a PR está realmente merged (via API GitHub), registrar resultado final da execução, atualizar metadados/métricas existentes, fazer comentário final no Jira com resumo, mover para `Done`. Nenhuma alteração funcional nova na branch neste ponto.

7. **Atualizar e criar testes** — executar a suíte de testes existente em `tests/` relacionada ao poller e ao fluxo Jira. Criar ou atualizar testes unitários para: (a) JQL expandido de Step B cobrindo todos os pós-gate, (b) shadow mode em Step B, (c) idempotência de polling (tick repetido em estado já processado não reprocessa), (d) retomada da mesma thread, (e) loop Ajustar Spec (Em Revisão de Spec → Ajustar Spec → Em Revisão de Spec), (f) loop Ajustar Code (Em Code Review → Ajustar Code → Em Code Review), (g) reviewer executa ao entrar em Em Code Review via Ajustar Code, (h) Em Merge não faz merge automático, (i) Mergeado interpretado como pós-merge, (j) docs e archive antes de Em Merge.

8. **Gerar relatório de validação** — ao final, gerar relatório objetivo com: fluxo antes/depois, divergências encontradas, arquivos modificados, mudanças feitas, máquina de estados final (quais estados são automáticos, quais são Human in the Loop), como poller detecta cada retomada, como thread é estacionada/retomada, resultado dos testes.

## Relevant files

- `agent/jira_poller.py`
- `agent/prompt.py`
- `agent/resources/default_prompt.md`
- `agent/tools/jira_park_at_gate.py`
- `agent/utils/jira.py`
- `openspec/changes/jira-openspec-coding-agent/design.md`
- `docs/JIRA_INTEGRATION.md`
- `tests/` (qualquer arquivo de teste existente relacionado ao poller ou fluxo Jira)
