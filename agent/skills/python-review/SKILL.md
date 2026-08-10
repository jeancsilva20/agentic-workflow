---
name: python-review
description: How to review a Python / FastAPI / SQLAlchemy pull request as an independent reviewer - a seven-pass checklist over correctness, Python idioms, FastAPI patterns, database and migrations, security, tests, and OpenSpec adherence, each pass ending in inline `add_finding` calls anchored to a changed line. Load at the start of a review whenever the diff touches Python files, before reading the diff end-to-end.
metadata:
  author: open-swe
  version: "1.0"
---

You are the reviewer. You are **not** the agent that wrote this code, and you do not inherit its
conclusions. The PR description, the commit messages and any self-review the author left behind
are claims to be checked, never evidence. Your analysis starts at the diff and at the code the
diff touches — if a claim ("added tests", "no schema change", "validated in the service layer")
is not visible in the diff, it is unverified and you treat it as such.

**Why this skill exists:** a generic reviewer on a Python service reports naming and formatting
and misses the mutable default, the missing `await`, the schema change with no Alembic revision,
and the requirement in `spec.md` nothing implements. The seven passes below are ordered by how
often each one catches something real on this stack.

---

## How to use the passes

Run them in order over the changed hunks. Each pass answers one question: *given what this
pass looks for, does a changed line fail?* When it does, record it immediately:

```
add_finding(
  severity=..., confidence=..., category="correctness"|"security"|"database"|"tests"|"spec"|...,
  file="app/services/order.py", start_line=118, end_line=121,
  title="Session commits before the balance check",
  description="...concrete failure mode, what breaks and when...",
)
```

Every finding must carry `file` + `start_line`/`end_line` inside the diff. That anchor is what
turns it into an inline GitHub comment on the offending line; a finding filed without lines
renders only as a top-level summary paragraph and is much easier for the author to skim past.
File-level findings are the exception, not the format.

The global bar in the system prompt still governs: a concrete, reachable failure mode on a
changed line. These passes tell you *where to look on a Python codebase*; they do not lower the
bar, and none of them makes a style preference into a finding.

When all seven passes are done, `list_findings`, prune, then `publish_review` once.

---

## 1. Correctness

The literal defect on the changed line, before anything clever.

- Wrong identifier, wrong key, wrong operator, inverted condition, off-by-one boundary.
- `None` reachable where the code dereferences, indexes, or arithmetics it. Trace where the
  value comes from rather than assuming the annotation is enforced at runtime.
- Exception handling that changes behaviour: a bare `except:` or `except Exception` that now
  swallows an error the caller relied on, a `raise` replaced by a `return None`, an exception
  raised inside a `finally`, a retry that re-raises the wrong type.
- Early returns and guard clauses that skip cleanup the old code performed.
- Data flow across the layers: the router passes what the service expects, the service passes
  what the repository expects, and the value that comes back is the shape the response model
  declares. A refactor that renames a field in one layer and not the next is the most common
  cross-layer defect on this stack.
- On a refactor, diff the old body against the new (`git show <base_sha>:path`) and look for
  silently dropped behaviour: validation, logging, a lock, a transaction boundary, an `await`.

## 2. Python

- **Mutable default arguments** (`def f(x=[])`, `=dict()`), and class-level mutable attributes
  shared across instances.
- **Async correctness**: a coroutine called without `await` (it becomes a truthy object and the
  work never runs), blocking I/O (`requests`, `time.sleep`, a sync DB driver, a large file read)
  inside an `async def`, `asyncio.create_task` whose result is never awaited nor stored, and
  shared state mutated across concurrent tasks.
- **Context managers**: files, sessions, locks and clients opened without `with`/`async with`,
  or closed on the happy path only.
- **Generators and iterators**: a generator consumed twice, a generator returned where the
  caller expects a list and the underlying resource is closed by then, `len()` on an iterator.
- **Typing that lies**: an annotation contradicted by the code (`-> str` with a `None` branch),
  `Optional` dropped from a parameter that still receives `None`, a `cast` used to silence a
  checker over a real mismatch.
- Equality/identity confusion (`is` on strings/ints), truthiness on values where `0` or `""` is
  legitimate, and dict/set ordering assumptions.
- Idiom only counts when it changes behaviour or hides a bug. "Could be a comprehension" is not
  a finding.

## 3. FastAPI

- **Request validation**: new input that is parsed by hand instead of by a Pydantic model, or a
  field typed `str`/`dict[str, Any]` where the endpoint depends on a narrower shape. Validation
  belonging to the request shape lives in the schema; validation depending on stored state lives
  in the service.
- **Response models**: `response_model` missing, or set to a model that exposes more than the
  endpoint should return (hashes, internal ids, soft-deleted rows, whole ORM objects).
- **Status codes**: a create endpoint returning 200 instead of 201, a business-rule violation
  escaping as a 500 rather than a 4xx `HTTPException` raised in the service, a 404 that leaks
  existence information, `status_code` on the decorator disagreeing with what the handler
  returns.
- **Dependency chains**: a `Depends` that is now unused, an auth dependency dropped from a route
  that previously had one, a dependency with side effects invoked per-request unintentionally,
  or a `yield` dependency whose cleanup no longer runs.
- **async vs sync**: a `def` path function doing async work, or an `async def` path function
  doing blocking work (see pass 2) — under load this is a real availability bug, not a style
  point.
- **Exception handlers and middleware**: a new exception type with no handler registered, or
  middleware ordering that puts a handler outside the scope it is meant to cover.

## 4. Database

- **Query correctness**: filters that no longer match the intended rows, a `first()` where the
  code assumes uniqueness, an implicit cross join, a `LIMIT` without an `ORDER BY` on a paginated
  endpoint.
- **Transaction boundaries**: `commit()` inside a loop or inside a helper the caller also
  commits, a commit before a validation that can still fail, an exception path that leaves the
  session dirty without a `rollback()`, or a session shared across concurrent tasks.
- **Migration presence — the hard rule**: any change to a SQLAlchemy model (new column, changed
  type, new constraint, new index, dropped column, new table) must ship an Alembic migration in
  the *same* diff. A model change with no revision under `alembic/versions/` is a CRITICAL
  finding anchored to the model line: the deploy will fail or the column will silently not
  exist. Check the reverse too — a migration that does not match the model, a `down_revision`
  that does not chain, or a `downgrade()` left as `pass` on a destructive change.
- **N+1**: a loop that touches a lazy relationship, or a serializer walking related objects
  without `selectinload`/`joinedload`. File it when the loop is over request-sized data, not
  when it is over two rows.
- **Concurrency**: read-modify-write on a row without a lock or a version column, and
  uniqueness enforced only in Python where two concurrent requests can both pass the check.

## 5. Security

- **Injection**: raw SQL built with f-strings or `%` on request data (parameterised queries or
  SQLAlchemy expressions only), shell commands built by concatenation, `eval`/`exec`/`pickle` on
  input, path traversal in a filename that reaches the filesystem.
- **Secrets**: a key, token, password or connection string literal in the diff; a secret logged,
  echoed in an error response, or committed to a fixture or `.env` that is tracked.
- **Auth / authz completeness**: a new endpoint with no authentication dependency, or with
  authentication but no ownership check — "is this user logged in" is not "may this user read
  this record". Compare against the sibling endpoints in the same router.
- **Input exposure**: stack traces, ORM objects or upstream error bodies returned to the client;
  overly broad CORS; user-controlled input reflected into a redirect, a template, or a log line
  without escaping.
- **Denial of service through input**: an unbounded page size, an unbounded upload, or an
  unbounded regex over request data.

## 6. Tests

- Does the changed behaviour have a test that would fail without this diff? Name the specific
  behaviour that is untested — "add tests" alone is not a finding.
- A test changed at the same time as the code it covers: did the assertion get weakened to make
  the new code pass? A deleted assertion, a widened `pytest.approx`, a new `xfail`/`skip`, or a
  mock now returning whatever the implementation happens to produce.
- Error paths and edge cases the diff introduces: the 4xx branch, the empty result, the
  concurrent case, the migration's `downgrade`.
- Tests removed, renamed out of collection, or moved out of the path CI runs. If a workflow,
  Makefile target or pytest config in the diff stops running a suite, that is a finding.
- The repository's own conventions decide the framework and layout — read what is already there
  before commenting on how a test is written.

## 7. OpenSpec adherence

Only when the PR carries OpenSpec artifacts (`openspec/changes/<change>/`). Read `proposal.md`,
`specs/*/spec.md`, `design.md` and `tasks.md` from the diff before this pass.

- **Traceability both ways**: every behaviour the diff implements traces to a requirement or
  scenario in `spec.md`, and every requirement the change claims is either implemented or
  explicitly deferred. Unspecified behaviour that ships is scope the human approver never saw;
  a specified requirement with no code is an unfinished change parked as done.
- **Design decisions are binding**: when `design.md` chose an approach, the code follows it. A
  silent departure is a finding — the alternative was rejected in writing.
- **Open Questions**: an unresolved product decision answered in code instead of escalated in
  `design.md` is a finding, anchored to the line that decided it.
- **`tasks.md` honesty**: a `- [x]` whose work is not in the diff is a false signal to the gate
  that reads it; unchecked boxes whose work *is* in the diff mean the checklist lies the other
  way. Both are findings.
- **Artifact shape**, only where it breaks the downstream parsers: a scenario written with three
  hashtags instead of `#### Scenario:`, a MODIFIED requirement pasted partially (detail is lost
  permanently at archive time), a capability named in the proposal with no matching
  `specs/<capability>/spec.md`.
- Spec findings use `category="spec"` and anchor to the artifact line or to the code line that
  diverges — whichever the author has to change.
