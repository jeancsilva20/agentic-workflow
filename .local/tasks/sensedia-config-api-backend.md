# Config API + Runtime Integration Backend

## What & Why
Adicionar uma camada de configuração operacional ao agent-console backend que exponha e controle dinamicamente `shadow_mode`, `model`, `effort` e `polling_interval`. Hoje essas quatro configurações são lidas uma vez na importação do módulo (variáveis de ambiente) e não podem ser alteradas sem reiniciar o processo. O objetivo é transformar o agent-console no ponto central de controle do runtime, com o backend como fonte de verdade.

## Done looks like
- `GET /api/config` retorna `shadow_mode`, `model`, `effort`, `polling_interval_minutes`, `available_models`, `available_efforts` e `available_polling_intervals` — sem nenhum secret ou credencial.
- `PUT /api/config` valida o payload, persiste, aplica ao runtime e retorna a configuração efetivamente aplicada; valores inválidos recebem 4xx com mensagem de erro.
- Alterar `shadow_mode` via API afeta o comportamento do Jira Poller na próxima verificação (sem reinicialização do processo).
- Alterar `polling_interval_minutes` cancela o cron anterior no LangGraph e cria somente um novo cron com o intervalo correto — nunca dois crons simultâneos.
- Alterar `model` e `effort` fica persistido e é utilizado nos novos runs Jira (via team_settings ou equivalente já existente).
- Qualquer alteração de config gera um evento `log` no execution log do console (ex: `config: shadow mode enabled`).
- A configuração sobrevive a refresh de página; preferencialmente sobrevive a restart do processo (arquivo JSON simples ou reutilização do LangGraph Store).
- Suite de testes de backend cobre os 17 cenários listados no spec (seção 28): GET, shadow toggle, shadow blocking execution, model/effort válido/inválido, polling 1/5/10/30/60 min, ausência de crons duplicados, persistência recarregada, API sem secrets.

## Out of scope
- Alterações no frontend (coberto pelo próximo task).
- Renomear diretórios, módulos ou endpoints internos existentes.
- Suporte a modelo/effort diferente por thread individual (continua via team_settings existente).
- Modificar o arquivo `.env` automaticamente.
- Auth/autenticação nos novos endpoints (mantém o padrão atual sem auth do agent-console).

## Steps

1. **Diagnóstico e mapeamento** — Ler `agent-console/app.py`, `agent-console/store.py`, `agent/jira_poller.py`, `agent/api/app.py` (lifespan do cron), `agent/team_settings.py` e `agent/dispatch.py`. Identificar exatamente onde `JIRA_POLLER_SHADOW_MODE`, `JIRA_POLL_INTERVAL_SECONDS`, model e effort são lidos; registrar no código onde injetar a nova configuração dinâmica.

2. **Camada de configuração operacional** — Criar `agent-console/config_store.py` com uma classe `OperationalConfig` que mantém os valores em memória, os inicializa a partir das variáveis de ambiente como default e persiste/restaura num arquivo JSON local (`agent-console/data/operational_config.json`). Expor métodos `get()`, `update(partial_dict) → dict` com validação (modelos válidos, efforts válidos, intervalos válidos, combinações model×effort). Nunca ler ou escrever secrets.

3. **Endpoints GET e PUT /api/config** — Em `agent-console/app.py`, adicionar os dois endpoints. `GET /api/config` lê `OperationalConfig.get()` e inclui as listas `available_models`, `available_efforts`, `available_polling_intervals`. `PUT /api/config` chama `OperationalConfig.update()`, aplica efeitos laterais (shadow, cron, model/effort) e emite evento de log para cada campo alterado usando o mecanismo de `store.add_log()` existente.

4. **Shadow mode dinâmico** — Em `agent/jira_poller.py`, substituir a leitura do env var em tempo de importação por uma função `is_shadow_mode() -> bool` que consulta a `OperationalConfig` (ou variável compartilhada de processo) em tempo de execução, mantendo fallback para o env var quando a config não estiver disponível. Garantir que a mudança via API afete o próximo tick sem restart.

5. **Reconfiguração segura do cron de polling** — Implementar `reconfigure_poller_cron(new_interval_minutes: int)` em `agent/jira_poller.py` ou em novo helper `agent/poller_cron.py`. A função deve: (a) listar crons existentes com metadata `{"kind":"jira_poller"}`, (b) deletar todos, (c) criar exatamente um novo cron com o intervalo correto. Integrar com `PUT /api/config` para chamar esse helper quando `polling_interval_minutes` mudar. Garantir que o LangGraph client é reutilizado corretamente (não criar nova conexão a cada chamada).

6. **Model e effort dinâmicos** — Quando `PUT /api/config` receber `model` ou `effort`, persistir via `OperationalConfig` e adicionalmente fazer upsert nos `team_settings` do LangGraph Store (reutilizando `agent/team_settings.py::upsert_team_settings`), para que novos runs Jira usem a configuração atualizada sem restart.

7. **Eventos de log administrativo** — Para cada campo que mudou em `PUT /api/config`, emitir via `store.add_log()` (ou equivalente) uma mensagem no formato `config: <campo> changed from <old> to <new>` (ex: `config: shadow mode enabled`, `config: polling interval changed from 1m to 10m`). Esses eventos aparecem automaticamente no execution log do console.

8. **Testes de backend** — Em `agent-console/tests/`, adicionar `test_config_api.py` cobrindo os 17 cenários da seção 28 do spec. Usar fixtures Flask test client. Garantir que os testes existentes continuam passando.

## Relevant files
- `agent-console/app.py`
- `agent-console/store.py`
- `agent-console/requirements.txt`
- `agent-console/tests/`
- `agent/jira_poller.py`
- `agent/api/app.py`
- `agent/team_settings.py`
- `agent/dispatch.py`
- `agent/utils/console_events.py`
