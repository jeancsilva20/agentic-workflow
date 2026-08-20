# Restaurar configuração do .replit e variáveis de ambiente perdidas

## Contexto

Durante a sessão de debug do GitHub PAT, o arquivo `.replit` foi sobrescrito por um commit
que gerou uma versão degradada. Comparação com o branch `main` original revelou as seguintes
perdas críticas.

## O que precisa ser restaurado

### 1. Variáveis de ambiente em `[userenv.shared]`

Restaurar no `.replit` (via `configureWorkflow` ou `setEnvVars`):

| Variável | Valor |
|---|---|
| `JIRA_POLLER_SHADOW_MODE` | `"1"` |
| `LANGGRAPH_URL` | `"http://localhost:8000"` |
| `AGENT_CONSOLE_URL` | `"http://localhost:5050"` |
| `DEFAULT_REPO_NAME` | `"sensedia-backend-case"` |
| `DEFAULT_REPO_OWNER` | `"guilhermeallen"` |
| `JIRA_PROJECT_KEY` | `"SSAI"` |

`SANDBOX_TYPE = "local"` já está presente.

### 2. Módulos Nix no `.replit`

Restaurar:
```toml
modules = ["python-3.11", "nodejs-24"]

[nix]
channel = "stable-25_05"
packages = ["cargo", "libiconv", "libxcrypt", "openssl", "pkg-config", "rustc"]

[agent]
expertMode = true
```

### 3. GIT_ASKPASS para push no GitHub

O fix de GIT_ASKPASS que estava descrito nas notas de sessão anterior **não existe no código
atual** — `agent/integrations/local.py` é idêntico ao commit original sem qualquer configuração
de git credential helper. Sem isso, o push de branches para o GitHub continuará falhando
(além do problema de permissão do PAT).

Implementar em `agent/integrations/local.py::create_local_sandbox`:
- Criar um script `replit-git-askpass` que usa o `GITHUB_PAT` como senha
- Setar `GIT_ASKPASS` e `GIT_CONFIG_*` no ambiente do `LocalShellBackend`
- Garantir que `inherit_env=True` não sobrescreva as variáveis de git config

## Critérios de aceitação

1. `viewEnvVars` mostra todas as 6 variáveis restauradas
2. `.replit` tem `modules = ["python-3.11", "nodejs-24"]` e seção `[nix]` com os pacotes
3. LangGraph Server e Agent Console reiniciam sem erros
4. No próximo tick do poller, o console mostra atividade (telemetria chegando)
5. O poller continua em shadow mode (nenhum card movido no Jira)
6. `git push` de uma branch de teste para `guilhermeallen/sensedia-backend-case` retorna
   autenticação OK (403 esperado só se o PAT não tiver write — mas não deve retornar falha
   de credencial)
