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

const HAIKU = "anthropic:claude-haiku-4-5-20251001";
const SOL = "openai:gpt-5.6-sol";

/** Shape mirrors GET /api/config: current values plus the option catalogs. */
const BACKEND_CONFIG = {
  shadow_mode: true,
  model: HAIKU,
  effort: "low",
  polling_interval_minutes: 1,
  available_models: [
    { id: HAIKU, label: "Claude Haiku 4.5", efforts: ["low", "medium", "high"], default_effort: "low" },
    { id: SOL, label: "GPT-5.6 Sol", efforts: ["none", "medium", "high"], default_effort: "high" },
  ],
  available_efforts: ["none", "low", "medium", "high"],
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

function jsonResponse(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

/**
 * Boot the real template in jsdom against a fake console backend.
 *
 * `putHandler` receives the parsed PUT body and returns whatever `fetch`
 * should resolve to; the default merges the patch like the real API does.
 */
function boot({ config = {}, state = EMPTY_STATE, putHandler } = {}) {
  const backend = { ...BACKEND_CONFIG, ...config };
  const puts = [];

  const respondToPut = putHandler
    ? putHandler
    : async (patch) => {
        Object.assign(backend, patch);
        return jsonResponse({ ...backend, warnings: [] });
      };

  const fetchStub = async (url, init = {}) => {
    const method = (init.method || "GET").toUpperCase();
    if (url === "/api/state") return jsonResponse(state);
    if (url === "/api/config" && method === "GET") return jsonResponse({ ...backend });
    if (url === "/api/config" && method === "PUT") {
      const patch = JSON.parse(init.body);
      puts.push(patch);
      return respondToPut(patch);
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
    $,
    optionValues,
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
  const ui = boot({ config: { model: SOL, effort: "medium", polling_interval_minutes: 30 } });

  // Before the first response nothing is editable and no value is implied.
  assert.equal(ui.$("cfg-model").disabled, true);
  assert.equal(ui.$("cfg-model").options.length, 0);
  assert.equal(ui.$("shadow-indicator").className, "shadow-indicator unknown");

  await ui.settle();

  assert.equal(ui.$("cfg-model").disabled, false);
  assert.equal(ui.$("cfg-model").value, SOL);
  assert.equal(ui.$("cfg-effort").value, "medium");
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

/** 5. The model list comes from the backend, keeping technical ids as values. */
test("model dropdown is built from available_models", async () => {
  const ui = boot();
  await ui.settle();

  assert.deepEqual(ui.optionValues("cfg-model"), [HAIKU, SOL]);
  assert.deepEqual(
    [...ui.$("cfg-model").options].map((o) => o.textContent),
    ["Claude Haiku 4.5", "GPT-5.6 Sol"],
  );
  ui.close();
});

/** 6. Effort options come from the backend; the model gates which are usable. */
test("effort dropdown is built from available_efforts and respects the model", async () => {
  const ui = boot();
  await ui.settle();

  assert.deepEqual(ui.optionValues("cfg-effort"), ["none", "low", "medium", "high"]);
  // Haiku does not accept "none": offered by the catalog, not selectable here.
  const disabled = [...ui.$("cfg-effort").options].filter((o) => o.disabled).map((o) => o.value);
  assert.deepEqual(disabled, ["none"]);
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
  assert.equal(ui.$("cfg-model").disabled, true, "other controls are locked while a save runs");

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
      jsonResponse({ error: "effort 'none' is not supported by model 'anthropic:claude-haiku-4-5-20251001'" }, 400),
  });
  await ui.settle();

  ui.change("cfg-effort", (el) => { el.value = "none"; });
  await ui.settle();

  assert.ok(ui.$("cfg-status").classList.contains("error"));
  assert.match(ui.$("cfg-status").textContent, /not supported by model/);
  ui.close();
});

/** 11. A failed save rolls the control back to the value actually in effect. */
test("a failed save rolls every control back to the backend value", async () => {
  const ui = boot({
    config: { shadow_mode: true, effort: "low", polling_interval_minutes: 1 },
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

  ui.change("cfg-effort", (el) => { el.value = "high"; });
  await ui.settle();
  assert.equal(ui.$("cfg-effort").value, "low");

  assert.match(ui.$("cfg-status").textContent, /reverted/i);
  assert.equal(ui.$("cfg-model").disabled, false, "controls are usable again after a failure");
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
  const reloaded = boot({ config: { polling_interval_minutes: 30, shadow_mode: false, effort: "high" } });
  await reloaded.settle();

  assert.equal(reloaded.$("cfg-interval").value, "30");
  assert.equal(reloaded.$("cfg-effort").value, "high");
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
