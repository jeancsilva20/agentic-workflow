---
name: Roteamento de modelo por papel
description: Por que modelo/effort deixaram de ser configuráveis e o que ainda parece configuração mas é só display
---

Modelo e reasoning effort são decididos pelo papel do agente, nunca por
configuração. Não existe override: nem console, nem perfil do dashboard, nem
chave por thread, nem team default. Um pedido de "deixar o operador escolher o
modelo" contraria o requisito, não é uma lacuna a preencher.

**Why:** antes disso a última camada que escrevesse ganhava, então todo passo do
fluxo Jira rodava no mesmo modelo — caro demais para mover um card, fraco demais
para revisar uma spec. Centralizar no papel foi o pré-requisito de observabilidade
(dá para atribuir custo por papel) e de execução multi-modelo correta.

**How to apply:** ao adicionar um passo que faz chamada de LLM, crie o papel no
enum e uma linha na tabela de rotas; não leia modelo de config nem aceite
parâmetro. Se um papel não estiver na tabela, a resolução estoura na primeira
chamada — é proposital.

## Armadilhas que já custaram tempo

- **Effort não é universal.** Cada modelo publica a própria lista no catálogo e
  rejeita o resto em tempo de request. A regra é derrubar o effort (mandar
  nenhum), nunca substituir por outro nível: um papel que pediu `high` e recebeu
  `low` calado é uma decisão que ninguém tomou.
- **Papéis Haiku não mandam effort algum** (`None`, não a string `"none"`) —
  raciocínio extra é cobrado em toda chamada e não compra nada em triagem.
- **Complexidade é aritmética determinística**, sem chamada de LLM: pedir para um
  modelo julgar dificuldade antes de escolher o modelo é circular e gasta uma
  chamada em toda decisão.
- **Tier é `Enum` com comparação explícita.** Ordenação de string colocaria
  "critical" abaixo de "low", e o roteador compara `tier >= HIGH` o tempo todo.
- **Subagente compartilha a rota do pai.** Subagente mais fraco produz saída que
  o pai depois precisa desconfiar.
- **Sobrou aparência de configuração**: o dashboard ainda tem seletor de modelo
  no perfil. Isso é só exibição — não chega ao `configurable` nem escolhe nada.
  Antes de "consertar" um valor estranho ali, confira se ele influencia execução.
- **Validação de imagem tem que usar o modelo roteado.** O `model` gravado no
  metadata da thread é o par que a execução vai receber, justamente porque o
  422 de imagem e o middleware de fila leem dali. Validar contra a escolha do
  perfil deixava o usuário mandar imagem para um modelo que não lê imagem (e o
  "fallback de visão" que existia trocava um modelo que já não decidia nada).
- **O papel vem da coluna Jira em que o poller retomou o card**, não de um nó do
  grafo: o fluxo é um deep agent só, então o modelo é escolhido uma vez por
  despacho e cada segmento é roteado pela fase mais exigente que ele cobre.
  Execução sem coluna (dashboard, Slack, Linear, comentário de PR) é coding.
- **Toda entrada de LLM é rota, não só o fluxo Jira.** Chat de review de PR e
  analyzer de estilo também têm papel; um id de modelo constante no factory do
  grafo continua sendo escolha fora do roteador. Existe teste que varre o
  código atrás de chave de override por request/perfil/team e de `make_model`
  em módulo que não chama `resolve_model` — papel novo sem rota quebra ali.
- **Nem todo papel do enum é alcançável.** Fases que acontecem dentro da execução
  de outro papel não são selecionadas por ninguém; a tabela marca `active` e
  `selected_by` para não passar por rota viva. Papel novo sem call site é isso,
  não bug.
