# Async Session — `AsyncSessionLocal` and `DbDep`

The database layer uses SQLAlchemy's async extension (`sqlalchemy.ext.asyncio`)
with the `asyncpg` driver for non-blocking PostgreSQL access. This page covers
the session factory, the FastAPI dependency that yields sessions per-request,
transaction management semantics, and the connection pool configuration.

> **Source files:** `backend/app/db/session.py`, `backend/app/core/dependencies.py`

---

## Architecture Overview

```mermaid
graph TD
    A["FastAPI Request"] --> B["get_db() dependency"]
    B --> C["AsyncSessionLocal()"]
    C --> D["AsyncSession"]
    D --> E["AsyncEngine"]
    E --> F["Connection Pool<br/>pool_size=10, max_overflow=20"]
    F --> G["PostgreSQL<br/>(asyncpg driver)"]
    B --> H{{"Exception?"}}
    H -->|"No"| I["await session.commit()"]
    H -->|"Yes"| J["await session.rollback()"]
    I --> K["await session.close()"]
    J --> K
```

---

## `AsyncEngine` — The Connection Pool

The engine is a module-level singleton defined in `backend/app/db/session.py`.
It is created once at import time and shared across all requests for the
lifetime of the process.

```python
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from app.core.config import get_settings

_settings = get_settings()

engine: AsyncEngine = create_async_engine(
    _settings.DATABASE_URL,
    echo=_settings.ENVIRONMENT == "development",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_timeout=30,
)
```

### Connection Pool Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `pool_size` | `10` | Number of persistent connections maintained in the pool |
| `max_overflow` | `20` | Additional connections allowed beyond `pool_size` (total max: 30) |
| `pool_pre_ping` | `True` | Test connections before use to detect stale connections |
| `pool_recycle` | `3600` | Recycle connections after 1 hour to prevent idle connection issues |
| `pool_timeout` | `30` | Seconds to wait for a connection before raising `TimeoutError` |
| `echo` | `True` in dev | Log all SQL statements to stdout (development only) |

#### `pool_pre_ping=True`

Before handing a connection from the pool to a session, SQLAlchemy sends a
lightweight `SELECT 1` ping to verify the connection is still alive. This
prevents `"connection already closed"` errors that occur when PostgreSQL
restarts or drops idle connections due to its `idle_in_transaction_session_timeout`
setting.

The ping adds a small overhead (~0.1ms) per connection checkout, but this is
negligible compared to the cost of a failed query and retry.

#### `pool_recycle=3600`

Connections are automatically replaced after 1 hour of use. This prevents
issues with PostgreSQL's `tcp_keepalives_idle` setting and ensures that
connections do not accumulate stale state over long-running processes.

#### `echo` in Development

When `ENVIRONMENT=development`, all SQL statements are logged to stdout. This
is invaluable for debugging query performance and verifying that the ORM
generates the expected SQL. In production (`ENVIRONMENT=production`), `echo`
is `False` to avoid log noise.

### `DATABASE_URL` Format

The engine requires an async-compatible DSN using the `asyncpg` driver:

```
postgresql+asyncpg://user:password@host:port/dbname
```

The URL is read from the `DATABASE_URL` environment variable (or `.env` file)
via `app.core.config.Settings`:

```python
DATABASE_URL: str = Field(
    default="postgresql+asyncpg://postgres:postgres@localhost:5432/portfolio_optimizer",
    description="Async PostgreSQL DSN (asyncpg driver)",
)
```

> **Note:** The `+asyncpg` driver prefix is required. Using the standard
> `postgresql://` URL (which uses `psycopg2`) will raise an error because
> `psycopg2` is a synchronous driver and cannot be used with SQLAlchemy's
> async extension.

---

## `AsyncSessionLocal` — Session Factory

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)
```

`AsyncSessionLocal` is an `async_sessionmaker` — the async equivalent of
SQLAlchemy's `sessionmaker`. Each call to `AsyncSessionLocal()` creates a new
`AsyncSession` bound to the shared `engine`.

### Session Factory Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `bind` | `engine` | The shared async engine |
| `class_` | `AsyncSession` | Session class to instantiate |
| `expire_on_commit` | `False` | Do not expire attributes after commit |
| `autocommit` | `False` | Explicit transaction management |
| `autoflush` | `False` | Explicit flush control |

#### `expire_on_commit=False`

By default, SQLAlchemy expires all ORM object attributes after a `commit()`.
The next access to any attribute triggers a lazy-load SQL query to refresh
the data. In an async context, this is problematic because:

1. The session may be closed by the time the attribute is accessed.
2. Lazy loading in async SQLAlchemy requires explicit `await` calls, which
   cannot happen transparently when accessing a Python attribute.

Setting `expire_on_commit=False` prevents attribute expiry after commit. ORM
objects retain their in-memory values after the session commits, which is safe
because the application does not modify objects after committing them.

#### `autocommit=False`

Transactions must be committed explicitly by calling `await session.commit()`.
This is the standard behavior for web applications — each request manages its
own transaction boundary.

#### `autoflush=False`

SQLAlchemy's autoflush automatically sends pending changes to the database
before executing a query (to ensure the query sees the latest data). With
`autoflush=False`, flushes must be triggered explicitly with
`await session.flush()`.

This gives the application precise control over when SQL is sent to the
database, which is important for:
- Avoiding premature constraint violations during multi-step operations
- Controlling the order of INSERT/UPDATE statements
- Preventing unnecessary round-trips to the database

---

## `DbDep` — FastAPI Dependency

The `DbDep` type alias provides a typed FastAPI dependency that yields an
`AsyncSession` per request:

```python
from collections.abc import AsyncGenerator
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session.

    Transaction management:
        - Commits on clean exit (no exception raised).
        - Rolls back on any exception to prevent partial writes.
        - Always closes the session in the finally block.
    """
    from app.db.session import AsyncSessionLocal  # lazy import

    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


DbDep = Annotated[AsyncSession, Depends(get_db)]
```

### Transaction Lifecycle

```mermaid
sequenceDiagram
    participant R as Request Handler
    participant D as get_db()
    participant S as AsyncSession
    participant DB as PostgreSQL

    R->>D: FastAPI injects DbDep
    D->>S: AsyncSessionLocal()
    D-->>R: yield session
    R->>S: session.add(run) / session.execute(...)
    S->>DB: (deferred — not sent yet)
    R->>D: handler returns normally
    D->>S: await session.commit()
    S->>DB: BEGIN + SQL statements + COMMIT
    D->>S: await session.close()
    S-->>DB: return connection to pool
```

**On exception:**

```mermaid
sequenceDiagram
    participant R as Request Handler
    participant D as get_db()
    participant S as AsyncSession
    participant DB as PostgreSQL

    D-->>R: yield session
    R->>S: session.add(run)
    R->>R: raise HTTPException(404)
    D->>S: await session.rollback()
    S->>DB: ROLLBACK
    D->>S: await session.close()
    D->>R: re-raise exception
```

### Using `DbDep` in Route Handlers

```python
from fastapi import APIRouter
from app.core.dependencies import DbDep
from app.db import repository

router = APIRouter()

@router.get("/runs/{run_id}")
async def get_run(run_id: str, db: DbDep):
    run = await repository.get_run_by_id(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
```

The `DbDep` type annotation tells FastAPI to inject a session from `get_db()`.
The session is automatically committed after the handler returns, or rolled
back if an exception is raised.

### Lazy Import in `get_db()`

```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    from app.db.session import AsyncSessionLocal  # noqa: PLC0415
    ...
```

`AsyncSessionLocal` is imported lazily (inside the function body) rather than
at module level. This avoids a circular import: `db.session` imports
`app.core.config`, which is also imported by `app.core.dependencies`. The lazy
import breaks the cycle by deferring the import until the function is first
called.

---

## `await db.flush()` vs `await db.commit()`

Understanding the difference between `flush()` and `commit()` is essential for
correct transaction management.

### `await db.flush()`

```python
session.add(run)
await db.flush()  # Sends SQL to DB but does NOT commit
# run.id is now populated (auto-increment assigned by DB)
# The INSERT is visible within this transaction but NOT to other connections
```

`flush()` sends pending SQL statements (INSERT, UPDATE, DELETE) to the database
within the current transaction. The changes are:

- **Visible** to subsequent queries within the same session/transaction
- **Not visible** to other database connections (not committed yet)
- **Reversible** — a subsequent `rollback()` will undo them

**When to use `flush()`:**

1. **To get auto-generated values** (e.g., auto-increment `id`) before
   committing:

   ```python
   session.add(run)
   await db.flush()
   print(run.id)  # Now populated — DB assigned the auto-increment value
   ```

2. **To enforce ordering** in multi-step operations where a later INSERT
   depends on the ID of an earlier INSERT.

3. **To trigger constraint checks** early (e.g., to catch a unique constraint
   violation before committing the full transaction).

### `await db.commit()`

```python
await db.commit()  # Flushes + commits the transaction
# Changes are now durable and visible to all connections
# Session attributes are NOT expired (expire_on_commit=False)
```

`commit()` flushes any pending changes and then commits the transaction to the
database. After commit:

- Changes are **durable** (written to the WAL and visible to all connections)
- The transaction is **closed** (a new transaction begins on the next operation)
- With `expire_on_commit=False`, ORM object attributes retain their values

**When to use `commit()`:**

- At the end of a successful request handler (done automatically by `get_db()`)
- After completing a multi-step operation that should be atomic

### `await db.rollback()`

```python
await db.rollback()  # Undoes all changes since the last commit
```

`rollback()` discards all pending changes (both flushed and unflushed) and
closes the current transaction. Called automatically by `get_db()` when an
exception is raised.

### Summary Table

| Operation | Sends SQL? | Commits? | Visible to others? | Reversible? |
|-----------|-----------|----------|-------------------|-------------|
| `session.add(obj)` | No | No | No | Yes |
| `await db.flush()` | Yes | No | No | Yes |
| `await db.commit()` | Yes (if pending) | Yes | Yes | No |
| `await db.rollback()` | No | No | — | Undoes all |

---

## Using `AsyncSessionLocal` Outside FastAPI

In Celery tasks and other non-FastAPI contexts, sessions are created directly
from `AsyncSessionLocal` using an async context manager:

```python
from app.db.session import AsyncSessionLocal
from app.db.models import OptimizationRun
from sqlalchemy import select

async def _persist_failure(run_id: str, error_message: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OptimizationRun).where(OptimizationRun.run_id == run_id)
        )
        run = result.scalar_one_or_none()

        if run is not None:
            run.mark_failed(
                error_message=error_message,
                completed_at=datetime.now(UTC),
            )
            await session.commit()
```

The `async with AsyncSessionLocal() as session:` pattern:
1. Creates a new `AsyncSession`
2. Yields it for use in the `async with` block
3. Automatically closes the session when the block exits (but does **not**
   automatically commit — you must call `await session.commit()` explicitly)

> **Note:** The `async with AsyncSessionLocal()` pattern does not automatically
> commit or rollback. Unlike the `get_db()` FastAPI dependency, you must manage
> the transaction explicitly. Always call `await session.commit()` after
> successful operations and `await session.rollback()` (or let the context
> manager close the session) on failure.

---

## Connection Pool Sizing

The default pool configuration (`pool_size=10`, `max_overflow=20`) allows up
to 30 simultaneous database connections. This is appropriate for a single
application server instance.

For production deployments with multiple Uvicorn workers or multiple application
server instances, consider:

1. **Per-worker pool:** Each Uvicorn worker process has its own connection pool.
   With 4 workers × 30 connections = 120 total connections to PostgreSQL.

2. **PostgreSQL `max_connections`:** The default is 100. Adjust
   `postgresql.conf` or use PgBouncer (connection pooler) for high-concurrency
   deployments.

3. **Celery workers:** Each Celery worker also creates its own connection pool
   when it first accesses the database. Factor this into your total connection
   count.

### Recommended Settings by Environment

| Environment | `pool_size` | `max_overflow` | Notes |
|-------------|-------------|----------------|-------|
| Development | 5 | 10 | Single process, low concurrency |
| Staging | 10 | 20 | Matches production config |
| Production | 10 | 20 | Per Uvicorn worker |
| Testing | 1 | 0 | Use `NullPool` or SQLite for unit tests |

---

## Related Pages

- [Schema](schema.md) — `optimization_runs` table structure
- [ORM Models](orm-models.md) — `OptimizationRun` model and lifecycle methods
- [Migrations](migrations.md) — Alembic setup and migration history
- [Dependencies](../03-backend/dependencies.md) — Full dependency injection reference
