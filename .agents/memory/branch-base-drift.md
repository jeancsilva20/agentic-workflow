---
name: Base errada de branch parece regressão
description: Quando funcionalidades "somem" do app rodando, checar a base do branch antes de depurar código
---

# Base errada de branch parece regressão

Quando o app rodando aparenta ter perdido funcionalidades, **cheque a base do branch
antes de investigar o código**:

```
git branch --show-current
git merge-base HEAD main
git diff main HEAD --stat
```

Um branch criado a partir do commit errado é indistinguível de uma regressão pela
interface: a página simplesmente renderiza uma versão antiga. A diferença aparece no
`--stat`, na forma de um número absurdo de deleções.

**Why:** um branch de spec foi criado a partir do "first commit" em vez do `main`,
ficando ~11 horas atrás. O diff acusava 208 arquivos e 27.558 deleções — módulos
inteiros, testes e metade do template do console. Sem checar a base, o diagnóstico
natural é "alguém quebrou o front", e o reflexo é reimplementar o que sumiu.

**O agravante:** todas as "correções" feitas em cima dessa base já existiam no `main`
— autenticação de git, endpoint de busca do Jira, variáveis de ambiente, script de
post-merge. Horas de trabalho reimplementando o que não estava quebrado, porque o que
estava quebrado era a base, não o código.

**Sintoma secundário útil:** erros de runtime que não batem com o código que você está
lendo. Se o arquivo em disco parece correto mas o processo erra como se fosse outra
versão, ou o processo precisa de restart, ou você está lendo um arquivo de um branch
diferente do que gerou o processo.

**How to apply:** ao receber "o sistema perdeu funcionalidade X" ou "voltou uma versão
antiga", o primeiro comando é `git merge-base HEAD main`, não a leitura do código. Se
a base não for o `main` esperado, pare: o conserto é reposicionar o branch, e qualquer
correção feita antes disso provavelmente é redundante.
