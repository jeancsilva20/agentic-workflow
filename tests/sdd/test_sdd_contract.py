"""The SDD contract, as executable assertions.

Spec-Driven Development on this agent is enforced by *text*: skills the agent
reads, gate rules in `AGENTS.md`, and per-artifact rules in `openspec/config.yaml`.
Nothing in the runtime stops a run from skipping the spec — so a silent edit to
one of those files silently removes a gate, and no other suite notices.

Each test below is one clause of that contract, numbered to match the twenty
requirements in §35 of the spec so a failure names the clause it broke. They are
pure filesystem and YAML checks: no LLM calls, no network, no sandbox.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

OPENSPEC_SKILLS = (
    "openspec-explore",
    "openspec-propose",
    "openspec-verify",
    "openspec-archive",
)


def _read_skill(skills_root: Path, skill: str) -> str:
    path = skills_root / skill / "SKILL.md"
    assert path.is_file(), f"missing skill file: {path}"
    return path.read_text(encoding="utf-8")


def _frontmatter(skills_root: Path, skill: str) -> dict[str, Any]:
    """Parse a skill's YAML frontmatter — SkillsMiddleware lists skills from it."""
    text = _read_skill(skills_root, skill)
    assert text.startswith("---\n"), f"{skill}: no YAML frontmatter"
    parsed = yaml.safe_load(text.split("---\n", 2)[1])
    assert isinstance(parsed, dict), f"{skill}: frontmatter is not a mapping"
    return parsed


def _load_yaml(path: Path) -> dict[str, Any]:
    assert path.is_file(), f"missing file: {path}"
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict), f"{path} does not parse to a mapping"
    return parsed


# 1 ------------------------------------------------------------------------


def test_sdd_01_openspec_skills_are_loadable_from_the_skills_root(skills_root: Path) -> None:
    """Each OpenSpec skill parses and declares the `name` the route serves it under.

    A skill whose frontmatter name drifts from its directory is invisible to the
    agent: the prompt lists one name, the path it must `read_file` is another.
    """
    assert skills_root.is_dir(), f"skills root missing: {skills_root}"
    for skill in OPENSPEC_SKILLS:
        meta = _frontmatter(skills_root, skill)
        assert meta.get("name") == skill
        description = meta.get("description")
        assert isinstance(description, str) and description.strip()


# 2 ------------------------------------------------------------------------


def test_sdd_02_openspec_version_manifest_exists_and_parses(openspec_version_path: Path) -> None:
    manifest = _load_yaml(openspec_version_path)
    assert manifest.get("source")


# 3 ------------------------------------------------------------------------


def test_sdd_03_openspec_version_and_commit_are_pinned(openspec_version_path: Path) -> None:
    """The pin is the audit trail for which upstream revision guided a run."""
    manifest = _load_yaml(openspec_version_path)

    version = manifest.get("version")
    commit = manifest.get("commit")
    assert isinstance(version, str) and version.strip(), "version is empty"
    assert isinstance(commit, str) and commit.strip(), "commit is empty"
    assert len(commit.strip()) >= 7, "commit must be a real SHA, not a branch name"


# 4 ------------------------------------------------------------------------


def test_sdd_04_openspec_config_has_a_non_empty_context_block(openspec_config_path: Path) -> None:
    """`context:` is what tells the agent which repository and stack it is speccing for."""
    config = _load_yaml(openspec_config_path)

    context = config.get("context")
    assert isinstance(context, str), "config.yaml has no `context:` block"
    assert len(context.strip()) > 200, "`context:` is too thin to ground an artifact"


# 5 ------------------------------------------------------------------------


@pytest.mark.parametrize("skill", OPENSPEC_SKILLS)
def test_sdd_05_the_four_lifecycle_skills_exist(skills_root: Path, skill: str) -> None:
    """Explore -> propose -> verify -> archive: the lifecycle the gates step through."""
    assert (skills_root / skill / "SKILL.md").is_file()


# 6 ------------------------------------------------------------------------


def test_sdd_06_python_harness_skill_exists_and_has_content(skills_root: Path) -> None:
    text = _read_skill(skills_root, "python-harness")
    assert len(text.strip()) > 500
    assert _frontmatter(skills_root, "python-harness").get("name") == "python-harness"


# 7 ------------------------------------------------------------------------


def test_sdd_07_python_review_skill_exists_and_has_content(skills_root: Path) -> None:
    """The reviewer's Python specialisation, served on the same static route."""
    text = _read_skill(skills_root, "python-review")
    assert len(text.strip()) > 500
    assert _frontmatter(skills_root, "python-review").get("name") == "python-review"


# 8 ------------------------------------------------------------------------


def test_sdd_08_harness_skill_emits_a_completion_signal(skills_root: Path) -> None:
    """Step 0 has to end in a signal later steps can key off — and a blocked path."""
    text = _read_skill(skills_root, "python-harness")

    assert "HARNESS COMPLETE" in text
    assert "HARNESS BLOCKED" in text


# 9 ------------------------------------------------------------------------


def test_sdd_09_verify_skill_walks_the_tasks_checklist(skills_root: Path) -> None:
    text = _read_skill(skills_root, "openspec-verify")

    assert "tasks.md" in text
    lowered = text.lower()
    assert "tasks checklist" in lowered or "checklist" in lowered
    assert "- [ ]" in text or "checkbox" in lowered


# 10 -----------------------------------------------------------------------


def test_sdd_10_archive_skill_moves_artifacts_before_the_merge_gate(skills_root: Path) -> None:
    """Archiving after the merge would leave work outstanding in a PR nobody watches."""
    text = _read_skill(skills_root, "openspec-archive")

    assert "openspec/changes/archive/" in text
    assert "Em Merge" in text
    assert "before" in text.lower()


# 11 -----------------------------------------------------------------------


def test_sdd_11_agents_md_declares_the_mandatory_gates(agents_md_path: Path) -> None:
    text = agents_md_path.read_text(encoding="utf-8")
    assert "## SDD Mandatory Gates" in text


def _gate_section(agents_md_path: Path, heading: str) -> str:
    text = agents_md_path.read_text(encoding="utf-8")
    assert heading in text, f"missing section: {heading}"
    after = text.split(heading, 1)[1]
    return after.split("\n### ", 1)[0].split("\n## ", 1)[0]


# 12 -----------------------------------------------------------------------


def test_sdd_12_spec_review_gate_requires_committed_pushed_artifacts(
    agents_md_path: Path,
) -> None:
    section = _gate_section(agents_md_path, "### Gate 1 — before `Em Revisão de Spec`")

    assert "MUST NOT call `jira_park_at_gate`" in section
    assert "Em Revisão de Spec" in section
    assert "committed" in section and "pushed" in section
    for artifact in ("proposal.md", "spec.md", "tasks.md"):
        assert artifact in section


# 13 -----------------------------------------------------------------------


def test_sdd_13_code_review_gate_requires_a_clean_verify(agents_md_path: Path) -> None:
    section = _gate_section(agents_md_path, "### Gate 2 — before `Em Code Review`")

    assert "MUST NOT call `jira_park_at_gate`" in section
    assert "Em Code Review" in section
    assert "openspec-verify" in section
    assert "CRITICAL" in section


# 14 -----------------------------------------------------------------------


def test_sdd_14_merge_gate_requires_a_completed_archive(agents_md_path: Path) -> None:
    section = _gate_section(agents_md_path, "### Gate 3 — before `Em Merge`")

    assert "MUST NOT call `jira_park_at_gate`" in section
    assert "Em Merge" in section
    assert "openspec-archive" in section
    assert "openspec/changes/archive/" in section


# 15 -----------------------------------------------------------------------


def test_sdd_15_tasks_rules_require_literal_checkboxes(openspec_config_path: Path) -> None:
    """Anything not in checkbox form is invisible to the verify step and to the gates."""
    config = _load_yaml(openspec_config_path)

    rules = config.get("rules")
    assert isinstance(rules, dict), "config.yaml has no `rules:` block"
    tasks_rules = rules.get("tasks")
    assert isinstance(tasks_rules, list) and tasks_rules, "`rules.tasks` is missing or empty"

    joined = "\n".join(str(rule) for rule in tasks_rules)
    assert "- [ ]" in joined
    assert "checkbox" in joined.lower()
    assert "- [x]" in joined


# 16 -----------------------------------------------------------------------


def test_sdd_16_python_engineering_covers_typing(skills_root: Path) -> None:
    text = _read_skill(skills_root, "python-engineering")
    lowered = text.lower()

    assert "## typing" in lowered
    assert "type hint" in lowered or "annotation" in lowered


# 17 -----------------------------------------------------------------------


def test_sdd_17_fastapi_engineering_covers_pydantic(skills_root: Path) -> None:
    text = _read_skill(skills_root, "fastapi-engineering")
    assert "Pydantic" in text


# 18 -----------------------------------------------------------------------


def test_sdd_18_python_database_requires_alembic_migrations(skills_root: Path) -> None:
    text = _read_skill(skills_root, "python-database")

    assert "Alembic" in text
    assert "migration" in text.lower()


# 19 -----------------------------------------------------------------------


def test_sdd_19_python_testing_covers_pytest(skills_root: Path) -> None:
    text = _read_skill(skills_root, "python-testing")
    assert "pytest" in text.lower()


# 20 -----------------------------------------------------------------------


def test_sdd_20_python_quality_detects_before_installing(skills_root: Path) -> None:
    """Detect the project's declared gates; never install tooling it did not declare."""
    text = _read_skill(skills_root, "python-quality")
    lowered = text.lower()

    assert "detect before assuming" in lowered
    assert "never install" in lowered
