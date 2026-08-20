# Analista de Estilo (`analyzer`)

Arquivo-fonte: `agent/analyzer.py` — factory `get_analyzer` (linha 165).

## Objetivo

Aprender e refinar o prompt de estilo de review **por-repositório**, minerando reviews humanos históricos e os outcomes dos findings do próprio reviewer.

## Intenção

Opera em dois modos: **bootstrap** (cold-start: rastreia reviews históricas) e **continual** (nightly: refina usando os outcomes dos findings via `read_finding_outcomes`).

## Resultado

Persiste o prompt de estilo via `save_review_style_prompt`, que é consumido pelo reviewer como apêndice de estilo específico do repositório.

## Fluxo de Entrada/Saída

- **Entrada**: `config` (`thread_id`, `review_style_full_name`, `review_style_samples_text`, `analyzer_mode`).
- **Saída**: prompt de estilo salvo.

## Conexões

Chamado pelos launchers/cron (`agent/dashboard/review_style_jobs.py`, `agent/dashboard/analyzer_cron.py`). Produz o estilo consumido pelo `reviewer`.

## Ferramentas

**Toolset** (analyzer.py:199): `save_review_style_prompt`, `read_finding_outcomes`.

**Middleware** (analyzer.py:202-214): `PrepareAnalyzerRun`, `SanitizeToolInputs`, `ModelCallLimit` (limite próprio `STYLE_ANALYZER_MODEL_CALL_LIMIT`), `ToolError`, `TimeoutWrapup`.

**Modelo**: `resolve_model(STYLE_ANALYZER)` → Sonnet/medium.
