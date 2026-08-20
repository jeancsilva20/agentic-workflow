# Decisões Arquiteturais e Trade-offs

## Decisão 1: Poller no Scheduler com Gates Não-Bloqueantes (revisada)

**Escolha:** cron de 60s no graph `scheduler` que dispara threads novas e acorda threads paradas. O agente **encerra o run** ao chegar num gate — não espera.

> **Histórico.** A primeira versão escolhia um middleware que bloqueava fazendo polling
> a cada 15s. Foi revertida por dois motivos verificados no código:
>
> 1. **O precedente citado não existe.** O racional afirmava que "o padrão de middleware
>    que espera já existe (`check_message_queue_before_model`)". Não existe: é um
>    `@before_model` que faz uma leitura do store e retorna. Nada no Open SWE bloqueia
>    dentro do loop do agente.
> 2. **Três limites rodam por relógio de parede.** `timeout_wrapup.py` injeta "wrap up
>    immediately" aos 45 min; `model_call_timeout.py` corta em 900s; o
>    `ModelCallLimitMiddleware` encerra o run no teto de chamadas. Um gate que dorme
>    queima esse orçamento sem fazer nada — e a APROVAÇÃO 3 é um humano mergeando uma
>    PR, o que não acontece em 45 minutos.
>
> Havia ainda o risco do sandbox: trabalho não commitado vive lá, e um sandbox
> inalcançável levanta `SandboxUnreachableError` em vez de ser substituído. Bloquear por
> horas só aumenta essa janela.

**Contexto:** o requisito é "o agente está sempre disponível e a cada 1 min procura trabalho no Jira". Isso pode ser um processo dormindo ou um cron tickando.

**Trade-offs analisados:**

| Dimensão | Middleware bloqueante | Processo único dormindo | Cron no `scheduler` |
|---|---|---|---|
| Limites de tempo | estoura os 45 min | estoura os 45 min | cada tick é um run curto |
| Infra | zero | zero | zero — o graph já existe |
| Isolamento | 1 sandbox preso por gate | 1 processo para tudo | 1 thread e 1 sandbox por card |
| Recuperação de falha | run perdido | processo morto = tudo parado | próximo tick reassume |
| Custo ocioso | queima orçamento parado | idem | zero quando não há trabalho |
| Latência no gate | até 15s | até 1 min | até 1 min |

**Racional:** "sempre em execução" precisa significar *cron tickando*, não *processo dormindo* — senão os mesmos 45 minutos derrubam o desenho. O graph `scheduler` já existe exatamente para isso (`agent/scheduler.py`: "fans cron ticks into fresh agent threads"). E como o `thread_id` é derivado da issue key, a thread re-disparada reconecta no mesmo sandbox e continua de onde parou — o mesmo mecanismo que já roteia follow-ups do Linear e do Slack.

Detecção de trigger e retomada de gate são a mesma forma de query, então um componente cobre os dois.

**Alternativa mantida como fallback:** `schedule_thread_wakeup(delay_minutes, prompt)` — cron one-shot que re-dispara a própria thread, já no toolset. Permite que a thread acorde sozinha sem o poller. Não foi escolhido como primário porque o poller precisa existir de qualquer forma para detectar trigger, e um componente é melhor que dois.

**Risco:** o poller vira ponto único de falha — se o tick para, tudo fica parado em silêncio. Mitigação: o console mostra "último tick há Ns" como sinal primário de saúde.

---

## Decisão 2: Jira via REST Direto (revisada)

**Escolha:** cliente REST v3 próprio em `agent/utils/jira.py` com Basic auth, seguindo o padrão `agent/utils/linear.py` + `agent/tools/linear_*.py`.

> **Histórico.** A primeira versão desta decisão escolhia o Atlassian Rovo MCP. Foi
> revertida por dois motivos: (a) o racional de segurança não separava as alternativas
> — no padrão Linear o token também roda no processo do servidor e nunca alcança o
> sandbox; (b) o Rovo exige OAuth interativo, que um agente disparado por webhook ou
> cron não consegue completar. A investigação do AI Gateway da Sensedia
> (`06-ai-gateway-sensedia.md`) trouxe uma terceira opção real, também avaliada abaixo.

**Contexto:** três caminhos viáveis — REST direto, MCP `Jira_CRUD_Issue` publicado pelo AI Gateway da Sensedia, ou o Atlassian Rovo MCP.

**Trade-offs analisados:**

| Dimensão | REST Direto | Gateway MCP | Rovo MCP |
|---|---|---|---|
| Camadas de auth | 1 (Basic com PAT) | 2 (OAuth2 do gateway + 3LO Atlassian) | 1 (OAuth 3LO) |
| Rotação de token | nenhuma | as duas camadas rotacionam | refresh token rotaciona |
| Funciona headless | sim | sim (refresh token em arquivo) | **não** (OAuth interativo) |
| Sessão MCP | não existe | `initialize` → `Mcp-Session-Id` → `notifications/initialized` | gerenciada pelo adapter |
| Serviços de pé | nenhum | gateway + Flask | servidor Rovo |
| Sync/async | async nativo | `McpService` é síncrono | async |
| Acesso do middleware | chamada HTTP direta | precisa cliente MCP no loop de polling | idem |
| Token no sandbox | nunca | nunca | nunca |
| Governança | só LangSmith | gateway observa as chamadas | nenhuma |

**Racional:** o fator decisivo é o poller do `scheduler` (Decisão 1). Ele roda num cron tick, **sem LLM no meio** — tool MCP é feita para o modelo invocar, então o poller teria que reabrir sessão MCP a cada 60s só para rodar duas queries JQL. O REST direto resolve isso nativamente e ainda elimina quatro modos de falha (duas rotações de token, handshake de sessão, dependência de dois serviços). O Open SWE já tem esse padrão pronto no Linear: cliente de 383 linhas em `utils/` e tools de 15 linhas que delegam.

Pesou também que o `transitionIssue` nunca foi executado em nenhuma integração existente. Os três gates de aprovação dependem dele; quanto menos camadas entre o agente e essa chamada, melhor para diagnosticar quando falhar.

**O que se aproveita do projeto Sensedia:** o `docs/swagger_jira_custom.yaml` vira o contrato dos endpoints (evita pesquisa na doc da Atlassian), e a normalização de caracteres do `_pre_validate_add_comment` é portada para `agent/utils/adf.py` — problema já diagnosticado e pago lá.

**Risco:** manutenção do cliente HTTP é nossa. Mitigação: são 6 endpoints estáveis da REST v3, cada um com poucas linhas de `httpx`.

**Adiado, não descartado:** se governança sobre as chamadas Jira virar requisito, o Gateway MCP entra como fonte adicional de tools sem tocar no middleware, que continua usando o cliente direto.

---

## Decisão 3: Single Agent com Plan Mode vs Multi-Agent (Planner/Implementer/Reviewer)

**Escolha:** Evoluir o plan mode existente, não criar agentes separados

**Contexto:** A arquitetura proposta sugeria 3 agentes especializados. O Open SWE já tem plan mode (mesmo agente, tools restritas) e reviewer graph (agente separado, read-only).

**Trade-offs analisados:**

| Dimensão | Multi-Agent (3 grafos) | Single Agent + Plan Mode |
|---|---|---|
| Complexidade | 3 grafos, cross-graph state | 1 grafo, state contínuo |
| Custos LLM | 3x chamadas por feature | 1x (com subagentes sob demanda) |
| Qualidade do planning | Prompt especializado | Mesmo modelo, tools restritas |
| Viés de implementação | Planner não "viu" o código | Mesmo agente, pode pular etapas |
| Manutenção | 3 system prompts, 3 tool sets | 1 system prompt |
| Reviewer | Já existe (reviewer graph) | Já existe (reviewer graph) |

**Racional:** O plan mode do Open SWE já restringe ferramentas e força o agente a planejar antes de implementar. Separar em 3 agentes dobraria os custos de LLM e complexidade sem ganho proporcional. O reviewer graph já é separado — cobre exatamente o que a arquitetura pedia.

**Risco:** O mesmo agente pode ter viés ao revisar o próprio código. Mitigação: o reviewer graph é um agente separado que atua como segunda camada de revisão.

---

## Decisão 4: OpenSpec como Skills + Tools Mecânicas (revisada)

**Escolha:** `explore` e `propose` são **skills** do deepagents (`agent/skills/`); só `validate`, `archive` e `status` são tools. Os artifacts continuam no sandbox em `/workspace/openspec/`.

> **Correção.** A versão original mandava criar `agent/tools/openspec_propose.py`, um
> *tool* que "gera proposal.md, design.md, specs e tasks". Isso é erro de categoria: um
> tool Python não escreve um `design.md`. Autorar uma proposta é procedimento de
> raciocínio, não escrita de arquivo — no melhor caso o tool carimba um template.

**Contexto:** OpenSpec poderia ser CLI no sandbox, serviço externo, tools, ou skills.

**Trade-offs analisados:**

| Dimensão | Skills + tools mecânicas | Só tools | CLI no sandbox | Serviço externo |
|---|---|---|---|---|
| Quem autora o conteúdo | o modelo, seguindo o procedimento | ninguém — template | o modelo, via CLI | o modelo |
| Dependências | nenhuma | nenhuma | instalar OpenSpec no snapshot | HTTP + auth |
| Mecanismo existe? | **sim**, `skill_sources` no server.py | sim | não | não |
| Procedimento já escrito? | **sim**, `.claude/skills/openspec-*/SKILL.md` | não | sim | — |
| Versionamento | specs no branch, viajam com a PR | idem | idem | sistema separado |

**Racional:** os dois lados já existem. O procedimento está escrito em
`.claude/skills/openspec-propose/SKILL.md`, e o Open SWE já serve skills ao agente
(`agent/skills/`, rota `/skills/`, `skill_sources` no `server.py` — é como o
`bootstrap-repo-analysis` funciona). Portar reaproveita ambos. O que sobra de
mecânico — validar estrutura, arquivar, ler status — continua sendo tool, no padrão
`save_plan.py`.

**Detalhe que confirma:** o skill declara `compatibility: Requires openspec CLI`, e
`npx openspec` falha neste ambiente — o CLI não está instalado. A Decisão 3 já proibia
CLI no sandbox, então a versão portada dropa essa dependência e o modelo escreve os
artifacts com o `write_file` que já existe.

**Risco:** specs muito grandes podem consumir contexto do agente. Mitigação: o agente lê specs sob demanda, não carrega tudo de uma vez.

---

## Decisão 5: Auto-Review Prompt-Driven vs Structural Gates

**Escolha:** Loops de auto-revisão guiados por system prompt, mirando ~3 ciclos como orientação

**Contexto:** O Playbook recomenda quality gates estruturais entre estágios do SDLC. Poderiam ser implementados como agents separados ou checks automatizados.

**Trade-offs analisados:**

| Dimensão | Prompt-Driven Loops | Structural Gates |
|---|---|---|
| Implementação | System prompt + cycle counter | Novos agentes ou CI checks |
| Robustez | Depende da qualidade do prompt | Determinístico |
| Flexibilidade | Fácil ajustar critérios | Requer código |
| Custo | Zero infra adicional | Novos grafos/infra |
| Alinhamento | Consistente com Open SWE | Mais alinhado ao Playbook |

**Racional:** O Open SWE é intencionalmente prompt-driven para validação. Adicionar gates estruturais seria uma mudança arquitetural significativa. Structural gates podem ser adicionados numa fase futura (maturidade Level 4→5).

**Decisão explícita: o limite de 3 ciclos é orientação, não garantia.** Nada conta os ciclos. O modelo é instruído a parar depois de três e espera-se que obedeça aproximadamente — pode fazer dois, pode fazer cinco. Com a Decisão 1, o run encerra e retoma a cada gate, então um contador teria que sobreviver ao fim do run, o que um prompt não faz.

> **Correção do racional anterior.** A versão original afirmava que "o limite de 3 ciclos
> previne loops infinitos". Isso é falso — um número num prompt não previne nada. O que
> realmente limita é o runtime, independentemente deste prompt: `ModelCallLimitMiddleware`
> encerra o run no teto de chamadas, `timeout_wrapup.py` força encerramento aos 45 min, e
> `notify_step_limit` reporta o limite de passos.

**O invariante que importa** não é a contagem, é: o agente **sempre** para comentando o que não conseguiu resolver. Isso está especificado em `column-approval-gate` e é observável — a contagem não é.

**Risco 1:** O agente pode "aprovar" a própria spec sem rigor. Mitigação: o checklist de auto-review é explícito no prompt; o humano revisa depois de qualquer forma.

**Risco 2:** A profundidade da auto-revisão varia por issue e não é reprodutível. Mitigação: cada ciclo é logado no console, então desvio fica visível ("rodou sete ciclos na SSAI-412") mesmo sem nada impedir. Se a contagem virar métrica de qualidade em que se precise confiar, ela tem que migrar para o state do agente — o que reverte esta decisão.

---

## Decisão 6: Docs Canônicos como PR Separada

**Escolha:** Após merge da PR principal, criar PR separada para docs

**Contexto:** Os docs poderiam ser atualizados na mesma PR ou em commit direto pós-merge.

**Trade-offs analisados:**

| Dimensão | PR Separada | Mesma PR | Commit Direto |
|---|---|---|---|
| Revisão | Independente, focada | Mistura código + docs | Sem revisão |
| Rollback | Docs não afetam código | Acoplados | Perigoso |
| Clareza | Propósito claro | Polui diff da implementação | Invisível |
| Complexidade | +1 PR, +1 branch | Mais simples | Mais simples |

**Racional:** Separar docs mantém a PR de implementação focada. Se a implementação precisar de ajustes, os docs não são atualizados prematuramente. A revisão de documentação pode ser feita por pessoas diferentes.

---

## Decisão 7: Branch Naming Convention

**Escolha:** `feat/spec-JIRA-XXXX-descricao-curta`

**Alternativas consideradas:**
- `feature/JIRA-XXXX` — muito genérico, não indica que carrega specs
- `openspec/JIRA-XXXX` — não segue conventional commits
- `spec/JIRA-XXXX` — mais curto mas menos explícito sobre o tipo de change

**Racional:** `feat/` segue conventional commits. `spec-` indica que a branch carrega artifacts OpenSpec. `JIRA-XXXX` provê rastreabilidade. `descricao-curta` dá contexto humano.

**Correção (validação):** a proposta original usava `feat/spec:JIRA-XXXX`. Dois-pontos é caractere proibido em nomes de ref no Git — `git check-ref-format --branch "feat/spec:JIRA-1234-x"` retorna `fatal: not a valid branch name`, ou seja, o `git checkout -b` falharia em 100% das execuções. Separador trocado para hífen. Regra dura: prefixo `feat/` + nome que passe em `git check-ref-format --branch`.

---

## Decisão 8: Não Remover Linear/Slack/GitHub

**Escolha:** Adicionar Jira como trigger adicional, mantendo os existentes

**Contexto:** A arquitetura proposta focava exclusivamente em Jira. O Open SWE já tem integração profunda com Linear, Slack e GitHub.

**Racional:** Remover triggers existentes quebraria funcionalidade sem benefício. Adicionar Jira como opção adicional segue o padrão de extensão, não substituição. O time pode usar Jira para o fluxo principal e manter Slack para notificações.

---

## Decisão 9: Não Implementar Webhook do Jira (MVP)

**Escolha:** Polling para MVP, webhook como melhoria futura

**Contexto:** Um webhook do Jira permitiria resposta instantânea a transições de coluna, mas requer endpoint público e configuração no Jira.

**Racional:** Polling funciona para o MVP sem infra adicional. Webhook pode ser adicionado depois como otimização (menor latência). O padrão de `schedule_thread_wakeup` do Open SWE já suporta wake-up externo.

---

## Decisão 10: Métricas no LangSmith (Não Banco Próprio)

**Escolha:** LangSmith traces com metadata customizada

**Contexto:** Poderíamos criar um banco de métricas dedicado ou usar o LangSmith que já está integrado.

**Racional:** LangSmith já é o sistema de tracing do Open SWE. Adicionar metadata (Jira key, fase, ciclos, timestamps) é trivial. Evita novo banco, nova UI, nova dependência. As métricas ficam junto com os traces para correlação.

---

## Decisão 11: `BACKLOG` como Coluna de Trigger

**Escolha:** o card que cai em `BACKLOG` inicia o fluxo. Não existe gesto separado de "pronto para desenvolvimento".

**Contexto:** o board `SSAI` foi criado com 11 status, três deles defaults do Jira (`BACKLOG`, `In Progress`, `Done`). O design pedia uma coluna `Pronto para Desenvolvimento` como trigger, que não foi criada.

**Trade-offs analisados:**

| Dimensão | `BACKLOG` como trigger | Coluna dedicada | Label `agent-ready` |
|---|---|---|---|
| Colunas no board | 11 | 12 | 11 |
| Gesto visível no Kanban | entrar no projeto já é o pedido | mover o card | invisível no board |
| Backlog como área segura | não — tudo dispara | sim | sim |
| Cards de integração (FA Alert) | disparam sozinhos | precisam ser promovidos | precisam de label |
| Continua column-driven | sim | sim | **não** |

**Racional:** a decisão é do time. Entrar no backlog **é** o pedido — não há triagem separada nesse fluxo, e uma coluna a mais seria cerimônia sem dono. A alternativa por label preservaria o backlog como área segura, mas tira o gesto do quadro e quebra o modelo column-driven que dá nome à capability.

**Riscos aceitos:**
1. Todo card criado no projeto vira um run no próximo tick, inclusive os abertos para triagem ou discussão.
2. A integração do FA Alert já arquiva bugs neste projeto. Esses cards passam a ser pegos sem humano no meio.

**Mitigação disponível se incomodar:** escopar o JQL do trigger no `agent/jira_poller.py` por tipo de issue, label ou responsável. É mudança de configuração, não redesenho — o board e o modelo column-driven ficam intactos.

---

## Decisão 12: Spec Ancorada em Card + Código, com Ambiguidade Escalada

**Escolha:** o agente lê as duas fontes antes de escrever qualquer artifact, trata recomendação de alerta como hipótese, e escala decisão de produto em vez de resolver.

**Contexto:** o `SSAI-88` expôs o problema. O card diz que `POST /clientes` devolve 500 porque a validação rejeita nomes com dígito, e recomenda *"ajustar validação para permitir números"*. O código conta outra história:

```python
if re.search(r'\d', dados_cliente.nome):
    raise RuntimeError(...)                    # → 500
if self.repository.buscar_por_cpf(...):
    raise HTTPException(status_code=400, ...)  # → 400
if self.repository.buscar_por_email(...):
    raise HTTPException(status_code=400, ...)  # → 400
```

As duas regras vizinhas devolvem 400. Só a do nome levanta `RuntimeError` puro. O defeito evidenciado é o **tipo de erro**, não a regra. Se a regra deve existir é decisão de produto, e nada no repo diz por que ela foi escrita.

**Regras estabelecidas:**

| Regra | Por quê |
|---|---|
| Card é a fonte da intenção, código é a fonte da verdade | card descreve o observado, código descreve o que acontece |
| Recomendação de alerta é hipótese | foi escrita sem ler o código; confirmar ou refutar e registrar qual |
| Olhar os vizinhos antes de propor | regra tratada de um jeito em três lugares e diferente no quarto é defeito no quarto |
| Decisão de produto vai para a APROVAÇÃO 1 | escrever as opções com evidência, recomendar uma, deixar o humano decidir |
| Todo requisito rastreia a uma fonte | se não dá para apontar de onde veio, não entra na spec |

**Racional:** é a aplicação direta do princípio do Playbook — *"humans own intent and judgment; agents own execution and coverage"*. Separar defeito evidenciado de decisão em aberto deixa o agente implementar o primeiro enquanto o segundo é respondido, sem travar nem decidir por conta.

**Risco:** o agente pode classificar como "decisão de produto" o que é só falta de investigação, e escalar demais. Mitigação: os sinais estão listados explicitamente em `../prompts/spec-grounding.md`, e o critério é evidência no repo — não desconforto.
