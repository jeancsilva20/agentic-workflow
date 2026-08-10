---
name: Fronteira entre o Open SWE e o repositório alvo
description: Por que a raiz do sandbox local nunca pode cair dentro do nosso checkout, e o que verificar antes de qualquer git da fase de spec
---

# A raiz do sandbox é a fronteira

No provider `local` não existe isolamento: a raiz do sandbox *é* a única coisa que separa
o Open SWE (a ferramenta) do repositório que o agente analisa (o objeto). Se a raiz cair
dentro do nosso checkout, o clone do repositório alvo vira um diretório comum sem `.git`
próprio — e aí **todo** `git` "dentro do alvo" sobe a árvore e opera no nosso repositório:
branch de spec, commits de artefatos e relatórios de harness aparecem aqui, e só o push
falhando dá algum sinal.

**Regra:** a raiz nunca pode ser herdada do diretório do processo servidor. Um default
fora da árvore (home) mais uma recusa explícita para qualquer caminho dentro do projeto —
falhar nomeando o caminho recusado, em vez de escolher outro candidato em silêncio.

**Why:** o modo de falha é silencioso e cumulativo. Cards inteiros rodaram "com sucesso"
escrevendo no repositório errado; o erro visível (403 no push) apareceu vários cards depois
da contaminação começar. Um run que não consegue se isolar tem que parar.

**How to apply:** ao mexer em resolução de diretório de trabalho, criação de sandbox ou
qualquer coisa que decida "onde o agente trabalha", aplicar a recusa nos dois pontos — na
criação do sandbox e na resolução do work dir. Nenhum fallback pode voltar a usar o cwd.

# O clone tem que ser um repositório de verdade

Existir um diretório com o nome do repositório alvo não prova nada. Antes da primeira
operação git da fase de spec, verificar deterministicamente, no servidor (não confiando no
modelo): o diretório tem `.git` próprio (o toplevel resolvido é ele mesmo) e o `origin`
normaliza para o `owner/name` esperado. Ausente → clonar; apontando para outro lugar →
abortar o run.

Um diretório sem `.git` próprio na raiz do sandbox pode ser removido e re-clonado: o
conteúdo pertence ao repositório alvo. Esse é exatamente o estado que produz a
contaminação, então "reparar" é mais seguro do que seguir em frente.

**Armadilha do `gh` no provider local:** ali o `GH_TOKEN` do ambiente já carrega o PAT real
(mais auth via `GIT_CONFIG_*`). Prefixar o clone com `GH_TOKEN=dummy` — padrão dos sandboxes
com proxy — quebra o clone no local.

# No prompt, git sempre nomeia o diretório

As operações de git da fase de spec usam `git -C <repo_dir>`, nunca o diretório corrente do
shell. Saída que não é artefato de spec (relatório de harness, rascunho) vai para o work dir,
fora do clone. O parser do guard de push já entende `git -C <dir> push`, então trocar o
prompt para `-C` não quebra a aprovação de workflow.
