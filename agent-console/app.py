"""Agent console: a small read-only Flask page reporting whether the Jira
poller is alive, the card queue, active/parked/dead runs, and a live
execution log (design.md / proposal.md).

Run with:
    pip install -r agent-console/requirements.txt
    python agent-console/app.py            # http://localhost:5050

Point the agent at it (agent/utils/console_events.py) via:
    AGENT_CONSOLE_URL=http://localhost:5050
"""

from __future__ import annotations

import os

from flask import Flask, jsonify, render_template, request
from store import store

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def get_state():
    return jsonify(store.status())


@app.post("/api/events/<kind>")
def post_event(kind: str):
    payload = request.get_json(silent=True) or {}

    if kind == "tick":
        store.record_tick(payload.get("step_a", {}), payload.get("step_b", {}))
    elif kind == "run":
        issue_key = payload.get("issue_key")
        action = payload.get("action")
        if not issue_key or not action:
            return jsonify({"error": "issue_key and action are required"}), 400
        extra = {k: v for k, v in payload.items() if k not in ("issue_key", "action")}
        store.record_run_event(issue_key, action, **extra)
    elif kind == "queue":
        issue_key = payload.get("issue_key")
        if not issue_key:
            return jsonify({"error": "issue_key is required"}), 400
        extra = {k: v for k, v in payload.items() if k != "issue_key"}
        store.record_queue_event(issue_key, **extra)
    elif kind == "log":
        store.record_log(payload.get("message", ""))
    else:
        return jsonify({"error": f"unknown event kind: {kind}"}), 404

    return jsonify({"success": True})


if __name__ == "__main__":
    port = int(os.environ.get("AGENT_CONSOLE_PORT", "5050"))
    app.run(host="0.0.0.0", port=port, debug=False)  # noqa: S104 — internal ops tool, not internet-facing
