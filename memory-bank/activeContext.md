# Active Context — Foco Atual

## Estado Atual

O sistema está **em produção**. As branches de feature existem e foram trabalhadas pelo agente:

- `feat/spec-SSAI-90-post-clientes-500-nome-numero`
- `feat/spec-SSAI-91-post-clientes-retornando-500`

Ambas têm correspondência remota (`remotes/origin/feat/spec-SSAI-91-...`), indicando fluxo Jira→spec→implementação→PR concluído.

## Mudanças Recentes

- **Workflow Jira + OpenSpec implementado de ponta a ponta** no change `openspec/changes/jira-openspec-coding-agent/` — **84 das 85 tasks marcadas como concluídas** em `tasks.md` (resta 1 pendente).
- O fluxo completo opera com os 3 gates: `Em Revisão de Spec` → `Em Code Review` → `Em Merge`, governados pelas colunas do Jira (`agent/jira_poller.py`).
- O sistema evoluiu para **5 grafos** (agent, reviewer, analyzer, chat, scheduler) e **24 middlewares**, conforme declarado em `langgraph.json` e `agent/middleware/`.

## Próximos Passos

- **Esta iniciativa de documentação em memory bank** — criar a estrutura `memory-bank/` com documentos de contexto global (este conjunto), por agente (`agents/`) e por camada (`camadas/`), mais `opencode.json` e índice no `AGENTS.md`. Planejado no change `openspec/changes/memory-bank-documentacao/`.
- Após a documentação global, seguir para a documentação por agente e por camada (tasks 2.x e 3.x do change).

## Notas de Atenção

- 3 middlewares estão definidos mas **não conectados** à stack do server: `ensure_no_empty_msg`, `SandboxCircuitBreakerMiddleware`, `WorkflowPushGuardMiddleware` (ver `memory-bank/systemPatterns.md`).
- O poller roda a cada 60s por padrão (`JIRA_POLL_INTERVAL_SECONDS`, `agent/jira_poller.py:37`), com intervalo configurável via console (`agent/operational_config.py`).
