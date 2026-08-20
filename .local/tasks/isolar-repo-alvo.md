# Isolar o repositório alvo do nosso projeto

## What & Why

O fluxo desenhado no prompt está correto: o agente clona `guilhermeallen/sensedia-backend-case`,
cria o branch `feat/spec-{ISSUE}-<slug>`, analisa o código daquele repositório, escreve os
artefatos OpenSpec, dá push naquele repositório e só então move o card para a coluna de
revisão de spec. O projeto do LangGraph é a ferramenta; ele não é o objeto da análise.

**A execução, porém, não respeita essa fronteira.** A raiz do sandbox local não está
definida, então o agente adota o diretório de trabalho do processo — que é a raiz do nosso
próprio projeto. A partir daí tudo desaba em cima de nós:

- O clone do repositório alvo cai dentro do nosso repositório, em `sensedia-backend-case/`.
- Esse caminho não está no nosso `.gitignore`, então os 42 arquivos-fonte do repositório
  alvo estão **commitados no nosso projeto**.
- O diretório não tem `.git` próprio: `git rev-parse --show-toplevel` executado lá dentro
  responde com a raiz do nosso projeto. Ou seja, **todo comando git que o agente roda
  "no repositório alvo" opera no nosso repositório**.
- O relatório do harness, que deveria ficar fora do clone, cai igualmente dentro do
  nosso repositório.

Foi exatamente esse mecanismo que produziu o incidente anterior: um branch de spec criado
no nosso projeto, artefatos de spec commitados aqui e uma árvore `home/runner/workspace/`
aninhada dentro do repositório. O push que falhou com 403 foi o único sinal visível de um
problema que já estava acontecendo em silêncio havia vários cards.

O objetivo desta tarefa é tornar a fronteira explícita e verificável: o agente opera
exclusivamente sobre o repositório alvo, e o nosso projeto passa a ser incapaz de receber
esse conteúdo por acidente.

## Done looks like

- O agente executa um card do início ao fim sem que nada apareça em `git status` do
  nosso projeto.
- O clone do repositório alvo vive fora da árvore do nosso projeto e tem `.git` próprio,
  com `origin` apontando para `guilhermeallen/sensedia-backend-case`.
- O branch `feat/spec-{ISSUE}-<slug>` é criado e existe **apenas** no repositório alvo,
  confirmável pelo remote.
- Nosso repositório não rastreia mais nenhum arquivo do repositório alvo nem saída de
  harness, e passa a ignorá-los.
- Se por qualquer motivo o diretório de trabalho resolver para dentro do nosso projeto,
  o run falha imediatamente com uma mensagem explícita, em vez de escrever aqui.
- O card só se move para a coluna de revisão de spec depois que o branch é confirmado
  no remote do repositório alvo.

## Out of scope

- Alterar o desenho do fluxo de colunas ou os gates de aprovação — o fluxo está correto,
  o que muda é onde ele executa.
- Implementar as fases posteriores à spec (implementação, code review, merge).
- Resolver as permissões do token no GitHub — o acesso de escrita já foi concedido.

## Steps

1. **Definir uma raiz de sandbox fora do projeto.** Estabelecer um diretório de trabalho
   dedicado, fora da árvore do nosso repositório, e garantir que o sandbox local o use
   sempre, em vez de herdar o diretório do processo servidor.

2. **Falhar rápido quando a fronteira for violada.** Na inicialização do sandbox, recusar
   qualquer diretório de trabalho que esteja dentro do nosso repositório, com mensagem
   nomeando o caminho recusado. Um run que não consegue se isolar deve parar, não seguir
   escrevendo no lugar errado.

3. **Limpar a contaminação existente.** Remover do rastreamento do nosso git os arquivos
   do repositório alvo e qualquer saída de harness, e adicionar as entradas
   correspondentes ao nosso `.gitignore`. O conteúdo em si não se perde: ele pertence ao
   repositório alvo, de onde é clonado.

4. **Garantir que o clone seja um repositório de verdade.** Antes de qualquer operação
   git da fase de spec, verificar que o diretório do repositório alvo tem `.git` próprio
   e que `origin` aponta para o repositório alvo esperado. Se não tiver, clonar; se
   apontar para outro lugar, abortar o run.

5. **Amarrar as operações git ao diretório do repositório alvo.** Assegurar que branch,
   commit, push e as verificações de remote sejam executados com o diretório do
   repositório alvo explícito, de modo que nunca dependam do diretório corrente do shell.

6. **Validar com um card real.** Rodar um card do início ao fim e conferir os dois lados:
   o branch e os artefatos presentes no repositório alvo, e o nosso projeto intocado.

## Relevant files

- `agent/integrations/local.py`
- `agent/utils/sandbox.py`
- `agent/utils/sandbox_paths.py`
- `agent/utils/repo_prep.py`
- `agent/middleware/workflow_push_guard.py`
- `agent/prompt.py:150-166,200-238`
- `agent/jira_poller.py`
- `agent/server.py:215-228`
- `.gitignore`
