# Frontend Rebrand + Config Panel UI

## What & Why
Evoluir o `agent-console/templates/index.html` para refletir a identidade "Sensedia Agentic Workflow" e adicionar um painel de configuração operacional que se comunica com os endpoints `GET /api/config` e `PUT /api/config` criados no task anterior. Todas as alterações são incrementais sobre o HTML/CSS/JS inline existente — sem reconstrução completa da interface.

## Done looks like
- Browser title e `<h1>` exibem "Sensedia Agentic Workflow".
- Header mostra o logo oficial da Sensedia (se houver asset no projeto) ou um slot preparado para recebê-lo, seguido do nome da aplicação.
- Header exibe o indicador de Shadow Mode: banner "SHADOW MODE — Monitoring only" (fundo âmbar/amarelo) quando ativo ou "LIVE EXECUTION — Agents can execute" (fundo verde discreto) quando inativo — sem nenhuma possibilidade de confusão entre os dois estados.
- Painel "Agent Configuration" abaixo do header com: toggle Shadow Mode, dropdown Modelo (lista vinda do backend), dropdown Effort, dropdown "Verificar Jira a cada".
- Ao carregar, os controles mostram os valores reais retornados por `GET /api/config`.
- Ao alterar qualquer controle: mostra estado "Saving…", faz `PUT /api/config`, exibe confirmação de sucesso ou mensagem de erro; se falhar, reverte o controle para o valor anterior (sem deixar valor "falso" como aplicado).
- As áreas existentes (status geral, cards WORKING/WAITING/QUEUED/DEAD, Queue, Runs, Execution Log) são preservadas sem alteração funcional.
- O execution log continua exibindo todos os eventos existentes, incluindo os novos eventos `config: …` injetados pelo backend.
- Testes de frontend (ou validações via pytest/selenium/playwright se já existirem) cobrem os 14 cenários da seção 29 do spec.

## Out of scope
- Mudanças no backend (coberto pelo task anterior).
- Reescrita completa de CSS ou estrutura de componentes.
- Autenticação ou controle de acesso na UI.
- Adicionar novas abas ou páginas além do dashboard atual.
- Internacionalização.

## Steps

1. **Buscar asset da Sensedia** — Verificar se existe qualquer arquivo de logo Sensedia no projeto (SVG, PNG, WebP) em `static/`, `assets/`, `agent-console/static/` ou similar. Reutilizar o asset encontrado. Se não existir, preparar o `<img>` com `src=""` e classe `sensedia-logo` e registrar no código que o asset precisa ser fornecido.

2. **Rebrand do cabeçalho** — Em `agent-console/templates/index.html`, alterar `<title>` para "Sensedia Agentic Workflow", substituir o `<h1>` atual por um header estruturado com logo + nome + indicador de shadow mode. Manter os CSS variables e o tema escuro existente; adicionar estilos apenas para os elementos novos.

3. **Indicador visual de Shadow Mode no header** — Criar um `<div id="shadow-indicator">` dentro do header que troca entre dois estados visuais: "SHADOW MODE / Monitoring only" (bg âmbar) e "LIVE EXECUTION / Agents can execute" (bg verde). A visibilidade e texto são atualizados pelo JavaScript quando a resposta de `/api/config` chega ou quando uma alteração é confirmada pelo backend.

4. **Painel Agent Configuration** — Inserir uma `<section id="agent-config">` logo abaixo do header e acima dos cards de métricas. Conteúdo: toggle (checkbox estilizado) para Shadow Mode; `<select id="cfg-model">` populado dinamicamente com `available_models`; `<select id="cfg-effort">` populado com `available_efforts`; `<select id="cfg-interval">` populado com `available_polling_intervals`. Estilizar no padrão dark existente — sem dependências externas.

5. **Fetch inicial da config** — Na função de inicialização do JS (junto com o poll existente de `/api/state`), adicionar `fetchConfig()` que chama `GET /api/config` e popula os selects/toggle com os valores reais. Chamar uma vez no load; não substituir o polling existente de state.

6. **Handlers de alteração com feedback e rollback** — Para cada controle, adicionar handler `onChange` que: (a) armazena o valor anterior, (b) desabilita o controle e mostra "Saving…", (c) faz `PUT /api/config` com o campo alterado, (d) em sucesso: re-habilita e atualiza o indicador de shadow mode se necessário; (e) em falha: reverte para o valor anterior, re-habilita e exibe mensagem de erro inline. Bloquear saves concorrentes (flag `saving`).

7. **Preservar áreas existentes** — Verificar que nenhuma alteração de layout, IDs ou classes quebrou as seções de métricas, queue, runs e execution log. Confirmar que o renderizado de eventos `[shadow]` no log continua funcionando.

8. **Testes de frontend** — Adicionar ou expandir testes em `agent-console/tests/` cobrindo os 14 cenários da seção 29: nome correto, estado inicial do backend, shadow mode refletindo API, model/effort/interval vindos do backend, loading state, erro e rollback, refresh mantém config real, responsividade do header.

## Relevant files
- `agent-console/templates/index.html`
- `agent-console/app.py`
- `agent-console/store.py`
- `agent-console/tests/`
- `agent-console/static/` (verificar existência)
