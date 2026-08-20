# Lite Mode toggle (força Haiku em todos os agentes)

## What & Why
Adicionar um toggle "Lite Mode" ao Agent Console, análogo ao Shadow Mode. Quando ativo, força o modelo `claude-haiku` em **todos os papéis de agente**, independente da tabela de roteamento. O objetivo é baratear e acelerar execuções de teste sem precisar alterar a configuração de roteamento permanente.

## Done looks like
- O painel "Agent Configuration" do console exibe um switch "Lite Mode" ao lado do "Shadow Mode".
- Ligar/desligar o toggle persiste imediatamente via `PUT /api/config`.
- Com Lite Mode ativo, `resolve_model()` retorna `claude-haiku` e `effort=None` para qualquer papel — Opus e Sonnet não são chamados.
- Com Lite Mode desligado, o roteamento volta ao normal sem reiniciar nenhum processo.
- O campo `lite_mode` aparece no JSON de `GET /api/config`.
- O Console exibe o estado atual do toggle ("ON" / "OFF") na interface, igual ao Shadow Mode.

## Out of scope
- Alterar o roteamento por papel individualmente (isso é tarefa separada).
- Aplicar Lite Mode retroativamente a runs já em andamento.
- Qualquer mudança no harness Python, poller Jira ou arquivo de status.

## Steps
1. **`agent/operational_config.py`** — Adicionar função `lite_mode_override() -> bool | None` seguindo o padrão de `shadow_mode_override()`: lê `"lite_mode"` do JSON compartilhado.
2. **`agent-console/config_store.py`** — Adicionar campo `lite_mode: bool` ao dataclass `OperationalConfig` (default `False`); incluí-lo na serialização/deserialização.
3. **`agent-console/app.py`** — Expor `lite_mode` em `GET /api/config` e aceitar/persistir em `PUT /api/config`, sem quebrar campos existentes.
4. **`agent/routing/router.py`** — No início de `resolve_model()`, após resolver role/complexity, verificar `lite_mode_override()`; se `True`, substituir modelo por `HAIKU_MODEL_ID` e `effort=None`, ajustando o campo `reason` para refletir o override. Escalation e docs-route não devem rodar quando Lite Mode está ativo.
5. **`agent-console/templates/index.html`** — Adicionar bloco `.config-field` para "Lite Mode" imediatamente abaixo do toggle do Shadow Mode, com mesmo markup (checkbox `#cfg-lite`, switch-track/thumb, switch-state). Conectar ao JS de load/save de config, espelhando exatamente o padrão do Shadow Mode.

## Relevant files
- `agent/operational_config.py`
- `agent-console/config_store.py`
- `agent-console/app.py:59-62,112-128`
- `agent/routing/router.py:77-210`
- `agent-console/templates/index.html:317-345,935-1045`
