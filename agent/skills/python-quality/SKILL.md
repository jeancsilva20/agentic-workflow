---
name: python-quality
description: How to find and run a Python project's quality gates before declaring work done - detect configured tooling (ruff, flake8, black, isort, mypy, pyright, bandit, pre-commit) instead of assuming it, never install tools the project has not declared, propose a minimal baseline when none exists, and interpret failures rather than silencing them. Load during implementation and again at the verification step.
metadata:
  author: open-swe
  version: "1.0"
---

The gates a project actually has are the only gates that matter. Read
`python-engineering` first; take the commands from the Harness Report, and use this skill to
derive them when the harness could not.

**Two rules govern everything here: detect before assuming, and never install what the project
has not declared.**

---

## 1. Detect

Read, in this order, and stop treating anything as "the project's tooling" until you have seen
it declared:

| File | What to look for |
|---|---|
| `pyproject.toml` | `[tool.ruff]`, `[tool.black]`, `[tool.isort]`, `[tool.mypy]`, `[tool.pyright]`/`[tool.basedpyright]`, `[tool.bandit]`, `[tool.pytest.ini_options]`, and the dev dependency group |
| `setup.cfg` / `tox.ini` | `[flake8]`, `[mypy]`, `[isort]` — older projects keep them here |
| `.ruff.toml`, `.flake8`, `mypy.ini`, `.pylintrc`, `pyrightconfig.json` | standalone configs |
| `.pre-commit-config.yaml` | the authoritative list of what runs on every commit — often stricter than CI |
| `Makefile` / `justfile` / `noxfile.py` / `tox.ini` | the *named* entry points (`make lint`, `make typecheck`) the team actually types |
| `.github/workflows/*.yml` | what CI enforces — this is what will fail your PR |
| lock file (`uv.lock`, `poetry.lock`, `requirements-dev.txt`) | whether the tool is actually installed |

Where the Makefile and CI disagree, CI wins for "will this be rejected", the Makefile wins for
"what the team runs locally". Run both if they differ.

Check the config's own settings before running: `line-length`, `target-version`, `select`/
`ignore` rule sets, `strict` mode, per-file ignores, excluded paths. A formatter run with the
wrong line length reformats the whole file and buries your change in noise.

## 2. The tools you will meet

**ruff** — the modern all-in-one linter and formatter, and what a new project should use.
`ruff check .` lints, `ruff check --fix .` applies safe fixes, `ruff format .` formats,
`ruff format --diff .` checks formatting without writing. When ruff is configured, it usually
replaces flake8 + isort + pyupgrade + a chunk of pylint — do not add those alongside it.

**black + isort + flake8** — the older stack. If the repo has it, use it as-is. Do not "migrate
it to ruff" as a side effect of a feature change; that is its own proposal.

**mypy / pyright / basedpyright** — static typing. Their strictness is configured, and it
matters: under `strict`, an unannotated function is an error, not a hint. Run the type checker
over the paths the project configures, not over the whole tree, and read whether existing
errors are baselined (`# type: ignore` comments, `exclude` lists) before concluding your change
introduced them.

**bandit** — security linting (hardcoded secrets, `subprocess` with `shell=True`, weak hashes,
`assert` in production paths, unsafe deserialization). Common in CI even when absent locally.
If it flags your change, fix the code; only add a `# nosec` with a comment explaining why when
the finding is genuinely a false positive.

**pre-commit** — runs the whole set. If `.pre-commit-config.yaml` exists and the hooks are
installed, `pre-commit run --files <changed files>` is the highest-signal single command you
can run.

**pip-audit / safety** — dependency vulnerability scanning. Relevant when the change adds or
bumps a dependency.

## 3. Never install blindly

Installing a linter the project has not declared produces findings against rules the team never
agreed to, and its default config will contradict theirs. It also mutates the environment for
everything that runs after you.

- If a declared tool is missing from the environment, install it through the project's own
  dependency manager and the declared version (the Harness Report has the install command).
  That is restoring the project's state, not adding tooling.
- If a tool is not declared anywhere, do not install it. Say what you would add and why, and
  let the spec/gate decide.
- Never edit `pyproject.toml` to add tooling, loosen a rule, raise `line-length`, or add an
  `ignore` entry just to make your change pass. Changing the gate to fit the code inverts the
  point of the gate. If a rule genuinely must change, that is a proposal with a rationale, not
  a silent edit.
- Same for `# noqa`, `# type: ignore`, `# nosec` and `@pytest.mark.skip`: each one is a claim
  that the tool is wrong. Use the narrowest form (`# noqa: E501`, not bare `# noqa`), add the
  reason, and only after you have tried to fix the code.

## 4. When the project has no quality gate

Some repositories have nothing — no linter config, no type checker, no CI check. Do not treat
that as permission to skip quality, and do not unilaterally impose a stack either.

Propose the smallest useful baseline and explain the reasoning:

```toml
# pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py311"   # match the project's actual Python version

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]  # pycodestyle, pyflakes, isort, pyupgrade, bugbear
```

plus `pytest` for tests. The reasoning to state: ruff is one dependency and one config that
replaces four tools, its default rule set is close to what most Python teams already expect,
and it can format as well as lint — so the whole gate is two commands. Static typing is
deliberately *not* in the baseline: turning mypy on over an untyped codebase produces hundreds
of pre-existing errors and blocks the change that introduced it.

Put the proposal in the change's `design.md` (or the Jira comment) and let the review gate
decide. Do not add it to the repo in the same commit as unrelated feature work.

## 5. Run the gates, then read them

Run everything the project declares, scoped to what you touched where the tool supports it:

```
<formatter check>   # e.g. ruff format --diff <paths>
<linter>            # e.g. ruff check <paths>
<type checker>      # e.g. mypy app  /  basedpyright
<security>          # e.g. bandit -r app
<tests>             # see python-testing
```

Set `NO_COLOR=1` so the output is readable in the log.

Interpreting the result:

- **Distinguish pre-existing failures from yours.** Run the gate on the base commit
  (`git stash`, or run it on an untouched path) before claiming the codebase was already
  broken — and equally, before taking blame for a failure you did not cause. Report
  pre-existing failures; do not fix them inside this change unless the spec says to.
- **Fix the cause, not the symptom.** A type error usually means the annotation is a lie or the
  `None` case is unhandled. A `B008`/mutable-default finding is a real bug. A complexity warning
  means the function is doing too much.
- **Auto-fix carefully.** `ruff check --fix` and formatters rewrite files: run them, then read
  the diff. If a formatter touches files unrelated to your change (because the repo was never
  formatted), revert those — a formatting-only diff across the repo hides the actual change and
  belongs in its own commit.
- **Re-run after fixing.** A gate you did not re-run is a gate you did not pass.

## 6. Before declaring the work done

State the result explicitly — which gates exist, which you ran, and their outcome. "Lint
passed" without naming the command is not a report.

Do not mark a task complete, park at a review gate, or claim verification passed while:

- a declared gate has not been run,
- a gate is failing because of your change,
- you silenced a finding instead of fixing it, or
- you changed the tool's configuration to make it pass.

If a gate cannot run in this sandbox (missing service, missing binary the project declares but
cannot install here), say exactly which one and why, in the gate comment. An unrun gate that is
named is recoverable; an unrun gate that is implied to have passed is not.
