# Fluxo Jira: agente autônomo e Human-in-the-Loop

## Objetivo

Este documento descreve o fluxo completo de uma demanda Jira processada pelo
agente Open SWE, estendido para trabalhar com Jira, OpenSpec e GitHub.

O fluxo combina:

- **Execução agêntica:** o agente lê contexto, analisa código, escreve a
  especificação, implementa, testa, cria/atualiza o Pull Request e prepara a
  entrega.
- **Human-in-the-Loop (HITL):** uma pessoa aprova a especificação, aprova ou
  solicita ajustes no código e faz o merge do Pull Request.
- **Poller:** um processo observa as mudanças de status no Jira e retoma a
  mesma execução quando uma decisão humana é registrada.

O agente **não fica bloqueado esperando**. Ao chegar a um gate, ele comenta no
card, estaciona o card na coluna correspondente e encerra a execução. O poller
retoma a mesma thread depois que uma pessoa move o card para a próxima etapa.

---

## Visão geral do fluxo

```text
BACKLOG
  │
  │ Poller detecta o card
  ▼
[Agente] Coleta contexto, prepara o sandbox e cria a OpenSpec
  │
  ▼
Em Revisão de Spec ─────────────── Gate 1
  │                                  │
  │ pessoa aprova                    │ pessoa pede ajustes
  ▼                                  ▼
Spec Aprovada                    Ajustar Spec
  │                                  │
  └───────────────┬──────────────────┘
                  │ agente revisa ou implementa
                  ▼
            In Progress
                  │
                  │ implementação, testes, PR e reviewer graph
                  ▼
Em Code Review ─────────────────── Gate 2
  │                                  │
  │ pessoa aprova                    │ pessoa pede ajustes
  ▼                                  ▼
Code Review Aprovado              Ajustar Code
  │                                  │
  └───────────────┬──────────────────┘
                  │ agente prepara a entrega
                  ▼
Em Merge ───────────────────────── Gate 3
  │
  │ pessoa faz o merge no GitHub e move o card
  ▼
Mergeado
  │
  │ agente confirma o merge e encerra administrativamente
  ▼
Done
```

### Regra central de responsabilidade

| Momento | Responsável por mover o card |
|---|---|
| Entrada em `BACKLOG` | Pessoa ou integração que cria/registra o card |
| Estacionamento nos gates (`Em Revisão de Spec`, `Em Code Review`, `Em Merge`) | Agente |
| Saída dos gates (`Spec Aprovada`, `Code Review Aprovado`, `Mergeado`, ou colunas de ajuste) | Pessoa |
| Demais transições automáticas | Agente |

O agente nunca:

- aprova a própria especificação;
- aprova o próprio código em nome da pessoa;
- move o card para `Code Review Aprovado`;
- move o card para `Mergeado`;
- faz o merge do Pull Request.

---

## Etapas detalhadas

### 0. Card entra em `BACKLOG`

**Tipo:** gatilho humano ou de integração  
**Responsável pela entrada:** pessoa ou integração de monitoramento  
**Responsável pela execução seguinte:** poller + agente

O card entra no projeto Jira com os requisitos, critérios de aceitação,
evidências e, quando aplicável, logs do problema.

O poller consulta periodicamente o Jira. Ao encontrar um card elegível em
`BACKLOG`, ele:

1. calcula uma thread determinística para a chave do Jira;
2. verifica se já existe uma thread ou execução ativa;
3. cria a thread se necessário;
4. dispara o agente;
5. registra o evento no Agent Console.

Se o shadow mode ou o pause estiverem ativos, o poller apenas registra o que
faria e não inicia nem retoma a execução.

---

### 1. Coleta de contexto

**Tipo:** agêntico  
**Card:** permanece em `BACKLOG`

O agente consulta:

- descrição completa do card;
- critérios de aceitação;
- comentários;
- logs, tracebacks e evidências anexadas;
- repositório alvo e instruções do projeto.

O agente deve entender primeiro o problema relatado e separar:

- comportamento atual, verificado no código;
- comportamento desejado, definido no Jira;
- hipóteses ou recomendações que ainda precisam de confirmação.

Durante a fase de especificação, o card não é movido para `In Progress`.

---

### 2. Preparação do ambiente

**Tipo:** agêntico  
**Card:** permanece em `BACKLOG`

O agente prepara um sandbox isolado e trabalha exclusivamente no repositório
alvo. Ele:

1. clona ou reutiliza o clone do repositório correto;
2. valida o `origin` e a existência de um `.git` próprio;
3. cria a branch da demanda, seguindo o padrão do Jira;
4. carrega as instruções e configurações do repositório;
5. identifica as ferramentas necessárias para executar e validar a mudança.

Commits, branches, pushes e Pull Requests pertencem ao repositório alvo, não
ao repositório que hospeda o agente.

Em repositórios Python, o agente também gera o Harness Report com os comandos
seguros de instalação, teste, lint, type-check e migração, quando aplicável.
Se não conseguir determinar um comando de teste seguro, ele comenta o bloqueio
no Jira e encerra a execução sem adivinhar um comando.

---

### 3. Análise e criação da OpenSpec

**Tipo:** agêntico  
**Card:** permanece em `BACKLOG`

O agente analisa o código existente e cria os artefatos de especificação da
mudança, normalmente:

```text
openspec/changes/<nome-da-mudanca>/
├── proposal.md
├── design.md
├── specs/<capability>/spec.md
└── tasks.md
```

A especificação deve:

- rastrear cada requisito do Jira;
- registrar cenários verificáveis;
- separar fatos observados de decisões de produto;
- documentar decisões abertas em `design.md`;
- decompor a implementação em tarefas pequenas.

O agente não deve escrever código funcional antes de a especificação existir e
ser aprovada.

---

### 4. Gate 1 — `Em Revisão de Spec`

**Tipo:** gate HITL  
**Entrada no gate:** agente  
**Saída do gate:** pessoa

Antes de estacionar o card, o agente:

1. revisa a própria especificação;
2. valida os artefatos;
3. commita a OpenSpec;
4. faz push da branch;
5. confirma que a branch remota existe;
6. comenta no Jira o que está pronto e quais decisões precisam de aprovação;
7. move o card para `Em Revisão de Spec`;
8. encerra a execução.

O agente não espera dentro do mesmo run. O poller detecta posteriormente a
decisão humana.

#### Decisões humanas possíveis

| Nova coluna | Significado | Próxima ação |
|---|---|---|
| `Spec Aprovada` | A especificação foi aceita | Agente retoma e inicia implementação |
| `Ajustar Spec` | A especificação precisa de mudanças | Agente retoma, lê o feedback e revisa a OpenSpec |

---

### 5. Retomada após a aprovação da especificação

**Tipo:** poller + agêntico  
**Entrada:** `Spec Aprovada` ou `Ajustar Spec`

No próximo tick, o poller:

1. encontra o card em uma coluna pós-gate;
2. verifica que existe uma thread estacionada;
3. compara a coluna atual com a coluna onde a thread foi estacionada;
4. busca os comentários recentes;
5. dispara uma nova execução na mesma thread;
6. remove a marca de thread estacionada.

Se o card estiver em `Spec Aprovada`, o agente:

1. confirma a continuidade da mesma branch;
2. move o card para `In Progress`;
3. implementa as tarefas da `tasks.md`;
4. executa testes e validações;
5. faz commit e push;
6. realiza o auto-review do código.

Se o card estiver em `Ajustar Spec`, o agente revisa a especificação na mesma
branch, commita, faz push e retorna o card para `Em Revisão de Spec`.

---

### 6. Criação ou atualização do Pull Request

**Tipo:** agêntico  
**Card:** `In Progress`

O PR precisa existir antes da revisão de código automatizada e antes de o card
entrar em `Em Code Review`.

O agente:

1. confirma que a branch foi publicada;
2. chama `open_pull_request`;
3. usa o mesmo PR durante todo o ciclo da demanda;
4. atualiza o PR em vez de abrir outro quando há correções;
5. registra a URL e o estado do PR.

Em runs do Jira, o `GITHUB_PAT` pode ser usado como fallback para criar o PR
quando não há token OAuth do usuário nem GitHub App disponível. O token é o
mesmo mecanismo usado para autenticar clone, commit e push.

Se a criação ou atualização do PR falhar, o agente:

- comenta a falha no Jira;
- deixa o card em `In Progress`;
- não chama o gate de code review;
- encerra a execução.

---

### 7. Reviewer graph e Gate 2 — `Em Code Review`

**Tipo:** revisão agêntica + gate HITL  
**Entrada no gate:** agente  
**Saída do gate:** pessoa

Depois que o PR existe, o agente chama o reviewer graph para analisar o diff.

#### Resultado do reviewer graph

| Resultado | Comportamento |
|---|---|
| `PASS`, sem findings bloqueantes | Agente estaciona em `Em Code Review` |
| `CHANGES_REQUIRED` ou finding bloqueante | Agente volta à implementação, corrige e solicita nova revisão |

Para estacionar corretamente em `Em Code Review`, todos estes requisitos
precisam estar satisfeitos:

- implementação concluída;
- testes e validações aplicáveis executados;
- auto-review concluído;
- `openspec-verify` sem finding crítico pendente;
- PR criado ou atualizado com sucesso;
- URL do PR confirmada.

O agente então comenta o resultado, move o card para `Em Code Review` e encerra
a execução.

#### Decisões humanas possíveis

| Nova coluna | Significado | Próxima ação |
|---|---|---|
| `Code Review Aprovado` | A pessoa aprovou o código | Agente retoma para preparação de merge |
| `Ajustar Code` | A pessoa solicitou alterações | Agente retoma e corrige a mesma branch/PR |

Em `Ajustar Code`, o GitHub é a fonte primária: o agente lê reviews,
comentários de review e comentários do PR antes de editar. Depois das
correções, ele faz commit, push, solicita nova revisão e estaciona novamente
em `Em Code Review`.

---

### 8. Retomada após `Code Review Aprovado`

**Tipo:** poller + agêntico  
**Entrada:** `Code Review Aprovado`

O poller retoma a mesma thread. O agente não faz merge nesta etapa. Ele executa
a preparação final da entrega:

1. roda testes, lint e checks finais;
2. confirma que não existem findings ou alterações pendentes;
3. arquiva a OpenSpec;
4. atualiza a documentação canônica afetada;
5. commita archive e documentação na mesma branch;
6. faz push para o mesmo PR;
7. revisa o diff acrescentado depois da aprovação humana;
8. confirma que o PR está pronto para merge.

O archive e a documentação entram no mesmo PR, antes do gate de merge. Não é
aberto um PR separado para essa etapa.

Se qualquer etapa falhar, o agente comenta a falha no Jira, não move o card para
`Em Merge` e encerra a execução.

---

### 9. Gate 3 — `Em Merge`

**Tipo:** gate HITL  
**Entrada no gate:** agente  
**Ação humana:** merge no GitHub

Quando a preparação termina, o agente:

1. confirma que o PR contém a implementação, archive e documentação;
2. comenta o resumo final no Jira com o link do PR;
3. move o card para `Em Merge`;
4. encerra a execução.

`Em Merge` significa que a automação terminou e que o PR está pronto para uma
decisão humana.

O agente não:

- faz o merge;
- move o card para `Mergeado`;
- adiciona trabalho funcional depois desse gate.

---

### 10. Merge humano e `Mergeado`

**Tipo:** HITL

A pessoa:

1. revisa o PR pronto;
2. faz o merge no GitHub;
3. move o card no Jira para `Mergeado`.

O merge no GitHub e a mudança para `Mergeado` são ações humanas distintas, mas
ambas fazem parte da confirmação de que a entrega foi aceita e integrada.

O poller detecta a mudança de status e retoma a mesma thread.

---

### 11. Encerramento e `Done`

**Tipo:** agêntico e administrativo  
**Entrada:** `Mergeado`

O agente:

1. confirma pela API do GitHub que o PR foi realmente mergeado;
2. verifica que o estado do PR e o card são consistentes;
3. registra o resultado final e as métricas disponíveis;
4. publica o comentário de encerramento no Jira;
5. move o card para `Done`.

Não há nova alteração funcional nesta fase. O trabalho de código, archive e
documentação já deve ter sido concluído antes de `Em Merge`.

---

## Matriz de responsabilidades

| Atividade | Agente | Pessoa |
|---|:---:|:---:|
| Criar ou registrar o card |  | ✓ |
| Colocar o card em `BACKLOG` |  | ✓ |
| Detectar o card e iniciar a thread | ✓ |  |
| Ler Jira, comentários e evidências | ✓ |  |
| Clonar e validar o repositório alvo | ✓ |  |
| Criar branch e commits | ✓ |  |
| Criar a OpenSpec | ✓ |  |
| Aprovar a OpenSpec |  | ✓ |
| Implementar e testar | ✓ |  |
| Criar ou atualizar o PR | ✓ |  |
| Executar o reviewer graph | ✓ |  |
| Aprovar o código |  | ✓ |
| Solicitar ajustes de código |  | ✓ |
| Corrigir findings e atualizar o PR | ✓ |  |
| Arquivar OpenSpec e atualizar docs | ✓ |  |
| Preparar o PR para merge | ✓ |  |
| Fazer o merge no GitHub |  | ✓ |
| Mover o card para `Mergeado` |  | ✓ |
| Confirmar o merge e mover para `Done` | ✓ |  |

---

## Regras de segurança e de parada

1. **Nunca avançar após uma etapa que falhou.** O status do Jira representa uma
   afirmação sobre o estado real do trabalho.
2. **Sem PR, sem `Em Code Review`.** O PR deve ser criado ou atualizado com
   sucesso antes do gate.
3. **Sem archive, docs, checks e push, sem `Em Merge`.**
4. **O agente não substitui decisões humanas.** Ele pode recomendar, revisar e
   preparar, mas não aprova a spec, não aprova o código e não faz o merge.
5. **Uma demanda usa a mesma branch e o mesmo PR.** Correções de spec ou de
   código continuam na branch existente.
6. **Falha deixa o card parado com explicação.** O agente comenta exatamente o
   que falhou e encerra o run; não entra em loop de transições.
7. **O poller retoma apenas quando o status mudou.** Se o card continua no mesmo
   gate, nenhuma nova execução é disparada.
8. **Shadow mode e pause bloqueiam launch e resume.** Eles impedem tanto novas
   execuções quanto retomadas após decisões humanas.

---

## Resumo dos gates humanos

| Gate | O agente entrega | A pessoa decide | Resultado |
|---|---|---|---|
| Gate 1 — `Em Revisão de Spec` | OpenSpec versionada e publicada | Aprovar ou pedir ajustes | Implementação começa ou spec retorna |
| Gate 2 — `Em Code Review` | Código testado e PR revisado pelo reviewer graph | Aprovar ou pedir ajustes | Preparação de merge começa ou código retorna |
| Gate 3 — `Em Merge` | PR completo, com archive, docs e checks | Fazer ou não fazer o merge | Card vai para `Mergeado` após merge |
