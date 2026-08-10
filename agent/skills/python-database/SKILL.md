---
name: python-database
description: How to change persistence safely in a SQLAlchemy + Alembic + PostgreSQL project - session and transaction lifecycle, unit of work, avoiding N+1, index decisions, writing and reviewing migrations including downgrades, where to enforce a constraint, and concurrency (row locking, optimistic concurrency). Load during implementation only when the change touches models, queries, or schema.
metadata:
  author: open-swe
  version: "1.0"
---

Load this when the change touches a model, a query, or the database schema. Read
`python-engineering` first, and the Harness Report for the migration command and the detected
ORM/driver.

**The rule that has no exception: every schema change ships with an Alembic migration, in the
same commit as the model change.** A model edited without a migration is a service that works
on your machine and fails on deploy.

---

## Session lifecycle

- One session per unit of work — per HTTP request in a web app, per job run in a worker. Never
  a module-level session, never a session shared between threads or tasks.
- The session is created and closed by one owner (a `Depends(get_db)` generator, an explicit
  context manager). Everything else receives it as a parameter.
- Every path must close it. Use `with`/`yield`-with-cleanup rather than manual `close()`.
- On error, roll back before closing. A session left in a failed state raises
  `PendingRollbackError` on its next use, which surfaces far from the real cause.
- Do not `commit()` inside a repository method. The caller that owns the unit of work decides
  when the work is complete — otherwise two "atomic" operations in one request commit
  independently and a later failure leaves half the change persisted.
- Expired-after-commit is the default: touching an ORM attribute after `commit()` triggers a
  refresh query, and after the session closes it raises `DetachedInstanceError`. Read what you
  need before the session ends, or return schema objects rather than ORM instances across the
  boundary.

## Transactions and unit of work

- Make the boundary explicit: `with session.begin():` (or the project's equivalent) around the
  operations that must succeed or fail together.
- Do not nest `begin()` blocks by accident; use `begin_nested()` (SAVEPOINT) when you genuinely
  need a partial rollback.
- Never do slow non-database work inside an open transaction — an HTTP call, a file upload, an
  email send. It holds locks for the duration and turns a remote timeout into a database
  incident. Do the external work before or after, and design for the retry.
- Non-transactional side effects (publishing an event, sending a notification) must happen
  *after* the commit succeeds, or they announce work that got rolled back.
- Follow the repo's existing unit-of-work shape. If services already receive a session and
  repositories only query, keep it that way rather than introducing a UoW class for one change.

## Queries and N+1

- The N+1 is the default failure of this layer: a list endpoint loads N rows, then serializes a
  relationship and issues one query per row. It passes every test on three fixture rows and
  falls over in production.
- Fix it at load time with eager loading — `selectinload` for collections, `joinedload` for
  many-to-one — not by looping and querying.
- Set relationship loading deliberately (`lazy="raise"` on relationships that must never
  lazy-load is the strongest guard; use it if the repo already does).
- Filter, sort, and paginate in SQL. Loading a table and slicing it in Python is a defect
  regardless of the current row count.
- Select only what you need for wide tables; avoid `SELECT *` semantics on rows with large
  columns.
- Any endpoint that returns a list has a bounded page size with a maximum — no unbounded query.
- Verify rather than assume: turn on SQL echo or the project's query logging in a scratch run
  and count the statements the endpoint issues.

## Indexes

- Index the columns you filter, join, and order by — foreign keys included (PostgreSQL does not
  index them automatically).
- Composite index column order follows the query: equality columns first, then range/sort.
- A `UNIQUE` constraint gives you an index; do not add a duplicate one beside it.
- Indexes cost write throughput and storage. Add one because a query needs it, not
  speculatively, and say which query in the migration or the spec.
- Creating an index on a large existing table locks writes. On PostgreSQL use
  `CREATE INDEX CONCURRENTLY` for that case — which means the migration must run outside a
  transaction (`op.execute` with the autocommit block Alembic provides). Flag it in the spec:
  it changes how the migration is deployed.

## Alembic migrations

1. Change the model, then autogenerate: the Harness Report has the exact command (typically
   `alembic revision --autogenerate -m "<message>"`).
2. **Read the generated file before doing anything else.** Autogenerate is a draft. It reliably
   misses server defaults, `CHECK` constraints, enum value changes, index renames, and anything
   in a schema it is not configured to see — and it happily emits a destructive `drop_table`
   for a model it cannot import.
3. Confirm `down_revision` points at the current head and that there is exactly one head
   (`alembic heads`). Two heads means a merge migration is needed.
4. Write the `downgrade()` for real. A `pass` body, or one that silently loses data, means the
   deploy has no way back. If the downgrade genuinely cannot restore data, say so in a comment
   in the migration.
5. Data migrations: when a column becomes `NOT NULL` on a populated table, the migration is
   three steps — add nullable, backfill, then alter to `NOT NULL`. Use SQL/core statements
   (`op.execute`, `op.bulk_insert`) inside migrations, never the application's ORM models: the
   models describe today's schema, and the migration will break the moment they change.
6. Test both directions against a real database: `upgrade head`, then `downgrade -1`, then
   `upgrade head` again.
7. Never edit a migration that has already been applied anywhere but your own branch. Add a new
   one.
8. Never generate a migration to "fix" a divergence you do not understand — find why the
   database and the models disagree first.

**Destructive operations** (dropping a column or table, narrowing a type, renaming) need an
explicit call-out in the spec and, for a live system, the expand/contract sequence: add the new
shape, migrate reads and writes, then remove the old shape in a later change.

`Base.metadata.create_all()` is for tests and local scratch only. If the app calls it at
startup, that is not a migration strategy and it will diverge from Alembic — do not extend it.

## Where a constraint belongs

Enforce at the database when correctness must survive a bug, a script, or a concurrent request:
`NOT NULL`, `UNIQUE`, foreign keys, `CHECK` for invariants that never change, and `ON DELETE`
behaviour chosen deliberately rather than defaulted.

Enforce in the application when the rule needs context the database does not have (the acting
user, an external service, a rule that varies by tenant or by time), or when the user deserves
a specific, friendly error.

Usually **both**: the database guarantees it, the application checks it first to produce a good
error message. A check-then-insert in the application alone is a race — two concurrent requests
both see "no duplicate" and both insert. Keep the `UNIQUE` constraint and catch
`IntegrityError` to convert it into the right 4xx (see `fastapi-engineering`).

## Concurrency

- Read-modify-write across two statements is a lost update waiting to happen. Either do it in
  one statement (`UPDATE ... SET balance = balance - :amount WHERE ...`), or take a lock, or use
  optimistic concurrency.
- Pessimistic: `SELECT ... FOR UPDATE` (`with_for_update()`) inside the transaction that will
  write. Always lock rows in a consistent order across the codebase, or two transactions will
  deadlock on each other.
- Optimistic: a `version` column (SQLAlchemy's `version_id_col`) or an `updated_at` compare, and
  a `409` when the update affects zero rows. Cheaper under low contention; the caller must be
  able to retry.
- Expect and handle `IntegrityError`, `OperationalError` (deadlock/serialization failure) and
  statement timeouts. On a deadlock the transaction is dead — roll back and retry the whole
  unit of work, do not retry the single statement.
- Set a statement timeout rather than letting one query hold connections indefinitely, and keep
  transactions short — a long transaction on PostgreSQL also blocks vacuum.

## Before you call the persistence change done

- Model change and migration in the same commit; upgrade and downgrade both exercised.
- No new N+1: the query count for the touched endpoint was actually observed.
- Indexes justified by a named query.
- Constraints in the right layer, with the race case handled.
- Repository holds queries only; the transaction boundary is owned by the caller.
