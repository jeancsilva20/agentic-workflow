# Corrigir Máquina de Estados Jira

## What & Why

O fluxo Jira implementado tem dois erros estruturais em relação à especificação do produto:

**Erro 1 — fluxo incorreto da fase de spec.**  
O prompt atual (PASSO 1) instrui o agente a mover o card de `BACKLOG → In Progress` *antes* de iniciar qualquer trabalho de spec. Isso faz o card aparecer visualmente na coluna "Em Desenvolvimento" enquanto o agente ainda está escrevendo a spec. O fluxo correto é: BACKLOG → agente trabalha sem alterar status → estaciona em "Em Revisão de Spec". O status "In Progress" (coluna "Em Desenvolvimento") só deve ser usado *depois* de "Spec Aprovada", quando a implementação começa.

**Erro 2 — confusão entre nome de coluna e status do Jira.**  
As constantes atuais se chamam `COLUMN_*` mas contêm os strings que são enviados para a API do Jira como status. O documento de especificação deixa claro que:
- O usuário vê **colunas** (ex: "Pronto para Desenvolvimento", "Em Desenvolvimento")
- A API usa **status** (ex: "BACKLOG", "In Progress")
- O backend nunca deve usar o nome visual da coluna diretamente

O sistema atual não tem uma fonte central de verdade para essa distinção, e strings de status estão espalhados em múltiplos arquivos.

## Done looks like

- Existe um módulo central (`agent/jira_statuses.py` ou equivalente) que mapeia cada etapa do workflow para: nome do status Jira, nome visual da coluna, papel do agente, e tipo de transição (humana vs automática vs gate).
- O prompt não instrui mais o agente a mover o card para "In Progress" ao iniciar a fase de spec. O agente parte de BACKLOG, faz todo o trabalho de spec, e estaciona em "Em Revisão de Spec" sem passar por "In Progress".
- "In Progress" só aparece no prompt ao retomar de "Spec Aprovada" (início da implementação).
- O poller usa os status reais do Jira nos JQL (não os nomes visuais das colunas), mesmo que os valores continuem sendo os mesmos no ambiente atual.
- `phases.py` e `dispatch_route.py` continuam roteando corretamente: BACKLOG → `SPEC_AUTHOR`; "Spec Aprovada" → `CODING_AGENT` (que por sua vez move para "In Progress" como primeiro passo).
- Antes de alterar qualquer string de status, o executor consulta a API do Jira (via `jira_get_transitions` ou equivalente) para confirmar os nomes e IDs reais dos statuses no projeto SSAI, e documenta as divergências encontradas.
- Os comentários, logs e metadados de telemetria usam o nome amigável da coluna (para humanos) e o status real (para o sistema) de forma consistente.

## Out of scope

- Alteração das regras de roteamento de modelo ou esforço (arquivo `model-routing.md` cobre isso separadamente).
- Criação de novos gates ou alteração do número de etapas do fluxo.
- Alteração de limites de tempo/passos (coberto por tarefa separada).
- Migração de qualquer dado persistido (threads LangGraph, histórico de runs).

## Steps

1. **Auditar Jira antes de tocar código** — Consultar a API do Jira para listar todos os statuses reais do projeto SSAI, seus IDs, e as transições disponíveis. Produzir a tabela COLUMN / JIRA STATUS / STATUS ID / ENTERED BY / NEXT ACTION / NEXT VALID STATUS. Se houver divergência entre o que está hardcoded no poller e o que a API retorna, documentar antes de prosseguir.

2. **Criar módulo central de statuses** — Criar `agent/jira_statuses.py` com uma estrutura de dados (dataclass, NamedTuple ou enum) que agrupe para cada etapa: o status Jira (usado pela API), o nome visual da coluna (para logs/comentários), o papel do agente que a processa, e o tipo de transição. Todos os arquivos que hoje espalhavam strings de status devem importar deste módulo.

3. **Corrigir o fluxo da fase de spec no prompt** — Remover de PASSO 1 a instrução de mover o card para `{col_in_progress}` antes do trabalho de spec. O agente deve iniciar o trabalho de spec sem alterar o status. Ajustar o diagrama de fluxo exibido no prompt para refletir o caminho correto: `BACKLOG → spec → Em Revisão de Spec`, sem "In Progress" nesse trecho. Ajustar PASSO 1 para refletir que a primeira transição automática do agente é para "Em Revisão de Spec" (via `jira_park_at_gate`), não para "In Progress".

4. **Ajustar o passo de retomada de "Spec Aprovada"** — Garantir que na seção `JIRA_RESUME_SECTION`, ao retomar de "Spec Aprovada", o agente mova o card para "In Progress" como *primeiro passo da implementação* (não da spec). Este comportamento já existe mas deve ser revisado para garantir que a instrução de mover para "In Progress" não apareça em nenhum contexto de spec.

5. **Verificar JQL do poller** — Confirmar que `_trigger_jql()` e `_parked_jql()` usam os status reais retornados pela auditoria do passo 1. Se os valores atuais estiverem corretos (ex: `"BACKLOG"`, `"In Progress"`, `"Em Revisão de Spec"` como strings de status), manter. Se a auditoria revelar que os status têm nomes diferentes (ex: status real é `"Pronto para Desenvolvimento"` em vez de `"BACKLOG"`), atualizar os defaults das variáveis de ambiente.

6. **Atualizar nomenclatura das constantes** — Renomear as constantes `COLUMN_*` no poller para refletir que contêm *status* Jira (não nomes de colunas visuais), ou adicionar comentários explícitos que deixem claro a distinção. Atualizar todas as referências. Se a tarefa de centralização (passo 2) absorver isso, o passo de renomeação pode ser feito junto.

7. **Atualizar testes e documentação** — Ajustar testes existentes que referenciem o fluxo de status, e atualizar `docs/RELATORIO_AJUSTE_FLUXO_JIRA.md` e o arquivo de memória `jira-flow-rules.md` para refletir o fluxo corrigido.

## Relevant files

- `agent/jira_poller.py:40-160`
- `agent/routing/phases.py`
- `agent/routing/dispatch_route.py`
- `agent/prompt.py:182-260`
- `agent/tools/jira_park_at_gate.py`
- `agent/utils/jira.py`
- `.agents/memory/jira-flow-rules.md`
- `docs/RELATORIO_AJUSTE_FLUXO_JIRA.md`
