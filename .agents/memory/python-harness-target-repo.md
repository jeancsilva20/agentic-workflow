---
name: Harness Python e a realidade do repo alvo
description: Por que o harness distingue "não existe suíte" de "comando de teste ambíguo", e o que o repositório alvo do case realmente tem
---

# Harness Python — o corte que importa

## "Sem suíte" não é bloqueio; "comando ambíguo" é

O harness só pode parar o run e perguntar quando **existem** testes e nenhum candidato de comando
é comprovadamente seguro (vários plausíveis, ou o único candidato bate em banco/serviço real).
Quando simplesmente **não há suíte alguma**, o harness completa, registra a ausência como risco e
deixa a proposta sugerir a baseline mínima.

**Why:** o repositório alvo do case não tem nenhum teste. Uma regra do tipo "sem comando de teste
→ HARNESS BLOCKED" trava todo run nele logo no passo 2.5, antes de qualquer spec — o agente ficaria
perguntando algo que a própria change deveria resolver.

**How to apply:** ao mexer no texto do harness, manter os dois casos separados e explícitos. O
mesmo corte vale para linter e CI ausentes: reportar como risco e propor, nunca instalar
silenciosamente um stack que o projeto não declarou.

## O repo alvo do case (perfil confirmado por inspeção)

FastAPI + SQLAlchemy + Alembic + Pydantic v2 + psycopg2 + Uvicorn, camadas
`app/{routers,services,repositories,schemas,models,core}`. Mas: **sem `pyproject.toml`, sem
Makefile, sem docker-compose, sem CI, sem linter, sem um único teste**. Dependências em
`requirements.txt` (pip, tudo pinado). Os comandos reais de subir e migrar só existem no
`start.sh` (`alembic upgrade head` + `uvicorn app.main:app`), e o deploy está no `render.yaml`.

**How to apply:** qualquer heurística de detecção que comece por `pyproject.toml`/Makefile acha
nada nesse repo. A busca de comandos precisa incluir scripts de start e manifests de deploy —
num projeto assim, é o `start.sh` que é a fonte de verdade.
