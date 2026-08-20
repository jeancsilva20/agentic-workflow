# Abrir PR via PAT e bloquear Code Review se o PR falhar

## What & Why

Duas falhas distintas permitiram que o SSAI-97 chegasse a "Em Merge" sem PR:

**1. `open_pull_request` não usa o GITHUB_PAT como fallback.**
A função `_resolve_pr_author_token` tenta: (a) token OAuth do usuário para runs
Slack/Linear, (b) GitHub App installation token. Runs do Jira não têm `github_login`
e a GitHub App não está instalada — resultado: sempre `(None, "bot")` → falha com
`no_github_token`. O mesmo PAT que autentica clone, branch e push consegue criar PRs
(confirmado: PR #1 criado via REST API com o PAT).

**2. O agente ignorou a falha e avançou o card mesmo sem PR.**
O prompt tem um guard explícito — "Do not move to `{col_code_review}` unless the PR
was created or updated successfully" — mas em Lite Mode (Haiku) o agente ignorou e
moveu o card para "Em Code Review" e depois "Em Merge".

Ambos precisam ser corrigidos: a causa técnica (sem PAT fallback) e a garantia
comportamental (card não avança sem PR confirmado).

## Done looks like

- Runs Jira criam o PR automaticamente usando o GITHUB_PAT — sem GitHub App,
  sem intervenção manual
- O PR é aberto **antes** de qualquer chamada a `jira_park_at_gate` para
  `{col_code_review}` — essa ordem é verificada no prompt e nos testes
- Se `open_pull_request` falhar mesmo com o PAT disponível, o agente posta um
  comentário no card descrevendo a falha, deixa o card em "Em Progresso" e encerra
  o turn — não avança para nenhum gate
- Runs Slack/Linear/GitHub não são afetados

## Out of scope

- Instalar ou configurar a GitHub App
- Alterar o comportamento de runs não-Jira

## Steps

1. **Adicionar fallback ao PAT em `_resolve_pr_author_token`** — após
   `get_github_app_installation_token()` retornar `None`, tentar `get_github_pat()`.
   Retornar `(pat, "pat")` para distinguir nas métricas. Atualizar o docstring.

2. **Verificar compatibilidade** — `_auth_headers` e `_preflight_pr_access` usam
   o token como Bearer para a API REST do GitHub; PAT clássico funciona da mesma
   forma que o App token, sem mudanças adicionais.

3. **Tornar o guard explícito no prompt do workflow Jira** — na seção de
   implementação (PASSO 5 / `{col_in_progress}`), adicionar instrução clara:
   "Confirme que `open_pull_request` retornou `success: true` e que você tem a URL
   do PR antes de chamar `jira_park_at_gate` para `{col_code_review}`. Se retornar
   `success: false`, comente a falha no card com `jira_add_comment` e encerre o
   turn — não avance o card."

4. **Adicionar testes** cobrindo:
   - Sem user token, sem App token, PAT disponível → `_resolve_pr_author_token`
     retorna `(pat, "pat")`
   - Prompt Jira com `{col_code_review}` contém instrução de verificar URL do PR

## Relevant files

- `agent/tools/open_pull_request.py:30-56` — `_resolve_pr_author_token`
- `agent/utils/github_pat.py` — `get_github_pat()`
- `agent/prompt.py:249-269` — seção de resume / `{col_spec_approved}` onde a
  implementação começa e o PR deve ser aberto
