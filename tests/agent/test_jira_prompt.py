from __future__ import annotations

import pytest

from agent import jira_poller
from agent.prompt import construct_system_prompt


def test_jira_sections_absent_without_issue_key() -> None:
    prompt = construct_system_prompt(working_dir="/workspace")

    assert "Jira Workflow" not in prompt
    assert "Spec Grounding Rules" not in prompt
    assert "Auto-Review Loops" not in prompt
    assert "jira_park_at_gate" not in prompt


def test_jira_sections_present_with_issue_key() -> None:
    prompt = construct_system_prompt(working_dir="/workspace", jira_issue_key="SSAI-42")

    assert "SSAI-42" in prompt
    assert "### Jira Workflow" in prompt
    assert "### Spec Grounding Rules" in prompt
    assert "### Auto-Review Loops" in prompt
    assert "### Reviewer Graph Integration" in prompt
    assert "### Canonical Docs Update" in prompt


def test_jira_branch_naming_uses_issue_key() -> None:
    prompt = construct_system_prompt(working_dir="/workspace", jira_issue_key="SSAI-42")

    assert "feat/spec-SSAI-42-<descricao-curta>" in prompt
    assert "git check-ref-format --branch" in prompt


def test_jira_gate_tool_and_review_cycle_tool_are_named() -> None:
    prompt = construct_system_prompt(working_dir="/workspace", jira_issue_key="SSAI-42")

    assert "jira_park_at_gate(issue_key, column_name, comment_body)" in prompt
    assert "log_review_cycle(phase, cycle_number, outcome)" in prompt
    assert "request_self_review" in prompt


def test_jira_issue_key_is_stripped() -> None:
    prompt = construct_system_prompt(working_dir="/workspace", jira_issue_key="  SSAI-7  ")

    assert "SSAI-7" in prompt
    assert "SSAI-7  " not in prompt


def test_blank_jira_issue_key_is_treated_as_absent() -> None:
    prompt = construct_system_prompt(working_dir="/workspace", jira_issue_key="   ")

    assert "Jira Workflow" not in prompt


def test_prompt_reflects_column_name_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """A JIRA_COLUMN_* override must reach every section, not just the poller.

    Regression test: the first cut only threaded 5 of 11 column names through
    to the prompt (the ones the poller itself queries by name); the other 6
    were hardcoded Portuguese strings that would silently drift from an
    operator's env-var override.
    """
    monkeypatch.setattr(jira_poller, "COLUMN_SPEC_REVIEW", "Revisão Técnica")
    monkeypatch.setattr(jira_poller, "COLUMN_SPEC_APPROVED", "Spec OK")
    monkeypatch.setattr(jira_poller, "COLUMN_MERGED", "Foi Pro Ar")

    prompt = construct_system_prompt(working_dir="/workspace", jira_issue_key="SSAI-42")

    assert "Revisão Técnica" in prompt
    assert "Spec OK" in prompt
    assert "Foi Pro Ar" in prompt
    assert "Em Revisão de Spec" not in prompt
    assert "Mergeado" not in prompt
