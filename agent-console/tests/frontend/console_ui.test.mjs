/**
 * Frontend coverage for the Sensedia Agentic Workflow console page.
 *
 * The page is a single server-rendered template with inline JS and no build
 * step, so the test loads that exact template into jsdom and stubs `fetch`.
 * Nothing is re-implemented here: what runs is the code the operator's browser
 * runs, which is the only way assertions about loading state, error handling
 * and rollback mean anything.
 *
 * Covers the 14 frontend scenarios of section 29 of the spec.
 *
 * Run with:  node --test agent-console/tests/frontend/
 * (also driven from pytest via tests/test_frontend.py)
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";

const TEMPLATE_PATH = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "templates",
  "index.html",
);
const TEMPLATE_HTML = readFileSync(TEMPLATE_PATH, "utf8");

/** Shape mirrors GET /api/config: current values plus the option catalogs.
 *  Model and effort are absent on purpose — the router picks them per agent
 *  role, so the console has nothing to offer the operator there. */
const BACKEND_CONFIG = {
  shadow_mode: true,
  polling_interval_minutes: 1,
  available_polling_intervals: [1, 5, 10, 30, 60],
};

const EMPTY_STATE = {
  overall_status: "idle",
  poller: { last_tick_at: null, seconds_since_tick: null, healthy: false },
  metrics: { working: 0, waiting: 0, queued: 0, dead: 0 },
  queue: [],
  runs: [],
  log: [],
};

/** Shape mirrors GET /api/config/routing: the router's baseline table. */
const ROUTING = [
  {
    role: "jira_triage",
    model: "anthropic:claude-haiku-4-5",
    effort: null,
    effort_supported: false,
    complexity: "low",
    reason: "jira_triage default route",
    escalation_reason: null,
    active: true,
    selected_by: "Jira run resumed from the trigger column",
  },
  {
    role: "code_reviewer",
    model: "anthropic:claude-opus-4-5",
    effort: "high",
    effort_supported: true,
    complexity: "low",
    reason: "code_reviewer default route",
    escalation_reason: null,
    active: false,
    selected_by: "not selected: runs inside the coding_agent run",
  },
];

/** Shape mirrors GET /api/observability/usage (DailyUsage.as_dict). */
const EMPTY_USAGE = {
  date: "2026-08-10",
  runs: 0,
  input_tokens: 0,
  output_tokens: 0,
  total_tokens: 0,
  runs_missing_tokens: 0,
  cost: null,
  runs_missing_cost: 0,
  by_agent: [],
  by_model: [],
  cards: [],
};

function jsonResponse(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

/**
 * Boot the real template in jsdom against a fake console backend.
 *
 * `putHandler` receives the parsed PUT body and returns whatever `fetch`
 * should resolve to; the default merges the patch like the real API does.
 */
function boot({
  config = {},
  state = EMPTY_STATE,
  putHandler,
  routing = ROUTING,
  live = [],
  usage = EMPTY_USAGE,
  cardUsage = {},
  cardTimeline = {},
} = {}) {
  const backend = { ...BACKEND_CONFIG, ...config };
  const puts = [];
  const gets = [];

  const respondToPut = putHandler
    ? putHandler
    : async (patch) => {
        Object.assign(backend, patch);
        return jsonResponse({ ...backend, warnings: [] });
      };

  const fetchStub = async (url, init = {}) => {
    const method = (init.method || "GET").toUpperCase();
    if (method === "GET") gets.push(url);
    if (url === "/api/state") return jsonResponse(state);
    if (url === "/api/config" && method === "GET") return jsonResponse({ ...backend });
    if (url === "/api/config" && method === "PUT") {
      const patch = JSON.parse(init.body);
      puts.push(patch);
      return respondToPut(patch);
    }
    if (url === "/api/config/routing") return jsonResponse({ routing });
    if (url === "/api/observability/live") return jsonResponse({ active: live });
    if (url === "/api/observability/usage") return jsonResponse(usage);
    const card = url.match(/^\/api\/observability\/cards\/([^/]+)\/(usage|timeline)$/);
    if (card) {
      const key = decodeURIComponent(card[1]);
      if (card[2] === "usage") {
        if (!cardUsage[key]) return jsonResponse({ error: "not stubbed" }, 500);
        return jsonResponse(cardUsage[key]);
      }
      return jsonResponse({ jira_issue_key: key, runs: cardTimeline[key] || [] });
    }
    throw new Error(`unexpected fetch: ${method} ${url}`);
  };

  const dom = new JSDOM(TEMPLATE_HTML, {
    runScripts: "dangerously",
    url: "http://localhost:5050/",
    beforeParse(window) {
      window.fetch = fetchStub;
    },
  });

  const { window } = dom;
  const $ = (id) => window.document.getElementById(id);
  const optionValues = (id) => [...$(id).options].map((o) => o.value);

  return {
    window,
    backend,
    puts,
    gets,
    $,
    optionValues,
    click(el) {
      el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    },
    async settle() {
      // The stubs resolve immediately, so a couple of macrotask turns is enough
      // for the fetch chains started on load (or by a change event) to finish.
      for (let i = 0; i < 5; i++) await new Promise((resolve) => setTimeout(resolve, 0));
    },
    change(id, mutate) {
      const el = $(id);
      mutate(el);
      el.dispatchEvent(new window.Event("change", { bubbles: true }));
    },
    close() {
      window.close();
    },
  };
}

/** 1. The application is named "Sensedia Agentic Workflow". */
test("page and header carry the Sensedia Agentic Workflow name", async () => {
  const ui = boot();
  await ui.settle();

  assert.equal(ui.window.document.title, "Sensedia Agentic Workflow");
  assert.equal(
    ui.window.document.querySelector(".app-header h1").textContent.trim(),
    "Sensedia Agentic Workflow",
  );
  ui.close();
});

/** 2. The Sensedia logo sits at the top left, with a slot when it is absent. */
test("header renders the Sensedia logo slot before the name", async () => {
  const ui = boot();
  await ui.settle();

  const logo = ui.$("sensedia-logo");
  assert.equal(logo.tagName, "IMG");
  assert.ok(logo.classList.contains("sensedia-logo"));
  assert.match(logo.getAttribute("src"), /sensedia-logo/);

  // No official asset in the repo yet: the fallback slot must exist and the
  // header must never fall back to a hand-drawn approximation of the mark.
  const slot = ui.$("sensedia-logo-slot");
  assert.ok(slot, "a placeholder slot must be ready to hold the official asset");
  assert.match(slot.getAttribute("aria-label"), /Sensedia logo/i);

  const brand = ui.window.document.querySelector(".brand");
  const children = [...brand.children].map((el) => el.id || el.tagName);
  assert.ok(children.indexOf("sensedia-logo") < children.indexOf("H1"), "logo comes before the name");
  ui.close();
});

/** 3. Every control starts from the backend, never from a hardcoded default. */
test("controls are inert until the backend answers, then show its values", async () => {
  const ui = boot({ config: { polling_interval_minutes: 30 } });

  // Before the first response nothing is editable and no value is implied.
  assert.equal(ui.$("cfg-interval").disabled, true);
  assert.equal(ui.$("cfg-interval").options.length, 0);
  assert.equal(ui.$("shadow-indicator").className, "shadow-indicator unknown");

  await ui.settle();

  assert.equal(ui.$("cfg-interval").disabled, false);
  assert.equal(ui.$("cfg-interval").value, "30");
  assert.equal(ui.$("cfg-shadow").checked, true);
  ui.close();
});

/** 4. Shadow mode indicator and toggle mirror the backend, both ways. */
test("shadow indicator distinguishes shadow mode from live execution", async () => {
  const shadow = boot({ config: { shadow_mode: true } });
  await shadow.settle();

  assert.ok(shadow.$("shadow-indicator").classList.contains("shadow"));
  assert.equal(shadow.$("shadow-indicator-title").textContent, "SHADOW MODE");
  assert.match(shadow.$("shadow-indicator-detail").textContent, /Monitoring only/i);
  assert.equal(shadow.$("cfg-shadow").checked, true);
  assert.equal(shadow.$("cfg-shadow-state").textContent, "ON");
  shadow.close();

  const live = boot({ config: { shadow_mode: false } });
  await live.settle();

  assert.ok(live.$("shadow-indicator").classList.contains("live"));
  assert.equal(live.$("shadow-indicator-title").textContent, "LIVE EXECUTION");
  assert.match(live.$("shadow-indicator-detail").textContent, /can execute/i);
  assert.equal(live.$("cfg-shadow").checked, false);
  assert.equal(live.$("cfg-shadow-state").textContent, "OFF");
  live.close();
});

/** 5. Model and effort are not operator settings any more. */
test("the panel offers no model or effort control", async () => {
  const ui = boot();
  await ui.settle();

  assert.equal(ui.$("cfg-model"), null);
  assert.equal(ui.$("cfg-effort"), null);
  ui.close();
});

/** 7. Polling intervals come from the backend. */
test("polling dropdown is built from available_polling_intervals", async () => {
  const ui = boot();
  await ui.settle();

  assert.deepEqual(ui.optionValues("cfg-interval"), ["1", "5", "10", "30", "60"]);
  assert.deepEqual(
    [...ui.$("cfg-interval").options].map((o) => o.textContent),
    ["1 minute", "5 minutes", "10 minutes", "30 minutes", "60 minutes"],
  );
  ui.close();
});

/** 8. A save in flight shows "Saving…" and blocks concurrent changes. */
test("changing a control shows a saving state and blocks concurrent saves", async () => {
  let release;
  const ui = boot({
    putHandler: () => new Promise((resolve) => { release = resolve; }),
  });
  await ui.settle();

  ui.change("cfg-interval", (el) => { el.value = "10"; });
  await ui.settle();

  assert.equal(ui.$("cfg-status").textContent, "Saving…");
  assert.ok(ui.$("cfg-status").classList.contains("saving"));
  assert.equal(ui.$("cfg-interval").disabled, true);
  assert.equal(ui.$("cfg-shadow").disabled, true, "other controls are locked while a save runs");

  // A second change while the first is in flight must not reach the backend.
  ui.change("cfg-shadow", (el) => { el.checked = false; });
  await ui.settle();
  assert.equal(ui.puts.length, 1);

  release(jsonResponse({ ...BACKEND_CONFIG, polling_interval_minutes: 10, warnings: [] }));
  await ui.settle();

  assert.equal(ui.$("cfg-interval").disabled, false);
  ui.close();
});

/** 9. A successful save is confirmed and reaches the backend as sent. */
test("a successful save confirms and keeps the new value", async () => {
  const ui = boot();
  await ui.settle();

  ui.change("cfg-shadow", (el) => { el.checked = false; });
  await ui.settle();

  assert.deepEqual(ui.puts, [{ shadow_mode: false }]);
  assert.equal(ui.$("cfg-status").textContent, "Saved");
  assert.ok(ui.$("cfg-status").classList.contains("ok"));
  assert.equal(ui.$("cfg-shadow").checked, false);
  assert.equal(ui.$("cfg-shadow-state").textContent, "OFF");
  // The header indicator follows the confirmed change, not the click.
  assert.ok(ui.$("shadow-indicator").classList.contains("live"));
  ui.close();
});

/** 10. A rejected save surfaces the backend's reason. */
test("a rejected save shows the backend error message", async () => {
  const ui = boot({
    putHandler: async () =>
      jsonResponse({ error: "polling_interval_minutes must be one of 1, 5, 10, 30, 60" }, 400),
  });
  await ui.settle();

  ui.change("cfg-interval", (el) => { el.value = "10"; });
  await ui.settle();

  assert.ok(ui.$("cfg-status").classList.contains("error"));
  assert.match(ui.$("cfg-status").textContent, /must be one of/);
  ui.close();
});

/** 11. A failed save rolls the control back to the value actually in effect. */
test("a failed save rolls every control back to the backend value", async () => {
  const ui = boot({
    config: { shadow_mode: true, polling_interval_minutes: 1 },
    putHandler: async () => { throw new Error("network down"); },
  });
  await ui.settle();

  ui.change("cfg-shadow", (el) => { el.checked = false; });
  await ui.settle();
  assert.equal(ui.$("cfg-shadow").checked, true, "toggle returns to the persisted value");
  assert.equal(ui.$("cfg-shadow-state").textContent, "ON");
  assert.ok(ui.$("shadow-indicator").classList.contains("shadow"));

  ui.change("cfg-interval", (el) => { el.value = "60"; });
  await ui.settle();
  assert.equal(ui.$("cfg-interval").value, "1");

  assert.match(ui.$("cfg-status").textContent, /reverted/i);
  assert.equal(ui.$("cfg-interval").disabled, false, "controls are usable again after a failure");
  ui.close();
});

/** 12. A page refresh shows the persisted configuration, not the last click. */
test("reloading the page renders the configuration the backend still holds", async () => {
  const first = boot();
  await first.settle();
  first.change("cfg-interval", (el) => { el.value = "10"; });
  await first.settle();
  assert.equal(first.backend.polling_interval_minutes, 10);
  first.close();

  // Fresh page against a backend that meanwhile holds a different value —
  // what renders must be the backend's, not anything cached in the browser.
  const reloaded = boot({ config: { polling_interval_minutes: 30, shadow_mode: false } });
  await reloaded.settle();

  assert.equal(reloaded.$("cfg-interval").value, "30");
  assert.equal(reloaded.$("cfg-shadow").checked, false);
  reloaded.close();
});

/** 13. The header survives a narrow viewport. */
test("header layout is responsive", () => {
  assert.match(TEMPLATE_HTML, /\.app-header\s*\{[^}]*flex-wrap:\s*wrap/);
  assert.match(TEMPLATE_HTML, /@media \(max-width: 720px\)[\s\S]*\.app-header\s*\{[^}]*flex-direction:\s*column/);
});

/** 14. The configuration area survives a narrow viewport. */
test("configuration area layout is responsive", () => {
  assert.match(TEMPLATE_HTML, /\.config-grid\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fit/);
  assert.match(TEMPLATE_HTML, /@media \(max-width: 720px\)[\s\S]*\.config-grid\s*\{[^}]*grid-template-columns:\s*1fr/);
});

/** 15. Routing is reported, not offered: a read-only table where the pickers were. */
test("model routing renders one read-only row per agent role", async () => {
  const ui = boot();
  await ui.settle();

  const rows = [...ui.$("routing-body").rows];
  assert.equal(rows.length, 2);
  assert.equal(ui.$("routing-body").querySelectorAll("select, input, button").length, 0);

  const [triage, reviewer] = rows.map((row) => [...row.cells].map((c) => c.textContent.trim()));
  assert.deepEqual(triage.slice(0, 3), [
    "jira_triage",
    "anthropic:claude-haiku-4-5",
    "N/A", // the model has no effort knob at all
  ]);
  assert.deepEqual(reviewer.slice(0, 3), [
    "code_reviewer",
    "anthropic:claude-opus-4-5",
    "high",
  ]);
  // A role nothing reaches must not read as a live route.
  assert.match(reviewer[3], /not on a live route/);
  assert.equal(ui.$("routing-empty").style.display, "none");
  ui.close();
});

/** 16. Active agents: one live row per running execution. */
test("active agents shows the running executions with their routing", async () => {
  const ui = boot({
    live: [
      {
        run_id: "run-1",
        started_at: new Date(Date.now() - 90_000).toISOString(),
        elapsed_seconds: 90,
        jira_issue_key: "SSAI-88",
        thread_id: "thread-1",
        agent_role: "coding_agent",
        model: "anthropic:claude-sonnet-5",
        effort: "medium",
        complexity_tier: "high",
        routing_reason: "coding_agent default route",
        escalation_reason: null,
      },
    ],
  });
  await ui.settle();

  const row = ui.$("active-agents-body").rows[0];
  const cells = [...row.cells].map((c) => c.textContent.trim());
  assert.equal(cells[0], "SSAI-88");
  assert.equal(cells[1], "coding_agent");
  assert.match(cells[2], /claude-sonnet-5 · medium/);
  assert.equal(cells[3], "HIGH");
  assert.match(cells[4], /1m 3\ds/); // elapsed is computed from started_at
  assert.equal(cells[5], "running");
  assert.ok(row.querySelector(".badge.tier-high"), "complexity is badged by tier");
  assert.equal(ui.$("active-agents-empty").style.display, "none");
  ui.close();
});

/** 17. An escalated run says so, with the reason attached. */
test("an escalated run carries an escalation badge and its reason", async () => {
  const ui = boot({
    live: [
      {
        run_id: "run-1",
        started_at: new Date().toISOString(),
        jira_issue_key: "SSAI-88",
        agent_role: "coding_agent",
        model: "anthropic:claude-opus-4-5",
        effort: "high",
        complexity_tier: "critical",
        routing_reason: "coding_agent escalated: 2 failed attempts",
        escalation_reason: "2 failed attempts",
      },
    ],
  });
  await ui.settle();

  const badge = ui.$("active-agents-body").querySelector(".badge.escalated");
  assert.ok(badge, "an escalated run must be visibly marked");
  assert.match(badge.textContent, /ESCALATED/);
  assert.equal(badge.getAttribute("title"), "2 failed attempts");
  ui.close();
});

/** 18. Live view stays empty — and says so — when nothing is running. */
test("active agents reports an empty live view rather than a blank table", async () => {
  const ui = boot();
  await ui.settle();

  assert.equal(ui.$("active-agents-body").rows.length, 0);
  assert.equal(ui.$("active-agents-empty").style.display, "block");
  assert.match(ui.$("active-agents-empty").textContent, /No agent is executing/i);
  ui.close();
});

/** 19. Today's usage: calls, tokens and cost, split by model. */
test("usage today shows calls, tokens and cost per model", async () => {
  const ui = boot({
    usage: {
      ...EMPTY_USAGE,
      runs: 3,
      input_tokens: 1200,
      output_tokens: 800,
      total_tokens: 2000,
      cost: 0.1234,
      cards: ["SSAI-88"],
      by_model: [
        { model: "anthropic:claude-haiku-4-5", runs: 1, total_tokens: 500, cost: 0.0004, runs_missing_cost: 0 },
        { model: "anthropic:claude-sonnet-5", runs: 1, total_tokens: 900, cost: 0.03, runs_missing_cost: 0 },
        { model: "anthropic:claude-opus-4-5", runs: 1, total_tokens: 600, cost: 0.093, runs_missing_cost: 0 },
      ],
    },
  });
  await ui.settle();

  const totals = ui.$("usage-totals").textContent;
  assert.match(totals, /LLM calls/i);
  assert.match(totals, /2,000/);
  assert.match(totals, /\$0\.1234/);

  const byModel = ui.$("usage-by-model").textContent;
  for (const label of ["Haiku", "Sonnet", "Opus"]) assert.match(byModel, new RegExp(label));
  assert.equal(ui.$("usage-empty").style.display, "none");
  assert.match(ui.$("usage-date").textContent, /2026-08-10/);
  ui.close();
});

/** 20. An unknown cost is never rendered as zero. */
test("a missing cost reads as unavailable, never as $0.00", async () => {
  const ui = boot({
    usage: {
      ...EMPTY_USAGE,
      runs: 1,
      total_tokens: 500,
      cost: null,
      runs_missing_cost: 1,
      by_model: [
        { model: "anthropic:claude-haiku-4-5", runs: 1, total_tokens: 500, cost: null, runs_missing_cost: 1 },
      ],
    },
  });
  await ui.settle();

  const rendered = ui.$("usage-totals").textContent + ui.$("usage-by-model").textContent;
  assert.match(rendered, /Cost unavailable/);
  assert.ok(!/\$0\.0000/.test(rendered), "an unknown cost must not be printed as a number");
  ui.close();
});

/** 21. Clicking a card opens its detail: totals, breakdowns and timeline. */
test("clicking a run opens the card detail with usage and timeline", async () => {
  const started = "2026-08-10T10:00:00+00:00";
  const ui = boot({
    state: {
      ...EMPTY_STATE,
      runs: [{ issue_key: "SSAI-88", status: "working", column: "Em Execução", time_parked_seconds: null }],
    },
    cardUsage: {
      "SSAI-88": {
        jira_issue_key: "SSAI-88",
        runs: 2,
        input_tokens: 1200,
        output_tokens: 800,
        total_tokens: 2000,
        runs_missing_tokens: 0,
        cost: 0.25,
        runs_missing_cost: 0,
        threads: ["thread-1"],
        by_agent: [{ agent_role: "coding_agent", runs: 2, total_tokens: 2000, cost: 0.25, runs_missing_cost: 0 }],
        by_model: [{ model: "anthropic:claude-sonnet-5", runs: 2, total_tokens: 2000, cost: 0.25, runs_missing_cost: 0 }],
        first_run_at: started,
        last_run_at: started,
      },
    },
    cardTimeline: {
      "SSAI-88": [
        {
          run_id: "run-1",
          status: "success",
          recorded_at: started,
          jira_issue_key: "SSAI-88",
          thread_id: "thread-1",
          agent_role: "spec_author",
          model: "anthropic:claude-sonnet-5",
          effort: "high",
          complexity_tier: "medium",
          routing_reason: "spec_author default route",
          escalation_reason: null,
          start_time: started,
          input_tokens: 600,
          output_tokens: 400,
          total_tokens: 1000,
          cost: 0.1,
          cost_source: "langsmith",
        },
      ],
    },
  });
  await ui.settle();

  assert.equal(ui.$("card-detail").hidden, true, "the detail stays closed until a card is clicked");

  ui.click(ui.$("runs-body").querySelector("tr[data-card]"));
  await ui.settle();

  assert.equal(ui.$("card-detail").hidden, false);
  assert.equal(ui.$("card-detail-key").textContent, "SSAI-88");
  assert.equal(ui.$("card-detail-loading").hidden, true);
  assert.equal(ui.$("card-detail-body").hidden, false);

  assert.match(ui.$("card-detail-totals").textContent, /2,000/);
  assert.match(ui.$("card-detail-totals").textContent, /\$0\.2500/);
  assert.match(ui.$("card-detail-by-model").textContent, /Sonnet/);
  assert.match(ui.$("card-detail-by-agent").textContent, /coding_agent/);

  const timeline = ui.$("card-detail-timeline").querySelectorAll("li");
  assert.equal(timeline.length, 1);
  assert.match(timeline[0].textContent, /spec_author/);
  assert.match(timeline[0].textContent, /claude-sonnet-5/);
  assert.match(timeline[0].textContent, /1,000 tokens/);
  assert.match(timeline[0].textContent, /\$0\.1000/);
  assert.match(timeline[0].textContent, /success/);

  ui.click(ui.$("card-detail-close"));
  assert.equal(ui.$("card-detail").hidden, true);
  ui.close();
});

/** 22. A card total priced from our own table is labelled as an estimate. */
test("a card total backed by estimated pricing says so", async () => {
  const ui = boot({
    state: { ...EMPTY_STATE, queue: [{ issue_key: "SSAI-90", waiting_seconds: 10 }] },
    cardUsage: {
      "SSAI-90": {
        jira_issue_key: "SSAI-90",
        runs: 1,
        input_tokens: 100,
        output_tokens: 100,
        total_tokens: 200,
        runs_missing_tokens: 0,
        cost: 0.02,
        runs_missing_cost: 0,
        threads: ["thread-9"],
        by_agent: [],
        by_model: [],
        first_run_at: null,
        last_run_at: null,
      },
    },
    cardTimeline: {
      "SSAI-90": [
        {
          run_id: "run-9",
          status: "success",
          recorded_at: "2026-08-10T11:00:00+00:00",
          agent_role: "docs_agent",
          model: "anthropic:claude-haiku-4-5",
          effort: null,
          complexity_tier: "low",
          routing_reason: "docs_agent default route",
          start_time: "2026-08-10T11:00:00+00:00",
          total_tokens: 200,
          cost: 0.02,
          cost_source: "estimated",
        },
      ],
    },
  });
  await ui.settle();

  ui.click(ui.$("queue-body").querySelector("tr[data-card]"));
  await ui.settle();

  assert.match(ui.$("card-detail-totals").textContent, /Estimated \$0\.0200/);
  assert.ok(ui.$("card-detail-totals").querySelector(".cost-estimated"));
  ui.close();
});

/** 23. The detail panel says it is loading before the numbers arrive. */
test("the card detail shows a loading state while it fetches", async () => {
  const ui = boot({
    state: { ...EMPTY_STATE, queue: [{ issue_key: "SSAI-91", waiting_seconds: 5 }] },
  });
  await ui.settle();

  ui.click(ui.$("queue-body").querySelector("tr[data-card]"));

  assert.equal(ui.$("card-detail").hidden, false);
  assert.equal(ui.$("card-detail-loading").hidden, false);
  assert.equal(ui.$("card-detail-body").hidden, true);

  // The stub answers 500 for a card it does not know: the failure is reported,
  // not left spinning.
  await ui.settle();
  assert.equal(ui.$("card-detail-loading").hidden, true);
  assert.equal(ui.$("card-detail-error").hidden, false);
  assert.match(ui.$("card-detail-error").textContent, /SSAI-91/);
  ui.close();
});

/** 24. Observability polls on its own cadence, not on the dashboard's. */
test("routing and usage are fetched once on load, not on every dashboard tick", async () => {
  const ui = boot();
  await ui.settle();

  const count = (url) => ui.gets.filter((u) => u === url).length;
  assert.equal(count("/api/config/routing"), 1);
  assert.equal(count("/api/observability/usage"), 1);
  // The live view rides the dashboard cycle instead of opening its own.
  assert.equal(count("/api/observability/live"), count("/api/state"));
  ui.close();
});

/** 25. No credential ever reaches the browser. */
test("the page carries no credential and calls nothing but the console", () => {
  for (const secret of [
    /api[_-]?key\s*[:=]\s*["']/i,
    /Authorization\s*[:=]/i,
    /Bearer\s+[A-Za-z0-9._-]{8,}/,
    /ls__[A-Za-z0-9]/,
    /sk-[A-Za-z0-9]/,
  ]) {
    assert.ok(!secret.test(TEMPLATE_HTML), `template must not embed ${secret}`);
  }

  // Every fetch target is a relative console path: the page never talks to
  // LangSmith (or anything else) directly, so it needs no credential to hold.
  for (const [, url] of TEMPLATE_HTML.matchAll(/fetch\(\s*"([^"]+)"/g)) {
    assert.ok(url.startsWith("/api/"), `unexpected fetch target: ${url}`);
  }
});

/** Regression guard: the config panel must not have displaced the dashboard. */
test("existing dashboard areas still render", async () => {
  const ui = boot({
    state: {
      ...EMPTY_STATE,
      overall_status: "working",
      poller: { last_tick_at: 1, seconds_since_tick: 3, healthy: true },
      metrics: { working: 1, waiting: 2, queued: 3, dead: 4 },
      queue: [{ issue_key: "SSAI-1", waiting_seconds: 12 }],
      runs: [{ issue_key: "SSAI-2", status: "waiting", column: "In Progress", time_parked_seconds: 30 }],
      log: [{ at: 1700000000, message: "[shadow] would trigger SSAI-88" }],
    },
  });
  await ui.settle();

  assert.equal(ui.$("status-text").textContent, "working");
  assert.equal(ui.$("m-working").textContent, "1");
  assert.equal(ui.$("m-dead").textContent, "4");
  assert.match(ui.$("queue-body").textContent, /SSAI-1/);
  assert.match(ui.$("runs-body").textContent, /SSAI-2/);
  assert.match(ui.$("log").textContent, /\[shadow\] would trigger SSAI-88/);
  ui.close();
});
