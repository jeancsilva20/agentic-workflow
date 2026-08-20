# Corrigir confiabilidade do ciclo de vida Jira

## What & Why

Três bugs no ciclo de vida do poller Jira causam execuções erradas, reinicializações fantasma e cards stranded:

1. **Role errado no launch inicial** — o dispatch de BACKLOG não passa `jira_new_column` nem `jira_column`, então `dispatch_route.py` cai no fallback `coding_agent` em vez de `spec_author`. Toda nova task abre como agente de código, não como spec_author.

2. **Run interrompida deixa card stranded para sempre** — quando uma run é cancelada/interrompida sem ter estacionado em gate (`jira_parked=False`), o thread ainda existe. O Step A do poller vê o thread e pula o card eternamente — não há caminho de recuperação. O card fica preso sem nenhuma execução ativa.

3. **Runs enfileiradas no platform sobrevivem ao restart do servidor** — o LangGraph platform persiste runs pendentes; ao reiniciar o servidor, ticks do scheduler já enfileirados são drenados e disparam launches reais mesmo depois de o operador ter parado e limpo as threads manualmente. É por isso que `SSAI-88` voltou a rodar após o restart, apesar do Shadow Mode estar ligado.

## Done looks like

- Um card `BACKLOG` novo abre como `spec_author`, nunca como `coding_agent`.
- Um card cujo thread existe mas não tem run ativa nem flag `jira_parked` é relançado como se fosse novo (recovery automático de run interrompida).
- O poller, ao encontrar um thread sem run ativa e sem `jira_parked`, deleta o thread fantasma antes de relançar — limpeza idempotente.
- O comportamento de restart é seguro: se runs do scheduler foram enfileiradas antes do restart, o tick seguinte não cria duplicatas porque o Step A detecta thread existente com run ativa.

## Out of scope

- Alterar o fluxo de gates (Em Revisão de Spec, Em Code Review, Em Merge).
- Alterar timeout ou limites de recursão.
- Mudanças no Agent Console ou telemetria.

## Steps

1. **Corrigir role inicial** — em `agent/jira_poller.py`, ao montar o payload de dispatch para Step A (BACKLOG trigger), incluir `jira_new_column=COLUMN_TRIGGER` e `jira_column=COLUMN_TRIGGER` no configurable. Em `agent/routing/dispatch_route.py`, garantir que `COLUMN_TRIGGER` seja mapeado para `spec_author` via `phases.py` — o mapeamento já existe em `phases.py` (linha 43-46), só falta o poller passar a coluna.

2. **Recovery de run interrompida** — em `agent/jira_poller.py` Step A, após detectar que o thread existe, checar via SDK se há alguma run ativa (status `running` ou `pending`). Se não houver run ativa E `jira_parked` for False, deletar o thread e prosseguir com o launch normal como se fosse um card novo. Adicionar log warning com issue key e thread_id para rastreabilidade.

3. **Idempotência no restart** — o fix do passo 2 já resolve o caso de restart: se o servidor subiu e o scheduler enfileirado disparar um tick, o Step A encontra o thread existente com run ativa (status `running`) e pula — sem duplicata. Verificar que a lógica de "run ativa" cobre tanto `running` quanto `pending`/`enqueued`.

## Relevant files

- `agent/jira_poller.py:103-110,233-284,296-368`
- `agent/routing/dispatch_route.py:53-74`
- `agent/routing/phases.py:18-46`
- `agent/dispatch.py:117-217`
