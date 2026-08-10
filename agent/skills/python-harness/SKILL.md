---
name: python-harness
description: Python Harness Engineer - the mandatory first step on a Python repository, run right after the clone and branch and before any exploration or code change. Detects Python version, dependency manager, install/run/test/lint/type-check/migration commands, framework, architecture layers and required environment variables, then writes a structured Harness Report the rest of the run reads instead of re-discovering. If a safe test command cannot be determined, it asks instead of guessing.
metadata:
  author: open-swe
  version: "1.0"
---

You are the harness engineer for this run. Before anything else happens on a Python
repository — before `openspec-explore`, before the proposal, and long before a single source
file is edited — you establish *how this project is built, run, tested and validated*, and you
record it once.

**Why this exists:** without it, every later step guesses. It invents `pytest` on a project
using `unittest`, runs `pip install -r requirements.txt` on a uv project, edits a model without
knowing Alembic is present, and reports "tests pass" after running a command that collected
zero tests. Every one of those failures is discoverable in under two minutes of filesystem
inspection.

**Scope:** run this once per run, on the repository that was just cloned. Everything you report
must come from files you actually read. Nothing in this skill is allowed to be answered from
memory of what a typical Python project looks like, or from what a previous run reported about
this repository.

---

## Order of operations

```
PASSO 2 (repo cloned, branch created)
   -> python-harness   <-- you are here; no code is read for meaning yet, only for setup facts
   -> openspec-explore -> openspec-propose -> ... -> implementation
```

You are a read-only step with one exception: installing the project's own declared
dependencies (step 3). You do not edit source, you do not create the change directory, you do
not add tooling the project has not declared (see `python-quality`).

---

## 1. Python version

Look, in this precedence order, and record which file answered:

1. `.python-version` (pyenv/uv)
2. `pyproject.toml` → `requires-python`, and `[tool.ruff] target-version` / mypy
   `python_version` as corroboration
3. `setup.cfg` / `setup.py` → `python_requires`
4. `Dockerfile` base image, `.github/workflows/*.yml` → `python-version:`,
   `runtime.txt`, `tool-versions`
5. The sandbox runtime: `python3 --version`

Report both the **declared** version (what the project targets) and the **available** version
(what this sandbox runs). When they differ, say so — it is the reason a syntax error appears in
CI but not here, or vice versa.

## 2. Dependency manager

Identify it from the files present, not from preference:

| Evidence | Manager | Install | Run a command |
|---|---|---|---|
| `uv.lock`, `[tool.uv]` | **uv** | `uv sync` (`--extra dev` / `--all-extras` if dev deps are an extra) | `uv run <cmd>` |
| `poetry.lock`, `[tool.poetry]` | **poetry** | `poetry install` | `poetry run <cmd>` |
| `Pipfile.lock` | **pipenv** | `pipenv install --dev` | `pipenv run <cmd>` |
| `pdm.lock` | **pdm** | `pdm install` | `pdm run <cmd>` |
| `requirements.txt` (+ `requirements-dev.txt` / `-test.txt`) | **pip** | `pip install -r requirements.txt` (and the dev file) | direct |
| `pyproject.toml` with a PEP 621 `[project]` and no lock | **pip** | `pip install -e ".[dev]"` | direct |
| `environment.yml` | **conda** | `conda env create -f environment.yml` | `conda run` |

If several are present, the lock file wins — a stale `requirements.txt` beside a `uv.lock` is
usually an export, not the source of truth. Say which you chose and why.

Record the **command prefix** every later command must carry (`uv run `, `poetry run `, or
empty). Getting this wrong is the single most common harness failure: `pytest` on a uv project
runs the wrong interpreter or nothing at all.

## 3. Install and validate

Run the install command. This is the one mutating action the harness takes, and it is limited
to what the project declares.

- If it succeeds, note how long it took and anything it warned about.
- If it fails, capture the actual error and report it as a **blocking risk** — a run that
  cannot install cannot test, and every later "it works" is unverified. Do not work around it
  by installing individual packages by hand.
- Confirm the environment afterwards: the project's own package imports, and the declared dev
  tools are present.
- Never install a tool the project has not declared (see `python-quality`).

## 4. Derive the commands

For each of these, find the command the *team* uses before constructing one yourself. Search in
this order: `Makefile` / `justfile` / `noxfile.py` / `tox.ini` targets → `[tool.poetry.scripts]`
or `[project.scripts]` → `.github/workflows/*.yml` steps → start/entrypoint scripts
(`start.sh`, `entrypoint.sh`, `Procfile`) and deploy manifests (`render.yaml`, `fly.toml`,
`app.yaml`) → `README.md` / `CONTRIBUTING.md` → `docker-compose.yml` / `Dockerfile` `CMD` →
tool config sections. A `make test` that exists is always better than a `pytest` you invented,
because it carries the flags CI uses; a one-line `start.sh` is often the only honest record of
how the app and its migrations are actually launched.

Record all seven, or record explicitly that one does not exist:

- **install** — from step 2.
- **run / start** — e.g. `uvicorn app.main:app --reload`, `python -m app`, a compose service.
  Note the port and whether it needs a database up.
- **test** — the full command including the path/flags the project uses.
- **lint / format** — see `python-quality` for how to detect each tool.
- **type-check** — mypy / pyright / basedpyright, with the paths the config targets.
- **migration** — `alembic upgrade head`, `alembic revision --autogenerate -m "..."`, or
  `manage.py migrate`. Include where `alembic.ini` and the versions directory live.
- **build / container** — only if the project has one and the change might affect it.

**The test command is the one you may not guess.** Separate the two cases before deciding:

- **No test suite exists at all** — no test files, no test runner declared, no CI test step.
  This is *not* a blocker. Record `test: none — no suite exists` plus the evidence (the paths
  you searched), raise it as a risk, and carry it into the proposal: the change adds its own
  tests and, if the project has no gate either, proposes the minimal `ruff + pytest` baseline
  from `python-quality`. Do not silently adopt `pytest` as the project's runner — the spec
  proposes it and the review gate accepts it.
- **Tests exist but the command is ambiguous or unsafe** — several plausible candidates, or the
  only candidate would hit a real database, a real external service, or a production-looking
  URL, or you cannot tell what it touches. **Stop and ask.** In a Jira-triggered run there is no
  synchronous user: post the question as a Jira comment naming the candidates you found and what
  makes each unsafe, and end the turn.

Guessing in the second case produces a run that reports green having executed nothing, or one
that mutates a real database. Both are worse than a run that stopped.

## 5. Framework detection

From dependencies (`pyproject.toml` / `requirements*.txt` / the lock file) plus the entry
point, not from directory names alone:

- **FastAPI** — `fastapi` dependency, an `APIRouter`/`FastAPI(` instance, usually `uvicorn`.
- **Django** — `manage.py`, `settings.py`, `INSTALLED_APPS`.
- **Flask** — `flask` dependency, `Flask(__name__)`.
- **Other / none** — a library, a CLI (`click`, `typer`), a worker (`celery`), a data pipeline.

Also record what surrounds it: ORM (`sqlalchemy`, `django.db`, `tortoise`, `peewee`), migrations
(`alembic`, Django migrations), validation (`pydantic` — **and its major version**, v1 and v2
have incompatible APIs), server (`uvicorn`, `gunicorn`), database driver (`psycopg`,
`psycopg2`, `asyncpg`, `aiosqlite`), queue/cache (`celery`, `redis`), HTTP client, auth
libraries. Each one changes how the change must be written.

Find the entry point concretely (`app/main.py`, `main:app`, the `CMD`/`uvicorn` target), and say
whether the stack is sync or async — a sync SQLAlchemy session behind an `async def` endpoint is
a defect you need to know about before writing code, not after.

## 6. Architecture

Read the directory tree (2–3 levels, ignoring `.venv`, `__pycache__`, `.git`) and open one
representative file per directory. Report the layering you actually observe, for example:

```
app/routers/      HTTP surface
app/services/     business rules
app/repositories/ persistence
app/schemas/      Pydantic models
app/models/       SQLAlchemy tables
app/core/         config, security, dependencies
alembic/versions/ migrations
tests/            mirrors app/
```

State the **direction of dependency** you observed and any place the code already violates it.
If the project has no layering (everything in one module, queries inside routes), say that
plainly — it changes what "follow the existing pattern" means, and it belongs in the proposal
rather than being silently refactored.

Note the test layout and count (`<test command> --collect-only -q | tail -1` or equivalent), the
presence and contents of `conftest.py`, and whether tests need a live database.

## 7. Environment and configuration

- `.env.example` / `.env.sample` / `.env.template` — list every variable, and mark which have no
  value in the sandbox. **Never read or print the contents of a real `.env`, and never echo a
  value that looks like a credential.** Names only.
- The settings module (`app/core/config.py`, `settings.py`, a `BaseSettings` class) — which
  variables are required, which have defaults.
- `docker-compose.yml` — the services the app expects (postgres, redis) and whether any is
  actually reachable from this sandbox.
- Database URL shape and what the tests use (a separate test database, SQLite, testcontainers).

Anything required and absent is a risk that will surface as a confusing failure later. Name it
now.

## 8. Risks

Call out explicitly, with the evidence for each:

- install failed, or a declared tool is not installable here
- no test suite at all (not blocking, but every later "it works" is unverified until the change
  brings its own tests), or tests that exist but cannot run in this sandbox (needs a
  database/service)
- zero tests collected by a command that should collect some, or a suite already failing before
  your change
- no lint/type-check/CI gate at all (see `python-quality` for the baseline to propose)
- declared Python version ≠ sandbox Python version
- Pydantic v1 vs v2, or sync ORM under async endpoints
- models present with no migrations directory, or migrations with multiple heads
- pinned/outdated dependencies that block the change
- secrets or credentials committed to the repo (report the *file*, never the value)

## 9. Write the Harness Report

Produce it **once**, in exactly this shape, and both:

1. emit it as a fenced block in your message to the thread, and
2. save it to `<working_dir>/harness/<ISSUE-KEY>-harness-report.md` (the sandbox working
   directory named in the system prompt, e.g. `/workspace/harness/SSAI-42-harness-report.md`) —
   outside the repository
   clone, so it never appears in `git status` or the PR.

The saved copy is what makes this cheap: a later step (or a resumed run after a gate) reads the
file instead of re-running the whole detection. Re-run the harness only if the branch changes
repository or the dependency files themselves change.

```markdown
# Harness Report — <owner>/<repo> @ <branch> (<ISSUE-KEY>)

## Environment
- Python (declared): <version>  — source: <file>
- Python (sandbox):  <version>
- Dependency manager: <uv|poetry|pipenv|pdm|pip|conda> — evidence: <file>
- Command prefix: `<uv run |poetry run |>`
- Install: `<command>` — result: <ok | failed: reason>

## Commands
| Purpose | Command | Source | Verified |
|---|---|---|---|
| install | `...` | `Makefile:12` | yes |
| run | `...` | `README.md` | not run |
| test | `...` | `pyproject.toml` | yes — N tests collected |
| lint | `...` | `[tool.ruff]` | yes |
| format | `...` | `[tool.ruff]` | yes |
| type-check | `...` | `[tool.mypy]` | yes |
| migration | `...` | `alembic.ini` | not run |

## Stack
- Framework: <FastAPI|Django|Flask|none> — evidence: <dependency + entry point>
- Entry point: <module:app>
- ORM / migrations: <...>
- Validation: <pydantic vN>
- Database: <engine + driver>
- Other: <server, queue, cache, http client, auth>
- Sync or async: <...>

## Architecture
<observed layer tree, dependency direction, and any observed violation>

## Tests
- Location: <...>   Count: <N collected>   Framework: <pytest|unittest>
- Fixtures / conftest: <...>
- Requires live services: <yes/no — which>

## Environment variables
- Required: <NAMES only>
- Missing in this sandbox: <NAMES only>
- Services expected: <postgres:5432, ...> — reachable: <yes/no>

## Risks
1. <risk> — evidence: <file:line or command output>
2. ...

## Harness status
- HARNESS COMPLETE  (or)  HARNESS BLOCKED — <what is missing and what was asked>
```

Every "Verified" cell must be honest: `yes` means you ran the command in this sandbox and saw
it succeed. `not run` is a perfectly good answer for the start command; a false `yes` poisons
every decision after it.

## 10. Signal completion

End with **`HARNESS COMPLETE`** and a two-line summary (stack + the test command), then continue
to `openspec-explore`. Carry the report forward: the proposal's Impact section, the tasks list's
lint/test tasks, and the implementation's verification step all draw their commands from it.

End with **`HARNESS BLOCKED`** instead in exactly two situations: the install failed hard, or
tests exist and no safe command among the candidates could be chosen (step 4). Post the question
or the failure on the Jira card and end the turn. Do not proceed into implementation on a blocked
harness: code written against an unknown harness cannot be validated, and the run will claim a
success it never had.

A project with **no** test suite, no linter and no CI is not blocked — it is
`HARNESS COMPLETE` with those absences recorded as risks, and the proposal is where the baseline
gets proposed. Report the gap; do not stall the run on it, and do not quietly install a stack
the project never declared.
