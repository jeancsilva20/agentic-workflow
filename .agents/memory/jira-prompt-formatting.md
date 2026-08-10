---
name: Armadilha de .format nas seções do prompt Jira
description: Por que uma chave nova entre chaves no texto do prompt Jira estoura em runtime, e o que fazer no lugar
---

# Seções do prompt Jira passam por `.format(**kwargs)`

As seções do fluxo Jira no prompt são templates renderizados com um dicionário **fixo** (a chave
da issue e os nomes das colunas). Qualquer `{outra_coisa}` que alguém escreva no meio do texto
vira um `KeyError` em runtime — não em import, não em lint, e não necessariamente no teste que
você rodou.

**Why:** escrevi `{working_dir}` numa instrução nova porque outra seção do prompt usa esse
placeholder; só que aquela seção é renderizada em outro ponto, com outro dicionário.

**How to apply:** ao editar esses textos, use só os placeholders que já aparecem na própria
seção. Para qualquer outro valor, escreva em prosa (`<working_dir>/...`). O mesmo vale para
chaves literais em exemplos de JSON dentro dessas strings — precisam ser duplicadas.
