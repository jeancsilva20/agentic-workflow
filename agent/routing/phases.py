"""Which role a dispatched run is actually performing.

The Jira workflow is one deep agent, not eleven graphs: a run picks up at the
column the poller resumed it from and works forward until it parks at the next
gate. So the model is chosen once per dispatch, and the honest question is not
"which PASSO is this" but "what is the most demanding phase in the segment this
run has to cover" — a run that starts at the trigger column has to write the
spec before it parks, so it cannot be routed as if it were only doing triage.

That makes the resumed column the routing key. Everything else (dashboard,
Slack, Linear, a PR comment) is a coding run.
"""

from __future__ import annotations

from .roles import AgentRole

# The role a run resumed from each column has to be good enough for. Keyed by
# the attribute name in ``agent.jira_poller`` so a deployment that renames its
# columns keeps working — the names are env-configurable, the phases are not.
_COLUMN_ROLE_BY_CONSTANT: tuple[tuple[str, AgentRole], ...] = (
    # Trigger: read the card, run the harness, write the spec, park at gate 1.
    ("COLUMN_TRIGGER", AgentRole.SPEC_AUTHOR),
    ("COLUMN_IN_PROGRESS", AgentRole.CODING_AGENT),
    # Gate 1 said no: revise the spec and park at gate 1 again.
    ("COLUMN_ADJUST_SPEC", AgentRole.SPEC_ADJUSTER),
    # Gate 1 said yes: implement, open the PR, park at gate 2.
    ("COLUMN_SPEC_APPROVED", AgentRole.CODING_AGENT),
    # Gate 2 said no: read the PR review and fix the code.
    ("COLUMN_ADJUST_CODE", AgentRole.CODE_ADJUSTER),
    # Gate 2 said yes: pre-merge preparation — final checks, OpenSpec archive
    # (whose `needs_manual_merge` reconciliation is the hard part), doc updates.
    ("COLUMN_CODE_APPROVED", AgentRole.OPENSPEC_VERIFIER),
    # Merged by a human: administrative closing only.
    ("COLUMN_MERGED", AgentRole.ARCHIVE_AGENT),
)

DEFAULT_DISPATCH_ROLE = AgentRole.CODING_AGENT

# Where each role is chosen at runtime, or why it cannot be chosen yet. The
# routing endpoint reports this so an operator reading the table can tell a
# route that runs from a route that only exists on paper.
ROLE_SELECTION: dict[AgentRole, str] = {
    AgentRole.SPEC_AUTHOR: "Jira run resumed from the trigger column",
    AgentRole.SPEC_ADJUSTER: "Jira run resumed from the adjust-spec column",
    AgentRole.CODING_AGENT: "Jira run resumed from the spec-approved column; every non-Jira run",
    AgentRole.CODE_ADJUSTER: "Jira run resumed from the adjust-code column",
    AgentRole.OPENSPEC_VERIFIER: "Jira run resumed from the code-approved column (pre-merge)",
    AgentRole.ARCHIVE_AGENT: "Jira run resumed from the merged column (closing)",
    AgentRole.CODE_REVIEWER: "reviewer graph",
    AgentRole.DIFF_GROUPING: "reviewer graph, file grouping pass",
    AgentRole.REVIEW_CHAT: "PR review chat graph",
    AgentRole.STYLE_ANALYZER: "analyzer graph (review-style learning)",
    # Dormant: real phases, but they happen inside another role's run because
    # the workflow is a single graph. Splitting them into their own
    # invocations is a topology change, not a routing change — until then the
    # run they belong to is routed by its most demanding phase.
    AgentRole.JIRA_TRIAGE: "not selected: runs inside the spec_author run",
    AgentRole.PYTHON_HARNESS: "not selected: runs inside the spec_author run",
    AgentRole.SPEC_REVIEWER: "not selected: spec self-review runs inside the authoring run",
    AgentRole.DOCS_AGENT: "not selected: doc updates run inside the openspec_verifier run",
    AgentRole.ESCALATION_AGENT: "not selected: exhaustion parks the card for a human",
}

ACTIVE_ROLES: frozenset[AgentRole] = frozenset(
    {role for role, where in ROLE_SELECTION.items() if not where.startswith("not selected")}
)


def _column_roles() -> dict[str, AgentRole]:
    """Column name → role, read at call time because the names come from env."""
    from .. import jira_poller  # imported lazily: it pulls in the LangGraph client

    roles: dict[str, AgentRole] = {}
    for constant, role in _COLUMN_ROLE_BY_CONSTANT:
        column = getattr(jira_poller, constant, None)
        if isinstance(column, str) and column.strip():
            roles[column.strip().casefold()] = role
    return roles


def role_for_column(column: str | None) -> AgentRole | None:
    """The role for a run resumed from ``column``, or ``None`` if it maps to no phase.

    ``None`` covers the gate columns (a parked card waiting on a human) and any
    column this deployment added that the workflow doesn't know about.
    """
    if not isinstance(column, str) or not column.strip():
        return None
    return _column_roles().get(column.strip().casefold())


def role_for_dispatch(column: str | None) -> AgentRole:
    """The role to route a dispatched run as, falling back to plain coding work."""
    return role_for_column(column) or DEFAULT_DISPATCH_ROLE


def is_active(role: AgentRole) -> bool:
    """Whether a runtime call site can currently select ``role``."""
    return role in ACTIVE_ROLES
