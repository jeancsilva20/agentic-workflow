"""Tool: ``openspec_archive``. Move a completed change's artifacts to
``openspec/changes/archive/`` and fold its ADDED capabilities into the
canonical ``openspec/specs/`` tree — the mechanical move+merge side of what
the ``openspec archive`` CLI command does, without needing the CLI
(Decision 4).

Deliberately conservative: a capability that already exists in
``openspec/specs/`` is left alone and reported as needing a manual merge,
rather than attempting to apply MODIFIED/REMOVED/RENAMED deltas
automatically. Silently getting that merge wrong would corrupt the canonical
spec; a human noticing a warning is the safer failure mode.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from langgraph.config import get_config

from ..utils.sandbox_state import get_sandbox_backend

_ADDED_SECTION_RE = re.compile(
    r"^##\s+ADDED Requirements\s*\n(.*?)(?=^##\s+\S|\Z)", re.MULTILINE | re.DOTALL
)


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


async def _walk_files(backend: Any, path: str) -> list[str]:
    """Recursively list file paths (not directories) under ``path``."""
    listing = await backend.als(path)
    entries = _value(listing, "entries") or []
    files: list[str] = []
    for entry in entries:
        entry_path = str(_value(entry, "path") or "")
        if not entry_path:
            continue
        full_path = f"{path.rstrip('/')}/{entry_path.strip('/')}"
        if _value(entry, "is_dir"):
            files.extend(await _walk_files(backend, full_path))
        else:
            files.append(full_path)
    return files


async def openspec_archive(change_name: str) -> dict[str, Any]:
    """Move a change's artifacts to ``openspec/changes/archive/`` and merge new capabilities.

    Args:
        change_name: The change directory name under ``openspec/changes/``.

    Returns:
        Dictionary with ``moved`` (file count), ``merged_capabilities`` (new
        capabilities folded into ``openspec/specs/``), and
        ``needs_manual_merge`` (capabilities that already existed and were
        left untouched).
    """
    thread_id = await _thread_id()
    if not thread_id:
        return {"error": "no thread_id in run config"}

    backend = await get_sandbox_backend(thread_id)
    change_dir = f"openspec/changes/{change_name}"
    archive_dir = f"openspec/changes/archive/{change_name}"

    files = await _walk_files(backend, change_dir)
    if not files:
        return {"error": f"no files found under {change_dir}"}

    merged: list[str] = []
    needs_manual_merge: list[str] = []
    specs_prefix = f"{change_dir}/specs/"
    for file_path in files:
        if file_path.startswith(specs_prefix) and file_path.endswith("/spec.md"):
            capability = file_path[len(specs_prefix) :].rsplit("/spec.md", 1)[0]
            canonical_path = f"openspec/specs/{capability}/spec.md"
            existing = _read_text(await backend.aread(canonical_path, offset=0, limit=1))
            if existing is not None:
                needs_manual_merge.append(capability)
                continue
            delta_text = _read_text(await backend.aread(file_path, offset=0, limit=20_000)) or ""
            added_match = _ADDED_SECTION_RE.search(delta_text)
            if added_match:
                await backend.awrite(canonical_path, added_match.group(1).strip() + "\n")
                merged.append(capability)

    moved = 0
    for file_path in files:
        content = _read_text(await backend.aread(file_path, offset=0, limit=20_000))
        if content is None:
            continue
        relative = file_path[len(change_dir) + 1 :]
        await backend.awrite(f"{archive_dir}/{relative}", content)
        await backend.adelete(file_path)
        moved += 1

    return {
        "moved": moved,
        "merged_capabilities": merged,
        "needs_manual_merge": needs_manual_merge,
    }
