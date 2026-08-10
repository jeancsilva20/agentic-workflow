---
name: Open SWE Jira Extension context
description: Decisões e restrições essenciais do projeto Open SWE com integração Jira — ler antes de qualquer trabalho
---

# Open SWE — Jira Extension

**Why:** Este projeto tem documentação de decisão extensa que deve ser consultada antes de qualquer mudança arquitetural. Ignorar isso causa retrabalho.

**How to apply:** Antes de qualquer edição não-trivial, ler:
1. `instruções replit.md` — estado atual, o que falta, bugs já corrigidos
2. `openspec/changes/jira-openspec-coding-agent/design.md` — todas as decisões técnicas com alternativas

## Restrição crítica: dois agent-console incompatíveis
- `agent-console/` dentro deste projeto = implementação correta (usada por `agent/utils/console_events.py` e `agent/jira_poller.py`)
- `agent-console/` na raiz do repositório pai = protótipo antigo, campos diferentes, não conectado a nada
- NUNCA apontar `AGENT_CONSOLE_URL` para o da raiz

## Estado do servidor
- Sobe com `SANDBOX_TYPE=local` (sem deps extras)
- Sem LLM key: sobe mas qualquer chamada de modelo falha
- Sem Jira creds: poller não funciona (creds em `.env.jira.local` na raiz do repo pai)
- Board Jira: projeto `SSAI` em `sensedia.atlassian.net`, 11 colunas

## O que NUNCA foi validado com LLM real
- Fluxo completo pelos 11 PASSOs do board
- Fluxo de PR (abrir draft, self-review, merge)
- Métricas LangSmith (tasks.md §10.1)
