# Revisor de PR (`reviewer`)

Arquivo-fonte: `agent/reviewer.py` — factory `get_reviewer_agent` (linha 1328).

## Objetivo

Revisão de código de PRs, **read-only**. Realiza análise fresca do diff e trata a autoavaliação do autor como dado não confiável (a ser verificado, nunca endossado).

## Intenção

Nunca abre PR, faz commit ou push. Mantém um modelo de findings únicos em evolução, ancorados inline no diff (arquivo + intervalo de linhas).

## Resultado

Publica a review via `publish_review` (comentários inline), adiciona/atualiza/resolve findings e reconcilia com threads do GitHub.

## Fluxo de Entrada/Saída

- **Entrada**: `config` (`thread_id`, `repo`, `pr_number`, `base_sha`, `head_sha`, `reviewer_event`).
- **Saída**: review publicada, findings atualizados/resolvidos, threads reconciliadas.

## Conexões

Chamado por `dispatch` (assistant_id `"reviewer"`) e pelos webhooks do GitHub (auto-review). Consome o estilo de review produzido pelo `analyzer`. Usa o subagente `_reviewer_subagent` (reviewer.py:1399).

## Ferramentas

**Toolset** (reviewer.py:1387-1398): `fetch_review_diff`, `add_finding`, `update_finding`, `list_findings`, `publish_review`, `resolve_finding_thread`, `reply_to_finding_thread`, `web_search`, `fetch_url`, `http_request`.

**Middleware** (reviewer.py:1404-1425): `PrepareReviewerRun`, `SanitizeToolInputs`, `ModelCallLimit`, `ToolError`, `refresh_github_proxy`, `check_message_queue`, `SlackAssistantStatus`, `TimeoutWrapup`, `SanitizeFireworks`, `SanitizeThinking`, `RepairOrphanedToolCalls`, `ModelCallTimeout`, `settle_review_check_on_exit`.

**Modelo**: `resolve_model(CODE_REVIEWER)` → Opus/high.
