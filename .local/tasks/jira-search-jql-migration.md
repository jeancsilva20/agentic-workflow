# Migrar busca Jira para /search/jql

## What & Why
A Atlassian removeu `POST /rest/api/3/search` (HTTP 410, CHANGE-2046), quebrando o poller (step_a/step_b) e a tool de busca. Validação já feita: credenciais e base path estão corretos (`GET /myself` = 200) e o endpoint novo `POST /rest/api/3/search/jql` funciona (200, retornou issues do SSAI). Migrar `search_issues()` para o endpoint novo.

## Done looks like
- Poller roda sem erro 410 nos logs (step_a/step_b lançam/retomam runs normalmente)
- Tool `jira_search_issues` retorna resultados
- Paginação continua funcionando com o novo contrato (o endpoint novo usa `nextPageToken` em vez de `startAt`/`total`)
- Testes existentes de busca Jira atualizados e passando

## Out of scope
- Demais endpoints Jira (issue, comments, transitions) — continuam funcionando, sem mudança
- Integração Linear
- Mudanças no AI Gateway/exploration docs

## Steps
1. **Migrar o client** — Trocar `search_issues()` para `POST /rest/api/3/search/jql`, adaptando o corpo da requisição e o contrato de resposta (paginação por `nextPageToken`; o campo `total` não existe mais — ajustar o formato retornado ou derivar equivalente) mantendo a assinatura o mais estável possível para os chamadores.
2. **Ajustar chamadores** — Revisar o poller e a tool de busca para o novo formato de retorno/paginação, garantindo que os JQLs de trigger e parked continuem funcionando (validado que o endpoint aceita `fields` e `maxResults`).
3. **Atualizar testes** — Adaptar mocks e asserções dos testes de `search_issues`, do poller e da tool para o novo endpoint e contrato; rodar a suíte.

## Relevant files
- `agent/utils/jira.py:118-135`
- `agent/jira_poller.py`
- `agent/tools/jira_search_issues.py`
- `tests/utils/test_jira.py`
- `tests/agent/test_jira_poller.py`
- `tests/tools/test_jira_tools.py`
