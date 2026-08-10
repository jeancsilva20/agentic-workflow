# Open SWE — Jira Extension

## Project overview

Este é o **Open SWE** (framework open-source de coding agent em LangGraph + Deep Agents), estendido para ser disparado por **Jira** em vez de só Slack/Linear/GitHub.

### Fluxo principal
1. Um card entra na coluna `BACKLOG` do projeto `SSAI` em `sensedia.atlassian.net`
2. O poller Jira (60s) detecta → dispara uma thread de agente
3. O agente usa **OpenSpec** como camada de especificação (gera `proposal.md`, `design.md`, `specs/*.md`, `tasks.md`)
4. Três aprovações humanas são feitas **movendo o card no board Jira** (spec, código, merge)
5. O agente comenta no card, move a coluna, encerra o run — o poller retoma quando o humano mover de volta

### Componentes
- **`agent/`** — LangGraph app principal (3 graphs: `agent`, `reviewer`, `analyzer`) + FastAPI (`agent/webapp.py`)
- **`agent-console/`** — console web Flask separado que exibe saúde do poller, fila e runs
- **`ui/`** — dashboard TanStack Start + Vite (login GitHub, settings, chat UI)
- **`desktop/`** — wrapper Electron experimental (não é o foco)
- **`openspec/`** — config da change + toda a documentação de decisão do projeto Jira

### Documentação-chave
- `instruções replit.md` — o que falta pra rodar, bugs encontrados, o que nunca foi validado
- `openspec/changes/jira-openspec-coding-agent/design.md` — todas as decisões técnicas
- `openspec/changes/jira-openspec-coding-agent/tasks.md` — checklist das 85 tarefas
- `docs/JIRA_INTEGRATION.md` — guia operacional: env vars, board setup, troubleshooting
- `docs/INSTALLATION.md` — setup completo (GitHub App, LangSmith, sandboxes)

## Como rodar (resumo)

O servidor usa `langgraph dev` a partir da raiz do projeto. Um `.env` mínimo com `SANDBOX_TYPE=local` é suficiente para o servidor subir — mas sem as credenciais abaixo nenhuma ação útil ocorre.

### Secrets necessários

| Variável | Finalidade | Obrigatório para rodar? |
|---|---|---|
| `ANTHROPIC_API_KEY` ou `OPENAI_API_KEY` | LLM do agente | Sim (qualquer chamada de modelo falha sem) |
| `JIRA_BASE_URL` | Endpoint Jira da Sensedia | Sim (poller não funciona sem) |
| `JIRA_EMAIL` | Auth Jira | Sim |
| `JIRA_API_TOKEN` | Auth Jira | Sim |
| `GITHUB_APP_ID` | Abrir PRs, clonar repos | Para funcionalidade completa |
| `GITHUB_APP_PRIVATE_KEY` | Auth GitHub App | Para funcionalidade completa |
| `GITHUB_APP_INSTALLATION_ID` | Escopo de repos | Para funcionalidade completa |
| `GITHUB_APP_CLIENT_ID` | Login dashboard | Para funcionalidade completa |
| `GITHUB_APP_CLIENT_SECRET` | Login dashboard | Para funcionalidade completa |
| `LANGSMITH_API_KEY` | Tracing (opcional) | Não (servidor sobe sem) |
| `AGENT_CONSOLE_URL` | Integração console Flask | Não (nada quebra sem) |

> ⚠️ As credenciais Jira estão em `.env.jira.local` na raiz do repositório pai (um nível acima). Copiar para `.env` faz o poller começar a consultar o board real da Sensedia. Usar `JIRA_POLLER_PAUSED=1` ou `JIRA_POLLER_SHADOW_MODE=1` para testar sem risco — ver `docs/JIRA_INTEGRATION.md`.

### Atenção: dois `agent-console/` diferentes
Existe um `agent-console/` na raiz do repositório pai que é um protótipo antigo **incompatível** com o que este projeto usa (`agent-console/` dentro deste diretório). Não apontar `AGENT_CONSOLE_URL` para o da raiz.

## Estado atual

- ✅ Servidor sobe com `SANDBOX_TYPE=local` (todos os 5 graphs carregam, `/docs` responde)
- ✅ Integração Jira implementada (`agent/jira_poller.py`, `agent/prompt.py`, `agent/utils/adf.py`)
- ✅ 11 colunas do board configuráveis via env var (bug de nomes fixos no prompt já corrigido)
- ✅ Race condition do registro do cron do poller já corrigida
- ❌ Nunca validado com LLM real processando um card pelos 11 PASSOs
- ❌ Fluxo de PR real nunca testado
- ❌ Métricas LangSmith incompletas (tasks.md §10.1)
- ❌ Botão de pausa no console web não existe (só env var)

## User preferences

- Não fazer mudanças no código sem instrução explícita
- Ler `instruções replit.md` antes de qualquer trabalho neste projeto
- Ler `openspec/changes/jira-openspec-coding-agent/design.md` antes de tomar decisões de arquitetura
