# GitHub fine-grained PAT para runs Jira

## What & Why

O poller Jira cria execuções com `source="jira"` mas não fornece `github_login`
nem `user_email`. O fluxo de autenticação GitHub tenta chamar
`leave_failure_comment("jira", ...)`, que não conhece essa fonte e lança
`ValueError: Unknown source: jira`, mascarando o erro real. Além disso, o
sistema não lê nenhuma variável de ambiente para um token GitHub global, então
execuções Jira nunca conseguem credencial. Este task adiciona suporte a um
**fine-grained Personal Access Token** como identidade técnica para runs Jira,
corrige o tratamento de falha de autenticação para essa fonte e injeta o token
no proxy do sandbox da mesma forma que o GitHub App.

## Done looks like

- Secret `GITHUB_PAT` configurado no ambiente é lido pelo sistema.
- Runs com `source="jira"` usam o PAT diretamente, sem tentar resolver
  `user_email` nem `github_login`.
- Quando o PAT está ausente ou inválido, o agente registra o erro em log e
  publica um comentário no card Jira antes de encerrar o run com falha limpa.
- `leave_failure_comment` aceita `source="jira"` sem lançar exceção secundária.
- O token é injetado no proxy do sandbox (LangSmith e local) pelo mesmo caminho
  que o token do GitHub App usa hoje.
- O comportamento das outras fontes (slack, linear, dashboard, github) permanece
  inalterado.
- Testes cobrem: PAT presente → token resolvido; PAT ausente → falha limpa com
  comentário Jira; App + PAT configurados → App tem precedência; sources
  existentes não são afetados.
- Nenhum valor real do token aparece em logs, traces do LangSmith, `configurable`
  da thread, metadata ou prompts.

## Out of scope

- Suporte a classic PAT ou PAT em sources não-Jira.
- Troca automática entre PAT e App com base em escopos/disponibilidade.
- Dashboard de login via PAT (`GITHUB_APP_CLIENT_ID`/`CLIENT_SECRET`).
- Renovação automática do PAT expirado.

## Permissions necessárias no fine-grained PAT

O token deve ser criado em **github.com → Settings → Developer Settings →
Personal access tokens → Fine-grained tokens** com as seguintes permissões nos
repositórios alvo:

| Permissão | Nível | Para quê |
|---|---|---|
| **Contents** | Read and write | Clone, branch, commit, push |
| **Pull requests** | Read and write | Abrir, atualizar e comentar PRs |
| **Issues** | Read and write | Comentar em issues |
| **Metadata** | Read-only | Sempre obrigatório pelo GitHub |
| **Checks** | Read and write | Criar/atualizar check runs de revisão |
| **Actions** | Read-only | Consultar logs de CI (opcional) |

O token deve ser escopado apenas para os repositórios que o agente deve acessar
(**Resource owner** = organização ou usuário; **Repository access** = only
selected repositories).

## Steps

1. **Ler o PAT do ambiente** — adicionar leitura de `GITHUB_PAT` em
   `agent/utils/github_app.py` (ou novo módulo `agent/utils/github_pat.py`).
   Expor uma função `get_github_pat() -> str | None` que retorna o valor limpo
   ou `None`.

2. **Corrigir `leave_failure_comment` para `source="jira"`** — em
   `agent/utils/auth.py`, adicionar um branch `if source == "jira":` que
   registra o erro em log e, quando `jira_issue_key` estiver disponível no
   `configurable`, publica um comentário no card Jira via `agent/utils/jira.py`.
   Se não houver chave, apenas loga. Em nenhum caso relança exceção.

3. **Rotear `source="jira"` para o PAT** — em
   `agent/utils/auth.py::resolve_github_token`, adicionar verificação logo após
   a resolução de `source`: se `source == "jira"` e `get_github_pat()` retorna
   valor, retornar `(pat, None)` imediatamente, sem tentar `user_email`,
   `github_login` nem LangSmith OAuth. Só cair no fluxo de email se o PAT não
   estiver configurado.

4. **Injetar PAT no proxy do sandbox** — em `agent/server.py::_prepare`, quando
   `resolve_github_token` retornar o PAT (identificável porque não há
   `expires_at`), passar o token para `_configure_github_proxy` da mesma forma
   que o token do App é passado hoje. Em `agent/integrations/local.py`,
   verificar se `GITHUB_PAT` está definido e injetá-lo no env do shell local,
   substituindo qualquer `GH_TOKEN` herdado.

5. **Garantir que o token não vaze** — revisar os caminhos de log, trace e
   metadata em `agent/utils/auth.py` e `agent/server.py` para confirmar que o
   valor do PAT nunca é serializado em `configurable`, metadata da thread ou
   strings de log.

6. **Testes** — em `tests/auth/`, adicionar casos: PAT presente usa PAT para
   source jira; PAT ausente produz falha limpa com comentário Jira; sources
   existentes (slack, linear) não são afetados; `leave_failure_comment("jira",
   ...)` não lança exceção.

## Relevant files

- `agent/utils/auth.py:240-296,432-499`
- `agent/utils/github_app.py:20-22,89-98`
- `agent/utils/github_token.py:38-55`
- `agent/jira_poller.py:240-272,333-349`
- `agent/server.py:887-916`
- `agent/integrations/langsmith.py:204-225,332-349,395-442`
- `agent/integrations/local.py`
- `agent/utils/jira.py`
- `tests/auth/test_auth_sources.py`
