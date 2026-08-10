"""Tool: ``openspec_validate``. Mechanical structural check for a change's
OpenSpec artifacts — required files present, every requirement has at least
one scenario, headers well-formed. This is deliberately *not* a judgment call
about quality; it catches the same class of silent failure the schema itself
warns about (e.g. a three-hashtag ``### Scenario`` that a real parser would
skip without error).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from langgraph.config import get_config

from ..utils.sandbox_state import get_sandbox_backend

_CAPABILITY_BULLET_RE = re.compile(r"^-\s*`([a-z0-9][a-z0-9-]*)`", re.MULTILINE)
_REQUIREMENT_RE = re.compile(r"^###\s+Requirement:\s*(.+)$", re.MULTILINE)
_SCENARIO_RE = re.compile(r"^####\s+Scenario:", re.MULTILINE)
_THREE_HASH_SCENARIO_RE = re.compile(r"^###\s+Scenario:", re.MULTILINE)
_TASK_CHECKBOX_RE = re.compile(r"^\s*-\s*\[([ x~])\]", re.MULTILINE)


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


def _validate_spec_content(capability: str, content: str, errors: list[str]) -> None:
    if _THREE_HASH_SCENARIO_RE.search(content):
        errors.append(
            f"specs/{capability}/spec.md: found '### Scenario:' (three hashtags) — "
            "scenarios must use exactly four hashtags ('#### Scenario:') or they are "
            "silently ignored"
        )

    requirement_matches = list(_REQUIREMENT_RE.finditer(content))
    if not requirement_matches:
        errors.append(f"specs/{capability}/spec.md: no '### Requirement:' headers found")
        return

    for i, match in enumerate(requirement_matches):
        start = match.end()
        end = (
            requirement_matches[i + 1].start() if i + 1 < len(requirement_matches) else len(content)
        )
        block = content[start:end]
        if not _SCENARIO_RE.search(block):
            errors.append(
                f"specs/{capability}/spec.md: requirement '{match.group(1).strip()}' "
                "has no '#### Scenario:' block"
            )


async def openspec_validate(change_name: str) -> dict[str, Any]:
    """Run a mechanical structural check on a change's OpenSpec artifacts.

    Args:
        change_name: The change directory name under ``openspec/changes/``.

    Returns:
        Dictionary with ``valid`` (bool), ``errors`` (blocking issues), and
        ``warnings`` (non-blocking issues).
    """
    thread_id = await _thread_id()
    if not thread_id:
        return {"error": "no thread_id in run config"}

    backend = await get_sandbox_backend(thread_id)
    change_dir = f"openspec/changes/{change_name}"

    errors: list[str] = []
    warnings: list[str] = []

    proposal_result = await backend.aread(f"{change_dir}/proposal.md", offset=0, limit=20_000)
    proposal_text = _read_text(proposal_result)
    if proposal_text is None:
        errors.append("proposal.md is missing")
        return {"valid": False, "errors": errors, "warnings": warnings}

    capabilities = sorted(set(_CAPABILITY_BULLET_RE.findall(proposal_text)))
    if not capabilities:
        warnings.append(
            "proposal.md lists no capabilities in backticks under 'New Capabilities' / "
            "'Modified Capabilities' — cannot cross-check spec files"
        )

    for capability in capabilities:
        spec_path = f"{change_dir}/specs/{capability}/spec.md"
        spec_result = await backend.aread(spec_path, offset=0, limit=20_000)
        spec_text = _read_text(spec_result)
        if spec_text is None:
            errors.append(f"proposal.md names capability '{capability}' but {spec_path} is missing")
            continue
        _validate_spec_content(capability, spec_text, errors)

    tasks_result = await backend.aread(f"{change_dir}/tasks.md", offset=0, limit=20_000)
    tasks_text = _read_text(tasks_result)
    if tasks_text is None:
        errors.append("tasks.md is missing")
    elif not _TASK_CHECKBOX_RE.search(tasks_text):
        errors.append("tasks.md has no '- [ ]' checkbox tasks — apply cannot track progress")

    design_result = await backend.aread(f"{change_dir}/design.md", offset=0, limit=20_000)
    if _read_text(design_result) is None:
        warnings.append("design.md is missing (acceptable for simple, single-file changes)")

    return {"valid": not errors, "errors": errors, "warnings": warnings}
