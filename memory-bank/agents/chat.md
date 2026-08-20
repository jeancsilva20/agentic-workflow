# Chat sobre PR (`chat`)

Arquivo-fonte: `agent/chat.py` — factory `get_chat_agent` (linha 180).

## Objetivo

Assistente de conversa "chat com este PR" para a UI de review. **Sem sandbox** — o contexto do PR vem via config.

## Intenção

Read-only: responde perguntas sobre um PR usando o diff, os findings e acesso read-only ao repositório via API do GitHub. Não aplica mudanças nem roda código.

## Resultado

Respostas textuais à conversa. Não altera o repositório, não executa comandos.

## Fluxo de Entrada/Saída

- **Entrada**: `config` (`thread_id`, `chat_repo_owner`, `chat_repo_name`, `chat_pr_number`), com o contexto do PR semeado como arquivos virtuais sob `/pr/`.
- **Saída**: respostas textuais.

## Conexões

Chamado por `agent/dashboard/review_chat_api.py` (proxy da UI). Usa o subagente `_chat_general_purpose_subagent` (chat.py:220).

## Ferramentas

**Toolset** (chat.py:213-219): `read_repo_file`, `search_repo_code`, `list_review_findings`, `web_search`, `fetch_url`. Exclui `execute`, `write_file`, `edit_file`, `delete` (via `ExcludeToolsMiddleware`).

**Middleware** (chat.py:221-233): `PrepareChatRun`, `SanitizeToolInputs`, `ModelCallLimit` (limite próprio `CHAT_MODEL_CALL_LIMIT`), `ToolError`, `ExcludeTools`, `SanitizeFireworks`, `SanitizeThinking`, `ModelCallTimeout`.

**Modelo**: `resolve_model(REVIEW_CHAT)` → Sonnet/medium.
