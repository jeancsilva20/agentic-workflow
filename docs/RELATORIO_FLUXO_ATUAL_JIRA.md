# Relatório do fluxo atual — Open SWE disparado pelo Jira

**Data da análise:** 10 de agosto de 2026  
**Escopo:** comportamento atualmente implementado e observado no ambiente Replit  
**Objetivo:** explicar por que o card `SSAI-88` aparece no execution log, mas o agente não começa a trabalhar.

> Este relatório é descritivo. Nenhuma alteração de comportamento foi feita durante esta análise.

---

## 1. Diagnóstico executivo

O sistema está funcionando até a etapa de leitura do Jira, mas está configurado em **shadow mode**.

O log observado contém esta sequência:

1. O cron do LangGraph executa o graph `scheduler`.
2. O scheduler chama o `jira_poller`.
3. O poller consulta o Jira usando `POST /rest/api/3/search/jql`.
4. O Jira responde `200 OK`.
5. O card `SSAI-88` é encontrado em `BACKLOG`.
6. O poller calcula o ID determinístico da thread e verifica se ela já existe.
7. Como não encontra uma thread com metadados correspondentes, registra:

   ```text
   Jira poller [shadow]: would launch thread for SSAI-88 (human_filed=True)
   ```

8. O poller envia apenas um evento de log para o Agent Console.
9. O poller **não cria a thread**, **não dispara o graph `agent`** e **não chama o LLM**.

Portanto, o comportamento atual é intencional para o modo de teste: o sistema observa o card e simula o que faria, mas não executa o agente.

### Evidências atuais

- A consulta Jira aparece com `HTTP/1.1 200 OK`.
- O log registra `Jira poller [shadow]: would launch thread for SSAI-88`.
- O mesmo card aparece novamente nos ticks seguintes, pois nenhuma thread é criada no shadow mode.
- O Agent Console recebe `POST /api/events/log` e `POST /api/events/tick` com `200 OK`.
- O cron do Jira está registrado e executando aproximadamente a cada minuto.
- O LangGraph Server e o Agent Console estão em execução.

O `404` observado ao consultar uma thread antiga também é compatível com esse cenário: a thread não existe no armazenamento atual, e o shadow mode impede que ela seja criada.

---

## 2. Componentes em execução

### 2.1 LangGraph Server

Workflow configurado:

```text
bash scripts/start-dev-server.sh
```

Responsabilidades:

- hospedar os graphs LangGraph;
- expor a API local em `0.0.0.0:8000`;
- executar crons;
- carregar os graphs `agent`, `reviewer`, `analyzer`, `chat` e `scheduler`;
- receber e despachar runs;
- servir as APIs do dashboard e do Agent Console via eventos internos.

O servidor está inicializando corretamente e registra no log:

```text
Application started up
Starting cron scheduler
Starting 1 background workers
```

### 2.2 Scheduler graph

O graph `scheduler` é uma pequena camada de roteamento. Ele recebe uma tarefa e escolhe o que executar:

- `jira_poll` → executa o tick do poller Jira;
- `reconcile` → reconcilia runs antigos;
- `schedule_id` → executa um agente agendado.

O cron do Jira é criado com metadados equivalentes a:

```json
{"kind": "jira_poller"}
```

Com o intervalo padrão de 60 segundos, o cron usa a expressão de um minuto:

```text
* * * * *
```

### 2.3 Jira Poller

Arquivo principal:

```text
agent/jira_poller.py
```

O poller executa duas etapas a cada tick:

- **Etapa A:** procura cards novos na coluna de gatilho e, em condições normais, inicia threads;
- **Etapa B:** procura cards parados em gates de aprovação e retoma threads quando a coluna muda.

### 2.4 Agent Console

Workflow configurado:

```text
cd agent-console && pip install -r requirements.txt -q && python app.py
```

O console Flask roda na porta `5050`.

Ele é somente observacional neste fluxo:

- mostra saúde do poller;
- mostra eventos de tick;
- mostra eventos de execução;
- mostra runs ativos, parados ou mortos;
- não é responsável por iniciar o agente;
- não possui botão para desligar o shadow mode ou liberar execuções.

O poller envia eventos para ele usando `AGENT_CONSOLE_URL`.

---

## 3. Configuração Jira atualmente usada

Valores padrão definidos pelo código:

| Configuração | Valor atual/padrão | Efeito |
|---|---:|---|
| Projeto | `SSAI` | Restringe as consultas ao projeto SSAI |
| Coluna de gatilho | `BACKLOG` | Card nessa coluna pode iniciar um agente |
| Intervalo | `60` segundos | Cron de aproximadamente um minuto |
| Endpoint de busca | `/rest/api/3/search/jql` | Endpoint novo exigido pelo Jira |
| Shadow mode | **Ativo no processo atual** | Registra o que faria, sem executar |
| Poller pausado | Não determinável apenas pelo log; não é necessário para explicar o bloqueio | Shadow mode já impede a execução |
| Label FA Alert | `fa-alert` por padrão | Usada apenas para classificar o card no log como humano/automação |

A classificação de `SSAI-88` como `human_filed=True` significa apenas que o card não possui a label configurada como `fa-alert`. Isso não é uma autorização extra para executar o card.

### Consultas executadas

#### Cards novos

O JQL construído é equivalente a:

```jql
project = SSAI AND status = "BACKLOG"
```

Se `JIRA_TRIGGER_JQL_FILTER` estiver definido, ele é adicionado como filtro extra.

#### Cards estacionados em gates

O JQL construído é equivalente a:

```jql
project = SSAI AND status in (
  "Em Revisão de Spec",
  "Em Code Review",
  "Em Merge"
)
```

A busca atual usa limite de 50 cards por consulta.

---

## 4. Fluxo de um card novo

### Etapa 0 — Card entra em `BACKLOG`

O modelo atual usa a movimentação para `BACKLOG` como gatilho. Não existe, por padrão, uma validação adicional de tipo, responsável ou intenção do card.

Se for necessário restringir o gatilho, o sistema suporta `JIRA_TRIGGER_JQL_FILTER`, por exemplo por tipo ou label.

### Etapa 1 — Poller consulta o Jira

A cada tick, o poller busca cards com status `BACKLOG`.

Se a busca falhar, ele:

- registra um warning;
- retorna erro para o resultado do tick;
- não inicia nenhum agente nessa etapa.

No estado observado, a busca funciona com `200 OK`.

### Etapa 2 — Poller calcula a thread determinística

Para cada card, o sistema gera um ID de thread a partir da chave do Jira, como `SSAI-88`.

O objetivo é permitir que ticks repetidos encontrem a mesma thread em vez de criar execuções duplicadas.

### Etapa 3 — Verificação de idempotência

O poller consulta os metadados da thread.

- Se a thread existir, o card é contado como `skipped` e não é disparado novamente.
- Se a thread não existir, o card é elegível para uma nova execução.

No caso de `SSAI-88`, o log mostra que a thread consultada não foi encontrada e o sistema chega ao ponto em que normalmente faria o launch.

### Etapa 4 — Shadow mode ou bloqueio de execução

A ordem atual é:

1. verificar shadow mode;
2. se shadow mode estiver ativo, registrar `would launch` e sair dessa parte;
3. somente se shadow mode estiver desligado, verificar `JIRA_POLLER_PAUSED`;
4. somente se ambos permitirem, criar a thread e disparar o agente.

Assim, no ambiente atual:

```text
SSAI-88 encontrado
  → thread não encontrada
  → shadow mode ativo
  → registra evento
  → não cria thread
  → não chama dispatch_agent_run
  → não chama o graph agent
  → não chama o LLM
```

### Etapa 5 — Criação e dispatch em modo normal

Se o shadow mode estiver desligado e o poller não estiver pausado, ele faria:

1. `client.threads.create(...)` com metadados:

   ```json
   {
     "jira_issue_key": "SSAI-88",
     "source": "jira",
     "jira_human_filed": true
   }
   ```

2. `dispatch_agent_run(...)` no thread determinístico;
3. envio de uma mensagem inicial ao graph `agent`:

   ```text
   Jira issue SSAI-88 entered BACKLOG. Begin PASSO 1: collect context
   (issue, description, acceptance criteria, comments).
   ```

4. envio de um evento `launched` ao Agent Console.

O dispatch usa as garantias de execução durável do projeto:

- `multitask_strategy="interrupt"`;
- `durability="sync"`;
- `stream_resumable=True`;
- webhook de conclusão somente quando configurado com URL pública e segredo válidos.

---

## 5. Fluxo total do agente após o launch

O fluxo abaixo é o planejado e implementado no prompt/integracão Jira. Ele só começa depois que a Etapa 5 acima realmente cria e dispara o run.

### PASSO 1 — Coletar contexto

O agente usa a chave Jira para consultar:

- título e descrição do card;
- critérios de aceitação;
- comentários recentes;
- status e contexto do card;
- informações necessárias para identificar o repositório.

### PASSO 2 — Preparar o ambiente

O agente prepara o sandbox:

- identifica ou clona o repositório;
- cria uma branch relacionada ao card;
- carrega as instruções do repositório;
- prepara o contexto de trabalho.

A sandbox atualmente configurada como padrão de desenvolvimento é `local`, que não oferece isolamento real. Ela serve para validar subida do servidor, mas não é a opção adequada para execução de agente com comandos não confiáveis.

### PASSO 3 — Analisar o código e gerar OpenSpec

O agente entra em modo de planejamento e analisa o repositório.

A camada OpenSpec deve produzir artefatos como:

```text
proposal.md
design.md
specs/*.md
tasks.md
```

### PASSO 4 — Fazer auto-review da especificação

O agente revisa a especificação e tenta corrigir lacunas. A orientação prevê aproximadamente três ciclos, mas isso é uma orientação de prompt, não uma garantia rígida do runtime.

Ao concluir ou esgotar a revisão, o agente:

- comenta o resultado no Jira;
- move o card para `Em Revisão de Spec`;
- marca a thread como estacionada;
- encerra o run sem ficar bloqueado esperando a pessoa.

### Gate 1 — Aprovação da especificação

A aprovação é feita movendo o card no Jira:

- `Spec Aprovada` → continua para implementação;
- `Ajustar Spec` → retorna à análise da especificação com os comentários humanos.

O poller só percebe essa mudança no próximo tick.

### PASSO 5 — Implementar

Depois da aprovação, o agente:

- sai do modo de planejamento;
- implementa os itens de `tasks.md`;
- executa testes e validações apropriados;
- faz commit das alterações.

### PASSO 6 — Fazer auto-review do código

O agente revisa as próprias alterações e corrige problemas encontrados, seguindo a mesma ideia de ciclos limitados.

### PASSO 7 — Reviewer graph

O reviewer automatizado analisa a alteração, normalmente usando uma PR existente ou draft PR para obter o diff.

- `PASS` → segue para o gate de code review;
- `CHANGES_REQUIRED` → retorna à implementação.

### Gate 2 — Aprovação do código

O agente estaciona o card em `Em Code Review` e encerra o run.

A pessoa move o card para:

- `Code Review Aprovado` → continua para finalização da PR;
- `Ajustar Code` → volta para implementação com o feedback.

### PASSO 8 — Testes finais e PR

O agente executa os testes finais, faz push e finaliza a PR, normalmente retirando o status draft conforme o fluxo previsto. Em seguida move o card para `Em Merge`.

### Gate 3 — Aprovação do merge

A pessoa faz o merge no GitHub e move o card para `Mergeado`.

O poller detecta a mudança no próximo tick e retoma a thread.

### PASSO 9 — Arquivar OpenSpec

O agente arquiva os artefatos OpenSpec associados ao card.

### PASSO 10 — Atualizar documentação canônica

O agente tenta atualizar a documentação canônica em uma PR separada. Essa atualização é best-effort e não deve bloquear a conclusão principal.

### PASSO 11 — Finalizar

O agente:

- comenta o resultado final no Jira;
- move o card para `Done`;
- registra metadados/métricas de execução quando disponíveis.

---

## 6. Fluxo de retomada depois de uma aprovação

A Etapa B do poller busca cards nas três colunas de gate:

- `Em Revisão de Spec`;
- `Em Code Review`;
- `Em Merge`.

Para cada card, o poller verifica:

1. se existe uma thread correspondente;
2. se os metadados indicam `jira_parked=True`;
3. qual era a coluna em que o agente estacionou (`jira_parked_column`);
4. se a coluna atual mudou.

Se a coluna não mudou, o card permanece `unchanged`.

Se mudou e o poller não estiver pausado, ele:

1. busca os últimos comentários do Jira;
2. monta uma mensagem de retomada;
3. chama `dispatch_agent_run` na mesma thread;
4. atualiza os metadados para remover o estado estacionado;
5. envia um evento `resumed` ao Agent Console.

A retomada não acontece instantaneamente: depende do próximo tick, normalmente em até aproximadamente 60 segundos.

---

## 7. O que acontece atualmente com `SSAI-88`

Com base nos logs observados, o estado atual é:

```text
Jira API: funcionando
Busca de BACKLOG: funcionando
Card SSAI-88: encontrado
Classificação: human_filed=True
Thread correspondente: não encontrada no armazenamento atual
Shadow mode: ativo
Criação de thread: não executada
Dispatch para graph agent: não executado
Chamada ao LLM: não executada
Evento no console: executado
Próximo tick: encontra o card novamente
```

Por isso o execution log pode dar a impressão de que o agente encontrou o card e deveria estar trabalhando. Na realidade, a mensagem `would launch` significa literalmente “lançaria”, não “lançou”.

---

## 8. O que precisa ser decidido antes de liberar a execução real

Este relatório não aplica essas mudanças; são pontos para revisão:

1. **Desligar ou manter o shadow mode**
   - Desligado: cards elegíveis poderão criar threads e chamar o LLM.
   - Mantido: o sistema continuará apenas observando.

2. **Manter `BACKLOG` como gatilho amplo ou restringir o JQL**
   - Atualmente qualquer card `SSAI` em `BACKLOG` é candidato.
   - Pode ser necessário filtrar por tipo, label, responsável ou outro critério.

3. **Definir o sandbox de execução real**
   - `local` executa comandos no host do workflow e não é isolamento adequado.
   - Para execução real, avaliar LangSmith, Daytona, Modal, E2B ou outro backend suportado.

4. **Confirmar o repositório que o agente deve trabalhar**
   - O card precisa fornecer ou herdar um repositório válido.
   - Sem GitHub App/configuração de acesso, a etapa de clone/PR não será concluída.

5. **Confirmar o comportamento de aprovação**
   - O agente encerra nos gates e espera o movimento humano do card.
   - O board precisa permitir as transições globais necessárias.

6. **Definir quando usar Haiku e quando usar Sonnet**
   - Atualmente o default configurado é Haiku `anthropic:claude-haiku-4-5-20251001` com esforço `low`.
   - Sonnet `anthropic:claude-sonnet-5` está disponível, mas não é selecionado automaticamente.

---

## 9. Resumo em uma frase

O sistema atualmente está **monitorando o Jira em modo seguro**, encontrou `SSAI-88`, registrou que o iniciaria, mas não fez isso porque `JIRA_POLLER_SHADOW_MODE` está ativo; nenhuma thread ou chamada ao LLM foi criada para esse card.
