# Python skills pack + harness engineer

## What & Why

The user's spec (sections 12–21, 25–28, 31–34) requires the coding agent to be a genuine
Python specialist, not a generic code assistant, when working on Python repositories. Two
separate concerns are addressed here:

1. **Python skill pack** — A set of SKILL.md files covering Python engineering, FastAPI,
   database (SQLAlchemy/Alembic), testing, and code quality. These are loaded contextually
   (not all at once) so context window cost is proportional to what the task actually needs.

2. **Python Harness Engineer** — A dedicated skill and a supporting harness step that runs
   before the coding agent makes any changes. The harness detects the project environment,
   installs/validates dependencies, identifies quality gates, and produces a structured
   "harness report" that the coding agent reads before touching any source file. Without the
   harness output, the coding agent does not know how to install, run, test, or validate.

Currently zero Python skills exist in `agent/skills/`. The agent has no harness step.

## Done looks like

- Six new SKILL.md files exist in `agent/skills/`:
  - `python-engineering/SKILL.md` — idiomatic Python, typing, coupling, patterns
  - `fastapi-engineering/SKILL.md` — routers, DI, Pydantic schemas, async/sync, lifecycle
  - `python-database/SKILL.md` — SQLAlchemy sessions/transactions, Alembic migrations, N+1,
    PostgreSQL constraints
  - `python-testing/SKILL.md` — pytest, fixtures, happy path + edge cases, test isolation
  - `python-quality/SKILL.md` — ruff, mypy/pyright, bandit; detect-first, don't install blindly
  - `python-harness/SKILL.md` — full harness engineer instructions (see below)
- The harness skill instructs the agent to produce a structured harness report **before any
  code change**, covering: Python version, dependency manager, install command, app start
  command, test command, lint command, type-check command, migration command, detected
  framework, detected architecture, detected risks.
- `AGENTS.md` documents contextual skill loading: which Python skills are activated at
  planning, implementation, database changes, and quality-gate stages.
- The harness report is committed to the thread as a structured comment/block so it is not
  re-discovered on every model call within the same run.
- For the target repo `guilhermeallen/sensedia-backend-case`, the harness correctly identifies
  FastAPI, SQLAlchemy, Alembic, Pydantic, Uvicorn, and PostgreSQL through filesystem
  inspection (not hardcoding).

## Out of scope

- Implementing a separate reviewer skill (Task 3 covers that).
- Installing Python tooling into the sandbox automatically — the harness detects what's already
  configured first; tool installation is a separate, agent-initiated decision.
- Changes to the Jira workflow, OpenSpec lifecycle, or reviewer graph.
- UI/frontend changes.

## Steps

1. **Write `agent/skills/python-engineering/SKILL.md`** — Covers: idiomatic Python (PEP 8
   beyond formatting), type hints on all public interfaces, low coupling + high cohesion,
   exception hierarchy and re-raise patterns, context managers, avoiding global state, dependency
   injection, small focused functions/classes, no premature abstractions, compatibility with the
   project's detected Python version, and always respecting existing patterns in the repo before
   introducing new ones.

2. **Write `agent/skills/fastapi-engineering/SKILL.md`** — Covers: router organisation,
   dependency injection (`Depends`), request/response Pydantic models, HTTP status codes and
   when to use each, exception handlers (`@app.exception_handler`), async vs sync path
   functions, middleware ordering, OpenAPI documentation hygiene, startup/shutdown lifecycle,
   and endpoint security (auth dependencies, input sanitisation). Reinforces the existing
   Routers → Services → Repositories → Schemas layering.

3. **Write `agent/skills/python-database/SKILL.md`** — Covers: SQLAlchemy session lifecycle
   (open, use, close, rollback), explicit transactions, Unit-of-Work pattern, avoiding N+1
   (eager loading vs lazy), index decisions for query patterns, Alembic migration authoring
   (auto-generate + manual review, downgrade scripts), PostgreSQL constraints and when to
   enforce at DB vs application layer, concurrency considerations (row locking, optimistic
   concurrency). Rule: every schema change needs an Alembic migration.

4. **Write `agent/skills/python-testing/SKILL.md`** — Covers: detecting existing test
   framework before assuming pytest, fixture patterns, test isolation (no shared mutable state),
   when to use mocks vs real implementations, what to test per layer (router → service →
   repository), happy path + validation + error + edge case coverage, async test support
   (`pytest-asyncio`), avoiding coverage theatre (lines covered ≠ correctness).

5. **Write `agent/skills/python-quality/SKILL.md`** — Covers: detect-first approach (read
   `pyproject.toml`, `setup.cfg`, `.ruff.toml`, `mypy.ini` before assuming any tool); ruff as
   modern all-in-one linter/formatter; mypy/pyright for static typing; bandit for security
   scanning; never install tools not already declared in the project without proposing it first;
   if no quality gate exists, propose a minimal `ruff + pytest` baseline and explain the
   reasoning; run all detected gates and surface failures before marking the task complete.

6. **Write `agent/skills/python-harness/SKILL.md`** — The Python Harness Engineer skill.
   Instructs the agent to, before any implementation step: (a) detect Python version from
   `.python-version`, `pyproject.toml`, or runtime; (b) detect dependency manager (pip,
   poetry, uv, pipenv); (c) derive install, run, test, lint, type-check, and migration
   commands; (d) detect framework (FastAPI/Django/Flask) by inspecting `pyproject.toml` and
   main entry points; (e) detect architecture layers by reading directory structure and
   key files; (f) identify environment variable requirements (`.env.example`, config files);
   (g) produce the structured Harness Report and write it to the thread; (h) only then signal
   "harness complete" to the coding step. The skill explicitly states: if the harness cannot
   determine a safe test command, it must ask rather than guess.

7. **Update `AGENTS.md` with skill loading table** — Add a "Python Skill Loading" section that
   maps workflow phase to which skills should be active: Explore/Propose → `python-engineering`
   + `python-harness`; Implementation → `python-engineering` + `fastapi-engineering` +
   `python-database` (if DB changes) + `python-testing` + `python-quality`; Review/Verify →
   `python-quality` + `openspec-verify`. This ensures skills are loaded on-demand, not always.

8. **Add harness step to the SDD flow in `AGENTS.md`** — In the execution plan section, insert
   "Run Python Harness Engineer" as the step immediately after "Repository cloned / branch
   created" and before "OpenSpec Explore". The Harness Report becomes part of the context for
   both the OpenSpec proposal and the implementation.

## Relevant files

- `agent/skills/__init__.py`
- `agent/skills/openspec-explore/SKILL.md`
- `agent/skills/bootstrap-repo-analysis/SKILL.md`
- `AGENTS.md`
- `openspec/changes/jira-openspec-coding-agent/design.md`
