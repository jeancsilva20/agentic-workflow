#!/usr/bin/env bash
# Start the LangGraph development server.
# Installs core deps via pip on first run (or when missing), then starts the server.
# The langchain-e2b/langchain-daytona/langchain-modal/langchain-runloop sandbox
# integrations have upstream dependency conflicts (deepagents version pins) that
# only uv's override-dependencies mechanism resolves; pip cannot. They are
# installed with --no-deps so their transitive deps don't fail resolution.
# SANDBOX_TYPE=local (the default for this env) does not use any of them.
set -euo pipefail

PYTHONLIBS="$(python3 -c 'import site; print(site.getusersitepackages())')"

# Fast check: if fastapi is importable the core packages are already present.
if ! python3 -c "import fastapi, langgraph_api, anthropic" 2>/dev/null; then
  echo "[start-dev-server] Installing core dependencies (first run)…"
  pip install -q \
    "langgraph-cli[inmem]>=0.4.31" \
    "fastapi>=0.141.1" \
    "uvicorn>=0.52.0" \
    "httpx>=0.28.1" \
    "PyJWT>=2.12.1" \
    "cryptography>=50.0.0" \
    "langgraph-sdk>=0.4.2" \
    "langchain>=1.3.9" \
    "langgraph>=1.2.10" \
    "markdownify>=1.2.3" \
    "langchain-anthropic>=1.5.4" \
    "langsmith>=0.10.16" \
    "langchain-openai>=1.4.1" \
    "langchain-fireworks>=1.5.2" \
    "fireworks-ai>=1.2.5" \
    "exa-py>=2.16.2" \
    "langchain-google-genai>=4.3.2" \
    "langchain-mcp-adapters>=0.3.1" \
    "stagehand>=3.22.0" \
    "websockets>=15.0.1" \
    "deepagents==0.7.1" \
    "wcmatch>=11.0"

  # Optional sandbox integrations — install without deps to skip conflict resolution.
  pip install -q --no-deps \
    "langchain-e2b==0.0.6" \
    "langchain-daytona>=0.0.8" \
    "langchain-modal>=0.0.6" \
    "langchain-runloop>=0.0.7" || true

  echo "[start-dev-server] Dependencies installed."
fi

exec langgraph dev --host 0.0.0.0 --port 8000 --no-reload --no-browser
