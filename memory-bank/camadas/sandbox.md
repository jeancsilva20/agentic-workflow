# Camada transversal: Ciclo de Vida do Sandbox

Cada thread do LangGraph tem seu próprio sandbox isolado em nuvem. O estado é
compartilhado entre `server.py` e os middlewares via `agent/utils/sandbox_state.py`.

---

## Providers — `agent/utils/sandbox.py`

Selecionados por `SANDBOX_TYPE` (default `langsmith`) via `SANDBOX_FACTORIES`
(`sandbox.py:13-20`):

| Chave | Factory |
|---|---|
| `langsmith` (default) | `agent.integrations.langsmith:create_langsmith_sandbox` |
| `daytona` | `agent.integrations.daytona:create_daytona_sandbox` |
| `modal` | `agent.integrations.modal:create_modal_sandbox` |
| `runloop` | `agent.integrations.runloop:create_runloop_sandbox` |
| `e2b` | `agent.integrations.e2b:create_e2b_sandbox` |
| `local` | `agent.integrations.local:create_local_sandbox` |

`create_sandbox` (`sandbox.py:35-66`) cria ou reconecta. `langsmith`, `modal` e
`local` provisionam nativamente async; `daytona`, `e2b` e `runloop` ficam em
`asyncio.to_thread` (seus wrappers `langchain_*` seguram um SDK síncrono).
Somente `langsmith` honra `snapshot_id` (senão cai em `DEFAULT_SANDBOX_SNAPSHOT_ID`).
`validate_sandbox_startup_config` (`sandbox.py:69-80`) valida env vars no boot.

---

## Estado por thread — `agent/utils/sandbox_state.py`

- `SANDBOX_BACKENDS` (`sandbox_state.py:258`): dict em processo `thread_id →
  SandboxBackendProxy`.
- `SandboxBackendProxy` (`sandbox_state.py:53-254`): handle estável por thread
  cujo alvo pode ser substituído (`replace_backend`). **Async-only**: os métodos
  síncronos levantam `NotImplementedError` (`_SYNC_UNSUPPORTED`). Subclasseia
  `BaseSandbox` para o `FilesystemMiddleware` reconhecer captura-na-fonte no
  offload de `execute`.
- `SandboxUnreachableError` (`sandbox_state.py:32-47`): o sandbox da thread não
  respondeu neste run. Nunca é resolvido criando substituto — um sandbox novo
  seria vazio e destruiria trabalho não commitado parecendo recuperação.

Helpers: `set_sandbox_backend`, `get_or_create_sandbox_backend_proxy`,
`clear_sandbox_backend`, `get_sandbox_backend`, `unwrap_sandbox_backend`,
`get_sandbox_id_from_metadata` (lê `sandbox_id` do metadata da thread).

---

## `ensure_sandbox_for_thread` — 3 casos

1. **Cacheado em memória** → ping (`echo ok`), depois refresh do proxy GitHub.
2. **Metadata tem id mas sem cache** → reconectar, depois refresh do proxy.
3. **Nenhum sandbox** → criar e persistir o id.

Só o caso 3 cria. Um sandbox existente inalcançável levanta
`SandboxUnreachableError` em vez de ser substituído; o agente principal captura
isso em `PrepareAgentRunMiddleware` e notifica o usuário via
`post_sandbox_unreachable_notification`.

---

## Proxy GitHub (langsmith)

Para `SANDBOX_TYPE=langsmith`, toda criação/refresh de sandbox chama
`_configure_github_proxy` com um token de instalação fresco do GitHub App
(`get_github_app_installation_token`). O proxy injeta:

- **Basic auth** para tráfego git de `github.com`.
- **Bearer auth** para `api.github.com`.

Assim comandos no sandbox podem usar `GH_TOKEN=dummy gh ...` sem armazenar
tokens reais no sandbox. Outros providers (modal, daytona, runloop, e2b, local)
pulam o proxy.

---

## `allow_replacement=True` — só no reviewer

`allow_replacement=True` opta fora da proteção contra substituição e é passado
**apenas** pelo reviewer (`agent/reviewer.py:_ensure_reviewer_sandbox_for_thread`),
cujo sandbox guarda só um checkout que `prepare_review_repo` re-deriva a cada run.
Threads de reviewer são um-por-PR e sobrevivem ao sandbox; sem isso, um sandbox
deletado travaria as revisões daquele PR permanentemente.

---

## Re-aplicação de `git config --global` por run

Todo run re-aplica `git config --global user.name/email` para a identidade do
bot, porque sandboxes reutilizados/reconectados podem perder config `--global`, e
deploys de preview do Vercel rejeitam commits cujo email de autor não resolve
para uma conta GitHub.
