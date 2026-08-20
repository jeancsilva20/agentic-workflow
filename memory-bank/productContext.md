# Product Context — Por que este projeto existe

## O Problema

Engenheiros gastam tempo significativo em tarefas repetitivas e mecânicas do ciclo de desenvolvimento: interpretar um card, redigir a especificação, implementar, rodar verificações, abrir o PR. Esse trabalho é determinístico o bastante para ser delegado a um agente, mas hoje consome horas humanas.

## A Solução

Um **coding agent interno** que executa o ciclo de desenvolvimento de ponta a ponta — do card do Jira ao PR aberto — enquanto **mantém humanos no controle em 3 checkpoints** de aprovação. O agente faz o trabalho pesado; os humanos revisam e aprovam.

Isso reduz o custo de tarefas repetitivas e padroniza o processo via **Spec-Driven Development** (spec primeiro, código depois), com gates explícitos que impedem avanço sem revisão humana.

## Os 3 Checkpoints Humanos

1. **Em Revisão de Spec** — humano valida a proposta/spec antes de qualquer código.
2. **Em Code Review** — humano revisa o código implementado contra a spec.
3. **Em Merge** — humano aprova o merge final.

O agente **pausa** o card nessas colunas e só continua após a transição manual no Jira (o poller detecta a mudança e retoma).

## Casos de Uso

| Origem | Descrição |
|---|---|
| **Jira (primário)** | Poller monitora colunas e despacha runs conforme o card avança pelos gates |
| **Slack** | Mensagens em thread disparam/continuam runs; o agente responde no canal |
| **Linear** | Issues e comentários disparam runs; o agente comenta na issue |
| **GitHub (PR comments)** | Comentários em PR disparam runs; auto-review em `opened` / `ready-for-review` |

## Como o Ciclo Funciona

```
Card no Jira → poller (60s) → dispatch → agente (spec → implementa → PR)
        ↑                                              │
        └── humano aprova (transição de coluna) ←──────┘
```

- O poller (`agent/jira_poller.py:436`) varre o Jira a cada 60s (`JIRA_POLL_INTERVAL_SECONDS`, `jira_poller.py:37`).
- Cada run é despachada via `agent/dispatch.py:189` (`dispatch_agent_run`).
- Ao concluir, o webhook de completion (`agent/completion.py:196`, rota `/webhooks/run-complete` em `agent/api/health.py:17`) garante que todo run termine com um sinal — fechando o ciclo.

## Valor para a Sensedia

- Automação do ciclo de desenvolvimento com supervisão humana obrigatória.
- Padronização via SDD/OpenSpec em todos os repos.
- Engenheiros focam em revisão e decisões de produto, não em mecânica.
