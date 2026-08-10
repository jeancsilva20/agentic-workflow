---
name: python-engineering
description: How to write and change Python in a target repository like a specialist rather than a generic code assistant - idiomatic style, typing on public interfaces, coupling and cohesion, exception design, resource handling, and the rule that the repository's existing pattern outranks any preference in this file. Load during exploration/proposal and during every implementation step on a Python repo.
metadata:
  author: open-swe
  version: "1.0"
---

You are writing Python that a maintainer of *this* repository will review. The bar is not
"it runs" — it is "it reads like the rest of the codebase and it fails in ways the codebase
already knows how to handle".

**Load order:** read the Harness Report (`python-harness`) first. Everything below assumes you
already know the project's Python version, layering and quality gates. Without that, you are
guessing at the target's constraints.

---

## Rule 0 — the repository outranks this file

Before introducing any pattern, find how the codebase already solves the same class of problem
(`grep`, `glob`, read the two or three nearest siblings of the file you are editing). If a
convention exists, follow it, even when you would have chosen differently. If a convention is
violated in exactly one place while three others agree, that one place is usually the defect —
say so rather than copying it.

Only propose a new pattern when none exists, and say in the change's `design.md` why the
existing ones did not fit.

## Target the detected Python version

The Harness Report names the version (`.python-version`, `requires-python`, or the runtime).
Write for it, not for the newest Python you know:

- `match`, `X | Y` unions in annotations and `tomllib` need 3.10/3.11+.
- `Self`, `assert_never`, `override` come from `typing_extensions` below the version that
  ships them.
- Never raise the floor (editing `requires-python`, using a 3.12-only builtin) as a side effect
  of a feature change. That is its own decision and belongs in the spec.

## Typing

- Every public function, method, and module-level constant gets annotations — parameters and
  return type. "Public" means anything imported by another module or reachable from a router.
- Private helpers: annotate when the type is not obvious from two lines of context.
- Prefer precise types over `Any`. Prefer `Sequence`/`Mapping`/`Iterable` for parameters and
  concrete `list`/`dict` for return values.
- `Optional[T]` (or `T | None`) means "absent is a real, handled case" — if the caller cannot
  handle `None`, do not return it; raise.
- Use `TypedDict`, `NamedTuple`, `dataclass`, or a Pydantic model instead of passing bare
  dicts between layers. A dict crossing a layer boundary erases the contract.
- Annotations are a claim the type checker verifies. If the project has mypy/pyright
  configured (see `python-quality`), a change that adds annotations must also pass it.

## Coupling and cohesion

- A module depends on the layer below it, never on the layer above. In a
  Routers → Services → Repositories → Schemas layout, a repository that imports a router, or a
  service that builds an HTTP response, is a defect.
- Pass collaborators in (constructor argument, function parameter, framework dependency), do
  not reach out for them. A function that imports and instantiates its own database session is
  untestable and couples two layers invisibly.
- No mutable module-level state. Module-level constants are fine; a module-level cache, list,
  or client that is mutated at runtime is shared state across requests and across tests, and it
  produces failures that only appear under concurrency or test ordering.
- Configuration is read once at a defined place (a settings object) and injected, not read from
  `os.environ` scattered through business logic.

## Functions and classes

- One reason to exist per function. If you need "and" to describe what it does, it is two
  functions.
- Prefer a function to a class with one method. Prefer a class when there is state plus
  behaviour that travel together.
- Argue against your own abstraction: two similar call sites are a coincidence, three are a
  pattern. Do not introduce a base class, a generic helper, or a plugin hook for a single
  current caller — that is a premature abstraction and it costs every future reader.
- Keep the happy path at the lowest indentation level. Guard clauses and early returns beat
  nested `if`/`else` pyramids.

## Exceptions

- Define or reuse the project's exception hierarchy: a package-level base exception with
  specific subclasses. Never raise bare `Exception` and never raise `RuntimeError` for a
  business-rule violation.
- Domain errors are raised where the rule lives (the service layer) and translated to a
  transport error at the boundary (see `fastapi-engineering`). A domain layer that raises
  `HTTPException` is coupled to HTTP; a service layer that lets a bare exception escape as a
  500 is a defect against its own siblings.
- Catch narrowly. `except Exception:` is acceptable only at a top-level boundary that logs and
  re-raises or converts.
- Never swallow. `except X: pass` and `except X: return None` hide the failure and move the
  crash somewhere unrelated. If recovery is genuinely correct, log why at the catch site.
- Preserve the chain: `raise NewError(...) from exc`. A bare `raise NewError(...)` inside an
  `except` block throws away the original traceback.
- Do not use exceptions for expected control flow that the caller checks every time.

## Resources and context managers

- Anything acquired must be released on both paths. Use `with` for files, connections,
  sessions, locks, and transactions rather than manual `close()` in a `finally`.
- Write `contextlib.contextmanager` / `asynccontextmanager` helpers for acquire-release pairs
  the project repeats.
- Async code: never call a blocking function inside an `async def` without offloading it
  (`asyncio.to_thread` or the framework's equivalent). One blocking call stalls the whole loop.
  Match the project's existing async/sync stance instead of mixing both (see
  `fastapi-engineering`).

## Idiomatic style beyond formatting

The formatter handles layout; these are the things it cannot fix.

- Name for the reader: `pending_invoices` over `data2`, `is_active` for booleans, verbs for
  functions, nouns for values. Match the project's language — do not mix English and
  Portuguese identifiers within a module that has already chosen one.
- Use comprehensions for mapping/filtering; use a loop when there is a side effect.
- Iterate directly (`for item in items`), use `enumerate`/`zip`, and unpack rather than
  indexing by position.
- Use `pathlib` over string path arithmetic, f-strings over `%`/`.format`, `enum` over magic
  string literals repeated across modules.
- Never use a mutable default argument (`def f(x: list = [])`) — use `None` and build inside.
- `is` for `None`/singletons, `==` for values.
- Delete dead code rather than commenting it out; git holds the history.
- Comments explain *why*, never *what*. A comment restating the line below it is noise. Keep
  docstrings to one line unless the project's existing docstrings are longer.

## Before you call the change done

- The diff touches only what the spec's tasks describe. Unrelated reformatting, renames, or
  "while I was here" fixes make review harder and belong in their own change.
- Every new public symbol is typed, named consistently with its neighbours, and reachable from
  a test.
- Every quality gate the Harness Report listed has been run (see `python-quality`).
