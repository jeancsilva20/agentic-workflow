# Spike de Validação — o que foi verificado contra o Jira real

Executado em 2026-08-09 pelo `scripts/spike_jira.py`, contra o board `SSAI` em
`sensedia.atlassian.net`, usando o card `SSAI-88`. Existe porque boa parte do plano
assumia comportamentos que ninguém tinha exercitado.

## Resultado

| Premissa | Como foi testada | Resultado |
|---|---|---|
| Basic auth com PAT funciona headless | `GET /rest/api/3/myself` | **confirmada** |
| Leitura de issue | `GET /rest/api/3/issue/{key}` | **confirmada** |
| Transições globais no board | mover o card pelas 11 colunas e listar destinos de cada uma | **confirmada** — 11/11 alcançam todas |
| `transitionIssue` funciona | `getTransitions` → resolver nome → `POST /transitions` | **confirmada** |
| ADF aceita texto de LLM em português | comentário com aspas curvas, travessão, meia-risca, NBSP, acentos e code block | **confirmada**, inclusive no round-trip |
| Título de issue vira ref git válido | slug + `git check-ref-format --branch` | **confirmada** |
| Nomes das colunas batem com o design | `GET /rest/api/3/project/SSAI/statuses` | **refutada** — três divergiam |

## O que mudou por causa do spike

**Nomes de coluna.** O board foi criado com três defaults do Jira em vez dos nomes do
design: `BACKLOG`, `In Progress` e `Done` no lugar de `Pronto para Desenvolvimento`,
`Em Desenvolvimento` e `Concluído`. Os outros oito batiam exatamente, acentuação
inclusive. Os artifacts foram alinhados ao board, não o contrário — ver Decisão 11
para o trigger.

**O risco da matriz de transições evaporou.** O design tratava a resolução nome → id e
a matriz de saltos permitidos como risco aberto. As transições globais já estavam
configuradas em todos os 11 status, então a matriz não existe: qualquer coluna alcança
qualquer outra. O risco continua registrado porque depende de configuração que alguém
pode desfazer.

**O script ganhou descoberta de status.** A primeira versão comparava contra uma lista
fixa e reportava como "não alcançável" colunas que simplesmente não existiam.
`--project SSAI` lê os status reais e diferencia as duas coisas.

## O que o spike NÃO prova

- **Que o LLM gera ADF válido.** O teste enviou ADF montado à mão. O problema
  documentado no projeto do AI Gateway (`_pre_validate_add_comment`) é o modelo
  produzindo ADF malformado, não o Jira rejeitando caracteres válidos. A task 2.x
  continua necessária.
- **Comportamento sob rate limit.** Nenhuma chamada chegou perto de 429. O tratamento
  com backoff da task 1.5 segue não exercitado.
- **Que a thread sobrevive a um gate longo.** Testar isso exige o poller e um sandbox
  real.
- **Concorrência.** Um card por vez. A idempotência do tick (task 5.5) é a garantia no
  papel, ainda não medida.

## Efeito colateral no card

O `SSAI-88` carrega onze transições e um comentário de teste no histórico, com
autorização. Foi restaurado para `BACKLOG` ao final.

## Como repetir

```bash
python scripts/spike_jira.py --issue SSAI-88 --project SSAI          # só leitura
python scripts/spike_jira.py --issue SSAI-88 --project SSAI --write  # completo
```

Vale rodar de novo depois de qualquer mexida no workflow do Jira — é a forma mais
barata de descobrir que alguém desfez as transições globais.
