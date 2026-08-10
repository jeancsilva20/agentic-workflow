---
name: Regras duráveis do fluxo Jira → agente → GitHub
description: Invariantes do fluxo de 11 colunas que não se deduzem lendo o código — quem move o card, o que o poller precisa enxergar, e onde archive/docs entram
---

# Fluxo Jira — invariantes

## O JQL de resume tem que cobrir os pós-gate, não só os gates

Um poller que consulta apenas as colunas de gate **nunca vê a decisão humana**: no instante em que a pessoa move o card para fora do gate, ele sai da query. A query de resume precisa listar gates **e** as colunas para as quais o humano move (`Spec Aprovada`, `Ajustar Spec`, `Code Review Aprovado`, `Ajustar Code`, `Mergeado`).

**Why:** esse bug travava o fluxo logo depois do primeiro gate e é invisível em teste que só exercita o gate.

**How to apply:** a idempotência não vem da query e sim de comparar a coluna atual com a coluna onde a thread foi estacionada. Ampliar a query é seguro; mexer nessa comparação não é.

Consequência que morde depois: uma query mais larga traz mais resultados, e a busca do Jira pagina. Ler só a primeira página passa a perder card — os parados no gate (que não geram ação) enchem a página e o card recém-movido fica de fora. Toda query de polling tem que percorrer todas as páginas, com teto e warning ao atingi-lo.

## Freios de operação valem para o tick inteiro

Shadow mode e pause precisam suprimir **launch e resume**. Suprimir só o launch dá uma garantia falsa de "nenhuma ação real" — o resume dispara run, lê comentários e altera metadados.

## Quem move o card

O humano move em exatamente três pontos: sair de `Em Revisão de Spec`, de `Em Code Review` e de `Em Merge`. Todas as outras transições são do agente e automáticas.

O agente **nunca** move para `Code Review Aprovado`, **nunca** move para `Mergeado`, **nunca** faz merge de PR. `Mergeado` é semanticamente "o merge já aconteceu no GitHub".

**How to apply:** cada transição automática é condicionada ao passo ter dado certo (branch remota confirmada, PR criada/atualizada, archive+docs+checks OK, merge confirmado). Falhou → comentar no Jira, não mover, encerrar o turno. Card parado com explicação é recuperável; card que avançou mentindo não é.

## Archive da OpenSpec e docs vão ANTES do merge

Reverte a Decision 6 original do `design.md` (que mandava abrir PR separada de docs depois do merge). `Em Merge` significa "a automação terminou tudo" — trabalho pendente depois do merge contradiz isso e entrega incompleta para quem aprova.

**How to apply:** archive + docs entram na mesma branch/PR, na preparação pós-`Code Review Aprovado`. A fase `Mergeado → Done` é só administrativa, sem alteração funcional na branch.

## `Ajustar Code` tem o GitHub como fonte primária

Comentário do Jira é contexto secundário. Os reviews e comentários da PR no GitHub são a fonte dos ajustes.

## Freio de operação ligado por env quebra teste

Os freios do poller (shadow/pause) vêm do ambiente e um deles costuma estar ligado aqui. Teste de "lança/retoma" que não fixa esses freios falha por configuração, não por regressão — e passa a afirmar o contrário do que o nome dele diz.
