# Alinhamento com The Agentic Development Playbook

## Mapeamento do fluxo para o Agentic SDLC

O Playbook define 5 estágios. Nosso fluxo de 11 passos mapeia assim:

```
PLAYBOOK STAGE          NOSSO FLUXO
─────────────────────────────────────────────
DEFINE                  PASSO 1: Coletar contexto do Jira
(problema, requisitos,  PASSO 3: Gerar spec (proposal + specs)
 prioridade)            
                        ← APROVAÇÃO 1: Spec Review

SHAPE                   PASSO 3: Gerar design + tasks
(arquitetura,           PASSO 4: Auto-review da spec
 decomposição)          

BUILD                   PASSO 5: Implementar
(implementação)         PASSO 6: Auto-review do código
                        PASSO 7: Reviewer automático
                        ← APROVAÇÃO 2: Code Review

VALIDATE                PASSO 7: Reviewer automático
(testes, segurança,     PASSO 8: Testes finais
 quality gates)         

RUN                     PASSO 8: Push + PR
(deploy, monitoramento) ← APROVAÇÃO 3: Merge
                        PASSO 9: Archive spec
                        PASSO 10: Atualizar docs canônicos
                        PASSO 11: Finalizar + métricas
```

## Princípios do Playbook aplicados

### "Humans own intent and judgment; agents own execution and coverage"

| Atividade | Quem faz |
|---|---|
| Definir o problema (Jira issue) | Humano |
| Especificar critérios de aceite | Humano |
| Gerar spec detalhada | Agente |
| **Decidir o que o produto deve fazer** | **Humano** |
| Revisar e aprovar spec | Humano |
| Decompor em tasks | Agente |
| Implementar código | Agente |
| Escrever testes | Agente |
| Revisar código (automático) | Agente (reviewer graph) |
| Revisar código (final) | Humano |
| Merge | Humano |
| Atualizar docs | Agente |

A linha nova é a que o `SSAI-88` obrigou a explicitar. O princípio não é só "humano
aprova no fim" — é que **julgamento não delega**. Quando resolver a issue exige decidir
o que o produto deveria fazer (a regra "sem números no nome" deve existir?), o agente
escreve as opções com evidência, recomenda uma, e para. Implementar a escolha mais
plausível seria o agente tomando posse do julgamento, mesmo acertando.

O corolário prático: **recomendação de ferramenta de alerta não é intenção humana.** O
card do `SSAI-88` recomenda "ajustar validação para permitir números", mas isso foi
gerado sem ler o código. Tratar essa frase como requisito seria o agente obedecendo uma
máquina e chamando de intenção do time. Ver Decisão 12.

### "The specification is the new source code"

Nosso fluxo coloca OpenSpec como etapa obrigatória antes de qualquer código:
- PASSO 3 gera proposal, design, specs, tasks
- PASSO 4 valida a spec antes de prosseguir
- APROVAÇÃO 1 garante que um humano revisou a spec
- A spec viaja no branch e na PR como contexto

### "Decomposition is a first-order engineering skill"

O PASSO 3 (plan mode) força o agente a decompor o problema em tasks atômicas antes de implementar. O `tasks.md` gerado é o contrato que guia o PASSO 5.

### "Quality must be structural, not informal"

Nossos gates:

| Gate do Playbook | Implementação |
|---|---|
| Spec completeness | PASSO 4 (auto-review) + APROVAÇÃO 1 |
| Architecture review | APROVAÇÃO 1 (humano revisa design.md) |
| Automated test coverage | PASSO 5 (tests por task) + PASSO 8 (suite completa) |
| Code review | PASSO 7 (reviewer graph) + APROVAÇÃO 2 |
| Security & compliance | PASSO 6 (auto-review checklist) + PASSO 7 (reviewer) |
| Release readiness | APROVAÇÃO 3 (humano decide merge) |

### "Measure leverage, not activity"

Métricas que registramos no LangSmith (PASSO 11):
- Tempo total do fluxo (cycle time)
- Ciclos de auto-review (spec + code) — indicador de qualidade da spec
- Findings do reviewer — indicador de qualidade do código
- Status final — taxa de sucesso
- Timestamps dos gates — tempo de espera em cada aprovação

**Não medimos:** linhas de código, tokens consumidos, número de commits.

## Maturity Curve: onde estamos mirando

| Nível | Descrição | Nosso alvo |
|---|---|---|
| 1: Non-Adopters | Uso ad-hoc de AI | — |
| 2: Individual Productivity | "Shadow AI", sem padrões | — |
| 3: Standardized Tooling | Tools padronizadas, práticas de time | — |
| **4: AI-Augmented** | **Agentes integrados ao workflow, spec-driven, quality gates** | **← MVP** |
| 5: AI-Native | Agentes autônomos, humanos só supervisionam | Futuro |

O MVP mira **Level 4**: agentes produzem PRs revisáveis, specs dirigem a implementação, quality gates são estruturais (não puramente prompt-driven), e o time confia no processo.

## Context Debt

O Playbook alerta sobre "context debt" — decisões informais que nunca voltam para os artifacts. Nosso fluxo mitiga isso:

- **Jira issue** → fonte canônica da demanda
- **OpenSpec artifacts** → especificação formal, versionada no repo
- **Comentários no Jira** → feedback humano fica registrado na issue
- **PR description** → gerada automaticamente com link para spec e Jira
- **Docs canônicos** → atualizados pós-merge (PASSO 10)
- **Decisões escaladas** → as opções e a evidência ficam no `design.md`, e a escolha do
  humano fica no comentário do Jira que destravou o gate

Nada fica só em Slack thread ou conversa de corredor.

**Onde ainda geramos context debt.** O `SSAI-88` mostra a forma mais comum: nada no
repositório diz *por que* a regra "sem números no nome" foi escrita. Quem decidir isso
na APROVAÇÃO 1 vai decidir sem esse contexto, e a decisão só sobrevive se voltar para
um artifact. É exatamente por isso que o PASSO 10 atualiza docs canônicos em vez de
deixar a resposta enterrada num comentário de card.

## Papéis do Playbook mapeados

| Papel do Playbook | Quem faz no nosso fluxo |
|---|---|
| Agentic Architect | Agente (PASSO 3: design + decomposição) + Humano (APROVAÇÃO 1) |
| Agent Coach | System prompt + AGENTS.md + custom instructions |
| Agentic Validation Architect | Agente (PASSO 4 e 6: auto-review) + Reviewer graph (PASSO 7) |
| Agent Bench | Subagentes do Open SWE (general purpose + browser) |
