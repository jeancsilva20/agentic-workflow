---
name: Config operacional em runtime (console ↔ poller)
description: Decisões duráveis sobre como o console controla o runtime do agente sem restart — transporte, atomicidade e o cron do poller
---

# Config operacional: console (escreve) ↔ agente (lê)

O console Flask e o servidor LangGraph são processos separados. O console é a fonte de verdade das configurações operacionais; o agente lê o que o operador escolheu.

## Transporte é arquivo no disco, não push HTTP

O agente lê a config do arquivo em tempo de execução, com fallback para env var.

**Why:** o console sempre foi infraestrutura opcional — todo push dele é fire-and-forget justamente para que um console fora do ar nunca atrase nem quebre um run. Poller consultando o console por HTTP a cada tick colocaria o console no caminho crítico.

**How to apply:** vale para qualquer config nova que o console passe a controlar. Um único lado define o caminho do arquivo e o outro importa — duas definições divergem em silêncio. Escrita sempre write-then-rename, porque o leitor pode estar no meio de um tick.

## Persistir e aplicar são um passo só

A mesma trava cobre validação, gravação e efeito colateral no runtime.

**Why:** dois PUTs simultâneos intercalam — arquivo fica com um valor, runtime com outro, e os dois chamadores recebem sucesso. É um estado que ninguém consegue diagnosticar depois.

## Freio ligado por env não isola mais um teste

Shadow mode tem duas fontes e o arquivo ganha da env. Teste de poller precisa apontar o caminho do arquivo para um tmp vazio, senão um console deixado em shadow na máquina de dev inverte o sentido de toda asserção de launch/resume.

## Um cron de poller, sempre — e o preço disso

Trocar o intervalo apaga os crons existentes **antes** de criar o novo: dois crons vivos dobram cada tick (duas buscas no Jira, dois launches por card, conta de modelo dobrada), e a idempotência do poller não existe para absorver isso.

Isso abre uma janela sem cron nenhum. Se a criação falhar ali, o poller **parou** — é um erro de tipo diferente de "não consegui trocar", e precisa ser reportado como parada, não como "seguiu no intervalo anterior". A recuperação é o startup do servidor, que reconcilia: "existe um cron" não basta, o schedule tem que bater com o configurado, senão a config salva vira mentira permanente.

## Falha de efeito colateral não é falha do PUT

O valor já foi persistido quando o cron ou o Store falham. 5xx mentiria dizendo que nada foi salvo; engolir mentiria dizendo que o runtime aceitou. Responder 200 com `warnings` e registrar no log de execução.
