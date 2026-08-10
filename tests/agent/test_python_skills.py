from __future__ import annotations

from pathlib import Path

import pytest
import yaml

SKILLS_DIR = Path(__file__).resolve().parents[2] / "agent" / "skills"
AGENTS_MD = Path(__file__).resolve().parents[2] / "AGENTS.md"

PYTHON_SKILLS = (
    "python-engineering",
    "fastapi-engineering",
    "python-database",
    "python-testing",
    "python-quality",
    "python-harness",
)


def _frontmatter(skill: str) -> dict[str, object]:
    text = (SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{skill} has no frontmatter"
    raw = text.split("---\n", 2)[1]
    parsed = yaml.safe_load(raw)
    assert isinstance(parsed, dict)
    return parsed


@pytest.mark.parametrize("skill", PYTHON_SKILLS)
def test_python_skill_is_served_and_discoverable(skill: str) -> None:
    """SkillsMiddleware lists skills by frontmatter, so a missing or mismatched
    `name`/`description` makes the skill invisible to the agent even though the
    file is on the static route."""
    meta = _frontmatter(skill)

    assert meta["name"] == skill
    description = meta["description"]
    assert isinstance(description, str)
    # The description is the only thing the agent sees before deciding to read
    # the skill; a one-liner cannot convey when the skill applies.
    assert len(description) > 120


def test_harness_skill_states_the_two_rules_the_flow_depends_on() -> None:
    """The harness may not guess a test command, and it must persist the report
    outside the repo clone so it never lands in `git status` or the PR."""
    text = (SKILLS_DIR / "python-harness" / "SKILL.md").read_text(encoding="utf-8")

    assert "HARNESS COMPLETE" in text
    assert "HARNESS BLOCKED" in text
    assert "/harness/<ISSUE-KEY>-harness-report.md" in text
    assert "outside the repository" in text


def test_agents_md_documents_contextual_loading_and_the_harness_step() -> None:
    text = AGENTS_MD.read_text(encoding="utf-8")

    assert "## Python Skill Loading" in text
    loading = text.split("## Python Skill Loading", 1)[1]
    for skill in PYTHON_SKILLS:
        assert f"`{skill}`" in loading

    step_zero = text.split("### Step 0 — Python Harness Engineer", 1)[1].split("### Gate 1", 1)[0]
    assert step_zero.index("repository cloned") < step_zero.index("Run Python Harness Engineer")
    assert step_zero.index("Run Python Harness Engineer") < step_zero.index("OpenSpec Explore")


def test_jira_prompt_runs_the_harness_between_branch_creation_and_the_spec() -> None:
    from agent.prompt import construct_system_prompt

    prompt = construct_system_prompt(working_dir="/workspace", jira_issue_key="SSAI-42")

    assert prompt.index("**PASSO 2 — Prepare environment.**") < prompt.index(
        "**PASSO 2.5 — Run the Python Harness Engineer.**"
    )
    assert prompt.index("**PASSO 2.5 — Run the Python Harness Engineer.**") < prompt.index(
        "**PASSO 3 — Analyze code and generate the spec.**"
    )
    assert "/openspec-skills/python-harness/SKILL.md" in prompt
    # The report path is resolved, not a literal placeholder: it has to name a
    # real directory outside the clone for the agent to write it there.
    assert "<working_dir>/harness/SSAI-42-harness-report.md" not in prompt
    assert "/workspace/harness/SSAI-42-harness-report.md" in prompt
