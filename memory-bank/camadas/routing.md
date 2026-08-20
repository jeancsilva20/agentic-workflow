# Camada transversal: Routing de Modelos

Um único lugar decide qual modelo roda qual papel: `agent/routing/`. Antes disso,
o modelo vinha de quem tivesse setado por último (default do console, perfil do
dashboard, chave por thread) — o que fazia todo passo do workflow Jira rodar no
mesmo modelo. O routing é automático e **não tem override de propósito**
(`agent/routing/router.py:1-12`).

Nada fora de `agent/routing` pode escolher modelo: nem campo de request, nem
perfil do dashboard, nem default de equipe.

---

## Papéis — `agent/routing/roles.py:15-45`

O enum `AgentRole` (StrEnum, 15 papéis):

| Papel | Valor |
|---|---|
| `JIRA_TRIAGE` | `jira_triage` |
| `PYTHON_HARNESS` | `python_harness` |
| `SPEC_AUTHOR` | `spec_author` |
| `SPEC_REVIEWER` | `spec_reviewer` |
| `SPEC_ADJUSTER` | `spec_adjuster` |
| `CODING_AGENT` | `coding_agent` |
| `CODE_ADJUSTER` | `code_adjuster` |
| `OPENSPEC_VERIFIER` | `openspec_verifier` |
| `CODE_REVIEWER` | `code_reviewer` |
| `DIFF_GROUPING` | `diff_grouping` |
| `REVIEW_CHAT` | `review_chat` |
| `STYLE_ANALYZER` | `style_analyzer` |
| `DOCS_AGENT` | `docs_agent` |
| `ARCHIVE_AGENT` | `archive_agent` |
| `ESCALATION_AGENT` | `escalation_agent` |

Alguns papéis não são selecionados por nada ainda (`jira_triage`,
`python_harness`, `spec_reviewer`, `docs_agent`, `escalation_agent`) — essas
fases acontecem dentro do run de outro papel. A tabela em
`GET /api/config/routing` marca cada linha `active` e diz o que a seleciona.

---

## Tabela de rotas — `agent/routing/router.py:81-99`

`_DEFAULT_ROUTES` mapeia papel → `(modelo, effort)`:

| Grupo | Papéis | Modelo / Effort |
|---|---|---|
| Haiku / sem effort | `JIRA_TRIAGE`, `PYTHON_HARNESS`, `ARCHIVE_AGENT`, `DIFF_GROUPING`, `DOCS_AGENT` | Haiku, `None` |
| Sonnet / high | `SPEC_AUTHOR`, `SPEC_ADJUSTER`, `OPENSPEC_VERIFIER` | Sonnet, `high` |
| Sonnet / medium | `CODING_AGENT`, `CODE_ADJUSTER`, `REVIEW_CHAT`, `STYLE_ANALYZER` | Sonnet, `medium` |
| Opus / high | `SPEC_REVIEWER`, `CODE_REVIEWER`, `ESCALATION_AGENT` | Opus, `high` |

Os ids são resolvidos por família ("Haiku"/"Sonnet"/"Opus") através do catálogo
em `agent/dashboard/options.py` (`_model_for_family`, `router.py:31-48`), então
um bump de versão move o routing junto.

`DOCS_AGENT` tem rota especial (`_docs_route`, `router.py:112-130`): trabalho
mecânico → Haiku; revisão semântica (`docs_mode=semantic` ou complexidade ≥ HIGH)
→ Sonnet/high.

---

## Escalada — `router.py:103-164`

Só `CODING_AGENT` e `CODE_ADJUSTER` escalam (`_ESCALATING_ROLES`). Um reviewer já
roda em Opus; um triage que falhou duas vezes não falhou porque Haiku era fraco.

`_escalate` decide, nesta ordem:

1. `retry_count >= 2` (`RETRY_ESCALATION_THRESHOLD`) → **Opus/high**.
2. Complexidade `CRITICAL` → **Opus/high**.
3. Complexidade ≥ `HIGH` **com** sinais de risco → **Opus/high**.
4. Complexidade ≥ `HIGH` sem risco → **Sonnet/high** (effort sobe, modelo mantido).
5. `retry_count >= 1` → **Sonnet/high** (2ª tentativa).

O `escalation_reason` é sempre registrado na decisão (`ModelConfig.escalation_reason`).

---

## Complexidade determinística — `agent/routing/complexity.py`

Sem chamada de LLM. Sinais vindos de metadata/JSON:

- Sinais de risco (`RISK_SIGNALS`, `complexity.py:24-29`): `has_migration`,
  `has_auth_change`, `has_security`, `has_concurrency` — cada um vale **peso 4**
  (`_RISK_SIGNAL_WEIGHT`).
- Contagem de arquivos (`_FILE_COUNT_POINTS`, `complexity.py:39`): ≥20 → 3 pts,
  ≥10 → 2 pts, ≥4 → 1 pt.
- `retry_count` (cap 3 pts) e `review_return_count` (cap 2 pts).

Limiares (`complexity.py:41-43`): `MEDIUM ≥ 2`, `HIGH ≥ 4`, `CRITICAL ≥ 8`.
`classify_complexity` é aritmética pura — mesmos sinais, mesmo tier.

---

## Sem override

Não há override por thread, perfil, equipe ou console. O único desvio é o
**lite mode** (`lite_mode_override`, `router.py:196-204`): força todos os papéis
para Haiku/sem effort, pulando escalada e rota de docs.

---

## Telemetria — `agent/routing/telemetry.py`

Uma card Jira não é um trace: uma card abrange vários runs (spec, review, code,
ajustes), separados por horas de humano num gate. A unidade de agregação é
`jira_issue_key` + `thread_id`, e só funciona se cada run for **taggeado** no
dispatch (LangSmith agrupa por metadata dada, nunca por inferida).

Metadados anexados por run: `jira_issue_key`, `agent_role`, `model`, `effort`,
`complexity_tier`, `routing_reason`, `routing_mode`, `workflow_stage`, além de
`telemetry_dispatch_id` (correlação). Custos/tokens são lidos **depois** do run
terminar, nunca por token.

- `agent/routing/usage_collection.py` — coleta pós-run (busca o trace pelo
  `telemetry_dispatch_id` no projeto de tracing).
- `agent/routing/pricing.py` — fallback de custo quando LangSmith não precifica;
  um run sem preço reporta `null`, não `0.0`.
- `agent/routing/usage_store.py` — agrega por card Jira entre todos os threads.
