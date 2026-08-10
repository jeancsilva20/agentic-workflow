# Harness Report — guilhermeallen/sensedia-backend-case @ feat/spec-SSAI-89-melhorar-erros-e-logs (SSAI-89)

## Environment
- Python (declared): no `.python-version`/`pyproject.toml`/`runtime.txt` found; only inferable from Render/CI, none present. No declared version — README says "Python 3.x".
- Python (sandbox): 3.11.14
- Dependency manager: **pip** — evidence: `requirements.txt` present, no lock file (`uv.lock`/`poetry.lock`/`Pipfile.lock`/`pdm.lock`) and no `pyproject.toml`.
- Command prefix: `` (empty — direct `python`/`pip` invocation, no wrapper)
- Install: `pip install -r requirements.txt` — result: ok (installed into the sandbox's active Python env; a handful of unrelated pip dependency-resolver warnings about other, unrelated packages in this sandbox image, not about this project's deps)

## Commands
| Purpose | Command | Source | Verified |
|---|---|---|---|
| install | `pip install -r requirements.txt` | `requirements.txt`, README.md step 3 | yes — installed, `import fastapi, sqlalchemy, alembic, loguru, pydantic` succeeded |
| run | `uvicorn app.main:app --reload` | README.md step 6, `start.sh` | not run (needs a live PostgreSQL `DATABASE_URL`) |
| test | none — no suite exists | see below | n/a |
| lint | none declared | no `ruff`/`flake8`/`.flake8`/`setup.cfg` found | n/a |
| format | none declared | no `black`/`[tool.ruff]` found | n/a |
| type-check | none declared | no `mypy`/`pyright` config found | n/a |
| migration | `alembic upgrade head` (apply), `alembic revision --autogenerate -m "..."` (new) | `alembic.ini` (root), `alembic/versions/`, `start.sh` runs `alembic upgrade head` before `uvicorn` | not run (needs live PostgreSQL) |

**Test command — no suite exists.** Searched for `test_*.py`, `*_test.py`, any `tests/` directory, any CI workflow (`.github/` absent entirely), any `Makefile`/`tox.ini`/`noxfile.py` — none found. This is not a blocker per skill guidance: recorded as a risk, and the change this run produces should bring its own tests and propose a minimal baseline if the spec calls for one.

## Stack
- Framework: **FastAPI** — evidence: `fastapi==0.135.1` in requirements.txt, `FastAPI(` instantiated in `app/main.py`, `uvicorn` as server.
- Entry point: `app.main:app` (see `start.sh`, README step 6).
- ORM / migrations: SQLAlchemy 2.0 (`declarative_base`, sync `Session`) + Alembic 1.18, `alembic/versions/`.
- Validation: Pydantic v2 (`pydantic==2.12.5`, `pydantic-settings==2.13.1`); schemas still use the Pydantic v1-style `@validator` import name (`from pydantic import ... validator`) though unused in the file read — worth checking during implementation for v1/v2 drift.
- Database: PostgreSQL via `psycopg2-binary` (sync driver).
- Other: `loguru==0.7.3` (structured logging, third-party), no queue/cache, no auth library visible at this layer (auth/interceptors live at the Sensedia API Gateway, outside this codebase per README).
- Sync or async: sync SQLAlchemy `Session` used directly inside `async def` FastAPI middleware/handlers (`app/main.py`) and inside sync service/repository methods called from sync route functions — routes themselves are defined as sync `def`, so this is consistent, not the async-session-under-sync-route mismatch pattern.

## Architecture
```
app/routers/       HTTP surface (cliente_router, apolice_router, log_router) — FastAPI APIRouter, thin, delegates to services
app/services/      business rules (ClienteService, ApoliceService, LogService) — construct their own Repository, raise HTTPException for business errors
app/repositories/   persistence (ClienteRepository, ApoliceRepository, LogRepository) — raw SQLAlchemy Session queries
app/schemas/        Pydantic request/response models (schemas.py, single file)
app/models/         SQLAlchemy declarative models (models.py, single file: Cliente, Apolice, LogErro)
app/core/           config (configs.py — pydantic-settings), database (database.py — engine/SessionLocal/get_db), logging_config.py (Loguru setup + Postgres sink)
alembic/versions/   migrations
```
Dependency direction observed: routers → services → repositories → models, consistently. `app/main.py` wires cross-cutting concerns (middleware, global exception handlers, Loguru setup) directly. No layering violations observed. One inconsistency already visible and load-bearing for this change: `ClienteService.criar_cliente` raises a bare `RuntimeError` for one business rule (name containing a digit) while every other business rule in every other service raises `HTTPException` with an explicit 4xx — the `RuntimeError` is uncaught by the app's own exception handlers' HTTPException branch and falls through to the generic `Exception` handler, becoming a 500.

No `tests/` directory exists; nothing to report on layout, count or fixtures.

## Tests
- Location: none. Count: 0. Framework: none declared (no pytest/unittest config, no CI test step).
- Fixtures / conftest: n/a.
- Requires live services: n/a (no tests exist to require them). The application itself requires a live PostgreSQL (`DATABASE_URL`) to run or migrate — not reachable from this sandbox.

## Environment variables
- Required: `DATABASE_URL` (from `app/core/configs.py` `Settings`, no default — required; matches `.env.example`).
- Missing in this sandbox: `DATABASE_URL` (no `.env` present, no live Postgres reachable here).
- Services expected: PostgreSQL (`psycopg2-binary` driver) — reachable: no.

## Risks
1. No test suite at all — not blocking, but every later "it works" is unverified until this change brings its own tests. Evidence: no `test_*.py`/`tests/`/CI found anywhere in the repo.
2. No lint/format/type-check tool declared and no CI gate — evidence: no `ruff`/`flake8`/`black`/`mypy`/`pyright` config, no `.github/` directory at all. `python-quality` will need to propose a minimal baseline if the spec calls for one.
3. No declared Python version — sandbox runs 3.11.14; risk of silent drift is low here since nothing pins a different version, but it is unverifiable against CI (there is no CI).
4. Cannot run the app, migrations, or any live-DB check in this sandbox — no reachable PostgreSQL and no `DATABASE_URL` configured. Verification of DB-touching behavior will have to rely on code review and, if added, tests using an in-memory/sqlite substitute or mocks rather than a live Postgres run.
5. `ClienteService.criar_cliente` raises a bare `RuntimeError` (not `HTTPException`) for the "nome contém número" rule, which the app's own `@app.exception_handler(Exception)` catches and turns into an undifferentiated 500 — inconsistent with the sibling 4xx rules in the same file and in `ApoliceService`. Evidence: `app/services/cliente_service.py:12-16` vs. lines 19-23, 26-30, and `app/main.py`'s two exception handlers.
6. Logging currently mixes `loguru` (third-party, declared in `requirements.txt`) with two raw `print()` calls inside `app/core/logging_config.py`'s own `postgres_sink` error-recovery paths — i.e. the sink's *own* failure handling doesn't go through the logging system it implements. Evidence: `app/core/logging_config.py:27,31`.
7. An OpenSpec change directory `openspec/changes/loguru-error-logging/` already exists and its content (LogErro model, sink, exception handlers, `GET/DELETE /api/v1/logs`) matches code already merged to `main` (commits `9493384`, `6751930`, `297f5a1`) — it was never archived. This is pre-existing repo debt, not something SSAI-89 asks to fix, but it means the "error-logging" capability already has a canonical spec file that this change may need to extend rather than duplicate.
8. The Jira card explicitly asks to favor Python's native/standard-library tooling for logging quality ("usar libs nativas do python") while the current implementation is built entirely on the third-party `loguru`. This is a product/architecture decision, not something the harness resolves — it goes into `design.md` as an open decision for spec review.

## Harness status
- HARNESS COMPLETE
