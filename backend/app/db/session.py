"""SQLAlchemy async engine and session factory.

The engine and session factory are module-level singletons created once
at import time. The ``get_db`` dependency in ``app.core.dependencies``
yields sessions from this factory.

Design decisions:
    - Uses asyncpg driver for non-blocking I/O with PostgreSQL.
    - pool_pre_ping=True detects stale connections before use, preventing
      "connection already closed" errors after PostgreSQL restarts.
    - pool_recycle=3600 prevents connections from being held open indefinitely,
      which can cause issues with PostgreSQL's idle connection limits.
    - expire_on_commit=False prevents lazy-loading errors after commit, which
      is important in async contexts where the session may be closed.
    - echo=True in development logs all SQL statements for debugging.
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


_settings = get_settings()

# ── Engine ────────────────────────────────────────────────────────────────────
#
# A single engine instance is shared across all requests. The connection pool
# manages individual database connections transparently.

engine: AsyncEngine = create_async_engine(
    _settings.DATABASE_URL,
    # Log all SQL in development for easier debugging
    echo=_settings.ENVIRONMENT == "development",
    # Connection pool configuration
    pool_size=10,          # Number of persistent connections in the pool
    max_overflow=20,       # Extra connections allowed beyond pool_size
    pool_pre_ping=True,    # Verify connections before use (handles DB restarts)
    pool_recycle=3600,     # Recycle connections after 1 hour (prevents stale conns)
    pool_timeout=30,       # Seconds to wait for a connection from the pool
)

# ── Session factory ───────────────────────────────────────────────────────────
#
# async_sessionmaker is the async equivalent of sessionmaker. Each call to
# AsyncSessionLocal() creates a new session bound to the shared engine.

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Prevent lazy-load errors after commit in async context
    autocommit=False,        # Explicit transaction management
    autoflush=False,         # Explicit flush control (flush before queries as needed)
)
