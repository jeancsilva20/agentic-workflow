# Python reviewer skill + SDD system tests

## What & Why

The user's spec (sections 22–24 and 35) requires two things:

1. **Python Reviewer specialisation** — The reviewer graph must analyse Python/FastAPI/DB/
   security/OpenSpec adherence independently from the coding agent. It must post inline GitHub
   comments on specific lines when it finds concrete problems, not just produce a generic
   summary. Currently the reviewer has no Python-specific instructions; it loads skills from the
   *target repository* (trusted skills at base SHA) and from built-in OpenSpec skills, but has
   no coding-stack specialisation.

2. **SDD system tests** — The 20 assertions in section 35 of the requirements must exist as
   automated tests that can be run in CI. These tests verify that the agent system enforces the
   SDD contract: OpenSpec is available, versioned, produced before code, committed before gate
   moves, verify happens before code review, archive happens before merge, etc.

## Done looks like

- `agent/skills/python-review/SKILL.md` exists and is loaded by the reviewer graph via the
  static skill route (`/openspec-skills/` maps to `agent/skills/`).
- The skill gives the reviewer a structured checklist across: Correctness, Python idioms,
  FastAPI patterns, Database (SQLAlchemy/Alembic), Security, Tests, and OpenSpec adherence.
- For each finding, the reviewer uses inline anchors (file + line) via `add_finding`, so
  `publish_review` posts inline review comments on the GitHub PR rather than only top-level
  summaries.
- The reviewer system prompt explicitly states it is a separate agent from the coding agent and
  must perform fresh analysis on the diff — it must not reproduce the coding agent's own
  conclusions.
- `tests/sdd/` directory contains `test_sdd_contract.py` with at minimum the 20 test
  assertions from requirement §35:
  1. OpenSpec skills are loadable from `agent/skills/`.
  2. `openspec-version.yaml` exists and is parseable.
  3. Recorded version/commit field is non-empty.
  4. `openspec/config.yaml` has a non-empty `context:` block.
  5. `openspec-explore`, `openspec-propose`, `openspec-verify`, `openspec-archive` skills exist.
  6. `python-harness` skill exists and has non-empty content.
  7. `python-review` skill exists and is non-empty.
  8. Harness skill mentions "harness complete" or equivalent signal.
  9. `openspec-verify` skill mentions checking tasks checklist.
  10. `openspec-archive` skill mentions moving artifacts before `Em Merge` gate.
  11. `AGENTS.md` contains the "SDD Mandatory Gates" section.
  12. `AGENTS.md` blocks `Em Revisão de Spec` gate without committed artifacts.
  13. `AGENTS.md` blocks `Em Code Review` gate without verify passing.
  14. `AGENTS.md` blocks `Em Merge` gate without archive completing.
  15. `openspec/config.yaml` `rules:` block includes `tasks` with checkbox constraint.
  16. `python-engineering` skill exists and mentions type hints.
  17. `fastapi-engineering` skill exists and mentions Pydantic.
  18. `python-database` skill exists and mentions Alembic migrations.
  19. `python-testing` skill exists and mentions pytest.
  20. `python-quality` skill mentions detect-first before installing tools.
- All 20 tests pass (`pytest tests/sdd/`).
- Existing test suites continue to pass.

## Out of scope

- Changing the reviewer graph code (`agent/reviewer.py`) beyond what's needed to load the new
  Python review skill — the reviewer already supports `SkillsMiddleware` and inline findings
  via `add_finding`/`publish_review`.
- Python quality-gate execution within the reviewer (reviewer is read-only; it reads the diff
  and existing test results, it does not re-run tests).
- UI/frontend, Jira poller, or OpenSpec lifecycle changes.

## Steps

1. **Write `agent/skills/python-review/SKILL.md`** — A structured review skill with seven
   labelled sections: **Correctness** (bugs, edge cases, exception handling, data flow),
   **Python** (typing, idiomatic style, mutability, generators, async/context managers),
   **FastAPI** (request validation, response models, status codes, dependency chains,
   async/sync, exception handlers), **Database** (query correctness, transaction boundaries,
   migration presence for schema changes, N+1, concurrency), **Security** (injection,
   secrets in code, auth/authz completeness, input exposure), **Tests** (coverage of changed
   behaviour, regression scenarios, missing edge cases), **OpenSpec** (each implemented item
   traces to a spec requirement; design decisions are respected; tasks.md checkboxes match
   code state). Each section produces `add_finding` calls with file+line anchors when a
   concrete issue is found. Concludes with `publish_review`.

2. **Document reviewer independence in AGENTS.md** — Add a "Reviewer Independence" rule:
   the reviewer graph must perform fresh analysis and must not simply validate the coding
   agent's own summary. It reads the PR diff directly. Its findings supersede any self-
   assessment from the coding agent.

3. **Create `tests/sdd/` directory and `tests/sdd/test_sdd_contract.py`** — Implement the 20
   test functions. Tests are purely filesystem/YAML-parsing checks — no LLM calls, no network.
   Each test reads a file or parses a config and asserts presence of expected content. Use
   `pytest` with clear test IDs matching the 20 requirement numbers so failures are instantly
   identifiable.

4. **Add `tests/sdd/conftest.py`** — Provide fixtures for the skills root path
   (`agent/skills/`), `openspec/config.yaml` path, `openspec/openspec-version.yaml` path, and
   `AGENTS.md` path, so test functions are decoupled from hard-coded paths.

5. **Run and fix** — Execute `pytest tests/sdd/ -v` and ensure all 20 tests pass. Fix any
   skill file content or AGENTS.md text that fails an assertion. Confirm existing test suites
   (`pytest tests/` excluding `sdd/`) still pass.

## Relevant files

- `agent/skills/` (directory — all existing SKILL.md files for reference)
- `agent/reviewer.py` (lines 1–50, 128–333, 1033–1060 for skill loading + finding tools)
- `AGENTS.md`
- `tests/conftest.py`
- `openspec/config.yaml`
