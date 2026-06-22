"""Integration tests for GET /health endpoint.

Tests cover:
1.  All services up → 200 with status=healthy
2.  All services down → 503 with status=unhealthy
3.  DB down, Redis+Celery up → 200 with status=degraded
4.  Redis down, DB+Celery up → 200 with status=degraded
5.  Celery down, DB+Redis up → 200 with status=degraded
6.  Two services down, one up → 200 with status=degraded
7.  Response body has required top-level fields: status, version, services
8.  services object has database, redis, celery fields with up/down values
9.  version field is a non-empty semver-like string
10. status field is always one of: healthy, degraded, unhealthy
11. Unhealthy response body still contains services detail
12. services values are exactly "up" or "down" (no other values)
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_checks(
    db: str = "up",
    redis: str = "up",
    celery: str = "up",
) -> tuple:
    """Return a tuple of context managers that patch all three health checks."""
    return (
        patch("app.api.health._check_database", new=AsyncMock(return_value=db)),
        patch("app.api.health._check_redis", new=AsyncMock(return_value=redis)),
        patch("app.api.health._check_celery", new=AsyncMock(return_value=celery)),
    )


# ---------------------------------------------------------------------------
# Happy path — all services up
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_all_up_returns_200(client: AsyncClient) -> None:
    """All services up → HTTP 200 with status=healthy."""
    db_p, redis_p, celery_p = _patch_checks("up", "up", "up")
    with db_p, redis_p, celery_p:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_all_up_services_all_up(client: AsyncClient) -> None:
    """When all services are up, services object shows all 'up'."""
    db_p, redis_p, celery_p = _patch_checks("up", "up", "up")
    with db_p, redis_p, celery_p:
        response = await client.get("/health")

    assert response.status_code == 200
    services = response.json()["services"]
    assert services["database"] == "up"
    assert services["redis"] == "up"
    assert services["celery"] == "up"


# ---------------------------------------------------------------------------
# Unhealthy — all services down
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_all_down_returns_503(client: AsyncClient) -> None:
    """All services down → HTTP 503 with status=unhealthy."""
    db_p, redis_p, celery_p = _patch_checks("down", "down", "down")
    with db_p, redis_p, celery_p:
        response = await client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_health_all_down_services_all_down(client: AsyncClient) -> None:
    """Unhealthy response body still contains services detail with all 'down'."""
    db_p, redis_p, celery_p = _patch_checks("down", "down", "down")
    with db_p, redis_p, celery_p:
        response = await client.get("/health")

    assert response.status_code == 503
    services = response.json()["services"]
    assert services["database"] == "down"
    assert services["redis"] == "down"
    assert services["celery"] == "down"


# ---------------------------------------------------------------------------
# Degraded — one service down
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_db_down_returns_degraded(client: AsyncClient) -> None:
    """DB down, Redis+Celery up → HTTP 200 with status=degraded."""
    db_p, redis_p, celery_p = _patch_checks("down", "up", "up")
    with db_p, redis_p, celery_p:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"]["database"] == "down"
    assert body["services"]["redis"] == "up"
    assert body["services"]["celery"] == "up"


@pytest.mark.asyncio
async def test_health_redis_down_returns_degraded(client: AsyncClient) -> None:
    """Redis down, DB+Celery up → HTTP 200 with status=degraded."""
    db_p, redis_p, celery_p = _patch_checks("up", "down", "up")
    with db_p, redis_p, celery_p:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"]["database"] == "up"
    assert body["services"]["redis"] == "down"
    assert body["services"]["celery"] == "up"


@pytest.mark.asyncio
async def test_health_celery_down_returns_degraded(client: AsyncClient) -> None:
    """Celery down, DB+Redis up → HTTP 200 with status=degraded."""
    db_p, redis_p, celery_p = _patch_checks("up", "up", "down")
    with db_p, redis_p, celery_p:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"]["database"] == "up"
    assert body["services"]["redis"] == "up"
    assert body["services"]["celery"] == "down"


@pytest.mark.asyncio
async def test_health_two_services_down_returns_degraded(client: AsyncClient) -> None:
    """Two services down, one up → HTTP 200 with status=degraded."""
    db_p, redis_p, celery_p = _patch_checks("down", "down", "up")
    with db_p, redis_p, celery_p:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_response_has_required_fields(client: AsyncClient) -> None:
    """Response body has required top-level fields: status, version, services."""
    db_p, redis_p, celery_p = _patch_checks("up", "up", "up")
    with db_p, redis_p, celery_p:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert "status" in body, "Missing 'status' field"
    assert "version" in body, "Missing 'version' field"
    assert "services" in body, "Missing 'services' field"


@pytest.mark.asyncio
async def test_health_services_has_all_three_fields(client: AsyncClient) -> None:
    """services object has database, redis, and celery fields."""
    db_p, redis_p, celery_p = _patch_checks("up", "up", "up")
    with db_p, redis_p, celery_p:
        response = await client.get("/health")

    services = response.json()["services"]
    assert "database" in services, "Missing 'database' in services"
    assert "redis" in services, "Missing 'redis' in services"
    assert "celery" in services, "Missing 'celery' in services"


@pytest.mark.asyncio
async def test_health_version_is_nonempty_string(client: AsyncClient) -> None:
    """version field is a non-empty string."""
    db_p, redis_p, celery_p = _patch_checks("up", "up", "up")
    with db_p, redis_p, celery_p:
        response = await client.get("/health")

    version = response.json()["version"]
    assert isinstance(version, str)
    assert len(version) > 0


@pytest.mark.asyncio
async def test_health_version_is_semver_like(client: AsyncClient) -> None:
    """version field looks like a semantic version (e.g. '0.1.0')."""
    db_p, redis_p, celery_p = _patch_checks("up", "up", "up")
    with db_p, redis_p, celery_p:
        response = await client.get("/health")

    version = response.json()["version"]
    parts = version.split(".")
    assert len(parts) >= 2, f"Expected semver-like version, got: {version!r}"
    assert all(p.isdigit() for p in parts), (
        f"Non-numeric version parts in: {version!r}"
    )


@pytest.mark.asyncio
async def test_health_status_is_valid_literal(client: AsyncClient) -> None:
    """status field is always one of: healthy, degraded, unhealthy."""
    valid_statuses = {"healthy", "degraded", "unhealthy"}

    for db, redis, celery in [
        ("up", "up", "up"),
        ("down", "up", "up"),
        ("up", "down", "up"),
        ("up", "up", "down"),
        ("down", "down", "down"),
    ]:
        db_p, redis_p, celery_p = _patch_checks(db, redis, celery)
        with db_p, redis_p, celery_p:
            response = await client.get("/health")

        status = response.json()["status"]
        assert status in valid_statuses, (
            f"Unexpected status {status!r} for db={db}, redis={redis}, celery={celery}"
        )


@pytest.mark.asyncio
async def test_health_services_values_are_up_or_down(client: AsyncClient) -> None:
    """services values are exactly 'up' or 'down' — no other values allowed."""
    valid_values = {"up", "down"}

    for db, redis, celery in [
        ("up", "up", "up"),
        ("down", "up", "up"),
        ("down", "down", "down"),
    ]:
        db_p, redis_p, celery_p = _patch_checks(db, redis, celery)
        with db_p, redis_p, celery_p:
            response = await client.get("/health")

        services = response.json()["services"]
        for key, val in services.items():
            assert val in valid_values, (
                f"services.{key}={val!r} is not 'up' or 'down'"
            )
