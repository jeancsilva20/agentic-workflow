# Harness Report — guilhermeallen/sensedia-backend-case @ feat/spec-SSAI-88-fix-500-validacao-nome-cliente (SSAI-88)

## Environment
- Python (declared): not pinned anywhere (no `.python-version`, no `pyproject.toml`, no `runtime.txt`, no CI) — evidence: repo root listing
- Python (sandbox):  3.11.14
- Dependency manager: **pip** — evidence: `requirements.txt` is the only dependency file, no lock file present
- Command prefix: `` (none — plain venv + pip)
- Install: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` — result: ok (pre-existing unrelated pip resolver warnings about the sandbox's own global langchain/langgraph packages, not this project's deps)

## Commands
| Purpose | Command | Source | Verified |
|---|---|---|---|
| install | `.venv/bin/pip install -r requirements.txt` | `requirements.txt` (only dep file) | yes — installed cleanly |
| run | `./start.sh` → `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` | `start.sh`, `render.yaml` | not run (needs live Postgres) |
| test | `DATABASE_URL=<placeholder> .venv/bin/python -m pytest -q` (once tests exist) | none declared — proposed baseline, see Risks | yes — verified the app's service layer can be exercised with `unittest.mock` and a dummy `DATABASE_URL`, no real DB connection needed for unit-level tests of `cliente_service.py` |
| lint | none configured | — | no tool declared |
| format | none configured | — | no tool declared |
| type-check | none configured | — | no tool declared |
| migration | `alembic upgrade head` / `alembic revision --autogenerate -m "..."` | `alembic.ini` (repo root), `alembic/versions/` | not run (needs live Postgres) |

## Stack
- Framework: **FastAPI** — evidence: `fastapi==0.135.1` in `requirements.txt`, `FastAPI(...)` instance in `app/main.py`, served via `uvicorn`
- Entry point: `app.main:app` (see `start.sh`, `render.yaml`)
- ORM / migrations: SQLAlchemy 2.0 (`app/core/database.py`) + Alembic (`alembic.ini`, `alembic/versions/`)
- Validation: Pydantic **v2** (`pydantic==2.12.5`, `pydantic-settings==2.13.1`) — schemas use `class Config` (v1-style nested config) rather than `model_config`, but the package itself is v2
- Database: PostgreSQL via `psycopg2-binary` (sync driver)
- Other: `loguru` for logging (custom Postgres sink, see `app/core/logging_config.py`), no queue/cache/auth libs present
- Sync or async: all endpoints defined as sync-style FastAPI handlers over a sync SQLAlchemy session — no sync-under-async mismatch observed

## Architecture
```
app/routers/       HTTP surface (cliente_router.py, apolice_router.py, log_router.py)
app/services/      business rules (cliente_service.py, apolice_service.py, log_service.py)
app/repositories/  persistence (cliente_repo.py, apolice_repo.py, log_repo.py)
app/schemas/        Pydantic request/response models (schemas.py)
app/models/         SQLAlchemy tables (models.py)
app/core/           config (configs.py), db session (database.py), logging (logging_config.py)
alembic/versions/   migrations
```
Dependency direction observed: Router → Service → Repository → Model, consistently. No layer inversion observed.

Exception handling convention: services raise `HTTPException` (4xx) for expected business-rule violations (duplicate CPF/email, not-found); `app/main.py` registers global `@app.exception_handler(HTTPException)` and `@app.exception_handler(Exception)` handlers that log via Loguru and return a JSON body. `cliente_service.criar_cliente`'s name-validation branch is the one place in the codebase that raises a bare `RuntimeError` instead of `HTTPException`, which the generic handler catches and turns into a 500 — this is the defect the Jira card's alert observed.

## Tests
- Location: none — no `tests/` directory, no `test_*.py` / `*_test.py` files anywhere in the repo
- Count: 0 collected (nothing to collect)
- Framework: none declared (no `pytest`/`unittest` runner configured, no CI workflow)
- Fixtures / conftest: none
- Requires live services: the app itself requires Postgres to run end-to-end (`DATABASE_URL`), but the service layer (`ClienteService`) can be unit-tested by injecting a mocked `Session`/repository, with no live DB — verified in this sandbox.

## Environment variables
- Required: `DATABASE_URL` (no default — `Settings.DATABASE_URL: str` in `app/core/configs.py`, app fails to start without it)
- Missing in this sandbox: `DATABASE_URL` (no `.env` present, only `.env.example`; no live Postgres reachable from this sandbox)
- Services expected: PostgreSQL (`localhost:5432` in `.env.example`, actual QA/prod DB on Render) — reachable: no

## Risks
1. **No test suite, no lint/type-check tooling, no CI at all** — evidence: no `tests/` dir, no `pyproject.toml`/`setup.cfg`/`tox.ini`, no `.github/workflows/`. Not blocking per `python-harness` guidance: the change will add its own focused unit tests for the fix and use `pytest` (installed as a dev dependency for this change) as the minimal baseline, run against mocked dependencies — no live DB needed.
2. **No Python version pinned anywhere** — sandbox runs 3.11.14; nothing declares a target, so no mismatch to report, but nothing to enforce it either.
3. **`DATABASE_URL` has no default and no `.env` in the sandbox** — `run`/`migration` commands cannot be executed live here; verification for this change is scoped to unit-level tests of `cliente_service.py` with a mocked session, which does not require a live DB.
4. **The defect under investigation**: `app/services/cliente_service.py` line 12-16 raises a bare `RuntimeError` for names containing digits, while every sibling validation in the same file (`buscar_por_cpf`, `buscar_por_email` duplicate checks, `buscar_cliente` not-found) raises `HTTPException` with an explicit 4xx status. The `RuntimeError` is uncaught by `http_exception_handler` and falls through to `generic_exception_handler`, producing the 500 the alert observed. This is evidence-backed by direct code reading, not the alert's own guess.

## Harness status
- HARNESS COMPLETE
