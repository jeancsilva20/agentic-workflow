"""Path fixtures for the SDD contract suite.

Every assertion in this suite is a filesystem/YAML check on the artifacts the
Spec-Driven Development contract depends on. Resolving the paths here keeps the
test bodies free of `parents[N]` arithmetic, which silently breaks the moment a
test file moves.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def skills_root() -> Path:
    """`agent/skills/` — served to both graphs on the `/openspec-skills/` route."""
    return REPO_ROOT / "agent" / "skills"


@pytest.fixture(scope="session")
def openspec_config_path() -> Path:
    return REPO_ROOT / "openspec" / "config.yaml"


@pytest.fixture(scope="session")
def openspec_version_path() -> Path:
    return REPO_ROOT / "openspec" / "openspec-version.yaml"


@pytest.fixture(scope="session")
def agents_md_path() -> Path:
    return REPO_ROOT / "AGENTS.md"
