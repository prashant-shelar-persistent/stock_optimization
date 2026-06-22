"""Health check endpoint.

Returns the operational status of the application and its dependencies
(database, Redis, Celery). Used by Docker healthchecks and load balancers.

Endpoint:
    GET /health

Response codes:
    200 — healthy or degraded (at least one service is up)
    503 — unhealthy (all services are down)

Design notes:
    - All dependency checks use ``asyncio.wait_for`` with a 2-second timeout
      to prevent the health endpoint from hanging when a service is slow.
    - The overall status is:
        * ``healthy``   — all three services are up
        * ``degraded``  — at least one service is up but not all
        * ``unhealthy`` — all services are down
    - HTTP 503 is returned only when ``overall == "unhealthy"`` so that
      load balancers can remove the instance from rotation.
"""

import asyncio
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.logging import get_logger


logger = get_logger(__name__)
router = APIRouter(tags=["health"])

# Application version — should match pyproject.toml / Docker image tag
_APP_VERSION = "0.1.0"

# Timeout for each individual dependency check (seconds)
_CHECK_TIMEOUT_SECONDS = 2.0


class ServiceStatus(BaseModel):
    database: Literal["up", "down"]
    redis: Literal["up", "down"]
    celery: Literal["up", "down"]


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    version: str
    services: ServiceStatus


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application health check",
    description=(
        "Returns the health status of the application and its dependencies. "
        "Returns HTTP 200 if healthy or degraded (at least one service up). "
        "Returns HTTP 503 if all services are down (unhealthy)."
    ),
    responses={
        200: {"description": "Application is healthy or degraded"},
        503: {"description": "Application is unhealthy — all services are down"},
    },
)
async def health_check(response: Response) -> "HealthResponse":
    """Check the health of all application dependencies.

    Runs all three checks concurrently to minimise latency. Each check
    has a 2-second timeout to prevent the endpoint from hanging.
    """
    # Run all checks concurrently
    db_status, redis_status, celery_status = await asyncio.gather(
        _check_database(),
        _check_redis(),
        _check_celery(),
        return_exceptions=False,
    )

    services = ServiceStatus(
        database=db_status,
        redis=redis_status,
        celery=celery_status,
    )

    # Determine overall status
    statuses = [db_status, redis_status, celery_status]
    all_up = all(s == "up" for s in statuses)
    any_up = any(s == "up" for s in statuses)

    if all_up:
        overall: Literal["healthy", "degraded", "unhealthy"] = "healthy"
    elif any_up:
        overall = "degraded"
    else:
        overall = "unhealthy"

    logger.info(
        "health_check",
        overall=overall,
        database=db_status,
        redis=redis_status,
        celery=celery_status,
    )

    # Return HTTP 503 when all services are down
    if overall == "unhealthy":
        response.status_code = 503

    return HealthResponse(
        status=overall,
        version=_APP_VERSION,
        services=services,
    )


async def _check_database() -> Literal["up", "down"]:
    """Ping the PostgreSQL database with a 2-second timeout."""
    try:
        from app.db.session import engine  # noqa: PLC0415
        import sqlalchemy  # noqa: PLC0415

        async def _ping() -> None:
            async with engine.connect() as conn:
                await conn.execute(sqlalchemy.text("SELECT 1"))

        await asyncio.wait_for(_ping(), timeout=_CHECK_TIMEOUT_SECONDS)
        return "up"
    except asyncio.TimeoutError:
        logger.warning("health_check_db_timeout")
        return "down"
    except Exception as exc:
        logger.warning("health_check_db_failed", error=str(exc))
        return "down"


async def _check_redis() -> Literal["up", "down"]:
    """Ping the Redis server with a 2-second timeout."""
    try:
        import redis.asyncio as aioredis  # noqa: PLC0415

        settings = get_settings()
        client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        try:
            await asyncio.wait_for(client.ping(), timeout=_CHECK_TIMEOUT_SECONDS)
        finally:
            await client.aclose()
        return "up"
    except asyncio.TimeoutError:
        logger.warning("health_check_redis_timeout")
        return "down"
    except Exception as exc:
        logger.warning("health_check_redis_failed", error=str(exc))
        return "down"


async def _check_celery() -> Literal["up", "down"]:
    """Check if Celery workers are reachable via broker ping.

    Runs the synchronous Celery ping in a thread pool executor to avoid
    blocking the async event loop.
    """
    try:
        from app.workers.celery_app import celery_app  # noqa: PLC0415

        loop = asyncio.get_running_loop()

        def _ping() -> list:  # type: ignore[type-arg]
            return celery_app.control.ping(timeout=_CHECK_TIMEOUT_SECONDS)

        result = await asyncio.wait_for(
            loop.run_in_executor(None, _ping),
            timeout=_CHECK_TIMEOUT_SECONDS + 1.0,  # Slightly longer than inner timeout
        )
        return "up" if result else "down"
    except asyncio.TimeoutError:
        logger.warning("health_check_celery_timeout")
        return "down"
    except Exception as exc:
        logger.warning("health_check_celery_failed", error=str(exc))
        return "down"
