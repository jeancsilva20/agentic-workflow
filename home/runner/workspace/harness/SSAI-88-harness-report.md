# Harness Report — guilhermeallen/sensedia-backend-case @ feat/spec-SSAI-88-post-clientes-500 (SSAI-88)

## Environment
- Python (declared): no `.python-version`, no `requires-python` in a `pyproject.toml` (repo has none); `render.yaml` sets `runtime: python` with no pinned minor version — effectively undeclared beyond "Python 3.x" in README.
- Python (sandbox): 3.11.14 (`.venv` created against this interpreter)
- Dependency manager: **pip** — evidence: `requirements.txt` (pinned versions), no lock file (`uv.lock`/`poetry.lock`/`Pipfile.lock`) present.
- Command prefix: `` (none — direct `.venv/bin/python` / `.venv/bin/<tool>`)
- Install: `.venv/bin/pip install -r requirements.txt` — result: ok (all packages already satisfied in the pre-existing `.venv`)

## Commands
| Purpose | Command | Source | Verified |
|---|---|---|---|
| install | `.venv/bin/pip install -r requirements.txt` | `requirements.txt`, `README.md` step 3 | yes — "Requirement already satisfied" for all 27 packages |
| run | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` | `start.sh`, `render.yaml` (`startCommand: ./start.sh`) | not run (needs live Postgres via `DATABASE_URL`) |
| test | `none — no suite exists` | see Tests section | n/a |
| lint | none declared | no `ruff`/`flake8`/`black` config or dependency anywhere in the repo | n/a |
| format | none declared | same as above | n/a |
| type-check | none declared | no `mypy`/`pyright` config or dependency | n/a |
| migration | `.venv/bin/alembic upgrade head` (or `alembic revision --autogenerate -m "..."`) | `alembic.ini` (repo root), `alembic/` dir, used in `start.sh` | not run (needs live Postgres) |

## Stack
- Framework: **FastAPI** — evidence: `fastapi==0.135.1` in `requirements.txt`, `FastAPI(...)` instantiated in `app/main.py`, `uvicorn` as ASGI server.
- Entry point: `app.main:app` (`app/main.py`)
- ORM / migrations: SQLAlchemy 2.0.48 (`app/models/models.py`, `app/core/database.py`) + Alembic 1.18.4 (`alembic.ini`, `alembic/` versions dir present).
- Validation: Pydantic v2 (`pydantic==2.12.5`, `pydantic-settings==2.13.1`) — schemas in `app/schemas/schemas.py`.
- Database: PostgreSQL via `psycopg2-binary==2.9.11` (sync driver); `DATABASE_URL` is a required `postgresql://` URL (`app/core/configs.py`, `.env.example`).
- Other: `uvicorn` (ASGI server, sync worker), `loguru` for structured logging (`app/core/logging_config.py`), no queue/cache/auth library present. Sensedia API Gateway sits in front in production (client-id auth, rate limiting) — not part of this codebase.
- Sync or async: mixed — routers are `async def` in `app/main.py` middleware, but `cliente_router.py` endpoints are plain `def` and `ClienteService`/`ClienteRepository` use a synchronous SQLAlchemy `Session` (`sqlalchemy.orm.Session`) — consistent sync-under-FastAPI pattern (FastAPI runs sync `def` routes in a threadpool), not a defect.

## Architecture
```
app/routers/      HTTP surface (cliente_router.py, apolice_router.py, log_router.py) — thin, delegate to services
app/services/     business rules (cliente_service.py, apolice_service.py, log_service.py) — raise HTTPException for expected 4xx cases
app/repositories/  persistence (cliente_repo.py, apolice_repo.py, log_repo.py) — direct SQLAlchemy Session queries
app/schemas/       Pydantic request/response models (schemas.py)
app/models/        SQLAlchemy ORM tables (models.py)
app/core/          config (configs.py), db session (database.py), logging (logging_config.py)
alembic/versions/  migrations
```
Dependency direction observed: routers → services → repositories → models, consistent throughout the three resource areas (Cliente, Apolice, Log). No `tests/` directory exists at all.

One observed violation of the service layer's own convention: in `cliente_service.py::criar_cliente`, the CPF-duplicate and email-duplicate checks both raise `HTTPException(status_code=400, ...)` (an expected, client-facing 4xx), but the name-contains-digit check raises a bare `RuntimeError` — an uncaught exception that falls through to the global `Exception` handler in `app/main.py` and returns HTTP 500. This is the root cause under investigation for SSAI-88.

## Tests
- Location: none. `find . -iname "*test*"` (excluding `.venv`/`.git`) returned no matches.
- Count: 0 collected — no test runner is even installed (`pytest` not in `requirements.txt`, not importable in `.venv`).
- Fixtures / conftest: none.
- Requires live services: n/a (no suite to run). The app itself requires a live PostgreSQL instance (`DATABASE_URL`) to start or to be tested end-to-end.

## Environment variables
- Required: `DATABASE_URL` (no default in `app/core/configs.py`'s `Settings`, `PROJECT_NAME` and `API_V1_STR` have defaults).
- Missing in this sandbox: `DATABASE_URL` (no `.env` present, only `.env.example`).
- Services expected: PostgreSQL (`postgresql://...`) — not reachable from this sandbox (no database provisioned here).

## Risks
1. **No test suite at all** — not blocking per harness policy, but every future "tests pass" claim needs the change to bring its own tests; no baseline lint/type-check gate exists either. — evidence: empty `find . -iname "*test*"`, no `pytest`/`ruff`/`mypy` in `requirements.txt`.
2. **No lint/format/type-check tooling declared** — nothing to run as a quality gate before this change; `python-quality` should be consulted to propose a minimal baseline if the spec calls for one. — evidence: no `ruff.toml`, `.flake8`, `pyproject.toml`, `mypy.ini`, or such packages in `requirements.txt`.
3. **The confirmed defect itself**: `cliente_service.py:13` raises `RuntimeError` (uncaught) instead of `HTTPException`, unlike its sibling validations in the same method — this is what SSAI-88 is about. — evidence: code excerpt above, matches the production traceback from the Jira card comments.
4. **No live database reachable in this sandbox** — any functional/integration test written for this change cannot hit a real Postgres here; must rely on unit-level tests against the service layer (e.g., mocking/faking the repository) or an in-memory/sqlite substitute if introduced. — evidence: `DATABASE_URL` unset, no docker-compose or local Postgres service in the sandbox.
5. **Declared vs. sandbox Python version is only loosely pinned** — repo declares no exact Python version; sandbox uses 3.11.14, which is compatible with all pinned dependencies observed. Low risk, noted for completeness.

## Harness status
- HARNESS COMPLETE
