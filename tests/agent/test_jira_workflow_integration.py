"""End-to-end orchestration test across the Jira integration's own pieces:
poller tick -> thread launch -> agent parks at a gate -> poller detects the
column change -> resumes -> parks at the next gate -> ... through all three
approval gates.

This does NOT exercise a real LLM, real Jira API, or real git/PR operations
(none of that infrastructure exists in this environment) — it verifies that
`agent/jira_poller.py`, `agent/tools/jira_park_at_gate.py`, and the console
store (`agent-console/store.py`, loaded directly since it's outside the
`agent` package) click together correctly across a full run of the workflow,
using fakes for the Jira REST client and the LangGraph SDK client.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent import jira_poller
from agent.tools.jira_park_at_gate import jira_park_at_gate


def _load_console_store() -> Any:
    """Load agent-console/store.py directly by path (it's not an importable
    package — its directory name has a hyphen)."""
    console_dir = Path(__file__).resolve().parents[2] / "agent-console"
    module_name = "agent_console_store_for_tests"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, console_dir / "store.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


store_module = _load_console_store()


class _FakeJiraClient:
    """Fake LangGraph client tracking thread metadata by thread_id, in-memory."""

    def __init__(self) -> None:
        self.metadata: dict[str, dict[str, Any]] = {}
        self.threads = MagicMock()
        self.threads.get = AsyncMock(side_effect=self._get)
        self.threads.create = AsyncMock(side_effect=self._create)
        self.threads.update = AsyncMock(side_effect=self._update)

    async def _get(self, thread_id: str) -> dict[str, Any]:
        if thread_id not in self.metadata:
            raise Exception("not found")  # noqa: TRY002
        return {"metadata": self.metadata[thread_id]}

    async def _create(self, *, thread_id: str, if_exists: str, metadata: dict[str, Any]) -> None:
        self.metadata.setdefault(thread_id, {}).update(metadata)

    async def _update(self, *, thread_id: str, metadata: dict[str, Any]) -> None:
        self.metadata.setdefault(thread_id, {}).update(metadata)


def _issue(key: str, status: str) -> dict[str, Any]:
    return {"key": key, "fields": {"status": {"name": status}, "labels": []}}


@pytest.fixture(autouse=True)
def _flags_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the poller brakes off — they're read from the environment at import
    time, and a deployment env with `JIRA_POLLER_SHADOW_MODE=1` would otherwise
    suppress every launch and resume this file asserts on."""
    monkeypatch.setattr(jira_poller, "JIRA_POLLER_SHADOW_MODE", False)
    monkeypatch.setattr(jira_poller, "JIRA_POLLER_PAUSED", False)


@contextmanager
def _parking_allowed(thread_id: str) -> Iterator[None]:
    """The fakes `jira_park_at_gate` needs to run without Jira or LangGraph."""
    with (
        patch(
            "agent.tools.jira_park_at_gate.get_config",
            return_value={"configurable": {"thread_id": thread_id}},
        ),
        patch(
            "agent.tools.jira_park_at_gate.add_comment",
            new_callable=AsyncMock,
            return_value={"success": True},
        ),
        patch(
            "agent.tools.jira_park_at_gate.transition_to_column",
            new_callable=AsyncMock,
            return_value={"success": True},
        ),
    ):
        yield


@pytest.mark.asyncio
async def test_full_workflow_through_all_three_gates() -> None:
    console_store = store_module.ConsoleStore(poll_interval_seconds=60)
    fake_client = _FakeJiraClient()
    issue_key = "SSAI-100"
    thread_id = jira_poller.generate_thread_id_from_jira_issue(issue_key)

    async def fake_push(kind: str, payload: dict[str, Any]) -> None:
        if kind == "tick":
            console_store.record_tick(payload.get("step_a", {}), payload.get("step_b", {}))
        elif kind == "run":
            issue = payload.pop("issue_key")
            action = payload.pop("action")
            console_store.record_run_event(issue, action, **payload)
        elif kind == "log":
            console_store.record_log(payload.get("message", ""))

    # Board state is a simple mutable box the fake search_issues reads from,
    # so each phase of the test can move the "card" itself.
    board = {"column": "BACKLOG"}

    async def fake_search_issues(jql: str, **_kwargs: Any) -> dict[str, Any]:
        if "BACKLOG" in jql:
            return (
                {"issues": [_issue(issue_key, "BACKLOG")]}
                if board["column"] == "BACKLOG"
                else {"issues": []}
            )
        return {"issues": [_issue(issue_key, board["column"])]}

    with (
        patch("agent.utils.console_events._push", side_effect=fake_push),
        patch.object(jira_poller, "search_issues", side_effect=fake_search_issues),
        patch.object(
            jira_poller, "get_comments", new_callable=AsyncMock, return_value={"comments": []}
        ),
        patch.object(jira_poller, "dispatch_agent_run", new_callable=AsyncMock),
        patch("agent.jira_poller.get_client", return_value=fake_client),
        patch("agent.tools.jira_park_at_gate.get_client", return_value=fake_client),
        patch("agent.utils.console_events.AGENT_CONSOLE_URL", "http://fake-console"),
    ):
        # --- Tick 1: card is in BACKLOG, no thread yet -> launches one ---
        tick_1 = await jira_poller.tick()
        assert tick_1["step_a"]["launched"] == 1
        state_after_launch = console_store.status()
        assert state_after_launch["overall_status"] == "working"
        assert state_after_launch["metrics"]["working"] == 1

        # --- Agent finishes spec generation, parks at gate 1 ---
        board["column"] = jira_poller.COLUMN_TRIGGER  # card hasn't visibly moved to the gate yet
        with (
            patch(
                "agent.tools.jira_park_at_gate.get_config",
                return_value={"configurable": {"thread_id": thread_id}},
            ),
            patch(
                "agent.tools.jira_park_at_gate.add_comment",
                new_callable=AsyncMock,
                return_value={"success": True},
            ),
            patch(
                "agent.tools.jira_park_at_gate.transition_to_column",
                new_callable=AsyncMock,
                return_value={"success": True},
            ),
        ):
            park_result = await jira_park_at_gate(
                issue_key, jira_poller.COLUMN_SPEC_REVIEW, "Spec ready for review."
            )
        assert park_result["end_run"] is True
        board["column"] = jira_poller.COLUMN_SPEC_REVIEW  # now reflect the real transition

        state_after_park_1 = console_store.status()
        waiting_run = next(r for r in state_after_park_1["runs"] if r["issue_key"] == issue_key)
        assert waiting_run["status"] == "waiting"
        assert waiting_run["column"] == jira_poller.COLUMN_SPEC_REVIEW
        assert fake_client.metadata[thread_id]["jira_gate_history"] == [
            {
                "column": jira_poller.COLUMN_SPEC_REVIEW,
                "parked_at": fake_client.metadata[thread_id]["jira_parked_at"],
            }
        ]

        # --- Tick 2: no change yet at the gate -> stays unchanged ---
        tick_2 = await jira_poller.tick()
        assert tick_2["step_b"]["unchanged"] == 1
        assert tick_2["step_b"]["resumed"] == 0

        # --- Human approves the spec ---
        board["column"] = jira_poller.COLUMN_SPEC_APPROVED
        tick_3 = await jira_poller.tick()
        assert tick_3["step_b"]["resumed"] == 1
        assert fake_client.metadata[thread_id]["jira_parked"] is False

        state_after_resume = console_store.status()
        resumed_run = next(r for r in state_after_resume["runs"] if r["issue_key"] == issue_key)
        assert resumed_run["status"] == "working"

        # --- Agent implements, requests review, parks at gate 2 ---
        board["column"] = jira_poller.COLUMN_SPEC_APPROVED
        with (
            patch(
                "agent.tools.jira_park_at_gate.get_config",
                return_value={"configurable": {"thread_id": thread_id}},
            ),
            patch(
                "agent.tools.jira_park_at_gate.add_comment",
                new_callable=AsyncMock,
                return_value={"success": True},
            ),
            patch(
                "agent.tools.jira_park_at_gate.transition_to_column",
                new_callable=AsyncMock,
                return_value={"success": True},
            ),
        ):
            await jira_park_at_gate(issue_key, jira_poller.COLUMN_CODE_REVIEW, "Code ready.")
        board["column"] = jira_poller.COLUMN_CODE_REVIEW

        assert len(fake_client.metadata[thread_id]["jira_gate_history"]) == 2

        # --- Human approves code, merges, agent parks at gate 3 (merge) ---
        board["column"] = jira_poller.COLUMN_CODE_APPROVED
        tick_4 = await jira_poller.tick()
        assert tick_4["step_b"]["resumed"] == 1

        board["column"] = jira_poller.COLUMN_CODE_APPROVED
        with (
            patch(
                "agent.tools.jira_park_at_gate.get_config",
                return_value={"configurable": {"thread_id": thread_id}},
            ),
            patch(
                "agent.tools.jira_park_at_gate.add_comment",
                new_callable=AsyncMock,
                return_value={"success": True},
            ),
            patch(
                "agent.tools.jira_park_at_gate.transition_to_column",
                new_callable=AsyncMock,
                return_value={"success": True},
            ),
        ):
            await jira_park_at_gate(
                issue_key, jira_poller.COLUMN_MERGE, "PR opened, ready to merge."
            )
        board["column"] = jira_poller.COLUMN_MERGE

        final_history = fake_client.metadata[thread_id]["jira_gate_history"]
        assert [h["column"] for h in final_history] == [
            jira_poller.COLUMN_SPEC_REVIEW,
            jira_poller.COLUMN_CODE_REVIEW,
            jira_poller.COLUMN_MERGE,
        ]

        # Duplicate tick with nothing new must stay idempotent (no re-launch,
        # no phantom resume) — the same invariant task 5.5 tests at the unit
        # level, exercised here across the full sequence instead of one step.
        tick_5 = await jira_poller.tick()
        assert tick_5["step_a"]["launched"] == 0
        assert tick_5["step_b"]["unchanged"] == 1

        # --- Em Merge is a human gate: the card sits there until a HUMAN
        # merges the PR and moves it. Nothing in the tick advances it. ---
        assert board["column"] == jira_poller.COLUMN_MERGE
        assert fake_client.metadata[thread_id]["jira_parked"] is True

        # --- Human merged on GitHub and moved the card -> post-merge resume ---
        board["column"] = jira_poller.COLUMN_MERGED
        tick_6 = await jira_poller.tick()
        assert tick_6["step_b"]["resumed"] == 1
        assert fake_client.metadata[thread_id]["jira_parked"] is False

        # The agent closes the card itself; Done is not a gate, so no further
        # park happens and the next tick has nothing left to do.
        board["column"] = jira_poller.COLUMN_DONE
        tick_7 = await jira_poller.tick()
        assert tick_7["step_a"]["launched"] == 0
        assert tick_7["step_b"] == {"resumed": 0, "unchanged": 0}


@pytest.mark.asyncio
async def test_adjust_spec_loop_reparks_the_same_thread_each_cycle() -> None:
    """Em Revisão de Spec -> Ajustar Spec -> (agent revises) -> Em Revisão de
    Spec, twice, on ONE thread. Each rejection must resume, and each revision
    must re-park at the same gate."""
    fake_client = _FakeJiraClient()
    issue_key = "SSAI-200"
    thread_id = jira_poller.generate_thread_id_from_jira_issue(issue_key)
    board = {"column": jira_poller.COLUMN_SPEC_REVIEW}
    fake_client.metadata[thread_id] = {
        "jira_issue_key": issue_key,
        "jira_parked": True,
        "jira_parked_column": jira_poller.COLUMN_SPEC_REVIEW,
    }

    async def fake_search_issues(jql: str, **_kwargs: Any) -> dict[str, Any]:
        if jira_poller.COLUMN_TRIGGER in jql:
            return {"issues": []}
        return {"issues": [_issue(issue_key, board["column"])]}

    resumed_columns: list[str] = []

    async def record_dispatch(*args: Any, **kwargs: Any) -> None:
        resumed_columns.append(kwargs["metadata"]["jira_column"])

    with (
        patch.object(jira_poller, "search_issues", side_effect=fake_search_issues),
        patch.object(
            jira_poller, "get_comments", new_callable=AsyncMock, return_value={"comments": []}
        ),
        patch.object(jira_poller, "dispatch_agent_run", side_effect=record_dispatch),
        patch("agent.jira_poller.get_client", return_value=fake_client),
        patch("agent.tools.jira_park_at_gate.get_client", return_value=fake_client),
        patch("agent.utils.console_events.AGENT_CONSOLE_URL", None),
    ):
        for cycle in range(2):
            # Human rejects the spec.
            board["column"] = jira_poller.COLUMN_ADJUST_SPEC
            tick = await jira_poller.tick()
            assert tick["step_b"]["resumed"] == 1, f"cycle {cycle} did not resume"
            assert fake_client.metadata[thread_id]["jira_parked"] is False

            # Agent revises the spec on the same branch and parks again.
            with _parking_allowed(thread_id):
                result = await jira_park_at_gate(
                    issue_key, jira_poller.COLUMN_SPEC_REVIEW, f"Spec revised (cycle {cycle})."
                )
            assert result["end_run"] is True
            board["column"] = jira_poller.COLUMN_SPEC_REVIEW

            # Sitting at the gate again is a no-op until the human moves it.
            idle = await jira_poller.tick()
            assert idle["step_b"] == {"resumed": 0, "unchanged": 1}

    assert resumed_columns == [jira_poller.COLUMN_ADJUST_SPEC] * 2
    assert [h["column"] for h in fake_client.metadata[thread_id]["jira_gate_history"]] == [
        jira_poller.COLUMN_SPEC_REVIEW,
        jira_poller.COLUMN_SPEC_REVIEW,
    ]


@pytest.mark.asyncio
async def test_adjust_code_loop_reparks_at_code_review_for_a_fresh_reviewer_pass() -> None:
    """Em Code Review -> Ajustar Code -> (agent fixes) -> Em Code Review.

    Each re-entry into Em Code Review is a new park at that gate, which is what
    makes the reviewer run again on the new version of the PR.
    """
    fake_client = _FakeJiraClient()
    issue_key = "SSAI-201"
    thread_id = jira_poller.generate_thread_id_from_jira_issue(issue_key)
    board = {"column": jira_poller.COLUMN_CODE_REVIEW}
    fake_client.metadata[thread_id] = {
        "jira_issue_key": issue_key,
        "jira_parked": True,
        "jira_parked_column": jira_poller.COLUMN_CODE_REVIEW,
    }

    async def fake_search_issues(jql: str, **_kwargs: Any) -> dict[str, Any]:
        if jira_poller.COLUMN_TRIGGER in jql:
            return {"issues": []}
        return {"issues": [_issue(issue_key, board["column"])]}

    dispatched_prompts: list[str] = []

    async def record_dispatch(*args: Any, **kwargs: Any) -> None:
        dispatched_prompts.append(args[1])

    with (
        patch.object(jira_poller, "search_issues", side_effect=fake_search_issues),
        patch.object(
            jira_poller,
            "get_comments",
            new_callable=AsyncMock,
            return_value={"comments": [{"body": "see the PR review comments"}]},
        ),
        patch.object(jira_poller, "dispatch_agent_run", side_effect=record_dispatch),
        patch("agent.jira_poller.get_client", return_value=fake_client),
        patch("agent.tools.jira_park_at_gate.get_client", return_value=fake_client),
        patch("agent.utils.console_events.AGENT_CONSOLE_URL", None),
    ):
        for cycle in range(2):
            board["column"] = jira_poller.COLUMN_ADJUST_CODE
            tick = await jira_poller.tick()
            assert tick["step_b"]["resumed"] == 1, f"cycle {cycle} did not resume"

            with _parking_allowed(thread_id):
                await jira_park_at_gate(
                    issue_key, jira_poller.COLUMN_CODE_REVIEW, f"Fixes pushed (cycle {cycle})."
                )
            board["column"] = jira_poller.COLUMN_CODE_REVIEW

    assert len(dispatched_prompts) == 2
    for prompt in dispatched_prompts:
        assert jira_poller.COLUMN_ADJUST_CODE in prompt
        assert jira_poller.COLUMN_CODE_REVIEW in prompt
    # Two separate visits to the code-review gate == two reviewer passes.
    assert [h["column"] for h in fake_client.metadata[thread_id]["jira_gate_history"]] == [
        jira_poller.COLUMN_CODE_REVIEW,
        jira_poller.COLUMN_CODE_REVIEW,
    ]


@pytest.mark.asyncio
async def test_merged_resume_carries_the_post_merge_context() -> None:
    """`Mergeado` resumes the same thread and is described to the agent as a
    move out of `Em Merge` — i.e. a post-merge event, not a merge request."""
    fake_client = _FakeJiraClient()
    issue_key = "SSAI-202"
    thread_id = jira_poller.generate_thread_id_from_jira_issue(issue_key)
    fake_client.metadata[thread_id] = {
        "jira_issue_key": issue_key,
        "jira_parked": True,
        "jira_parked_column": jira_poller.COLUMN_MERGE,
    }

    async def fake_search_issues(jql: str, **_kwargs: Any) -> dict[str, Any]:
        if jira_poller.COLUMN_TRIGGER in jql:
            return {"issues": []}
        return {"issues": [_issue(issue_key, jira_poller.COLUMN_MERGED)]}

    with (
        patch.object(jira_poller, "search_issues", side_effect=fake_search_issues),
        patch.object(
            jira_poller, "get_comments", new_callable=AsyncMock, return_value={"comments": []}
        ),
        patch.object(jira_poller, "dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch,
        patch("agent.jira_poller.get_client", return_value=fake_client),
        patch("agent.utils.console_events.AGENT_CONSOLE_URL", None),
    ):
        tick = await jira_poller.tick()

    assert tick["step_b"]["resumed"] == 1
    assert mock_dispatch.await_args.args[0] == thread_id
    prompt = mock_dispatch.await_args.args[1]
    assert f"moved from '{jira_poller.COLUMN_MERGE}' to '{jira_poller.COLUMN_MERGED}'" in prompt
    assert mock_dispatch.await_args.kwargs["metadata"]["jira_column"] == jira_poller.COLUMN_MERGED
