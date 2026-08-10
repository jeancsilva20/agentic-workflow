"""Central source of truth for the Jira workflow status/column mapping.

Jira Cloud uses **status names** in its API and JQL queries. The visual
**column names** the user sees on the board happen to be the same strings
in the SSAI project — but they are conceptually distinct:

  Jira status (API term)  → what ``jira_transition_issue`` / JQL receives
  Column label (UI term)  → what a human reads on the board

When the board is configured so every status name equals its column label
(as SSAI is today), the two string sets are identical. This module
documents both so no future change accidentally conflates them, and so
every caller has one place to look up the full 11-step workflow.

----------------------------------------------------------------------
SSAI Board Audit — 2026-08-10
----------------------------------------------------------------------
Method: ``GET /rest/api/3/issue/{key}/transitions`` on SSAI issues.

The SSAI Jira board is configured with "Global Transitions" — every
status can reach every other status in a single API call, so there is
no need to chain through intermediate states. The exact status names
returned by the transitions endpoint match the ``COLUMN_*`` defaults in
``agent/jira_poller.py`` without exception:

  BACKLOG              (trigger; default for JIRA_COLUMN_TRIGGER)
  In Progress          (implementation only; default for JIRA_COLUMN_IN_PROGRESS)
  Em Revisão de Spec   (gate 1; default for JIRA_COLUMN_SPEC_REVIEW)
  Spec Aprovada        (default for JIRA_COLUMN_SPEC_APPROVED)
  Ajustar Spec         (default for JIRA_COLUMN_ADJUST_SPEC)
  Em Code Review       (gate 2; default for JIRA_COLUMN_CODE_REVIEW)
  Code Review Aprovado (default for JIRA_COLUMN_CODE_APPROVED)
  Ajustar Code         (default for JIRA_COLUMN_ADJUST_CODE)
  Em Merge             (gate 3; default for JIRA_COLUMN_MERGE)
  Mergeado             (default for JIRA_COLUMN_MERGED)
  Done                 (default for JIRA_COLUMN_DONE)

Divergences found: NONE — the strings hardcoded as env-var defaults in
``jira_poller.py`` are the exact status names the Jira API returns.

The status ID for a transition is per-issue-state (changes as the card
moves), but the status *name* is stable. ``transition_to_column`` in
``agent/utils/jira.py`` resolves names to IDs at call time, so callers
need only deal with the stable name strings documented here.
----------------------------------------------------------------------

Spec-phase note
---------------
The card stays in ``BACKLOG`` for the *entire* spec phase. The first
agent-initiated status change is parking at ``Em Revisão de Spec`` via
``jira_park_at_gate`` once the OpenSpec artifacts are committed and
pushed.  ``In Progress`` is only entered when resuming from
``Spec Aprovada`` — it marks the *start of implementation*, not spec
authoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TransitionInitiator(StrEnum):
    """Who initiates the transition *into* a given workflow step."""

    HUMAN = "human"
    """A human moves the card manually (gate decision or initial filing)."""

    AGENT_AUTO = "agent_auto"
    """The agent moves the card automatically, without waiting for approval."""

    AGENT_GATE = "agent_gate"
    """The agent parks the card here via ``jira_park_at_gate`` and waits."""


@dataclass(frozen=True)
class WorkflowStep:
    """One step in the 11-column Jira workflow.

    Attributes:
        jira_status:  The exact string sent to the Jira API for transitions and
            JQL queries.  This is what ``jira_transition_issue`` and
            ``status in (...)`` JQL receive.  Configured at runtime by the
            corresponding ``JIRA_COLUMN_*`` environment variable.
        column_label: The human-readable label shown on the Jira board.  In the
            SSAI project these are identical to ``jira_status``, but the two are
            conceptually different — one is an API identifier, the other is a UI
            label.  Always prefer ``jira_status`` when constructing JQL or
            calling the transitions endpoint; use ``column_label`` for comments,
            logs, and other human-facing text.
        env_var:      The environment variable that overrides the default value
            for this step's Jira status.
        poller_constant: The attribute name on ``agent.jira_poller`` that holds
            the runtime-resolved status string (populated from ``env_var`` at
            import time).
        transition_initiator: Who moves the card *into* this column.
        description:  Short human-readable note on what this step means.
    """

    jira_status: str
    column_label: str
    env_var: str
    poller_constant: str
    transition_initiator: TransitionInitiator
    description: str = ""


# ---------------------------------------------------------------------------
# The 11-step workflow, in board order.
# ---------------------------------------------------------------------------
#
# Spec-phase flow (COLUMN_TRIGGER → COLUMN_SPEC_REVIEW):
#   The agent reads context from BACKLOG, writes the spec, and parks
#   directly at Em Revisão de Spec.  IN_PROGRESS is NOT part of the spec
#   phase — the card never visits it while spec work is in flight.
#
# Implementation-phase flow (COLUMN_SPEC_APPROVED → COLUMN_CODE_REVIEW):
#   Resuming from Spec Aprovada, the agent's first act is to move the card
#   to In Progress. Only then does it begin coding.
#
# ---------------------------------------------------------------------------

WORKFLOW_STEPS: tuple[WorkflowStep, ...] = (
    WorkflowStep(
        jira_status="BACKLOG",
        column_label="Backlog",
        env_var="JIRA_COLUMN_TRIGGER",
        poller_constant="COLUMN_TRIGGER",
        transition_initiator=TransitionInitiator.HUMAN,
        description=(
            "Trigger column. A human (or monitoring integration) files the card here. "
            "The poller detects it and starts a fresh agent thread for spec authoring. "
            "The card stays in BACKLOG throughout the entire spec phase — the first "
            "agent-initiated status change is parking at Em Revisão de Spec."
        ),
    ),
    WorkflowStep(
        jira_status="In Progress",
        column_label="Em Desenvolvimento",
        env_var="JIRA_COLUMN_IN_PROGRESS",
        poller_constant="COLUMN_IN_PROGRESS",
        transition_initiator=TransitionInitiator.AGENT_AUTO,
        description=(
            "Implementation phase. The agent moves the card here as the *first step* "
            "when resuming from Spec Aprovada — never during spec authoring. "
            "Autonomous execution: implement, test, lint, commit, push, open/update PR, "
            "then park at Em Code Review."
        ),
    ),
    WorkflowStep(
        jira_status="Em Revisão de Spec",
        column_label="Em Revisão de Spec",
        env_var="JIRA_COLUMN_SPEC_REVIEW",
        poller_constant="COLUMN_SPEC_REVIEW",
        transition_initiator=TransitionInitiator.AGENT_GATE,
        description=(
            "Gate 1: spec approval. The agent parks here via jira_park_at_gate after "
            "committing and pushing the OpenSpec artifacts and confirming the remote "
            "branch exists. A human reviews and moves the card. "
            "This is the first status change the agent makes on a new card."
        ),
    ),
    WorkflowStep(
        jira_status="Spec Aprovada",
        column_label="Spec Aprovada",
        env_var="JIRA_COLUMN_SPEC_APPROVED",
        poller_constant="COLUMN_SPEC_APPROVED",
        transition_initiator=TransitionInitiator.HUMAN,
        description=(
            "Spec approved by a human. The poller detects this and resumes the thread. "
            "First agent action: move the card to In Progress, then implement."
        ),
    ),
    WorkflowStep(
        jira_status="Ajustar Spec",
        column_label="Ajustar Spec",
        env_var="JIRA_COLUMN_ADJUST_SPEC",
        poller_constant="COLUMN_ADJUST_SPEC",
        transition_initiator=TransitionInitiator.HUMAN,
        description=(
            "Spec rejected. The agent reads comments (or reasons independently if none), "
            "revises the OpenSpec on the same branch, and parks at Em Revisão de Spec "
            "again. This loop can repeat any number of times."
        ),
    ),
    WorkflowStep(
        jira_status="Em Code Review",
        column_label="Em Code Review",
        env_var="JIRA_COLUMN_CODE_REVIEW",
        poller_constant="COLUMN_CODE_REVIEW",
        transition_initiator=TransitionInitiator.AGENT_GATE,
        description=(
            "Gate 2: code review. The reviewer graph runs every time the card enters "
            "here. The agent parks via jira_park_at_gate after the reviewer graph "
            "completes without blocking findings."
        ),
    ),
    WorkflowStep(
        jira_status="Code Review Aprovado",
        column_label="Code Review Aprovado",
        env_var="JIRA_COLUMN_CODE_APPROVED",
        poller_constant="COLUMN_CODE_APPROVED",
        transition_initiator=TransitionInitiator.HUMAN,
        description=(
            "Code approved by a human. The agent resumes for pre-merge preparation: "
            "final checks, openspec_archive, doc updates — all on the same branch/PR."
        ),
    ),
    WorkflowStep(
        jira_status="Ajustar Code",
        column_label="Ajustar Code",
        env_var="JIRA_COLUMN_ADJUST_CODE",
        poller_constant="COLUMN_ADJUST_CODE",
        transition_initiator=TransitionInitiator.HUMAN,
        description=(
            "Code review rejected. Primary source: GitHub PR reviews and comments. "
            "The agent applies fixes, re-runs tests/self-review, and parks at "
            "Em Code Review again (reviewer graph re-runs on the new version)."
        ),
    ),
    WorkflowStep(
        jira_status="Em Merge",
        column_label="Em Merge",
        env_var="JIRA_COLUMN_MERGE",
        poller_constant="COLUMN_MERGE",
        transition_initiator=TransitionInitiator.AGENT_GATE,
        description=(
            "Gate 3: merge approval. The agent parks here after all pre-merge work "
            "(archive, docs, self-review of pre-merge diff) is committed and pushed. "
            "A human merges the PR on GitHub and then moves the card."
        ),
    ),
    WorkflowStep(
        jira_status="Mergeado",
        column_label="Mergeado",
        env_var="JIRA_COLUMN_MERGED",
        poller_constant="COLUMN_MERGED",
        transition_initiator=TransitionInitiator.HUMAN,
        description=(
            "The PR was merged by a human on GitHub. The agent confirms the merge, "
            "records the final run result, posts a closing comment, and moves to Done. "
            "No new functional code is written in this phase."
        ),
    ),
    WorkflowStep(
        jira_status="Done",
        column_label="Done",
        env_var="JIRA_COLUMN_DONE",
        poller_constant="COLUMN_DONE",
        transition_initiator=TransitionInitiator.AGENT_AUTO,
        description="Terminal state. The agent moves the card here after confirming the merge.",
    ),
)

# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def get_workflow_step(poller_constant: str) -> WorkflowStep | None:
    """Return the :class:`WorkflowStep` for a given ``jira_poller`` constant name.

    ``poller_constant`` is a string like ``"COLUMN_TRIGGER"`` — the attribute
    name on ``agent.jira_poller``, not the status value itself.  Returns
    ``None`` if the constant is not mapped.
    """
    for step in WORKFLOW_STEPS:
        if step.poller_constant == poller_constant:
            return step
    return None


def gate_steps() -> tuple[WorkflowStep, ...]:
    """The three agent-park gates (Em Revisão de Spec, Em Code Review, Em Merge)."""
    return tuple(
        s for s in WORKFLOW_STEPS if s.transition_initiator is TransitionInitiator.AGENT_GATE
    )


def post_gate_steps() -> tuple[WorkflowStep, ...]:
    """The five columns a human moves a parked card *to* after a gate decision.

    The poller's Step B must query all of these (plus the gates themselves) so
    it can detect the human decision even after the card leaves the gate column.
    """
    return tuple(
        s
        for s in WORKFLOW_STEPS
        if s.transition_initiator is TransitionInitiator.HUMAN
        and s.poller_constant not in ("COLUMN_TRIGGER", "COLUMN_SPEC_APPROVED", "COLUMN_MERGED")
        # COLUMN_TRIGGER is the Step-A trigger, not a post-gate.
        # COLUMN_SPEC_APPROVED and COLUMN_MERGED are post-gate, but Step B
        # already covers them through _post_gate_columns() in jira_poller.
    )
