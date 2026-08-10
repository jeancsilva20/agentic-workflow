---
name: Telemetria entre os dois processos
description: Por que o console mantém uma cópia própria dos dados de execução em vez de ler o agente ou um serviço externo
---

O console Flask e o servidor LangGraph são **processos separados**, e o spec do
console diz que ele é display read-only alimentado por eventos empurrados — ele
não pode chamar Jira, LangGraph nem o agente.

**Regra:** dados de execução (uso de tokens, custo, o que está rodando agora)
moram em classes escritas uma única vez do lado do agente; o console instancia
as **mesmas classes** e as preenche com eventos empurrados. Endpoints do console
leem só essa cópia local.

**Why:** importar estado entre processos é impossível; consultar um serviço
externo a cada refresh de página põe latência e credencial dentro do console; um
banco novo duplicaria a fonte durável que o LangSmith já é. Aceita-se que um
restart do console esvazie a janela e que um push perdido custe uma linha.

**How to apply:** ao expor no console algo que o agente sabe, empurre o evento e
escreva a linha do Execution Log **no ingest**, do lado do console — assim
estado e log não podem divergir. Nunca acrescente ao console uma chamada de
saída para outro serviço.

## Duas armadilhas específicas

- **Desconhecido não é zero.** O LangSmith devolve custo `None` para modelos que
  ele não precifica. Custo ausente tem que propagar como `null` até o JSON, com
  a contagem de runs sem custo ao lado; `0.0` seria lido como "rodou de graça".
- **O id de run do LangGraph não é o id de run do LangSmith.** A plataforma cria
  o run; o tracer cria o trace; nenhum dos dois deriva do outro, então ler o
  trace pelo id que o webhook de conclusão entrega falha em silêncio e tudo vira
  "desconhecido". O que liga os dois é metadata: o dispatch carimba um id próprio
  no run e a conclusão procura o trace por ele — no projeto de tracing daquele
  grafo, porque cada grafo escreve em um projeto e a busca no projeto errado não
  acha nada.
- **Instrumentação é do ponto único de criação de run, não do call site.** Se
  cada gatilho (Jira, Slack, GitHub, agendamento) tivesse que montar e passar a
  telemetria, os que esquecerem somem das métricas. A derivação de rota é
  compartilhada com quem monta o grafo, senão a telemetria nomeia um modelo e o
  run usa outro. A unidade de agregação é o **card**, não a thread: um card
  atravessa vários runs HITL em threads diferentes.
