---
name: fastapi-engineering
description: How to add or change endpoints in a FastAPI service - router organisation, Depends-based injection, Pydantic request/response models, choosing HTTP status codes, exception handlers, async vs sync path functions, middleware order, OpenAPI hygiene, lifespan, and endpoint security. Load during implementation whenever the Harness Report detects FastAPI.
metadata:
  author: open-swe
  version: "1.0"
---

Load this only when the Harness Report says the framework is FastAPI. Read
`python-engineering` first — this skill adds the framework-specific layer on top of it.

The layering this skill assumes (confirm it against the Harness Report before applying):

```
Routers (app/routers/)        HTTP surface only: path, status code, dependencies, serialization
  -> Services (app/services/) business rules; decides what is valid and which error a violation is
    -> Repositories (app/repositories/) persistence only: SQLAlchemy queries, no rules
Schemas (app/schemas/)        Pydantic models shared by routers and services
Models  (app/models/)         SQLAlchemy tables
```

A router with business logic in it, or a service that builds a `JSONResponse`, breaks the
layering even if the tests pass.

---

## Routers

- One `APIRouter` per resource, with `prefix` and `tags` set on the router, not repeated on
  every decorator. Register it in the app factory / `main.py` next to its siblings.
- The path function is thin: resolve dependencies, call one service method, return its result.
  If a path function is longer than a handful of lines, the logic belongs in a service.
- Follow the repo's existing path style (plural nouns, kebab or snake, trailing slash or not).
  Inconsistent URLs are a public, permanent defect.
- Declare `response_model` (or a typed return annotation FastAPI can use) on every endpoint.
  It is what stops an ORM object with a password hash from being serialized to a client.
- Path/query parameters get real types and validation (`Annotated[int, Path(ge=1)]`,
  `Annotated[str | None, Query(max_length=100)]`), not bare `str` you parse by hand.
- Register the specific route before the ambiguous one — `/users/me` must be declared before
  `/users/{user_id}` or it will never match.

## Dependency injection

- Everything a path function needs comes from `Depends`: the DB session, the current user,
  pagination parameters, the service instance. Never construct a session or a client inside a
  path function.
- Use `Annotated[Session, Depends(get_db)]` style aliases (`SessionDep`, `CurrentUser`) and
  reuse them; repeating the raw `Depends(...)` in twenty signatures makes changing it a
  twenty-file edit.
- Dependencies that yield (`yield` + cleanup after) are how sessions and transactions are
  scoped. Do not swallow exceptions in the cleanup half — the framework needs them to roll back.
- Put shared authorization on the router or app (`dependencies=[Depends(require_role(...))]`)
  when it applies to every route in the group, and only per-route when it genuinely differs.
- Dependencies are cached per request by default. Do not rely on a dependency running twice.

## Request and response schemas

- Separate models for input and output. A single model reused for both leaks fields the client
  must not set (`id`, `created_at`, `is_admin`) and fields the client must never see
  (`password_hash`).
- Naming follows the repo, typically `XCreate`, `XUpdate`, `XRead`/`XResponse`.
- Validation that depends only on the payload shape belongs in the schema (`Field(gt=0)`,
  `field_validator`, `EmailStr`). Validation that depends on stored state (uniqueness,
  existence, current balance) belongs in the service — a schema cannot query the database.
- Match the project's Pydantic major version. v2 uses `model_config = ConfigDict(...)`,
  `model_validate`, `field_validator`, `from_attributes=True`; v1 uses `class Config`,
  `from_orm`, `validator`, `orm_mode`. Check an existing schema before writing a new one —
  mixing the two APIs fails at import time or, worse, silently does nothing.
- `PATCH` bodies use all-optional fields plus `exclude_unset=True` when applying, so "not sent"
  and "explicitly set to null" stay distinguishable.

## Status codes

Pick the code from what happened, not from habit:

| Situation | Code |
|---|---|
| Read / update succeeded with a body | `200` |
| Resource created | `201` (+ `Location` when the repo does that) |
| Accepted for async processing | `202` |
| Succeeded with no body (typically delete) | `204` — return nothing |
| Payload failed schema validation | `422` (FastAPI's default; do not fight it) |
| Well-formed payload, business rule refused it | `400` (or `409` for a conflict/duplicate, `422` if the repo uses it that way) |
| No/!invalid credentials | `401` |
| Authenticated but not allowed | `403` |
| Target does not exist | `404` |
| State conflict: duplicate key, concurrent update | `409` |
| Rate limited | `429` |
| Unhandled failure | `500` — never a code you chose deliberately |

Declare the non-default one on the decorator (`status_code=status.HTTP_201_CREATED`) and use
the `status` constants rather than integer literals if the repo does.

**A 500 in a response the code chose is always a defect.** If a business rule can refuse a
request, that refusal has a 4xx.

## Errors and exception handlers

- Services raise domain exceptions (`CustomerNotFound`, `DuplicateDocument`). The HTTP
  translation happens once, in an `@app.exception_handler(DomainError)`, or in the router if
  that is the established pattern in this repo. Do not invent a second mechanism alongside the
  existing one.
- Keep the error body shape identical across endpoints — clients parse it. Match whatever the
  repo already returns (`{"detail": ...}` by default).
- Never put internal details (SQL, tracebacks, file paths) in an error body. Log them; return a
  generic message.
- If you add a handler for a broad type, register the specific handlers too — the most specific
  registered handler wins, and a bare `Exception` handler will otherwise mask everything.

## Async vs sync path functions

- `async def` **only** when the body awaits something. An `async def` that runs blocking I/O
  (a synchronous SQLAlchemy query, `requests`, `time.sleep`, heavy CPU work) blocks the event
  loop for every other request.
- A plain `def` path function is run in a threadpool by FastAPI and is the correct choice for
  synchronous drivers. This is the common case with sync SQLAlchemy.
- Do not mix: if the repo uses sync SQLAlchemy sessions, keep the whole path sync. Introducing
  `async` in one endpoint drags in an async driver, an async session and an async test setup.
- Dependencies follow the same rule as the path functions they serve.

## Middleware and lifecycle

- Middleware runs outermost-first for the request and in reverse for the response. Order
  matters: `CORSMiddleware` goes outermost or preflight/error responses lose their headers;
  request-id / logging middleware goes outside error-handling middleware so failures are still
  logged with their id.
- Never do per-request blocking work in middleware — it runs for every route.
- Startup/shutdown belongs in the `lifespan` context manager (`@asynccontextmanager`, passed as
  `lifespan=` to `FastAPI(...)`), not in the deprecated `@app.on_event`. Create pools/clients
  before `yield`, close them after. Match the repo's existing style if it still uses
  `on_event`; do not migrate it as a side effect of an unrelated change.
- `create_all()` at startup is not a substitute for migrations (see `python-database`).

## OpenAPI hygiene

The generated docs are part of the deliverable, not a by-product.

- `summary` and, when non-obvious, `description` on each endpoint (or a one-line docstring the
  framework picks up).
- Declare the non-2xx outcomes clients must handle via `responses={404: {...}, 409: {...}}`.
- `operation_id` stays stable when clients are generated from the schema — renaming a function
  changes the default one.
- Give schemas realistic examples when the repo already does.
- After changing an endpoint, load `/docs` or dump `/openapi.json` and confirm it says what you
  intended.

## Security at the endpoint

- Authentication is a dependency, never an `if` inside the path function. Apply it at the
  router level so a newly added route is protected by default rather than by remembering.
- Authorization is checked against the resource, not only the route: "is this user allowed to
  read *this* record". An IDOR — accepting `user_id` from the path and trusting it — is the
  most common defect in this layer.
- Never accept an object id, role, price, or status from a client and pass it straight through
  to the persistence layer. Whitelist the fields the client may set (that is what a separate
  `XCreate` schema is for).
- Never log or return secrets, tokens, or password hashes. Exclude them at the schema level so
  it cannot happen by accident.
- Bound anything unbounded: pagination limits with a maximum, upload size limits, query
  `max_length`.

## Before you call the endpoint done

- Router thin, rules in the service, queries in the repository.
- Input schema, output schema, status code, and error paths all declared.
- Tests cover the happy path, the validation failure, the business-rule refusal and the
  not-found (see `python-testing`).
- `/openapi.json` reflects the change.
