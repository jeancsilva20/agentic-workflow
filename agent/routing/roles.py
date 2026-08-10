"""The named agent roles the model router knows how to route.

Every model call the Jira workflow makes belongs to exactly one of these
roles. The role — not a per-thread setting, not a console toggle — is what
decides which model and reasoning effort the call runs with, so the name has
to be stable enough to appear in the routing table, in telemetry, and in a
run's logs.
"""

from __future__ import annotations

from enum import StrEnum


class AgentRole(StrEnum):
    """A workflow activity with its own model/effort budget.

    ``str`` based so a role round-trips through JSON (the routing endpoint),
    thread metadata, and log lines without an explicit conversion.
    """

    JIRA_TRIAGE = "jira_triage"
    PYTHON_HARNESS = "python_harness"
    SPEC_AUTHOR = "spec_author"
    SPEC_REVIEWER = "spec_reviewer"
    SPEC_ADJUSTER = "spec_adjuster"
    CODING_AGENT = "coding_agent"
    CODE_ADJUSTER = "code_adjuster"
    OPENSPEC_VERIFIER = "openspec_verifier"
    CODE_REVIEWER = "code_reviewer"
    # Not a workflow step: the reviewer's best-effort "AI sorted" pass that
    # buckets a PR's files for the review UI. It needs a route like everything
    # else, and it is mechanical classification, not review.
    DIFF_GROUPING = "diff_grouping"
    # Also not a workflow step: the read-only chat a human holds with the
    # review of an open PR. It answers questions about a review that already
    # exists rather than producing one, so it is not the reviewer's route.
    REVIEW_CHAT = "review_chat"
    # Background job: mines a repo's review history to learn what that team
    # flags. Nobody is waiting on it, but it reads a lot and writes a prompt
    # the reviewer then follows.
    STYLE_ANALYZER = "style_analyzer"
    DOCS_AGENT = "docs_agent"
    ARCHIVE_AGENT = "archive_agent"
    ESCALATION_AGENT = "escalation_agent"


def coerce_role(role: AgentRole | str) -> AgentRole:
    """Accept either the enum or its wire value (thread metadata, JSON, logs)."""
    if isinstance(role, AgentRole):
        return role
    try:
        return AgentRole(role)
    except ValueError as exc:
        raise ValueError(f"unknown agent role: {role!r}") from exc
