# OpenSpec skills vendor + SDD enforcement

## What & Why

The user's spec (sections 1–8, 11, 29–38 of the uploaded requirements) demands that OpenSpec
be the mandatory development standard: every Jira card must produce
`proposal/specs/design/tasks` **before** any implementation, the official skills from
`Fission-AI/OpenSpec` must be vendored at a pinned commit (not fetched on every run), and two
new lifecycle skills — **verify** and **archive** — must exist alongside the current
`openspec-explore` and `openspec-propose` skills.

Currently:
- `openspec/config.yaml` has `schema: spec-driven` but zero Python context.
- Only two OpenSpec skills exist: `openspec-explore` and `openspec-propose`; there are no
  `openspec-verify` or `openspec-archive` skills.
- No version/commit of the upstream skill source is recorded anywhere.
- The agent prompt does not contain an explicit gate that blocks the coding step until the spec
  artifacts exist on the remote branch.

## Done looks like

- `openspec/openspec-version.yaml` records `source`, `commit`, `fetched_at`, and `skill_files`
  so any future agent can know exactly which version of OpenSpec guided it.
- `openspec/config.yaml` contains a `context:` block describing the Python/FastAPI/PostgreSQL
  stack of `guilhermeallen/sensedia-backend-case` and per-artifact rules aligned to the SDD
  workflow.
- Four skills exist in `agent/skills/`: `openspec-explore`, `openspec-propose`,
  `openspec-verify`, `openspec-archive`.
- `openspec-verify/SKILL.md` instructs the agent to diff the implementation against the spec
  artifacts (requirements, scenarios, tasks checklist, design decisions) and surface divergences
  before marking the run ready for human code review.
- `openspec-archive/SKILL.md` instructs the agent to move active change artifacts to
  `openspec/archive/<change>/`, update `openspec/config.yaml` change log, commit, and push —
  all within the same branch before parking at `Em Merge`.
- `AGENTS.md` (root) and/or the agent system prompt explicitly states: the agent MUST NOT call
  `jira_park_at_gate` for `Em Revisão de Spec` until the OpenSpec artifacts are committed and
  pushed; and MUST NOT call `jira_park_at_gate` for `Em Code Review` until `opsx:verify` has
  run and passed.
- A `scripts/sync-openspec-skills.sh` script can be run explicitly (not on every agent run) to
  re-fetch skills from the upstream repo at a specific tag/commit and update
  `openspec-version.yaml`.

## Out of scope

- Changing how user-uploaded skills or Replit platform skills work.
- Modifying the Jira poller, column names, or resume logic (Task #11 handled those).
- Implementing Python-specific skills (Task 2 covers that).
- Frontend / UI changes.

## Steps

1. **Inspect upstream OpenSpec skill content** — Clone or `curl` the `Fission-AI/OpenSpec`
   repository at a known recent tag/commit to examine what skill files it ships (SKILL.md
   naming, directory layout, any OPSX action definitions). Record the commit SHA.

2. **Create `openspec/openspec-version.yaml`** — Write the version manifest with fields:
   `source`, `version`, `commit`, `fetched_at`, and `skill_files` (list of vendored skill
   names). This becomes the audit trail for which instructions guided the agent.

3. **Write `scripts/sync-openspec-skills.sh`** — A shell script that accepts an optional
   `--commit <SHA>` argument, fetches the skill files from `Fission-AI/OpenSpec` at that
   commit, copies them into `agent/skills/`, and updates `openspec-version.yaml`. The script
   must fail loudly if the commit is not provided or the fetch fails — it must never silently
   pull from `main` at runtime.

4. **Update `openspec/config.yaml`** — Add a `context:` block documenting the target repo
   (`guilhermeallen/sensedia-backend-case`), its stack (Python 3, FastAPI, SQLAlchemy, Alembic,
   Pydantic, Uvicorn, PostgreSQL), and its architecture layers (Routers → Services →
   Repositories → Schemas). Add `rules:` blocks for `proposal`, `specs`, `design`, and `tasks`
   that reinforce the SDD constraints (e.g., "tasks.md must use `- [ ]` checkboxes grouped by
   numbered heading", "design.md must include an Open Questions section for unresolved product
   decisions").

5. **Write `agent/skills/openspec-verify/SKILL.md`** — Skill that instructs the agent, after
   implementation, to: (a) read all spec files in the active change directory; (b) for each
   requirement/scenario, locate the corresponding code and assert it matches; (c) walk the
   tasks checklist and mark what is done/missing; (d) if divergences exist, either fix the code
   or update the spec with a rationale, then re-run; (e) only after clean verification, proceed
   to the code-review gate. Emphasise: this is a reasoning + code-reading step, not a separate
   binary — it uses the existing `grep`, `read_file`, `execute` tools.

6. **Write `agent/skills/openspec-archive/SKILL.md`** — Skill that instructs the agent to:
   (a) confirm the branch has a merged or approved PR (or the human code review gate is passed);
   (b) move `openspec/changes/<change>/` to `openspec/archive/<change>/`; (c) append an entry
   to `openspec/archive/index.md` with the change name, Jira key, date, and summary; (d)
   commit and push these changes; (e) only then call `jira_park_at_gate` for `Em Merge`.

7. **Enforce SDD gates in AGENTS.md** — In the root `AGENTS.md`, add a clearly labelled
   "SDD Mandatory Gates" section stating: (i) OpenSpec artifacts (`.openspec.yaml`,
   `proposal.md`, at least one `specs/*/spec.md`, `tasks.md`) MUST exist and be pushed before
   `Em Revisão de Spec`; (ii) `openspec-verify` MUST run and find no unresolved divergences
   before `Em Code Review`; (iii) `openspec-archive` MUST complete before `Em Merge`. These
   rules take precedence over any agent default behavior.

8. **Emit observability events** — In the same `AGENTS.md` section (or the relevant skill
   files), document that the agent should emit console log events at each OpenSpec lifecycle
   point: `openspec: version <X> loaded`, `openspec: proposal generated`, `openspec:
   verification passed`, `openspec: archived`. These use the existing `console_events` pattern.

## Relevant files

- `agent/skills/openspec-explore/SKILL.md`
- `agent/skills/openspec-propose/SKILL.md`
- `agent/skills/__init__.py`
- `openspec/config.yaml`
- `openspec/changes/jira-openspec-coding-agent/design.md`
- `AGENTS.md`
- `scripts/`
