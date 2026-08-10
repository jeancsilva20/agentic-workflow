# Instruções para continuar este projeto (Replit)

Este arquivo existe pra alguém (ou algum agente) que abrir este repositório no Replit conseguir entender rápido: o que é o projeto, onde está cada coisa, e o que falta pra rodar e testar de verdade. Tudo que era documentação/decisão de projeto foi movido pra dentro de `open-swe/` nesta reorganização — antes estava espalhado na raiz do repositório, um nível acima.

## Objetivo do projeto

Este é o **Open SWE** (framework de coding agent open-source em LangGraph + Deep Agents) estendido para ser disparado por **Jira** em vez de só Slack/Linear/GitHub. A ideia:

- Um card entrando na coluna `BACKLOG` de um projeto Jira dispara um agente.
- O agente usa **OpenSpec** como camada de especificação — gera `proposal.md`/`design.md`/`specs/*.md`/`tasks.md` antes de implementar.
- Três aprovações humanas são feitas **movendo o card no board Jira** (spec, código, merge) — o agente nunca fica bloqueado esperando; ele comenta, move o card, e termina o run. Um poller de 60s detecta quando o humano moveu o card e retoma a thread.
- Um console web (Flask, separado do agente) mostra o estado disso tudo: saúde do poller, fila, runs ativos/parados/mortos, log de execução.

O racional completo — por que Jira via REST direto (não MCP), por que o poller não bloqueia, por que `BACKLOG` é o gatilho, etc. — está em `openspec/changes/jira-openspec-coding-agent/design.md`. Não repita essas decisões sem ler esse arquivo primeiro.

## O que foi movido nesta reorganização

Estava na raiz do repositório (um nível acima de `open-swe/`), agora está aqui dentro:

| Antes (raiz do repo) | Agora (dentro de `open-swe/`) |
|---|---|
| `openspec/` (config.yaml + a change inteira: proposal, design, tasks, 6 specs, 7 docs de exploração, spec-grounding.md) | `open-swe/openspec/` |
| `The Agentic Development Playbook.md` | `open-swe/docs/reference/agentic-development-playbook.md` |
| `langgraph-coding-agent-open-swe-arquitetura.md` | `open-swe/docs/reference/langgraph-coding-agent-open-swe-arquitetura.md` |
| `scripts/spike_jira.py` | `open-swe/scripts/spike_jira.py` (ajustei o caminho relativo que ele usa pra achar `.env.jira.local` — ver abaixo) |

**Ficou de fora, de propósito:**
- `.env.jira.local` (raiz do repo, um nível acima de `open-swe/`) — tem credencial real do Jira da Sensedia. Não movi/dupliquei porque isso não é documentação, é segredo — ver seção abaixo sobre como usá-lo.
- `sensedia-ai-gateway-agent-demo-*/` (raiz) — é um projeto de referência inteiro (não documentação deste projeto), citado no design.md Decisão 2 como fonte do contrato de endpoints e da normalização de caracteres ADF. Já portei o que era relevante para `agent/utils/adf.py`; o resto continua lá como referência histórica se precisar consultar de novo.

**Se você (ou algum script) rodava `openspec status`/`openspec list` a partir da raiz do repositório antigo, isso para de funcionar** — o `openspec/` agora só existe dentro de `open-swe/`. Rode esses comandos com `open-swe/` como diretório de trabalho.

## Achado ao reorganizar: dois `agent-console/` diferentes

Existe um `agent-console/` na **raiz do repositório** (fora de `open-swe/`) que é uma implementação **diferente e incompatível** da que está em `open-swe/agent-console/` (a que este projeto realmente usa — ligada em `agent/utils/console_events.py`, `agent/jira_poller.py`, etc.). A da raiz:

- Usa nomes de campo diferentes no ingest (`store.upsert_run(issue_key, state=..., step=..., column=...)` vs. o formato real `{"issue_key", "action", ...}` que o código em `open-swe/` efetivamente envia).
- Tem um modo `--demo` com dados de exemplo em português, não tem testes, não tem `requirements.txt`.
- Foi criada **antes** de qualquer trabalho desta sessão (timestamp anterior) — parece ser um protótipo/rascunho anterior que nunca foi conectado a nada.

**Isso precisa ser resolvido antes de ir pra produção**: se alguém apontar `AGENT_CONSOLE_URL` pro `agent-console/` da raiz por engano, os eventos que o poller manda não vão bater com o que aquele `store.py` espera. Recomendo apagar o da raiz depois de confirmar que não tem nada útil nele que falte no de `open-swe/` — não apaguei sozinho porque não tenho certeza de quem criou aquilo nem se você quer olhar antes.

## O que falta para RODAR

O servidor (LangGraph + FastAPI) precisa de configuração que não existe neste ambiente. Já criei um `open-swe/.env` mínimo (só `SANDBOX_TYPE=local`) que permite o servidor **subir e responder** — confirmei isso rodando `langgraph dev` de verdade (todos os 5 graphs carregam, a API responde em `/docs`). Mas pra fazer qualquer coisa útil, falta:

1. **Um provedor de LLM** — `ANTHROPIC_API_KEY` ou `OPENAI_API_KEY` (o modelo default é resolvido em `agent/dashboard/options.py`). Sem isso o agente sobe mas qualquer chamada de modelo falha.
2. **Credenciais do Jira** — copiar as 3 variáveis de `.env.jira.local` (na raiz do repo, um nível acima) pra dentro de `open-swe/.env`:
   ```
   JIRA_BASE_URL=...
   JIRA_EMAIL=...
   JIRA_API_TOKEN=...
   ```
   **Atenção**: assim que isso estiver no `.env` e o servidor subir, o poller começa a consultar o board real da Sensedia (`sensedia.atlassian.net`, projeto SSAI) a cada tick. Isso é só leitura a menos que um card realmente esteja em `BACKLOG` — nesse caso ele tentaria disparar uma thread de verdade. Ver `JIRA_POLLER_PAUSED=1` e `JIRA_POLLER_SHADOW_MODE=1` em `docs/JIRA_INTEGRATION.md` se quiser testar sem esse risco.
3. **Sandbox real** (opcional pra teste local) — `SANDBOX_TYPE=local` roda comandos direto na máquina host, **sem isolamento nenhum** (aviso no próprio código, `agent/integrations/local.py`). Serve pra testar se o servidor sobe, não serve pra deixar um agente de verdade implementar coisas. Pra isso, configurar `SANDBOX_TYPE=langsmith` (ou `daytona`/`modal`/`e2b`) com as credenciais do provedor — ver `docs/INSTALLATION.md`.
4. **GitHub App** — necessário pro agente clonar repos, commitar, abrir PR. Ver `docs/INSTALLATION.md` passo 3. Sem isso, tudo que envolve `open_pull_request`/`gh` falha.
5. **LangSmith** (opcional pra rodar, recomendado) — `LANGSMITH_API_KEY`/`LANGCHAIN_API_KEY` pra tracing. O servidor sobe sem isso (viu no log: "No license key or control plane API key set, skipping metadata loop").
6. **Console do agente** (opcional) — `pip install -r open-swe/agent-console/requirements.txt` e rodar `python open-swe/agent-console/app.py` separadamente, depois `AGENT_CONSOLE_URL=http://localhost:5050` no `.env` do servidor principal. Sem isso, o agente/poller simplesmente não mandam eventos — nada quebra.
7. **Board Jira** — isso já existe (projeto `SSAI` em `sensedia.atlassian.net`, 11 colunas, transições globais configuradas — ver `design.md`, seção "Jira Column Configuration"). Não é um pendente.

## O que falta para TESTAR de ponta a ponta

Tudo abaixo eu não consegui validar neste ambiente (sem LLM real, sem GitHub App, sem tocar no board de produção):

- **Nunca foi validado com um LLM de verdade processando um card real através dos 11 PASSOs.** O prompt inteiro (`agent/prompt.py`, seções `JIRA_*`) foi verificado estruturalmente (que o texto renderiza certo, que os nomes de coluna batem) mas nunca visto na prática decidindo o que fazer.
- **Fluxo de PR real nunca testado** — abrir draft PR, rodar o reviewer graph nela (`request_self_review`), receber `CHANGES_REQUIRED`, finalizar. Só a lógica de encaminhamento foi testada com mocks.
- **Métricas LangSmith incompletas** (tasks.md §10.1): tempo total de run, contagem de findings do reviewer, e status final não são gravados em lugar nenhum — só o contador de ciclos de self-review e o histórico de timestamps por gate existem de verdade.
- **`JIRA_FA_ALERT_LABEL` é um palpite** (`"fa-alert"`, default) — a label real que a integração de monitoramento FA Alert usa nos cards nunca foi confirmada.
- **Botão de pausa no console não existe** — só a env var `JIRA_POLLER_PAUSED` no servidor. O console mostra o estado mas não tem uma ação pra mudar isso.
- **Console sem autenticação** — aceitável só em rede interna (ver `agent-console/README.md`, "Known gaps").

## Bugs encontrados e corrigidos ao testar de verdade

Vale saber que já apareceram (e foram corrigidos) dois problemas que só um teste real revelou — não apareceriam em nenhum teste unitário:

1. **Corrida no registro do cron do poller**: o registro chamava a própria API do servidor no `startup` do FastAPI, antes do servidor aceitar conexões — falhava sempre. Corrigido com retry em background (`ensure_jira_poller_cron_with_retry` em `agent/jira_poller.py`).
2. **Nomes de coluna dessincronizados**: só 5 das 11 colunas eram configuráveis por env var; as outras 6 estavam fixas em português dentro do prompt, então uma sobrescrita de env var não alcançava o agente. Corrigido — todas as 11 agora fluem do mesmo lugar (`agent/jira_poller.py`) pro prompt.

## Onde ler mais

- `openspec/changes/jira-openspec-coding-agent/proposal.md` — o quê e por quê, resumido.
- `openspec/changes/jira-openspec-coding-agent/design.md` — todas as decisões técnicas com alternativas consideradas.
- `openspec/changes/jira-openspec-coding-agent/tasks.md` — checklist das 85 tarefas, todas marcadas com o que foi feito e qualquer ressalva/correção encontrada no caminho.
- `openspec/changes/jira-openspec-coding-agent/specs/` — os requisitos formais por capability (jira-integration, column-approval-gate, auto-review-loop, agent-console, canonical-docs-update, openspec-workflow).
- `openspec/changes/jira-openspec-coding-agent/exploration/` — o raciocínio bruto antes das decisões finais (7 documentos).
- `docs/JIRA_INTEGRATION.md` — guia operacional: setup do board, todas as env vars, diagrama do workflow, troubleshooting.
- `docs/reference/` — os dois documentos que guiaram a arquitetura original (Playbook + proposta de arquitetura).
