---
name: OpenSpec vendorizado e portado
description: Por que as skills OpenSpec servidas ao agente são ports e não cópias do upstream, e o que o script de sync pode e não pode tocar
---

# OpenSpec: vendor pinado, skills portadas

## As skills servidas ao agente NÃO são as do upstream

Toda skill oficial do `Fission-AI/OpenSpec` declara `compatibility: Requires openspec CLI` e
dirige comandos (`openspec status`, `openspec instructions`, `openspec archive`). Não existe
binário `openspec` no sandbox, e não existe usuário síncrono para responder aos prompts
interativos que essas skills fazem — a issue do Jira é que nomeia a change.

**Why:** copiar o upstream direto para dentro do diretório servido ao agente quebra o agente em
toda sincronização, de forma silenciosa: a skill continua legível, só que manda rodar um comando
que não existe.

**How to apply:** o script de sync grava cópias pristinas em um diretório de vendor e **nunca**
sobrescreve as skills portadas. Depois de sincronizar, a reconciliação é manual: diff do arquivo
vendorizado contra o port e decisão humana sobre o que trazer. Cada port carrega no frontmatter
de onde veio e por que divergiu.

## Nada busca OpenSpec em tempo de execução

A proveniência (source, version, commit, data, arquivos) fica num manifesto versionado, escrito
pelo script. O script exige `--commit` com SHA completo e falha ruidosamente sem ele.

**Why:** sem pin, duas execuções do mesmo card podem seguir instruções diferentes e nada no
histórico explica a diferença. O manifesto é o rastro de auditoria de qual revisão guiou um run.

## Os três gates de SDD são de prompt/doc, não estruturais

Nada no runtime impede o agente de pular a spec. As regras vivem no `AGENTS.md` ("SDD Mandatory
Gates") e no system prompt, e são condicionadas ao passo ter dado certo de verdade (artefatos
commitados **e** empurrados; verificação sem CRITICAL aberto; archive concluído e empurrado).

Como o contrato é texto, a suíte de contrato SDD assere o texto: cabeçalhos das seções de gate,
a formulação negativa, os nomes das skills e as chaves do config. Mexer na redação de um gate ou
renomear uma seção quebra esses testes de propósito — eles são a única coisa que percebe que uma
trava sumiu. Ao reformular, atualize a assertiva junto, nunca afrouxe para "passar".

**How to apply:** ao mexer nesses textos, manter a formulação negativa ("MUST NOT call
`jira_park_at_gate` para X até Y") — ela é o que dá para checar depois lendo o log do run. A
observabilidade dos quatro checkpoints do ciclo (versão carregada, proposta gerada, verificação
passou, arquivado) é log de console fire-and-forget: serve para enxergar desvio, não para barrar.
