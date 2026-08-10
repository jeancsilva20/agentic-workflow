"""Agent console: a small Flask page reporting whether the Jira poller is
alive, the card queue, active/parked/dead runs, and a live execution log
(design.md / proposal.md), plus the operational configuration an operator can
change at runtime (`/api/config` — shadow mode, poll interval) and the model
router's per-role table (`/api/config/routing`, read-only).

Run with:
    pip install -r agent-console/requirements.txt
    python agent-console/app.py            # http://localhost:5050

Point the agent at it (agent/utils/console_events.py) via:
    AGENT_CONSOLE_URL=http://localhost:5050
"""

from __future__ import annotations

import os
from typing import Any

import runtime_bridge
from config_store import ConfigValidationError, operational_config
from flask import Flask, jsonify, render_template, request
from store import store

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def get_state():
    return jsonify(store.status())


@app.get("/api/config")
def get_config():
    return jsonify({**operational_config.get(), **operational_config.options()})


@app.get("/api/config/routing")
def get_routing_config():
    """The model router's table: which model and effort each agent role runs on.

    Read-only by design — routing is automatic, so there is no PUT counterpart.
    """
    return jsonify({"routing": runtime_bridge.routing_table()})


@app.put("/api/config")
def put_config():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "a JSON object body is required"}), 400

    # One lock over "save" and "apply": concurrent PUTs must not end up with the
    # file on one operator's choice and the runtime on the other's.
    with operational_config.transaction():
        try:
            applied, changes = operational_config.update(payload)
        except ConfigValidationError as exc:
            return jsonify({"error": str(exc)}), 400

        warnings = _apply_to_runtime(applied, changes)

    return jsonify({**applied, **operational_config.options(), "warnings": warnings})


def _apply_to_runtime(applied: dict[str, Any], changes: list[tuple[str, Any, Any]]) -> list[str]:
    """Push each changed field to the runtime, logging what changed either way.

    Persisting is not applying: the poller picks shadow mode up from the shared
    config file on its next tick, but the cron lives on the LangGraph server and
    can fail independently. Those failures come back as warnings — the value is
    saved, the runtime just hasn't taken it yet.
    """
    for field, old, new in changes:
        store.record_log(_change_message(field, old, new))

    changed = {field for field, _old, _new in changes}
    warnings: list[str] = []
    if "polling_interval_minutes" in changed:
        warnings.append(runtime_bridge.apply_polling_interval(applied["polling_interval_minutes"]))

    warnings = [warning for warning in warnings if warning]
    for warning in warnings:
        store.record_log(f"config: {warning}")
    return warnings


def _change_message(field: str, old: Any, new: Any) -> str:
    if field == "shadow_mode":
        return f"config: shadow mode {'enabled' if new else 'disabled'}"
    if field == "polling_interval_minutes":
        return f"config: polling interval changed from {old}m to {new}m"
    return f"config: {field} changed from {old} to {new}"


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
