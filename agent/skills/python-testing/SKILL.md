---
name: python-testing
description: How to test a Python change properly - detect the project's framework and conventions before assuming pytest, fixture and isolation patterns, what to test at the router/service/repository layer, mocks vs real implementations, async tests, and why coverage is not correctness. Load during implementation on any Python repo, and whenever a spec task mentions tests.
metadata:
  author: open-swe
  version: "1.0"
---

Every change ships with tests. Read `python-engineering` first and take the test command from
the Harness Report — never invent one.

---

## 1. Detect before you assume

Do not write a single test file until you have read the existing ones.

- `pytest` is the likely answer but not the given one. Check `pyproject.toml`
  (`[tool.pytest.ini_options]`), `pytest.ini`, `setup.cfg`, `tox.ini`, and whether tests are
  `unittest.TestCase` subclasses. A repo on `unittest` gets `unittest` tests.
- Read `conftest.py` at every level. It holds the fixtures you are supposed to reuse — a
  session fixture, a `TestClient`, a factory, an auth helper. Reinventing one of these is the
  most common way an agent's tests look foreign in review.
- Copy the conventions of the nearest existing test: file naming (`test_*.py`), directory
  layout (mirroring the package or grouped by layer), class-based vs function-based, naming
  style (`test_<unit>_<condition>_<expected>`), how markers are used.
- Note the configured options: `asyncio_mode`, `--strict-markers`, coverage thresholds,
  `filterwarnings = error`. They change what a passing test even means.
- If tests need a live database or another service, find how the repo provides it (a Docker
  compose file, a session-scoped fixture, SQLite fallback, `testcontainers`). If it cannot be
  provided in this sandbox, say so explicitly rather than quietly rewriting the test to avoid
  the dependency.

## 2. Fixtures

- Reuse before you create. A new fixture that duplicates one in `conftest.py` is a defect.
- Scope deliberately: `function` by default; `session`/`module` only for genuinely immutable
  setup. A session-scoped fixture holding mutable state couples every test that touches it.
- Fixtures that acquire something use `yield` and clean up after — the cleanup runs even when
  the test fails.
- Build test data with factories or a small helper with sensible defaults and overrides, so a
  test states only the field it cares about. Twenty-line literal payloads copied across tests
  rot within a month.
- Put a fixture in `conftest.py` only when more than one module uses it. Otherwise keep it next
  to its test.
- Prefer parametrization (`@pytest.mark.parametrize`) over near-duplicate test bodies, but not
  when the cases need different assertions — a parametrized test with `if` branches inside is
  two tests wearing one coat.

## 3. Isolation

A test that passes alone and fails in the suite (or vice versa) is worse than no test.

- No shared mutable state between tests: no module-level lists, no reused client with cached
  auth, no singleton reset only in one test.
- Each test rolls back or truncates what it wrote. The standard pattern is a transaction per
  test rolled back in the fixture teardown; if the repo does that, use it rather than deleting
  rows by hand.
- Never depend on execution order or on another test's leftovers. Run your new tests in
  isolation *and* in the file to confirm.
- Freeze or inject anything non-deterministic: time (`freezegun` or an injected clock), random
  seeds, uuids, timezone-sensitive values. `datetime.now()` inside an assertion is a flake.
- No network. A test that reaches the internet is not a unit test; it is an outage waiting to
  fail CI.
- Do not mutate global config or environment variables without restoring them
  (`monkeypatch` does this for you).

## 4. What to test at each layer

**Repository** — that the query does what it claims against a real database (or the repo's test
database): filters, joins, ordering, pagination boundaries, uniqueness violations. Mocking the
ORM here tests nothing but your mock.

**Service** — the business rules, with the repository either real (against the test database) or
substituted by a thin fake. This is where most of the value is: each rule, each refusal, each
edge of a boundary condition.

**Router** — the HTTP contract through the framework's test client: status code, response body
shape, validation failure (422), auth (401/403), not found (404), conflict (409). Do not re-test
every business rule here; test that the endpoint is wired to the rule and translates the error.

**Migration** — for a schema change, that `upgrade` and `downgrade` both run (see
`python-database`).

## 5. Mocks vs real implementations

- Prefer the real thing when it is fast and deterministic: your own functions, the ORM against
  a test database, Pydantic models.
- Mock at the process boundary — a third-party HTTP API, a payment provider, a clock, an email
  sender. Use `responses`/`respx`/`httpx.MockTransport` for HTTP rather than patching your own
  client's internals.
- Patch where the name is *used*, not where it is defined
  (`patch("app.services.orders.send_email")`).
- A test that asserts only "the mock was called" verifies wiring, not behaviour. Pair it with an
  assertion about the outcome.
- If a unit needs five mocks to be testable, that is a design signal (see `python-engineering`
  on coupling) — consider injecting a collaborator instead of patching internals.

## 6. Coverage per change

For each behaviour the change introduces or modifies:

- **Happy path** — the intended use, asserting the actual returned values, not just a 200.
- **Input validation** — the field that is missing, the wrong type, the out-of-range value.
- **Business-rule failure** — every refusal the service can produce, asserting the specific
  error/status, not merely "it raised".
- **Not found / unauthorised** — for anything addressed by an id or protected by auth.
- **Edge cases** — empty collection, exactly-at-the-boundary value, zero and negative numbers,
  duplicate submission, unicode and long strings for text fields, `None` where optional.
- **Regression** — when the change fixes a bug, write the test that fails on the old code
  first, and confirm it actually fails before the fix.

Assert on the specific thing: `assert response.json()["detail"] == "..."` beats
`assert response.status_code != 200`. `pytest.raises(SpecificError, match=...)` beats
`pytest.raises(Exception)`.

## 7. Async tests

- Only if the code under test is async. Check `asyncio_mode` in the pytest config: with
  `auto`, an `async def test_` just works; otherwise it needs `@pytest.mark.asyncio` and
  `pytest-asyncio` installed. A missing marker makes the test silently skip or pass without
  running — check the test actually executed.
- Async fixtures must match the plugin's expectations, and event-loop scope must match the
  fixture scope, or you get "attached to a different loop" errors.
- FastAPI: `TestClient` (sync, threadpool) is fine for sync path functions;
  `httpx.AsyncClient` with `ASGITransport` is the async equivalent. Follow the repo's choice.
- Never `time.sleep` in an async test; await the thing or use the loop's clock.

## 8. Coverage theatre

A line executed is not a line verified.

- Do not chase a percentage by writing tests with no assertions, tests that assert
  `is not None`, or tests that call every getter.
- Do not delete or `xfail` a failing test to make the gate green. A test failing after your
  change is information: either the behaviour changed on purpose (update the test and say why
  in the change) or you broke something.
- Do not weaken an assertion to match new output without confirming the new output is correct.
- Missing coverage on an untouched module is not your change's problem; missing coverage on the
  branch you just added is.

## 9. Running them

- Use the exact command from the Harness Report, scoped to what you changed
  (`<test command> tests/services/test_orders.py`). Do not run the whole suite unless the
  project is small or the change is broad — CI runs it.
- Disable colour in captured output (`NO_COLOR=1`, `-p no:cacheprovider` if the sandbox is
  read-only in places).
- A test you wrote must be observed passing *and*, for a regression test, observed failing
  before the fix. Never report a test as written without running it.
- If a pre-existing test fails for reasons unrelated to your change, report it — do not fix it
  silently inside this change and do not pretend it passed.
