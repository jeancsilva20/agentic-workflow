"""Tool: ``openspec_status``. Read OpenSpec artifact status for a change directly
from the sandbox — the mechanical read side of what ``openspec status --change
<name> --json`` gives the CLI, without needing the CLI (Decision 4).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langgraph.config import get_config

from ..utils.sandbox_state import get_sandbox_backend

_ARTIFACT_FILES = ("proposal.md", "design.md", "tasks.md")


def _value(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _read_text(read_result: Any) -> str | None:
    if _value(read_result, "error"):
        return None
    file_data = _value(read_result, "file_data")
    content = _value(file_data, "content")
    return content if isinstance(content, str) else None


async def _thread_id() -> str | None:
    try:
        config = get_config()
    except Exception:  # noqa: BLE001
        return None
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    thread_id = configurable.get("thread_id") if isinstance(configurable, dict) else None
    return thread_id if isinstance(thread_id, str) and thread_id else None


async def openspec_status(change_name: str) -> dict[str, Any]:
    """Report which OpenSpec artifacts exist for a change and task progress.

    Args:
        change_name: The change directory name under ``openspec/changes/``.

    Returns:
        Dictionary with ``artifacts`` (per-file existence), ``capabilities``
        (spec sub-directories found under ``specs/``), and — when
        ``tasks.md`` exists — ``tasks_total`` / ``tasks_complete``.
    """
    thread_id = await _thread_id()
    if not thread_id:
        return {"error": "no thread_id in run config"}

    backend = await get_sandbox_backend(thread_id)
    change_dir = f"openspec/changes/{change_name}"

    artifacts: dict[str, bool] = {}
    contents: dict[str, str | None] = {}
    for name in _ARTIFACT_FILES:
        read_result = await backend.aread(f"{change_dir}/{name}", offset=0, limit=20_000)
        text = _read_text(read_result)
        artifacts[name] = text is not None
        contents[name] = text

    specs_listing = await backend.als(f"{change_dir}/specs")
    entries = _value(specs_listing, "entries") or []
    capabilities = sorted(
        {
            str(_value(entry, "path") or "").strip("/").split("/")[0]
            for entry in entries
            if _value(entry, "is_dir")
        }
        - {""}
    )

    result: dict[str, Any] = {
        "change_name": change_name,
        "artifacts": artifacts,
        "capabilities": capabilities,
    }

    tasks_text = contents.get("tasks.md")
    if tasks_text is not None:
        result["tasks_total"] = (
            tasks_text.count("- [ ]") + tasks_text.count("- [x]") + tasks_text.count("- [~]")
        )
        result["tasks_complete"] = tasks_text.count("- [x]")

    return result
