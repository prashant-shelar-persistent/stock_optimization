"""FastAPI dependency injection providers.

All shared dependencies are defined here so that every module imports from
a single, consistent location. Dependencies are created lazily on first
request and cleaned up after each request via async generators.

Available dependencies:
    SettingsDep  — Cached Settings singleton
    RedisDep     — Async Redis client from the connection pool
    DbDep        — Async SQLAlchemy session (auto-commit/rollback)

Lifecycle:
    - The Redis connection pool is created on first use and closed in the
      FastAPI lifespan shutdown handler via ``close_redis()``.
    - Each database session is opened per-request, committed on clean exit,
      rolled back on exception, and always closed in the ``finally`` block.

Security hardening (Phase 1)
-----------------------------
The Redis connection pool now uses ``settings.REDIS_URL`` which has already
been rewritten by the ``Settings._inject_redis_auth`` Pydantic validator to
embed the ``REDIS_PASSWORD`` in the URL authority
(``redis://:password@host:port/db``).  This means:

  - No code in this module needs to handle the password explicitly.
  - All Redis clients created from this pool authenticate automatically.
  - The password is never logged (it is embedded in the URL, not passed as a
    separate argument that might appear in tracebacks or debug output).

The ``decode_responses=False`` setting is preserved because the data layer
uses JSON serialisation (replacing the previous pickle) for cached NumPy
arrays and DataFrames.  The WebSocket handler creates its own client with
``decode_responses=True`` for pub/sub message handling.
"""

from collections.abc import AsyncGenerator
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings


# ── Settings ──────────────────────────────────────────────────────────────────


def get_app_settings() -> "Settings":
    """FastAPI dependency that returns the cached Settings singleton.

    Uses ``lru_cache`` under the hood (via ``get_settings``) so the
    ``.env`` file is read only once per process.
    """
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


# ── Redis ─────────────────────────────────────────────────────────────────────

# Module-level connection pool singleton.
# Created on first request; reused for the lifetime of the process.
_redis_pool: aioredis.Redis | None = None  # type: ignore[type-arg]


async def get_redis(
    settings: SettingsDep,
) -> AsyncGenerator[aioredis.Redis, None]:  # type: ignore[type-arg]
    """Yield an async Redis client from the shared connection pool.

    The pool is created on first call and reused for the lifetime of the
    process. Individual connections are checked out per-request from the pool.

    Authentication
    --------------
    ``settings.REDIS_URL`` already contains the password embedded in the URL
    authority by the ``Settings._inject_redis_auth`` validator, so no
    additional auth configuration is needed here.  The ``redis.asyncio``
    client parses the URL and sends the AUTH command automatically on connect.

    The client is configured with ``decode_responses=False`` because the
    data layer uses JSON serialisation for cached NumPy arrays and DataFrames.
    The WebSocket handler creates its own client with ``decode_responses=True``
    for pub/sub message handling.

    Args:
        settings: Injected Settings singleton (contains the authenticated URL).

    Yields:
        An async Redis client backed by the shared connection pool.
    """
    global _redis_pool  # noqa: PLW0603
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,  # Password already embedded by Settings validator
            encoding="utf-8",
            decode_responses=False,  # Data layer uses JSON serialisation
            max_connections=20,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
    yield _redis_pool


RedisDep = Annotated[aioredis.Redis, Depends(get_redis)]  # type: ignore[type-arg]


# ── Database ──────────────────────────────────────────────────────────────────


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session.

    Transaction management:
        - Commits on clean exit (no exception raised).
        - Rolls back on any exception to prevent partial writes.
        - Always closes the session in the ``finally`` block to return
          the connection to the pool.

    The session factory is imported lazily to avoid circular imports
    (``db.session`` imports ``config`` which imports this module indirectly).

    Yields:
        An ``AsyncSession`` bound to the shared async engine.
    """
    from app.db.session import AsyncSessionLocal  # noqa: PLC0415

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


# ── Cleanup ───────────────────────────────────────────────────────────────────


async def close_redis() -> "None":
    """Close the global Redis connection pool.

    Call this in the FastAPI lifespan shutdown handler (``main.py``) to
    gracefully release all Redis connections before the process exits.

    This is a no-op if the pool was never initialised (e.g., in tests
    that never make a request requiring Redis).
    """
    global _redis_pool  # noqa: PLW0603
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None
