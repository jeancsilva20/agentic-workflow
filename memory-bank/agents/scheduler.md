# Orquestrador de Cron (`scheduler`)

Arquivo-fonte: `agent/scheduler.py` — factory `get_scheduler` (linha 38).

## Objetivo

Entrypoint LangGraph que transforma ticks de cron em ações: lança runs agendados, executa o tick do poller Jira ou uma varredura de reconciliação.

## Intenção

Orquestrador **procedural** (StateGraph de 2 nós: `START → launch → END`, scheduler.py:39-42), não um deep agent. Não possui modelo próprio nem ferramentas.

## Resultado

Dicionário `result` conforme a tarefa executada: `reconcile_stale_runs`, `jira_poller_tick` ou `launch_scheduled_agent_run`.

## Fluxo de Entrada/Saída

- **Entrada**: `SchedulerState` (`schedule_id`, `task`, `result` — scheduler.py:18-21) + `config.task`.
- **Saída**: dicionário `result` correspondente à tarefa.

## Conexões

Host do cron do poller Jira (`ensure_jira_poller_cron`). Chama `reconcile_stale_runs` (de `agent/reconcile.py`), `jira_poller_tick` (de `agent/jira_poller.py`) e `launch_scheduled_agent_run` (de `agent/dashboard/schedules.py`).

## Ferramentas

Nenhuma — não é um deep agent. Sem middleware e sem modelo próprio.
