# Investigação: AI Gateway da Sensedia como camada Jira

Projeto analisado: `sensedia-ai-gateway-agent-demo-631725a6ff24/`. App Flask que consome o
AI Gateway da Sensedia e já conversa com o Jira via MCP em produção. A pergunta era se
dava para reaproveitar essa integração no coding agent.

## O que existe lá

### Servidor MCP `Jira_CRUD_Issue`

Não é o Atlassian Rovo. É um MCP próprio, gerado a partir de um swagger customizado
(`docs/swagger_jira_custom.yaml`, title `Jira_CRUD_Issue`) e publicado pelo AI Gateway.
O swagger aponta para `https://sensedia.atlassian.net` e expõe seis operações — que são
exatamente as seis de que este workflow precisa:

| operationId | endpoint | nome exposto ao LLM |
|---|---|---|
| `createIssue` | `POST /rest/api/3/issue` | `Jira_CRUD_Issue_createIssue` |
| `getIssue` | `GET /rest/api/3/issue/{issueIdOrKey}` | `Jira_CRUD_Issue_getIssue` |
| `searchIssuesWithJql` | `POST /rest/api/3/search` | `Jira_CRUD_Issue_searchIssuesWithJql` |
| `addComment` | `POST /rest/api/3/issue/{issueIdOrKey}/comment` | `Jira_CRUD_Issue_addComment` |
| `getTransitions` | `GET /rest/api/3/issue/{issueIdOrKey}/transitions` | `Jira_CRUD_Issue_getTransitions` |
| `transitionIssue` | `POST /rest/api/3/issue/{issueIdOrKey}/transitions` | `Jira_CRUD_Issue_transitionIssue` |

O prefixo vem do `McpToolAdapter`, que nomeia as tools como `{server_name}_{tool_name}`.

### OAuth 3LO headless resolvido

`services/atlassian_token_service.py` resolve o problema que inviabilizava o Rovo:
refresh token persistido em arquivo com escrita atômica, access token só em memória,
renovação automática com buffer de 60s, e tratamento de rotação do refresh token pela
Atlassian. Há ainda um modo alternativo `AI_GATEWAY_ATLASSIAN_TYPE_AUTH=basic` que usa
`base64(email:api_token)`.

### Arquitetura de acesso

`client.py` (facade `AiGateway`) faz auto-discovery de agentes de chat e servidores MCP
a partir de variáveis de ambiente, e injeta o `token_provider` do Atlassian no servidor
cujo `auth_key` é `Atlassian-Token`. O `McpService` implementa o protocolo à mão:
`initialize` → captura `Mcp-Session-Id` do header → `notifications/initialized` →
`tools/list` / `tools/call`, com parser de SSE.

## Por que não foi adotado no MVP

| | Corridor (padrão do Open SWE) | AI Gateway |
|---|---|---|
| Auth | 1 header estático | 2 camadas, ambas rotacionando |
| Sessão | implícita no `MultiServerMCPClient` | gerenciada manualmente |
| Retorno | `BaseTool` do LangChain | schema OpenAI function calling |
| I/O | async | `McpService` é síncrono (httpx sync) |

Três problemas concretos:

1. **O poller não é um LLM.** O poller do `scheduler` roda num cron tick de 60s, sem
   modelo no meio. Tool MCP existe para o modelo invocar; usar uma no poller significa
   reabrir sessão MCP a cada tick só para rodar duas queries JQL.
2. **Headers rotativos.** O `MultiServerMCPClient` do `langchain-mcp-adapters` recebe
   `headers` como dict fixo na construção. Os dois tokens do gateway rotacionam e o
   agente do Open SWE roda até 45 minutos — risco de 401 no meio da execução. Não
   testado.
3. **Dependência de topologia.** Exigiria gateway e Flask de pé para o coding agent
   funcionar. E o `MEMORY.md` do projeto registra que as rotas MCP no Flask nunca foram
   criadas ("Endpoints de MCP — expor tools/list e tools/call via API REST: não feito").

Somado a isso, o `transitionIssue` nunca foi executado — só o `createIssue` foi exercido
em produção. Construir os três gates de aprovação sobre uma camada não testada, quando a
alternativa é um `POST` com Basic auth, é assumir risco sem contrapartida.

## O que foi aproveitado

1. **O swagger vira o contrato.** `docs/swagger_jira_custom.yaml` documenta os seis
   endpoints com payloads e códigos de erro — é a referência para `agent/utils/jira.py`.
2. **A cicatriz do ADF.** `services/agent_service.py` tem `_pre_validate_create_issue` e
   `_pre_validate_add_comment`, que normalizam aspas curvas, travessões e NBSP dentro do
   ADF antes de mandar pro MCP — porque o Jira devolvia `INVALID_INPUT` / HTTP 400. Texto
   gerado por LLM em português contém exatamente esses caracteres. Essa lógica é portada
   para `agent/utils/adf.py`.
3. **Confirmação de que `transitionIssue` exige transition id**, não nome de coluna. O
   próprio swagger diz: *"Use this to find the transition ID needed to move a card"*.
   Daí a decisão de transições globais no workflow e a resolução nome→id dentro do
   cliente.

## Reavaliar quando

- Governança e observabilidade sobre as chamadas Jira do agente virarem requisito.
- O gateway passar a expor as tools por um transporte que o `langchain-mcp-adapters`
  consuma com header dinâmico.

Nesse cenário o Gateway MCP entra como fonte adicional de tools para o agente, e o
middleware continua usando o cliente REST direto — as duas coisas coexistem.
