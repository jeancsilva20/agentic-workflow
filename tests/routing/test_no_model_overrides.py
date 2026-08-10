"""No LLM entrypoint may take its model from a request, a profile or a team default.

The router is the single authority. This is a source scan rather than a
behavioural test on purpose: the failure mode it guards against is a *new* call
site quietly reintroducing the old precedence, which no existing test would
notice. Every allowance below is a place that only stores or displays a model
choice — nothing there reaches a run.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_AGENT_ROOT = Path(__file__).resolve().parents[2] / "agent"

# Per-run model selection keys from before the router. None of them may be read
# or written anywhere: a key that is set but ignored is worse than one that is
# honoured, because the UI keeps offering a choice that does nothing.
_FORBIDDEN_CONFIG_KEYS = (
    "agent_model_id",
    "agent_effort",
    "chat_model_id",
    "chat_effort",
    "reviewer_model_id",
    "reviewer_reasoning_effort",
)

# Where a stored model choice may still be read: settings and profile CRUD,
# which serve the dashboard's own forms, plus the catalog they validate against.
_SETTINGS_MODULES = {
    "dashboard/team_settings.py",
    "dashboard/routes.py",
    "dashboard/profiles.py",
    "dashboard/options.py",
}


def _sources() -> list[tuple[str, str]]:
    files = []
    for path in sorted(_AGENT_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        files.append((path.relative_to(_AGENT_ROOT).as_posix(), path.read_text()))
    assert files, "no agent sources found — the scan would pass vacuously"
    return files


_SOURCES = _sources()


@pytest.mark.parametrize("key", _FORBIDDEN_CONFIG_KEYS)
def test_no_module_reads_a_per_run_model_key(key: str) -> None:
    offenders = [name for name, source in _SOURCES if f'"{key}"' in source or f"'{key}'" in source]

    assert not offenders, (
        f"{key} is a pre-router model override; the router decides per role now. Found in: "
        + ", ".join(offenders)
    )


def test_only_settings_modules_read_the_team_default_model() -> None:
    """A team default is an operator preference — it must not steer an execution."""
    offenders = [
        name
        for name, source in _SOURCES
        if "get_team_default_model" in source and name not in _SETTINGS_MODULES
    ]

    assert not offenders, (
        "team defaults may only be read by the settings API that stores them. Found in: "
        + ", ".join(offenders)
    )


def test_profile_model_overrides_have_no_helper_left() -> None:
    """The profile still shows a model field; nothing may resolve a run from it."""
    offenders = [
        name
        for name, source in _SOURCES
        if "normalize_profile_overrides" in source or "resolve_agent_model_id" in source
    ]

    assert not offenders, (
        "profile model precedence helpers are gone; do not reintroduce them. Found in: "
        + ", ".join(offenders)
    )


def _calls_named(source: str, name: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            called = getattr(func, "id", None) or getattr(func, "attr", None)
            if called == name:
                return True
    return False


def test_every_module_that_builds_a_model_resolves_a_role_first() -> None:
    """``make_model`` is the last step of a route, never a decision of its own."""
    builders = {
        name
        for name, source in _SOURCES
        if _calls_named(source, "make_model") and not name.startswith("utils/")
    }
    assert builders, "no model construction found — the scan would pass vacuously"

    unrouted = {
        name
        for name in builders
        if not any("resolve_model" in source for other, source in _SOURCES if other == name)
    }

    assert not unrouted, (
        "these modules build a model without asking the router for a role: " + ", ".join(unrouted)
    )
