"""Frontend coverage for the console page (section 29 of the spec).

Two layers, on purpose:

* what the server renders — name, logo slot, the config controls' markup — is
  asserted here, so a broken template fails the normal Python test run;
* what the page *does* — loading state, error handling, rollback — needs a DOM,
  and lives in ``tests/frontend/console_ui.test.mjs``. This module shells out to
  it so ``pytest`` stays the single entry point, and skips (rather than fails)
  where Node or its ``jsdom`` dev dependency is not installed, since the Python
  side of this repo must remain installable without npm.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from app import app as flask_app

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND_TESTS = "agent-console/tests/frontend/*.test.mjs"


@pytest.fixture
def client():
    flask_app.config.update(TESTING=True)
    with flask_app.test_client() as client:
        yield client


@pytest.fixture
def page(client) -> str:
    response = client.get("/")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_page_is_branded_sensedia_agentic_workflow(page: str) -> None:
    assert "<title>Sensedia Agentic Workflow</title>" in page
    assert "<h1>Sensedia Agentic Workflow</h1>" in page
    assert "Jira Agent Console" not in page


def test_header_has_a_logo_slot_ahead_of_the_name(page: str) -> None:
    assert 'id="sensedia-logo"' in page
    assert 'class="sensedia-logo"' in page
    # No official Sensedia asset ships with the repo, so the header must fall
    # back to an empty slot — never to a redrawn approximation of the mark.
    assert 'id="sensedia-logo-slot"' in page
    assert page.index('id="sensedia-logo"') < page.index("<h1>Sensedia Agentic Workflow</h1>")


def test_official_logo_asset_is_available() -> None:
    static_dir = _REPO_ROOT / "agent-console" / "static"
    logo = static_dir / "sensedia-logo.svg"
    assert logo.is_file()
    assert logo.read_text(encoding="utf-8").lstrip().startswith("<svg")


def test_config_panel_exposes_the_operational_controls(page: str) -> None:
    assert 'id="agent-config"' in page
    assert "Agent Configuration" in page
    for control_id in ("cfg-shadow", "cfg-interval"):
        assert f'id="{control_id}"' in page
    # The router owns model and effort, so the panel offers no picker for them.
    for gone in ('id="cfg-model"', 'id="cfg-effort"'):
        assert gone not in page
    # Values only ever arrive from the API — no interval is baked in.
    assert "claude" not in page.lower()


def test_config_panel_reports_the_routing_table_instead_of_offering_it(page: str) -> None:
    """Routing replaced the pickers: a table the operator reads, not edits."""
    assert 'id="routing-body"' in page
    for column in ("Agent", "Model", "Effort"):
        assert f"<th>{column}</th>" in page
    assert '"/api/config/routing"' in page
    # A read-only table has no form control of its own.
    assert page.index('id="routing-body"') > page.index('id="agent-config"')


def test_observability_sections_are_rendered(page: str) -> None:
    for element_id in (
        "active-agents",
        "active-agents-body",
        "tick-log",
        "agent-log",
    ):
        assert f'id="{element_id}"' in page
    assert 'class="log-grid"' in page
    assert "Usage today" not in page
    assert ">Queue<" not in page
    assert "Card detail" not in page
    assert '"/api/observability/live"' in page
    # Active agents sits before the run and split-log panels.
    assert page.index('class="metrics"') < page.index('id="active-agents"')
    assert page.index('id="active-agents"') < page.index('class="panels"')


def test_recovery_control_can_reset_a_card_without_a_visible_run(page: str) -> None:
    assert 'id="recovery-form"' in page
    assert 'id="recovery-issue-key"' in page
    assert 'id="recovery-reset"' in page
    assert '"/api/cards/"' in page


def test_the_page_never_carries_a_credential(page: str) -> None:
    """The console makes no outbound call, so it has no token to embed."""
    for secret_marker in ("api_key", "apiKey", "Authorization", "Bearer ", "ls__", "sk-"):
        assert secret_marker not in page
    # And nothing to send one to: every request target is a console path.
    assert "https://" not in page


def test_shadow_indicator_has_both_unmistakable_states(page: str) -> None:
    assert 'id="shadow-indicator"' in page
    assert "SHADOW MODE" in page
    assert "LIVE EXECUTION" in page


def test_existing_dashboard_areas_are_preserved(page: str) -> None:
    for element_id in (
        "status-dot",
        "status-text",
        "m-working",
        "m-waiting",
        "m-dead",
        "runs-body",
        "tick-log",
        "agent-log",
    ):
        assert f'id="{element_id}"' in page
    for removed_id in ("m-queued", "queue-body", "log", "usage-overview", "card-detail"):
        assert f'id="{removed_id}"' not in page


def test_page_talks_to_the_real_config_endpoints(client) -> None:
    page = client.get("/").get_data(as_text=True)
    assert '"/api/config"' in page

    config = client.get("/api/config").get_json()
    for field in ("shadow_mode", "polling_interval_minutes", "available_polling_intervals"):
        assert field in config

    routing = client.get("/api/config/routing").get_json()["routing"]
    assert routing and all({"role", "model", "effort"} <= set(entry) for entry in routing)


def test_browser_behaviour_suite_passes() -> None:
    """Run the jsdom suite: saving state, success, error, rollback, refresh."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    if not (_REPO_ROOT / "node_modules" / "jsdom").exists():
        pytest.skip("jsdom is not installed (run `npm install`)")

    result = subprocess.run(  # noqa: S603 — fixed argv, no shell
        [node, "--test", _FRONTEND_TESTS],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
