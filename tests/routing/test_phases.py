"""Which role a dispatched run is routed as, from the Jira column it resumed at."""

from __future__ import annotations

import pytest

from agent import jira_poller
from agent.routing import AgentRole, resolve_model, routing_table
from agent.routing.phases import (
    ACTIVE_ROLES,
    DEFAULT_DISPATCH_ROLE,
    ROLE_SELECTION,
    is_active,
    role_for_column,
    role_for_dispatch,
)

_COLUMN_ROLES = [
    ("COLUMN_TRIGGER", AgentRole.SPEC_AUTHOR),
    ("COLUMN_IN_PROGRESS", AgentRole.CODING_AGENT),
    ("COLUMN_ADJUST_SPEC", AgentRole.SPEC_ADJUSTER),
    ("COLUMN_SPEC_APPROVED", AgentRole.CODING_AGENT),
    ("COLUMN_ADJUST_CODE", AgentRole.CODE_ADJUSTER),
    ("COLUMN_CODE_APPROVED", AgentRole.OPENSPEC_VERIFIER),
    ("COLUMN_MERGED", AgentRole.ARCHIVE_AGENT),
]


@pytest.mark.parametrize(("constant", "expected"), _COLUMN_ROLES)
def test_each_resumable_column_routes_to_its_phase(constant: str, expected: AgentRole) -> None:
    assert role_for_column(getattr(jira_poller, constant)) is expected


def test_trigger_column_is_routed_as_spec_authoring() -> None:
    """The first run writes the spec before it parks — Haiku triage would write it."""
    route = resolve_model(role_for_dispatch(jira_poller.COLUMN_TRIGGER))

    assert route.role is AgentRole.SPEC_AUTHOR
    assert route.effort == "high"


def test_pre_merge_column_is_routed_as_verification() -> None:
    """Archiving is mechanical, but reconciling the spec afterwards is not."""
    assert role_for_dispatch(jira_poller.COLUMN_CODE_APPROVED) is AgentRole.OPENSPEC_VERIFIER


@pytest.mark.parametrize(
    "constant", ["COLUMN_SPEC_REVIEW", "COLUMN_CODE_REVIEW", "COLUMN_MERGE", "COLUMN_DONE"]
)
def test_gate_columns_map_to_no_phase(constant: str) -> None:
    """A card at a gate is waiting on a human; no run should be resumed there."""
    assert role_for_column(getattr(jira_poller, constant)) is None


@pytest.mark.parametrize("column", [None, "", "   ", "Some Column This Board Invented"])
def test_a_run_without_a_known_column_is_coding_work(column: str | None) -> None:
    """Dashboard, Slack, Linear and PR-comment runs arrive with no Jira column."""
    assert role_for_column(column) is None
    assert role_for_dispatch(column) is DEFAULT_DISPATCH_ROLE


def test_column_matching_ignores_case_and_padding() -> None:
    assert (
        role_for_column(f"  {jira_poller.COLUMN_ADJUST_CODE.upper()} ") is AgentRole.CODE_ADJUSTER
    )


def test_columns_are_read_when_asked_not_at_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """Column names are env-configurable, so a deployment can rename them."""
    monkeypatch.setattr(jira_poller, "COLUMN_ADJUST_CODE", "Precisa de Ajustes")

    assert role_for_column("Precisa de Ajustes") is AgentRole.CODE_ADJUSTER


def test_every_role_says_where_it_is_selected() -> None:
    assert set(ROLE_SELECTION) == set(AgentRole)


def test_dormant_roles_are_reported_as_inactive() -> None:
    """A phase that runs inside another role's run must not read as a live route."""
    for role in (
        AgentRole.JIRA_TRIAGE,
        AgentRole.PYTHON_HARNESS,
        AgentRole.SPEC_REVIEWER,
        AgentRole.DOCS_AGENT,
        AgentRole.ESCALATION_AGENT,
    ):
        assert not is_active(role)
        assert role not in ACTIVE_ROLES


def test_dispatchable_roles_are_reported_as_active() -> None:
    for _constant, role in _COLUMN_ROLES:
        assert is_active(role)
    assert is_active(AgentRole.CODE_REVIEWER)
    assert is_active(AgentRole.DIFF_GROUPING)


def test_routing_table_marks_each_row() -> None:
    table = {entry["role"]: entry for entry in routing_table()}

    assert table["coding_agent"]["active"] is True
    assert table["jira_triage"]["active"] is False
    assert table["jira_triage"]["selected_by"].startswith("not selected")
