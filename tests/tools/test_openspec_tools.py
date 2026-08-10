from __future__ import annotations

from typing import Any
from unittest.mock import patch

from agent.tools.openspec_archive import openspec_archive
from agent.tools.openspec_status import openspec_status
from agent.tools.openspec_validate import openspec_validate

_CONFIG = {"configurable": {"thread_id": "thread-1"}}


class _FakeBackend:
    """Minimal in-memory stand-in for a sandbox backend, keyed by flat path."""

    def __init__(self, files: dict[str, str]) -> None:
        self.files = dict(files)

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> dict[str, Any]:
        content = self.files.get(file_path.lstrip("/"))
        if content is None:
            return {"error": "not found"}
        return {"file_data": {"content": content, "encoding": "utf-8"}}

    async def awrite(self, file_path: str, content: str) -> dict[str, Any]:
        self.files[file_path.lstrip("/")] = content
        return {"success": True}

    async def adelete(self, file_path: str) -> dict[str, Any]:
        self.files.pop(file_path.lstrip("/"), None)
        return {"success": True}

    async def als(self, path: str) -> dict[str, Any]:
        prefix = path.strip("/") + "/"
        seen_dirs: set[str] = set()
        entries: list[dict[str, Any]] = []
        for key in self.files:
            if not key.startswith(prefix):
                continue
            rest = key[len(prefix) :]
            if "/" in rest:
                top = rest.split("/", 1)[0]
                if top not in seen_dirs:
                    seen_dirs.add(top)
                    entries.append({"path": f"/{top}/", "is_dir": True})
            else:
                entries.append({"path": f"/{rest}", "is_dir": False})
        return {"entries": entries}


_VALID_PROPOSAL = """## Why

Testing.

## Capabilities

### New Capabilities
- `widgets`: widget capability

## Impact

None.
"""

_VALID_SPEC = """## ADDED Requirements

### Requirement: Widgets can be created
The system SHALL allow widget creation.

#### Scenario: Create a widget
- **WHEN** a user creates a widget
- **THEN** it exists
"""

_VALID_TASKS = """## 1. Setup

- [ ] 1.1 Do the thing
- [x] 1.2 Do the other thing
"""


def _backend_with(files: dict[str, str]) -> _FakeBackend:
    return _FakeBackend(files)


async def test_openspec_status_reports_missing_thread_id() -> None:
    with patch("agent.tools.openspec_status.get_config", return_value={"configurable": {}}):
        result = await openspec_status("my-change")

    assert result == {"error": "no thread_id in run config"}


async def test_openspec_status_reports_artifacts_and_task_progress() -> None:
    backend = _backend_with(
        {
            "openspec/changes/my-change/proposal.md": _VALID_PROPOSAL,
            "openspec/changes/my-change/tasks.md": _VALID_TASKS,
            "openspec/changes/my-change/specs/widgets/spec.md": _VALID_SPEC,
        }
    )
    with (
        patch("agent.tools.openspec_status.get_config", return_value=_CONFIG),
        patch("agent.tools.openspec_status.get_sandbox_backend", return_value=backend),
    ):
        result = await openspec_status("my-change")

    assert result["artifacts"]["proposal.md"] is True
    assert result["artifacts"]["design.md"] is False
    assert result["artifacts"]["tasks.md"] is True
    assert result["capabilities"] == ["widgets"]
    assert result["tasks_total"] == 2
    assert result["tasks_complete"] == 1


async def test_openspec_validate_passes_for_well_formed_change() -> None:
    backend = _backend_with(
        {
            "openspec/changes/my-change/proposal.md": _VALID_PROPOSAL,
            "openspec/changes/my-change/tasks.md": _VALID_TASKS,
            "openspec/changes/my-change/specs/widgets/spec.md": _VALID_SPEC,
        }
    )
    with (
        patch("agent.tools.openspec_validate.get_config", return_value=_CONFIG),
        patch("agent.tools.openspec_validate.get_sandbox_backend", return_value=backend),
    ):
        result = await openspec_validate("my-change")

    assert result["valid"] is True
    assert result["errors"] == []


async def test_openspec_validate_flags_missing_proposal() -> None:
    backend = _backend_with({})
    with (
        patch("agent.tools.openspec_validate.get_config", return_value=_CONFIG),
        patch("agent.tools.openspec_validate.get_sandbox_backend", return_value=backend),
    ):
        result = await openspec_validate("my-change")

    assert result["valid"] is False
    assert "proposal.md is missing" in result["errors"]


async def test_openspec_validate_flags_missing_spec_for_named_capability() -> None:
    backend = _backend_with(
        {
            "openspec/changes/my-change/proposal.md": _VALID_PROPOSAL,
            "openspec/changes/my-change/tasks.md": _VALID_TASKS,
        }
    )
    with (
        patch("agent.tools.openspec_validate.get_config", return_value=_CONFIG),
        patch("agent.tools.openspec_validate.get_sandbox_backend", return_value=backend),
    ):
        result = await openspec_validate("my-change")

    assert result["valid"] is False
    assert any("widgets" in e and "missing" in e for e in result["errors"])


async def test_openspec_validate_flags_three_hashtag_scenario() -> None:
    bad_spec = _VALID_SPEC.replace("#### Scenario:", "### Scenario:")
    backend = _backend_with(
        {
            "openspec/changes/my-change/proposal.md": _VALID_PROPOSAL,
            "openspec/changes/my-change/tasks.md": _VALID_TASKS,
            "openspec/changes/my-change/specs/widgets/spec.md": bad_spec,
        }
    )
    with (
        patch("agent.tools.openspec_validate.get_config", return_value=_CONFIG),
        patch("agent.tools.openspec_validate.get_sandbox_backend", return_value=backend),
    ):
        result = await openspec_validate("my-change")

    assert result["valid"] is False
    assert any("four hashtags" in e for e in result["errors"])


async def test_openspec_validate_flags_missing_task_checkboxes() -> None:
    backend = _backend_with(
        {
            "openspec/changes/my-change/proposal.md": _VALID_PROPOSAL,
            "openspec/changes/my-change/tasks.md": "## 1. Setup\n\nNo real checkboxes here.\n",
            "openspec/changes/my-change/specs/widgets/spec.md": _VALID_SPEC,
        }
    )
    with (
        patch("agent.tools.openspec_validate.get_config", return_value=_CONFIG),
        patch("agent.tools.openspec_validate.get_sandbox_backend", return_value=backend),
    ):
        result = await openspec_validate("my-change")

    assert result["valid"] is False
    assert any("checkbox" in e for e in result["errors"])


async def test_openspec_archive_moves_files_and_merges_new_capability() -> None:
    backend = _backend_with(
        {
            "openspec/changes/my-change/proposal.md": _VALID_PROPOSAL,
            "openspec/changes/my-change/tasks.md": _VALID_TASKS,
            "openspec/changes/my-change/specs/widgets/spec.md": _VALID_SPEC,
        }
    )
    with (
        patch("agent.tools.openspec_archive.get_config", return_value=_CONFIG),
        patch("agent.tools.openspec_archive.get_sandbox_backend", return_value=backend),
    ):
        result = await openspec_archive("my-change")

    assert result["moved"] == 3
    assert result["merged_capabilities"] == ["widgets"]
    assert result["needs_manual_merge"] == []
    assert "openspec/changes/my-change/proposal.md" not in backend.files
    assert "openspec/changes/archive/my-change/proposal.md" in backend.files
    assert "openspec/specs/widgets/spec.md" in backend.files


async def test_openspec_archive_flags_existing_capability_for_manual_merge() -> None:
    backend = _backend_with(
        {
            "openspec/changes/my-change/proposal.md": _VALID_PROPOSAL,
            "openspec/changes/my-change/tasks.md": _VALID_TASKS,
            "openspec/changes/my-change/specs/widgets/spec.md": _VALID_SPEC,
            "openspec/specs/widgets/spec.md": "### Requirement: Pre-existing\nAlready here.\n",
        }
    )
    with (
        patch("agent.tools.openspec_archive.get_config", return_value=_CONFIG),
        patch("agent.tools.openspec_archive.get_sandbox_backend", return_value=backend),
    ):
        result = await openspec_archive("my-change")

    assert result["needs_manual_merge"] == ["widgets"]
    assert result["merged_capabilities"] == []
    # Pre-existing canonical spec must be left untouched.
    assert (
        backend.files["openspec/specs/widgets/spec.md"]
        == "### Requirement: Pre-existing\nAlready here.\n"
    )


async def test_openspec_archive_reports_error_for_empty_change() -> None:
    backend = _backend_with({})
    with (
        patch("agent.tools.openspec_archive.get_config", return_value=_CONFIG),
        patch("agent.tools.openspec_archive.get_sandbox_backend", return_value=backend),
    ):
        result = await openspec_archive("my-change")

    assert "error" in result
