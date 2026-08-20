# Remover Limite de Tempo para Runs Jira

## What & Why

O middleware `TimeoutWrapupMiddleware` injeta uma instrução de "encerrar imediatamente" no system prompt quando o run ultrapassa 45 minutos (`_DEFAULT_TIMEOUT_SECONDS = 45 * 60`). Esse limite é apropriado para runs interativos de engenharia genérica, mas inadequado para runs Jira:

A fase de spec de um card Jira envolve, na mesma run: ler o card e comentários, executar o Python Harness (que instala dependências e roda a suíte de testes), analisar o codebase, escrever o OpenSpec, fazer self-review, commitar e fazer push. Em repositórios de médio/grande porte, isso facilmente ultrapassa 45 minutos.

Quando o timeout dispara, o agente recebe a instrução de encerrar e termina o run sem concluir a fase de spec e sem chamar `jira_park_at_gate`. O card fica em BACKLOG (ou em "In Progress", dependendo do momento) sem gate, e um comentário de "run encerrado por limite" é postado. O comportamento correto é: **o agente deve rodar pelo tempo que for necessário para concluir a fase corrente e estacionar no gate adequado**.

## Done looks like

- Runs disparados por um card Jira (`source = "jira"`) não são interrompidos pelo timeout de wrapup durante a execução normal da fase corrente.
- Runs não-Jira continuam com o comportamento atual (timeout de 45 min ou `OPEN_SWE_WRAPUP_TIMEOUT_SECONDS`).
- Há uma variável de ambiente `JIRA_RUN_WRAPUP_TIMEOUT_SECONDS` que permite configurar explicitamente o timeout para runs Jira (default: sem timeout, ou valor alto como 8 horas).
- Se o timeout Jira for atingido mesmo assim, o comportamento correto ainda é tentar estacionar no gate atual antes de encerrar — não apenas "encerrar imediatamente".
- A mudança é coberta por um teste unitário que verifica que `TimeoutWrapupMiddleware` aplica limites diferentes conforme o contexto do run.

## Out of scope

- Alteração dos limites de recursão do grafo (`GRAPH_RECURSION_LIMIT = 9999`) — esses limites são adequados.
- Alteração do limite de chamadas ao modelo (`MODEL_CALL_LIMIT = 5000`) — também adequado.
- Timeout de infraestrutura (proxy, LangGraph server, containers) — fora do escopo desta tarefa.

## Steps

1. **Tornar o timeout configável por fonte de run** — Modificar `TimeoutWrapupMiddleware` (ou sua instanciação em `server.py`) para aceitar um timeout diferente dependendo se o run veio de uma fonte Jira. Adicionar leitura de `JIRA_RUN_WRAPUP_TIMEOUT_SECONDS` com default alto (ex: 8 horas = 28800 segundos) ou sem limite (0 = desativado).

2. **Propagar o contexto de fonte de run ao middleware** — Verificar como `server.py` instancia o middleware e se a informação `source: "jira"` dos metadados do run já está disponível nesse ponto. Se necessário, passar o contexto ao construtor do middleware ou tornar o timeout dinamicamente configurável por run.

3. **Suavizar a instrução de wrapup para runs Jira** — Quando o timeout Jira for atingido (caso configurado), a instrução injetada não deve dizer "encerrar imediatamente", mas sim "concluir o passo atual e estacionar no gate mais próximo via `jira_park_at_gate` antes de encerrar". Isso evita que o agente abandone o trabalho pela metade sem marcar o card corretamente.

4. **Adicionar teste** — Escrever teste unitário em `tests/` que verifique: (a) middleware com timeout padrão injeta instrução após 45 min em run não-Jira; (b) middleware com timeout Jira não injeta (ou injeta muito mais tarde) em run com `source = "jira"`; (c) instrução injetada em run Jira menciona `jira_park_at_gate`.

## Relevant files

- `agent/middleware/timeout_wrapup.py`
- `agent/server.py:1220-1240`
- `agent/runtime/constants.py`
