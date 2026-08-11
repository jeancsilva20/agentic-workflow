#!/usr/bin/env bash
set -euo pipefail

# The console is the public web service. LangGraph stays on the internal
# localhost:8000 endpoint used by the console runtime bridge and scheduler.
CONSOLE_PORT="${PORT:-5000}"
export AGENT_CONSOLE_PORT="$CONSOLE_PORT"
export AGENT_CONSOLE_URL="${AGENT_CONSOLE_URL:-http://127.0.0.1:${CONSOLE_PORT}}"
export LANGGRAPH_URL="${LANGGRAPH_URL:-http://127.0.0.1:8000}"

bash scripts/start-dev-server.sh &
langgraph_pid=$!

cleanup() {
  kill "$langgraph_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd agent-console
pip install -r requirements.txt -q
python app.py &
console_pid=$!

wait -n "$langgraph_pid" "$console_pid"
exit $?