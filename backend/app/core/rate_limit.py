"""Redis-backed rate limiting via slowapi.

This module provides a shared ``Limiter`` instance that is used across all
API routers to enforce per-client request rate limits.  The limiter uses
Redis as its storage backend so that limits are enforced consistently across
multiple Uvicorn worker processes and Celery workers — unlike the previous
in-process ``defaultdict`` approach which was per-process only.

Architecture
------------
- ``get_limiter()`` — factory that creates (or returns the cached) ``Limiter``
  instance.  The Redis URL is read from ``Settings.REDIS_URL`` which already
  has the password embedded by the ``Settings._inject_redis_auth`` validator.
- ``limiter`` — module-level singleton used as a decorator source in route
  handlers (``@limiter.limit("5/minute")``).
- ``_key_func`` — extracts the client identifier from the request.  Uses the
  ``X-Forwarded-For`` header when present (for deployments behind a reverse
  proxy) and falls back to the direct client IP.

Rate limit strings follow the ``slowapi`` / ``limits`` library format:
    ``"N/period"`` where period is ``second``, ``minute``, ``hour``, ``day``.
    Examples: ``"10/minute"``, ``"100/hour"``, ``"5/second"``.

Usage in route handlers::

    from app.core.rate_limit import limiter

    @router.get("/my-endpoint")
    @limiter.limit("30/minute")
    async def my_endpoint(request: Request) -> ...:
        ...

The ``request: Request`` parameter MUST be present in the route handler
signature for slowapi to inject the rate-limit state.  slowapi inspects the
function signature to find the ``Request`` object.

The ``Limiter`` must also be attached to the FastAPI ``app.state`` in
``main.py`` (``app.state.limiter = limiter``) and the ``RateLimitExceeded``
exception handler must be registered.  Both are handled in ``main.py``.

Graceful degradation
--------------------
If Redis is unavailable at startup the limiter falls back to an in-memory
storage backend so the application continues to serve requests (without
cross-process rate limiting).  A warning is logged in that case.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from slowapi import Limiter


logger = logging.getLogger(__name__)

# ── Default rate limits per endpoint category ─────────────────────────────────
# These are the default limits applied via decorators on each route.
# They can be overridden per-route by passing a different string to
# ``@limiter.limit()``.

#: General read endpoints (assets search, run history, run status)
RATE_LIMIT_READ = "60/minute"

#: Write / compute-intensive endpoints (optimize submission)
RATE_LIMIT_WRITE = "10/minute"

#: Chat message endpoints (LLM calls are expensive)
RATE_LIMIT_CHAT = "30/minute"

#: Chat session creation
RATE_LIMIT_CHAT_CREATE = "10/minute"


def _get_client_ip(request: Request) -> str:
    """Extract the real client IP from the request.

    Checks ``X-Forwarded-For`` first (set by reverse proxies / load balancers)
    and falls back to the direct connection IP.  Only the first IP in the
    ``X-Forwarded-For`` chain is used (the original client IP).

    Args:
        request: The incoming FastAPI/Starlette request.

    Returns:
        Client IP address string, or ``"unknown"`` if it cannot be determined.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For: client, proxy1, proxy2
        # Take the leftmost (original client) IP
        return forwarded_for.split(",")[0].strip()

    if request.client:
        return request.client.host

    return "unknown"


@lru_cache(maxsize=1)
def get_limiter() -> "Limiter":
    """Create and return the shared slowapi ``Limiter`` instance.

    The limiter is created once per process (``lru_cache`` ensures this) and
    uses Redis as its storage backend.  The Redis URL is read from application
    settings so that the password (if configured) is automatically included.

    Storage backend selection:
    1. If ``slowapi`` and ``limits`` are installed and Redis is reachable,
       uses ``RedisStorage`` for cross-process rate limiting.
    2. Falls back to in-memory storage if Redis is unavailable, logging a
       warning.  This means rate limits are per-process only in that case.

    Returns:
        A configured ``slowapi.Limiter`` instance.
    """
    from slowapi import Limiter  # noqa: PLC0415

    try:
        from app.core.config import get_settings  # noqa: PLC0415

        settings = get_settings()
        redis_url = settings.REDIS_URL

        # Use Redis storage for cross-process rate limiting.
        # slowapi uses the ``limits`` library under the hood; the storage URI
        # format for Redis is ``redis://host:port/db`` (same as redis-py).
        storage_uri = redis_url

        limiter_instance = Limiter(
            key_func=_get_client_ip,
            storage_uri=storage_uri,
            default_limits=[],  # No global default; limits are per-route
            headers_enabled=True,  # Add X-RateLimit-* headers to responses
            strategy="fixed-window",  # Simple fixed-window counter
        )

        logger.info(
            "rate_limiter_initialised",
            extra={"storage": "redis", "redis_url": redis_url.split("@")[-1]},
        )
        return limiter_instance

    except Exception as exc:
        logger.warning(
            "rate_limiter_redis_unavailable_falling_back_to_memory",
            extra={"error": str(exc)},
        )
        # Fallback: in-memory storage (per-process only)
        return Limiter(
            key_func=_get_client_ip,
            default_limits=[],
            headers_enabled=True,
            strategy="fixed-window",
        )


# ── Module-level singleton ─────────────────────────────────────────────────────
# Import this in route handlers:
#   from app.core.rate_limit import limiter
#
# The limiter is initialised lazily on first access via get_limiter().
# This avoids importing Redis/settings at module import time, which would
# break tests that patch settings before importing route modules.

class _LazyLimiter:
    """Proxy that initialises the real Limiter on first attribute access.

    This allows ``from app.core.rate_limit import limiter`` at module level
    in route handlers without triggering Redis connections at import time.
    The real ``Limiter`` is created on the first ``@limiter.limit(...)`` call
    or when the limiter is attached to ``app.state``.
    """

    def __init__(self) -> None:
        self._instance: "Limiter | None" = None

    def _get(self) -> "Limiter":
        if self._instance is None:
            self._instance = get_limiter()
        return self._instance

    def __getattr__(self, name: str) -> object:
        return getattr(self._get(), name)

    def limit(self, *args: object, **kwargs: object) -> object:  # type: ignore[override]
        """Delegate to the real Limiter.limit() decorator."""
        return self._get().limit(*args, **kwargs)  # type: ignore[return-value]

    def shared_limit(self, *args: object, **kwargs: object) -> object:
        """Delegate to the real Limiter.shared_limit() decorator."""
        return self._get().shared_limit(*args, **kwargs)  # type: ignore[return-value]


#: Shared rate limiter instance.  Import this in route handlers.
limiter: "Limiter" = _LazyLimiter()  # type: ignore[assignment]
