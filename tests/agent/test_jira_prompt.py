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
    assert "### Resuming After a Human Decision" in prompt
    assert "### Pre-Merge Preparation" in prompt
    assert "### Post-Merge Closing" in prompt


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


def test_prompt_guards_spec_review_move_on_a_pushed_remote_branch() -> None:
    """The card must not reach `Em Revisão de Spec` on an unpushed spec."""
    prompt = construct_system_prompt(working_dir="/workspace", jira_issue_key="SSAI-42")

    assert "Guard before `Em Revisão de Spec`" in prompt
    assert "ls-remote --heads origin" in prompt
    assert (
        "Do not move to `Em Revisão de Spec` unless the OpenSpec artifacts are committed" in prompt
    )


def test_prompt_puts_archive_and_docs_before_the_merge_gate() -> None:
    """Archive + docs belong to the delivery, on the same branch/PR, before
    `Em Merge` — not to a separate post-merge docs PR."""
    prompt = construct_system_prompt(working_dir="/workspace", jira_issue_key="SSAI-42")

    pre_merge = prompt.split("### Pre-Merge Preparation", 1)[1].split("### Post-Merge Closing", 1)[
        0
    ]
    assert "openspec_archive" in pre_merge
    assert "same branch and the same PR" in pre_merge
    assert "do not open a second PR for docs" in pre_merge

    assert "Put doc updates in a **separate** PR" not in prompt


def test_prompt_post_merge_phase_is_administrative_only() -> None:
    prompt = construct_system_prompt(working_dir="/workspace", jira_issue_key="SSAI-42")

    post_merge = prompt.split("### Post-Merge Closing", 1)[1]
    assert "introduce no new functional changes on the branch" in post_merge
    assert "gh pr view <number> --json state,merged,mergedAt" in post_merge
    assert "Move the card to `Done`" in post_merge


def test_prompt_sources_adjust_code_fixes_from_github() -> None:
    prompt = construct_system_prompt(working_dir="/workspace", jira_issue_key="SSAI-42")

    adjust_code = prompt.split("`Ajustar Code` — the code needs fixes", 1)[1].split(
        "`Mergeado` — the merge already happened", 1
    )[0]
    assert "pulls/<number>/reviews" in adjust_code
    assert "pulls/<number>/comments" in adjust_code
    assert "list_review_findings" in adjust_code
    assert "structured list" in adjust_code
    # Jira comments are explicitly secondary to the GitHub review.
    assert adjust_code.index("reviews") < adjust_code.index("Only then consult the Jira comments")


def test_prompt_never_auto_merges_or_self_approves() -> None:
    prompt = construct_system_prompt(working_dir="/workspace", jira_issue_key="SSAI-42")

    assert "Never move a card to `Code Review Aprovado` yourself" in prompt
    assert "you never move a card into `Mergeado` yourself" in prompt
    assert "you never merge a PR yourself" in prompt


def test_prompt_spec_phase_does_not_move_card_to_in_progress() -> None:
    """The spec phase must NOT move the card to ``In Progress``.

    The card stays in the trigger column (``BACKLOG``) for the entire spec
    phase.  The first agent-initiated status change is parking at
    ``Em Revisão de Spec`` via ``jira_park_at_gate`` — never an intermediate
    move to ``In Progress``.

    ``In Progress`` belongs exclusively to the implementation phase that
    begins when the agent resumes from ``Spec Aprovada``.
    """
    prompt = construct_system_prompt(working_dir="/workspace", jira_issue_key="SSAI-42")

    passo_1 = prompt.split("**PASSO 1", 1)[1].split("**PASSO 2", 1)[0]
    # PASSO 1 must NOT instruct a transition to In Progress.
    assert 'jira_transition_issue(SSAI-42, "In Progress")' not in passo_1
    # PASSO 1 should explicitly say the card stays in the trigger column.
    assert "Do not move the card out of `BACKLOG`" in passo_1
    # The spec phase note must appear before PASSO 3 so the agent cannot
    # miss it on its way to writing the spec.
    assert prompt.index("Do not move the card out of `BACKLOG`") < prompt.index(
        "**PASSO 3 — Analyze code and generate the spec.**"
    )
    # The first transition mentioned for the spec phase is the gate park.
    assert "jira_park_at_gate" in passo_1
    assert "col_spec_review" not in passo_1  # rendered, not raw placeholder
    assert "Em Revisão de Spec" in passo_1


def test_prompt_reviews_the_pre_merge_commits_before_parking_at_the_merge_gate() -> None:
    """Archive/doc commits land after the human's code-review approval, so they
    are the one part of the PR nobody reviewed — the agent has to check them."""
    prompt = construct_system_prompt(working_dir="/workspace", jira_issue_key="SSAI-42")

    pre_merge = prompt.split("### Pre-Merge Preparation", 1)[1].split("### Post-Merge Closing", 1)[
        0
    ]
    assert "they are the only part of the PR nobody has reviewed" in pre_merge
    # Reviewing them has to happen before the park, not after.
    assert pre_merge.index("Review what you just added") < pre_merge.index("jira_park_at_gate")
    # Functional code smuggled into the pre-merge commits goes back through review.
    assert "go back through `Em Code Review`" in pre_merge


def test_prompt_makes_the_agent_own_every_non_gate_transition() -> None:
    prompt = construct_system_prompt(working_dir="/workspace", jira_issue_key="SSAI-42")

    ownership = prompt.split("**Every automatic move is yours to make.**", 1)[1].split("\n\n", 1)[0]
    for transition in (
        # Implementation start — the ONLY time the agent moves to In Progress.
        "`Spec Aprovada` → `In Progress`",
        "`Ajustar Spec` → `Em Revisão de Spec`",
        "`Ajustar Code` → `Em Code Review`",
        "`Code Review Aprovado` → `Em Merge`",
        "`Mergeado` → `Done`",
    ):
        assert transition in ownership
    # BACKLOG → In Progress must NOT appear: the spec phase keeps the card in
    # the trigger column; In Progress is reserved for implementation only.
    assert "`BACKLOG` → `In Progress`" not in ownership


def test_prompt_runs_the_reviewer_on_every_code_review_entry() -> None:
    prompt = construct_system_prompt(working_dir="/workspace", jira_issue_key="SSAI-42")

    assert "including each pass through the `Ajustar Code` loop" in prompt


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


def test_prompt_names_the_verified_target_repo_clone() -> None:
    """PASSO 2 must not tell the agent to clone a repo that is already prepped."""
    prompt = construct_system_prompt(
        working_dir="/sandbox",
        jira_issue_key="SSAI-42",
        target_repo_dir="/sandbox/sensedia-backend-case",
    )

    assert "already cloned at `/sandbox/sensedia-backend-case`" in prompt
    assert "Clone the target repository as usual" not in prompt


def test_prompt_binds_git_to_the_target_repo_dir() -> None:
    """Git must never depend on the shell's current directory."""
    prompt = construct_system_prompt(
        working_dir="/sandbox",
        jira_issue_key="SSAI-42",
        target_repo_dir="/sandbox/sensedia-backend-case",
    )

    assert "git -C /sandbox/sensedia-backend-case" in prompt
    assert "The target repository is the only repository you touch." in prompt
    assert "git -C /sandbox/sensedia-backend-case ls-remote --heads origin" in prompt


def test_prompt_keeps_harness_output_out_of_the_clone() -> None:
    prompt = construct_system_prompt(
        working_dir="/sandbox",
        jira_issue_key="SSAI-42",
        target_repo_dir="/sandbox/sensedia-backend-case",
    )

    assert "/sandbox/harness/SSAI-42-harness-report.md" in prompt


def test_prompt_falls_back_to_cloning_when_no_repo_was_prepped() -> None:
    prompt = construct_system_prompt(working_dir="/sandbox", jira_issue_key="SSAI-42")

    assert "Clone the target repository as usual" in prompt
    assert "git -C <target-repo-dir>" in prompt


def test_prompt_guards_code_review_move_on_pr_creation() -> None:
    """The card must not reach Em Code Review unless the PR was created successfully.

    The guard must:
    - Appear in the spec-approved / in-progress implementation section.
    - Require confirming ``open_pull_request`` returned ``success: true`` and a PR URL.
    - Instruct the agent to comment the failure with ``jira_add_comment`` and end the
      turn without advancing the card when ``open_pull_request`` fails.
    """
    prompt = construct_system_prompt(working_dir="/workspace", jira_issue_key="SSAI-42")

    # The guard section must exist and be correctly labelled.
    assert "Guard before `Em Code Review`" in prompt

    # Must require a confirmed success and a PR URL before parking.
    assert "success: true" in prompt
    assert "PR URL" in prompt

    # On failure the agent posts a comment and ends its turn without advancing.
    assert "jira_add_comment" in prompt
    assert "end your turn" in prompt

    # The guard must live inside the "Resuming After a Human Decision" section,
    # specifically within the Spec Aprovada / in-progress path — before the agent
    # reaches the col_adjust_code (Ajustar Code) sub-section of that same block.
    resume_section = prompt.split("### Resuming After a Human Decision", 1)[1]
    spec_approved_block = resume_section.split("`Ajustar Code`", 1)[0]
    assert "Guard before `Em Code Review`" in spec_approved_block
