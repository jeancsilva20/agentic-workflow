# Mapa de Arquivos e Padrões do Open SWE

## Estrutura de diretórios relevante

```
open-swe/
├── agent/
│   ├── server.py              ← Graph factory principal (get_agent)
│   ├── prompt.py              ← Construção do system prompt
│   ├── webapp.py              ← Entrypoint FastAPI (delega para api/app.py)
│   ├── reviewer.py            ← Reviewer graph factory
│   ├── analyzer.py            ← Review style analyzer
│   │
│   ├── tools/                 ← Todas as tools do agente
│   │   ├── __init__.py        ← Lazy loading, registro de tools
│   │   ├── linear_*.py        ← Tools do Linear (get, search, comment, etc.)
│   │   ├── slack_*.py         ← Tools do Slack
│   │   ├── save_plan.py       ← Padrão para tools que escrevem no sandbox
│   │   ├── enter_plan_mode.py ← Ativa plan mode
│   │   ├── approve_plan.py    ← Aprova plano
│   │   └── ...
│   │
│   ├── middleware/            ← Middleware stack
│   │   ├── __init__.py        ← Lazy loading, registro de middleware
│   │   ├── dynamic_tools.py   ← DynamicToolMiddleware (integrações MCP)
│   │   ├── plan_mode.py       ← PlanModeMiddleware (restringe tools)
│   │   ├── check_message_queue.py ← Polling de mensagens (padrão!)
│   │   ├── prepare_run.py     ← BasePrepareRunMiddleware
│   │   └── ...
│   │
│   ├── integrations/          ← Integrações externas (MCP, sandbox)
│   │   ├── corridor_mcp.py    ← PADRÃO: MCP loader (MultiServerMCPClient)
│   │   ├── datadog_mcp.py     ← Outro exemplo de MCP loader
│   │   ├── langsmith_tools.py ← Tools do LangSmith
│   │   └── ...
│   │
│   ├── utils/                 ← Utilitários
│   │   ├── linear.py          ← Cliente HTTP do Linear
│   │   ├── slack.py           ← Cliente do Slack
│   │   ├── sandbox_state.py   ← Gerenciamento de sandbox por thread
│   │   ├── auth.py            ← Resolução de tokens
│   │   └── ...
│   │
│   ├── graphs/                ← Entrypoints registrados no langgraph.json
│   │   ├── agent.py           ← Delega para server.py:get_agent
│   │   ├── reviewer.py        ← Delega para reviewer.py
│   │   ├── analyzer.py        ← Delega para analyzer.py
│   │   ├── chat.py            ← Chat agent
│   │   └── scheduler.py       ← Cron jobs
│   │
│   ├── dashboard/             ← API do dashboard (OAuth, perfis, settings)
│   ├── api/                   ← Rotas da API (webhooks, etc.)
│   └── resources/             ← Recursos estáticos (default_prompt.md)
│
├── langgraph.json             ← Registro de grafos + app HTTP
├── pyproject.toml             ← Dependências (langchain-mcp-adapters já incluso)
└── Makefile                   ← Comandos (install, dev, test, lint, typecheck)
```

## Padrões de código a seguir

### Padrão 1: Nova tool

```python
# agent/tools/minha_tool.py
from typing import Any

async def minha_tool(param: str) -> dict[str, Any]:
    """Descrição da tool.

    Args:
        param: Descrição do parâmetro.

    Returns:
        Dicionário com resultado.
    """
    # implementação
    return {"result": "..."}
```

Registrar em `agent/tools/__init__.py`:
```python
# Adicionar em _TOOL_MODULES
"minha_tool": ".minha_tool",

# Adicionar em __all__
"minha_tool",

# Adicionar TYPE_CHECKING import
from .minha_tool import minha_tool
```

Adicionar em `agent/server.py`:
```python
from .tools import (
    # ... existing imports ...
    minha_tool,
)

static_tools = [
    # ... existing tools ...
    minha_tool,
]
```

### Padrão 2: Integração MCP

```python
# agent/integrations/minha_mcp.py
import logging
import os
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

async def load_minha_tools() -> list[BaseTool]:
    """Carrega tools do MCP, degrada graciosamente."""
    url = os.environ.get("MINHA_MCP_URL", "").strip()
    token = os.environ.get("MINHA_API_TOKEN", "").strip()
    if not url or not token:
        return []
    
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        client = MultiServerMCPClient({...})
        tools = await client.get_tools()
    except Exception:
        logger.warning("Failed to load tools", exc_info=True)
        return []
    
    return tools
```

### Padrão 3: Middleware

```python
# agent/middleware/meu_middleware.py
from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
from collections.abc import Awaitable, Callable

class MeuMiddleware(AgentMiddleware):
    state_schema = AgentState  # ou schema customizado
    
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        # Antes do model call
        response = await handler(request)
        # Depois do model call
        return response
```

Registrar em `agent/middleware/__init__.py` (mesmo padrão das tools).

### Padrão 4: Tool que opera no sandbox

```python
# agent/tools/tool_sandbox.py
from langgraph.config import get_config
from ..utils.sandbox_state import get_sandbox_backend

async def tool_sandbox(path: str) -> dict[str, Any]:
    config = get_config()
    thread_id = config.get("configurable", {}).get("thread_id")
    
    backend = await get_sandbox_backend(thread_id)
    content = await backend.aread(path, offset=0, limit=1000)
    
    return {"content": content}
```

### Padrão 5: Lazy loading nos __init__.py

Tanto `agent/tools/__init__.py` quanto `agent/middleware/__init__.py` usam o mesmo padrão:
- `_TOOL_MODULES` / `_MIDDLEWARE_MODULES`: dicionário mapeando nome → módulo relativo
- `__all__`: lista de exports públicos
- `TYPE_CHECKING`: imports para type checking
- `_LazyToolsModule` / `_LazyMiddlewareModule`: classe que faz lazy load
- `sys.modules[__name__].__class__ = _LazyToolsModule`: substitui a classe do módulo

## Pontos de extensão no server.py

### Onde adicionar tools estáticas (linha ~1125):
```python
static_tools = [
    http_request,
    fetch_url,
    # ... existing tools ...
    slack_thread_reply,
    # NOVAS TOOLS AQUI
]
```

### Onde adicionar tools dinâmicas (linha ~1154):
```python
integration_tool_groups = {
    "Corridor": corridor_tools,
    "Observability": observability_tools,
    # NOVOS GRUPOS AQUI
}
```

### Onde adicionar middleware (linha ~1197):
```python
middleware=cast(
    list[AgentMiddleware[Any, Any, Any]],
    [
        PrepareAgentRunMiddleware(...),
        # ... existing middleware ...
        ModelCallTimeoutMiddleware(),
        # NOVO MIDDLEWARE AQUI (posição importa!)
    ],
)
```

### Onde tools são excluídas no plan mode (linha ~574):
```python
PLAN_MODE_EXCLUDED_TOOLS: frozenset[str] = frozenset(
    {
        "task",
        "http_request",
        "open_pull_request",
        # ... existing exclusions ...
        # NOVAS EXCLUSÕES AQUI (se necessário)
    }
)
```

## Fluxo de uma requisição

```
1. Trigger (webhook ou dashboard)
   ↓
2. langgraph.json → agent.graphs.agent:traced_agent
   ↓
3. agent/graphs/agent.py → agent/server.py:get_agent(config)
   ↓
4. get_agent():
   a. Resolve thread_id
   b. Resolve model (team default → profile → per-thread)
   c. ensure_sandbox_for_thread()
   d. Load integration tools (Corridor, Datadog, etc.)
   e. Build static_tools list
   f. Build middleware stack
   g. create_deep_agent(model, tools, middleware, backend)
   ↓
5. Deep Agent loop:
   a. PrepareAgentRunMiddleware._prepare() → system prompt, work_dir
   b. Model call → agent decides action
   c. Tool execution → agent acts
   d. Middleware wraps each model call
   e. Repeat until task complete or limit reached
```
