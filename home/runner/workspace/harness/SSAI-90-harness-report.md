# Harness Report — guilhermeallen/sensedia-backend-case @ feat/spec-SSAI-90-post-clientes-500-nome-numero (SSAI-90)

## Environment
- Python (declared): none declared (no `.python-version`, no `pyproject.toml`, no `python_requires`, no CI file) — evidence: repo root listing
- Python (sandbox): 3.11.14
- Dependency manager: **pip** — evidence: `requirements.txt` present, no lock file, no `pyproject.toml`/`Pipfile`
- Command prefix: `` (none — run interpreter/tools directly)
- Install: `pip install -r requirements.txt` (inside a project-local `.venv`, with `PIP_CONFIG_FILE=/dev/null` to bypass the sandbox's global `pip.conf` which forces `--user` and breaks venv installs) — result: ok

## Commands
| Purpose | Command | Source | Verified |
|---|---|---|---|
| install | `python3 -m venv .venv && source .venv/bin/activate && PIP_CONFIG_FILE=/dev/null pip install -r requirements.txt` | `requirements.txt` (only manifest) | yes — installed fastapi 0.135.1, sqlalchemy 2.0.48, pydantic 2.12.5, alembic 1.18.4 |
| run | `./start.sh` (= `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`) | `start.sh`, `render.yaml` (`startCommand: ./start.sh`) | not run (needs live Postgres) |
| test | **none — no suite exists** | evidence: no `tests/` dir, no `test_*.py`/`*_test.py` anywhere, no pytest/unittest dependency in `requirements.txt`, no CI workflow (`.github` absent) | n/a |
| lint | none configured | evidence: no ruff/flake8/pylint config in any file, not in `requirements.txt` | n/a |
| format | none configured | evidence: no black/ruff-format config | n/a |
| type-check | none configured | evidence: no mypy/pyright config, not in `requirements.txt` | n/a |
| migration | `alembic upgrade head` / `alembic revision --autogenerate -m "..."` | `alembic.ini` (root), versions in `alembic/versions/` | not run (no live DB in sandbox) |

**Test command decision:** No test suite exists at all (not ambiguous/unsafe — simply absent). Per `python-harness` this is not a blocker: recorded as a risk below, and the OpenSpec proposal for this change will need to add targeted unit tests for the code path it touches (`ClienteService.criar_cliente`), using a minimal `pytest` baseline since the project has none.

## Stack
- Framework: **FastAPI** 0.135.1 — evidence: `fastapi` in `requirements.txt`, `FastAPI(...)` instantiated in `app/main.py`, `APIRouter` in `app/routers/*.py`
- Entry point: `app.main:app`, served via `uvicorn` (see `start.sh`)
- ORM / migrations: SQLAlchemy 2.0.48 (`app/models/models.py`, `app/repositories/*.py`) + Alembic 1.18.4 (`alembic.ini`, `alembic/versions/`)
- Validation: Pydantic **v2** (`pydantic==2.12.5`, `pydantic-settings==2.13.1`) — schemas in `app/schemas/schemas.py` use `ClienteCreate`/`ClienteResponse`
- Database: PostgreSQL via `psycopg2-binary` driver (sync). `.env.example` shows `DATABASE_URL=postgresql://usuario:senha@localhost:5432/nome_do_banco`
- Other: `loguru` for logging (`app/core/logging_config.py`, correlation-ID middleware in `app/main.py`), `python-dotenv`/`pydantic-settings` for config (`app/core/configs.py`)
- Sync or async: **sync** throughout — route handlers are `def` (not `async def`), SQLAlchemy `Session` (not `AsyncSession`), no `asyncpg`/`aiosqlite`. Consistent, no sync-under-async mismatch observed.

## Architecture
```
app/routers/      HTTP surface (APIRouter per resource: cliente_router, apolice_router, log_router)
app/services/     business rules (ClienteService, ApoliceService, LogService)
app/repositories/ persistence (ClienteRepository, ApoliceRepository, LogRepository) — wrap SQLAlchemy Session
app/schemas/       Pydantic v2 request/response models
app/models/       SQLAlchemy declarative models (Base)
app/core/         settings (pydantic-settings), database session factory, logging setup
alembic/versions/ migrations
```
Dependency direction observed: `router -> service -> repository -> SQLAlchemy Session`, matching a classic layered architecture. Routers instantiate `Service(db)` directly per request (no dependency-injection container beyond FastAPI's `Depends(get_db)`).

Observed violation relevant to this ticket: in `app/services/cliente_service.py::criar_cliente`, the name-validation check raises a bare `RuntimeError` (uncaught by FastAPI's `HTTPException` handler, so it falls through to the generic `Exception` handler and returns HTTP 500), while the two adjacent business rules in the same method (duplicate CPF, duplicate e-mail) raise `HTTPException(status_code=400, ...)`. This is a defect against the file's own convention — evidence: `app/services/cliente_service.py:12-30`.

## Tests
- Location: none — no `tests/` directory exists in the repository.
- Count: 0 collected (no runner declared).
- Framework: none declared.
- Fixtures / conftest: none.
- Requires live services: n/a (no tests to run). The app itself requires a live PostgreSQL for `run`/`migration`; not reachable in this sandbox.

## Environment variables
- Required: `DATABASE_URL` (from `Settings(BaseSettings)` in `app/core/configs.py`, no default — app raises `ValidationError` on startup without it)
- Missing in this sandbox: `DATABASE_URL` (no real Postgres instance running here; app import was verified by injecting `DATABASE_URL=sqlite:///:memory:` for a smoke import only, not for running migrations or hitting the DB)
- Services expected: PostgreSQL (`postgresql://...@localhost:5432/...` per `.env.example`) — reachable: no (not provisioned in this sandbox)

## Risks
1. **No test suite exists at all** — evidence: no `tests/` dir, no `test_*.py` files, no pytest/unittest in `requirements.txt`, no CI workflow. Every future "tests pass" claim needs the change to add its own tests; recommend a minimal `pytest` + `httpx`/`TestClient` baseline scoped to the touched service.
2. **No lint/format/type-check tooling configured** — evidence: nothing in `requirements.txt`, no `ruff`/`black`/`mypy`/`flake8` config files anywhere in the repo. Any quality gate for this change must be proposed fresh (see `python-quality`), not assumed.
3. **No declared Python version** — evidence: no `.python-version`, no `pyproject.toml`, no CI. Sandbox uses 3.11.14; `render.yaml` (`runtime: python`) does not pin a version either, so Render's default may differ from this sandbox. Low risk given the code has no version-specific syntax.
4. **No live PostgreSQL in this sandbox** — `run` and `migration` commands could not be verified end-to-end; only a Python-level import smoke-test was performed with a substitute in-memory SQLite URL, and even that did not exercise the ORM against a real schema.
5. **Confirmed code defect matching the alert** — `criar_cliente` raises `RuntimeError` (→ uncaught → 500) instead of `HTTPException` (→ 4xx) when the client name contains a digit, while sibling validations in the same method correctly raise `HTTPException(400, ...)`. This is the root cause the OpenSpec proposal must address. Whether digits should be rejected in names at all is a separate product decision not evidenced anywhere in the code or the card — it belongs in `design.md` as an open decision, not a silent removal.
6. No secrets/credentials found committed in the repo; `.env.example` contains only placeholder values (`usuario:senha`).

## Harness status
- HARNESS COMPLETE
