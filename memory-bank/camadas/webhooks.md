# Camada transversal: Webhooks

Três webhooks disparam runs do agente. Cada um resolve um `thread_id`
determinístico (para mensagens de acompanhamento rotearem para o mesmo run) e
dispara/transmite um run via cliente `langgraph_sdk`. Todos são montados no
webapp FastAPI (`agent/api/app.py:62-68`).

---

## GitHub — `agent/webhooks/github_routes.py`

- Rota: `POST /webhooks/github` (`github_routes.py:11`).
- Verificação: `X-Hub-Signature-256` via `verify_github_signature`
  (`common.py`), com segredo `GITHUB_WEBHOOK_SECRET`; 401 se inválida.
- Eventos suportados (`_SUPPORTED_GH_EVENTS`, `common.py:1021-1030`):
  `issue_comment`, `issues`, `pull_request`, `push`,
  `pull_request_review_comment`, `pull_request_review`.
- Ações de PR (`_SUPPORTED_GH_PULL_REQUEST_ACTIONS`): `opened`,
  `ready_for_review`, `converted_to_draft`, `closed`, `reopened`.
- **Auto-review** em `opened` / `ready_for_review`
  (`_GH_PR_FIRST_REVIEW_ACTIONS`, `github_routes.py:62-70`): agenda
  `process_github_pr_ready` quando o repo+autor optam in
  (`_is_repo_auto_review_enabled`).
- Outros fluxos: `push` → avaliação de reviewer watch; `issue_comment`/`issues`
  → `process_github_issue`; comentários de PR → `process_github_pr_comment`;
  reply de finding → `process_github_review_finding_reply`.
- Gates: allowlist de repos (`_is_repo_allowed`), gate de org para repos
  públicos (`_enforce_public_repo_org_gate`), e exigência de menção
  `@openswe`/`@open-swe` (`OPEN_SWE_TAGS`).

---

## Linear — `agent/webhooks/linear_routes.py`

- Rota: `POST /webhooks/linear`.
- Verificação: `Linear-Signature` via `verify_linear_signature` (`common.py:998-1018`),
  HMAC-SHA256 com `LINEAR_WEBHOOK_SECRET`.
- Processa comentários que mencionam `@openswe` (aciona o agente na issue).

---

## Slack — `agent/webhooks/slack_routes.py`

- Rotas: `POST /webhooks/slack` e `POST /interactivity`.
- Verificação: `X-Slack-Signature` via `verify_slack_signature`, com
  `SLACK_SIGNING_SECRET`.
- Dispara em: `app_mention`, mensagens diretas (DM), reações
  (`process_slack_reaction_added`/`removed` via `slack_feedback.py`) e botões
  Block Kit (interatividade, ex.: aprovação de plano).

---

## Derivação determinística de thread-ids — `agent/webhooks/common.py`

Funções que derivam ids estáveis para que a mesma issue/thread/PR roteie de volta
ao mesmo agente:

| Função | Origem | Formato |
|---|---|---|
| `generate_thread_id_from_issue` | `common.py:471-484` | Linear issue id → SHA-256 de `linear-issue:<id>` → UUID-formatted. |
| `generate_thread_id_from_github_issue` | `common.py:487-493` | GitHub issue id → SHA-256 de `github-issue:<id>`. |
| `generate_reviewer_thread_id` | `common.py:496-498` | `owner/repo/pr/<n>/reviewer` → `uuid5(NAMESPACE_URL, key)`. |
| `generate_thread_id_from_slack_thread` | `agent/utils/thread_ids.py` | Canal + thread ts do Slack. |
| `generate_thread_id_from_jira_issue` | (poller Jira) | Issue key do Jira. |

Threads de reviewer têm ids determinísticos próprios e são marcados com
`REVIEWER_THREAD_KIND` (metadata) para o lado FastAPI encontrá-los
(`agent/review/findings.py`).

> Nota: `get_thread_id_from_branch` (`agent/utils/github_comments.py`) deriva o
> id a partir do branch do PR — usado no fluxo de PRs.
