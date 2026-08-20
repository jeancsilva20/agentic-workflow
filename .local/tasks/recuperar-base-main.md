# Apagar os branches da base errada e consolidar o `main`

## Situação atual

O checkout para `main` já foi feito — workspace em `c131a40` ("Add Lite Mode toggle").
Confirmado:

- `git branch --show-current` → `main`
- `agent-console/templates/index.html` → 1080 linhas (versão completa, com Lite Mode)
- `agent/routing/` → presente

**Porém o console ainda renderiza a versão antiga** — o processo Flask precisa de
restart para recarregar o template.

## Causa raiz (para registro)

O branch `feat/spec-SSAI-92-post-clientes-500-validation` foi criado a partir de
`08a0b8e` ("first commit", 2026-08-09 22:01) em vez de `main` (`c131a40`,
2026-08-10 09:01). O checkout ocorreu às 12:15. Todo o trabalho entre 12:39 e 13:09
foi construído sobre essa base ~11 horas mais antiga e é redundante: o `main` já
continha GIT_ASKPASS, o endpoint `/search/jql`, o `.replit` completo com as 7
variáveis, `scripts/start-dev-server.sh` e `[postMerge]` configurado.

## Decisão do usuário

O branch SSAI-92 foi um equívoco e não pertence a este repositório. **Nada dele deve
ser salvo ou mergeado.** Ele deve ser apagado.

## O que fazer

### 1. Apagar os branches criados da base errada

Verificado via `merge-base` contra `08a0b8e` — dois branches têm a base errada:

- `feat/spec-SSAI-92-post-clientes-500-validation`
- `subrepl-n5b08oqz`

Apagar ambos com `git branch -D`.

**Não apagar:** `main`, `replit-agent`, `feat/spec-SSAI-90-*` e `feat/spec-SSAI-91-*`
(estes foram criados corretamente a partir de `main`).

### 2. Remover a árvore `home/` espúria

Confirmado que existe um diretório `home/` na raiz do repositório — resultado de um
caminho absoluto (`/home/runner/workspace/...`) tratado como relativo por um run
anterior. Remover.

### 3. Reiniciar os workflows

Necessário para o console recarregar o template de 1080 linhas.

### 4. Verificar o erro 400 do Jira

Nos ticks do poller aparece, de forma recorrente:

```
Jira rejected the request (400): {"errorMessages":["Invalid request payload."]}
```

Isto ocorre no `main` também. Provável causa: o endpoint novo
`/rest/api/3/search/jql` não aceita o parâmetro `startAt` do endpoint antigo —
a paginação passou a usar `nextPageToken`. Verificar o corpo enviado em
`agent/utils/jira.py::search_issues` e ajustar ao contrato atual da API.

## Critérios de aceitação

1. `git branch --show-current` → `main`
2. `feat/spec-SSAI-92-post-clientes-500-validation` e `subrepl-n5b08oqz` não aparecem
   em `git branch -a`
3. Nenhum diretório `home/` na raiz do repositório
4. `git status` limpo (ou apenas com arquivos intencionalmente não rastreados)
5. Ambos os workflows rodando sem erro
6. Console em `:5050` exibe os controles de Lite Mode e shadow mode
7. Os ticks do poller deixam de registrar erro 400 do Jira
