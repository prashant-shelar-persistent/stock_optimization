"""Integration tests for GET /health endpoint.

Tests cover:
1. All services up → 200 with status=healthy
2. One service down → 200 with status=degraded
3. All services down → 503 with status=unhealthy
4. Response body has correct shape (status, version, services)
5. services object has database, redis, celery fields
6. version field is a non-empty string
7. DB down, Redis+Celery up → degraded
8. Redis down, DB+Celery up → degraded
9. Celery down, DB+Redis up → degraded
10. status field is one of: healthy, degraded, unhealthy
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_checks(db: str = "up", redis: str = "up", celery: str = "up"):
    """Context manager that patches all three health check functions."""
    return (
        patch("app.api.health._check_database", new=AsyncMock(return_value=db)),
        patch("app.api.health._check_redis", new=AsyncMock(return_value=redis)),
        patch("app.api.health._check_celery", new=AsyncMock(return_value=celery)),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_all_up_returns_200_healthy() -> None:
    """All services up → HTTP 200 with status=healthy."""
    db_patch, redis_patch, celery_patch = _patch_checks("up", "up", "up")
    with db_patch, redis_patch, celery_patch:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_response_shape() -> None:
    """Response body has required top-level fields."""
    db_patch, redis_patch, celery_patch = _patch_checks("up", "up", "up")
    with db_patch, redis_patch, celery_patch:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "version" in body
    assert "services" in body
    assert isinstance(body["version"], str)
    assert len(body["version"]) > 0


@pytest.mark.asyncio
async def test_health_services_shape() -> None:
    """services object has database, redis, celery fields."""
    db_patch, redis_patch, celery_patch = _patch_checks("up", "up", "up")
    with db_patch, redis_patch, celery_patch:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    services = response.json()["services"]
    assert "database" in services
    assert "redis" in services
    assert "celery" in services
    assert services["database"] == "up"
    assert services["redis"] == "up"
    assert services["celery"] == "up"


@pytest.mark.asyncio
async def test_health_all_down_returns_503_unhealthy() -> None:
    """All services down → HTTP 503 with status=unhealthy."""
    db_patch, redis_patch, celery_patch = _patch_checks("down", "down", "down")
    with db_patch, redis_patch, celery_patch:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["services"]["database"] == "down"
    assert body["services"]["redis"] == "down"
    assert body["services"]["celery"] == "down"


@pytest.mark.asyncio
async def test_health_db_down_returns_degraded() -> None:
    """DB down, Redis+Celery up → HTTP 200 with status=degraded."""
    db_patch, redis_patch, celery_patch = _patch_checks("down", "up", "up")
    with db_patch, redis_patch, celery_patch:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"]["database"] == "down"
    assert body["services"]["redis"] == "up"
    assert body["services"]["celery"] == "up"


@pytest.mark.asyncio
async def test_health_redis_down_returns_degraded() -> None:
    """Redis down, DB+Celery up → HTTP 200 with status=degraded."""
    db_patch, redis_patch, celery_patch = _patch_checks("up", "down", "up")
    with db_patch, redis_patch, celery_patch:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"]["database"] == "up"
    assert body["services"]["redis"] == "down"
    assert body["services"]["celery"] == "up"


@pytest.mark.asyncio
async def test_health_celery_down_returns_degraded() -> None:
    """Celery down, DB+Redis up → HTTP 200 with status=degraded."""
    db_patch, redis_patch, celery_patch = _patch_checks("up", "up", "down")
    with db_patch, redis_patch, celery_patch:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"]["database"] == "up"
    assert body["services"]["redis"] == "up"
    assert body["services"]["celery"] == "down"


@pytest.mark.asyncio
async def test_health_two_services_down_returns_degraded() -> None:
    """Two services down, one up → HTTP 200 with status=degraded."""
    db_patch, redis_patch, celery_patch = _patch_checks("down", "down", "up")
    with db_patch, redis_patch, celery_patch:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_health_status_is_valid_literal() -> None:
    """Status field is always one of: healthy, degraded, unhealthy."""
    valid_statuses = {"healthy", "degraded", "unhealthy"}

    for db, redis, celery in [
        ("up", "up", "up"),
        ("down", "up", "up"),
        ("down", "down", "down"),
    ]:
        db_patch, redis_patch, celery_patch = _patch_checks(db, redis, celery)
        with db_patch, redis_patch, celery_patch:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/health")

        assert response.json()["status"] in valid_statuses


@pytest.mark.asyncio
async def test_health_version_is_semver_like() -> None:
    """Version field looks like a semantic version string (e.g. '0.1.0')."""
    db_patch, redis_patch, celery_patch = _patch_checks("up", "up", "up")
    with db_patch, redis_patch, celery_patch:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    version = response.json()["version"]
    parts = version.split(".")
    assert len(parts) >= 2, f"Expected semver-like version, got: {version!r}"
    assert all(p.isdigit() for p in parts), f"Non-numeric version parts in: {version!r}"
