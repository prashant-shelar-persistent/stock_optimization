"""E2E smoke tests for the Portfolio Optimizer API.

These tests exercise every public API endpoint end-to-end using real HTTP
requests.  By default they use ASGI transport (no real network socket) so
they run in CI without any external services.  Set ``E2E_USE_REAL_SERVER=1``
and ``E2E_BASE_URL=http://localhost:8000`` to run against a live deployment.

Scenarios covered
-----------------
1.  Health endpoint — returns 200 with ``status``, ``version``, ``services``
2.  Health endpoint — all-services-down returns 503 with ``status=unhealthy``
3.  Health endpoint — partial degradation returns 200 with ``status=degraded``
4.  Asset search — known ticker (AAPL) returns correct name and sector
5.  Asset search — company name query (Apple) returns AAPL in results
6.  Asset search — empty query returns 422 validation error
7.  Asset search — limit parameter is respected
8.  Optimize submit — minimal valid request returns 202 with UUID run_id
9.  Optimize submit — full request with all constraints returns 202
10. Optimize submit — missing required field returns 422 with detail
11. Optimize submit — single ticker (< 2) returns 422 validation error
12. Optimize submit — ticker exceeding max length returns 422
13. Run status — pending run returns correct shape
14. Run status — unknown run_id returns 404 with ``error_code=RUN_NOT_FOUND``
15. Run detail — completed run returns full result shape
16. Run detail — unknown run_id returns 404 with ``error_code=RUN_NOT_FOUND``
17. Run list — returns paginated response with ``items``, ``total``, ``page``
18. Run list — page_size parameter is respected
19. Run list — status filter returns only matching runs
20. Run list — invalid status filter returns 422
21. Full flow — submit → run appears in list with correct run_id
22. Prometheus /metrics — returns text/plain content with metric names
23. OpenAPI schema — /openapi.json documents all key routes
24. CORS headers — preflight returns ``Access-Control-Allow-Origin``
25. Concurrent submits — all return unique run_ids (no collisions)
"""

import asyncio
import os
import re
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.db.models import OptimizationRun
from app.main import app


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_USE_REAL_SERVER: bool = os.getenv("E2E_USE_REAL_SERVER", "0") == "1"
_BASE_URL: str = os.getenv("E2E_BASE_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Async HTTP client.

    Uses ASGI transport by default (no real socket).  Set
    ``E2E_USE_REAL_SERVER=1`` to send real HTTP requests to ``E2E_BASE_URL``.
    """
    if _USE_REAL_SERVER:
        async with AsyncClient(base_url=_BASE_URL, timeout=30.0) as ac:
            yield ac
    else:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            yield ac


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_write_session() -> AsyncMock:
    """Mock DB session for write operations (POST /optimize)."""
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


def _make_list_session(
    runs: list[OptimizationRun],
    total: int | None = None,
) -> AsyncMock:
    """Mock DB session for paginated list queries."""
    session = AsyncMock(spec=AsyncSession)

    count_result = MagicMock()
    count_result.scalar_one.return_value = total if total is not None else len(runs)

    rows_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = runs
    rows_result.scalars.return_value = scalars_mock

    session.execute = AsyncMock(side_effect=[count_result, rows_result])
    return session


def _make_single_session(run: OptimizationRun | None) -> AsyncMock:
    """Mock DB session for single-row lookup queries."""
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = run
    session.execute = AsyncMock(return_value=result)
    return session


def _make_run(
    run_id: str | None = None,
    status: str = "completed",
    tickers: list[str] | None = None,
    budget: float = 100_000.0,
    classical_sharpe: float | None = 1.25,
    quantum_sharpe: float | None = None,
    classical_result: dict[str, Any] | None = None,
    llm_explanation: str | None = None,
    error_message: str | None = None,
) -> OptimizationRun:
    """Build a minimal OptimizationRun ORM object for testing."""
    run = OptimizationRun()
    run.run_id = run_id or str(uuid.uuid4())
    run.status = status
    run.tickers = tickers or ["AAPL", "MSFT", "GOOGL"]
    run.budget = budget
    run.request_params = {
        "tickers": run.tickers,
        "budget": budget,
        "run_quantum": False,
    }
    run.classical_sharpe = classical_sharpe
    run.quantum_sharpe = quantum_sharpe
    run.classical_result = classical_result
    run.quantum_result = None
    run.comparison = None
    run.llm_explanation = llm_explanation
    run.error_message = error_message
    run.created_at = datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)
    run.completed_at = (
        datetime(2024, 6, 1, 10, 5, 0, tzinfo=UTC)
        if status in ("completed", "failed")
        else None
    )
    return run


def _override_db(session: AsyncMock):
    """Return an async generator dependency override."""

    async def _dep():
        yield session

    return _dep


# ---------------------------------------------------------------------------
# Scenario 1: Health endpoint — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_returns_200_when_all_services_up(client: AsyncClient) -> None:
    """GET /health returns HTTP 200 when all services are up."""
    with (
        patch("app.api.health._check_database", return_value="up"),
        patch("app.api.health._check_redis", return_value="up"),
        patch("app.api.health._check_celery", return_value="up"),
    ):
        response = await client.get("/health")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_body_contains_status_healthy(client: AsyncClient) -> None:
    """GET /health body has status='healthy' when all services are up."""
    with (
        patch("app.api.health._check_database", return_value="up"),
        patch("app.api.health._check_redis", return_value="up"),
        patch("app.api.health._check_celery", return_value="up"),
    ):
        response = await client.get("/health")

    body = response.json()
    assert body["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_body_contains_version_semver(client: AsyncClient) -> None:
    """GET /health body has a semver-formatted version string."""
    with (
        patch("app.api.health._check_database", return_value="up"),
        patch("app.api.health._check_redis", return_value="up"),
        patch("app.api.health._check_celery", return_value="up"),
    ):
        response = await client.get("/health")

    body = response.json()
    assert "version" in body
    assert re.match(r"^\d+\.\d+\.\d+", body["version"]), (
        f"version '{body['version']}' does not look like semver"
    )


@pytest.mark.asyncio
async def test_health_body_contains_all_service_keys(client: AsyncClient) -> None:
    """GET /health body has services.database, services.redis, services.celery."""
    with (
        patch("app.api.health._check_database", return_value="up"),
        patch("app.api.health._check_redis", return_value="up"),
        patch("app.api.health._check_celery", return_value="up"),
    ):
        response = await client.get("/health")

    body = response.json()
    services = body["services"]
    assert services["database"] == "up"
    assert services["redis"] == "up"
    assert services["celery"] == "up"


# ---------------------------------------------------------------------------
# Scenario 2: Health endpoint — all services down → 503
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_returns_503_when_all_services_down(client: AsyncClient) -> None:
    """GET /health returns HTTP 503 when all services are down."""
    with (
        patch("app.api.health._check_database", return_value="down"),
        patch("app.api.health._check_redis", return_value="down"),
        patch("app.api.health._check_celery", return_value="down"),
    ):
        response = await client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"


# ---------------------------------------------------------------------------
# Scenario 3: Health endpoint — partial degradation → 200 degraded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_returns_200_degraded_when_some_services_down(
    client: AsyncClient,
) -> None:
    """GET /health returns 200 with status='degraded' when only DB is up."""
    with (
        patch("app.api.health._check_database", return_value="up"),
        patch("app.api.health._check_redis", return_value="down"),
        patch("app.api.health._check_celery", return_value="down"),
    ):
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"]["database"] == "up"
    assert body["services"]["redis"] == "down"
    assert body["services"]["celery"] == "down"


# ---------------------------------------------------------------------------
# Scenario 4: Asset search — known ticker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_asset_search_aapl_returns_correct_name_and_sector(
    client: AsyncClient,
) -> None:
    """GET /api/v1/assets/search?q=AAPL returns Apple Inc. in Technology sector."""
    response = await client.get("/api/v1/assets/search", params={"q": "AAPL"})

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1

    # First result should be AAPL
    first = body[0]
    assert first["ticker"] == "AAPL"
    assert "Apple" in first["name"]
    assert first["sector"] == "Technology"


@pytest.mark.asyncio
async def test_asset_search_result_has_required_fields(client: AsyncClient) -> None:
    """GET /api/v1/assets/search result items have ticker, name, sector, exchange."""
    response = await client.get("/api/v1/assets/search", params={"q": "MSFT"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 1

    item = body[0]
    assert "ticker" in item
    assert "name" in item
    # sector and exchange may be None for unknown tickers but key must exist
    assert "sector" in item
    assert "exchange" in item


# ---------------------------------------------------------------------------
# Scenario 5: Asset search — company name query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_asset_search_by_company_name_returns_results(
    client: AsyncClient,
) -> None:
    """GET /api/v1/assets/search?q=Apple returns results containing AAPL."""
    response = await client.get("/api/v1/assets/search", params={"q": "Apple"})

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1

    tickers = [item["ticker"] for item in body]
    assert "AAPL" in tickers, f"Expected AAPL in results, got: {tickers}"


# ---------------------------------------------------------------------------
# Scenario 6: Asset search — empty query returns 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_asset_search_empty_query_returns_422(client: AsyncClient) -> None:
    """GET /api/v1/assets/search?q= returns 422 for empty query string."""
    response = await client.get("/api/v1/assets/search", params={"q": ""})

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body


# ---------------------------------------------------------------------------
# Scenario 7: Asset search — limit parameter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_asset_search_limit_parameter_is_respected(client: AsyncClient) -> None:
    """GET /api/v1/assets/search?q=a&limit=3 returns at most 3 results."""
    response = await client.get(
        "/api/v1/assets/search", params={"q": "a", "limit": 3}
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) <= 3


# ---------------------------------------------------------------------------
# Scenario 8: Optimize submit — minimal valid request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimize_submit_minimal_request_returns_202(
    client: AsyncClient,
) -> None:
    """POST /api/v1/optimize with minimal valid payload returns 202."""
    session = _make_write_session()
    app.dependency_overrides[get_db] = _override_db(session)

    try:
        with patch(
            "app.workers.tasks.run_optimization_task.apply_async"
        ) as mock_task:
            mock_task.return_value = MagicMock()
            response = await client.post(
                "/api/v1/optimize",
                json={
                    "tickers": ["AAPL", "MSFT"],
                    "budget": 50_000.0,
                    "run_quantum": False,
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 202
    body = response.json()
    assert "run_id" in body
    # run_id must be a valid UUID
    try:
        uuid.UUID(body["run_id"])
    except ValueError:
        pytest.fail(f"run_id '{body['run_id']}' is not a valid UUID")


@pytest.mark.asyncio
async def test_optimize_submit_returns_unique_run_id(client: AsyncClient) -> None:
    """POST /api/v1/optimize returns a non-empty UUID string as run_id."""
    session = _make_write_session()
    app.dependency_overrides[get_db] = _override_db(session)

    try:
        with patch(
            "app.workers.tasks.run_optimization_task.apply_async"
        ) as mock_task:
            mock_task.return_value = MagicMock()
            response = await client.post(
                "/api/v1/optimize",
                json={
                    "tickers": ["AAPL", "MSFT"],
                    "budget": 50_000.0,
                    "run_quantum": False,
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    body = response.json()
    run_id = body["run_id"]
    assert len(run_id) > 0
    # UUID4 format: 8-4-4-4-12 hex chars
    assert re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        run_id,
    ), f"run_id '{run_id}' is not a valid UUID4"


# ---------------------------------------------------------------------------
# Scenario 9: Optimize submit — full request with all constraints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimize_submit_full_request_returns_202(client: AsyncClient) -> None:
    """POST /api/v1/optimize with all optional constraints returns 202."""
    session = _make_write_session()
    app.dependency_overrides[get_db] = _override_db(session)

    try:
        with patch(
            "app.workers.tasks.run_optimization_task.apply_async"
        ) as mock_task:
            mock_task.return_value = MagicMock()
            response = await client.post(
                "/api/v1/optimize",
                json={
                    "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN"],
                    "budget": 200_000.0,
                    "run_quantum": False,
                    "min_return": 0.08,
                    "max_volatility": 0.25,
                    "max_weight_per_asset": 0.4,
                    "min_weight_per_asset": 0.05,
                    "sector_constraints": [
                        {"sector": "Technology", "max_weight": 0.6}
                    ],
                    "num_assets_to_select": 3,
                    "lookback_days": 365,
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 202
    body = response.json()
    assert "run_id" in body
    uuid.UUID(body["run_id"])  # Must be a valid UUID


# ---------------------------------------------------------------------------
# Scenario 10: Optimize submit — missing required field → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimize_submit_missing_budget_returns_422(
    client: AsyncClient,
) -> None:
    """POST /api/v1/optimize without 'budget' returns 422 with detail."""
    response = await client.post(
        "/api/v1/optimize",
        json={"tickers": ["AAPL", "MSFT"]},
    )

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
    # detail should mention the missing field
    detail_str = str(body["detail"])
    assert "budget" in detail_str.lower()


# ---------------------------------------------------------------------------
# Scenario 11: Optimize submit — single ticker → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimize_submit_single_ticker_returns_422(
    client: AsyncClient,
) -> None:
    """POST /api/v1/optimize with only one ticker returns 422."""
    response = await client.post(
        "/api/v1/optimize",
        json={"tickers": ["AAPL"], "budget": 10_000.0},
    )

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body


# ---------------------------------------------------------------------------
# Scenario 12: Optimize submit — ticker exceeding max length → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimize_submit_long_ticker_returns_422(client: AsyncClient) -> None:
    """POST /api/v1/optimize with a ticker > 10 chars returns 422."""
    response = await client.post(
        "/api/v1/optimize",
        json={
            "tickers": ["AAPL", "TOOLONGTICKER"],
            "budget": 10_000.0,
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body


# ---------------------------------------------------------------------------
# Scenario 13: Run status — pending run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_status_pending_run_returns_correct_shape(
    client: AsyncClient,
) -> None:
    """GET /api/v1/runs/{run_id}/status returns run_id, status, created_at."""
    run_id = str(uuid.uuid4())
    run = _make_run(run_id=run_id, status="pending")
    run.completed_at = None  # Pending runs have no completed_at

    session = _make_single_session(run)
    app.dependency_overrides[get_db] = _override_db(session)

    try:
        response = await client.get(f"/api/v1/runs/{run_id}/status")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["status"] == "pending"
    assert "created_at" in body
    assert body["completed_at"] is None


# ---------------------------------------------------------------------------
# Scenario 14: Run status — unknown run_id → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_status_unknown_run_id_returns_404(client: AsyncClient) -> None:
    """GET /api/v1/runs/{run_id}/status returns 404 for unknown run_id."""
    unknown_id = str(uuid.uuid4())
    session = _make_single_session(None)
    app.dependency_overrides[get_db] = _override_db(session)

    try:
        response = await client.get(f"/api/v1/runs/{unknown_id}/status")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404
    body = response.json()
    assert "detail" in body
    detail = body["detail"]
    assert detail["error_code"] == "RUN_NOT_FOUND"
    assert unknown_id in detail["message"]


# ---------------------------------------------------------------------------
# Scenario 15: Run detail — completed run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_detail_completed_run_returns_full_shape(
    client: AsyncClient,
) -> None:
    """GET /api/v1/runs/{run_id} returns full detail for a completed run."""
    run_id = str(uuid.uuid4())
    run = _make_run(
        run_id=run_id,
        status="completed",
        classical_sharpe=1.42,
        llm_explanation="The portfolio is well-diversified.",
    )

    session = _make_single_session(run)
    app.dependency_overrides[get_db] = _override_db(session)

    try:
        response = await client.get(f"/api/v1/runs/{run_id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["status"] == "completed"
    assert body["classical_sharpe"] == pytest.approx(1.42)
    assert body["llm_explanation"] == "The portfolio is well-diversified."
    assert "tickers" in body
    assert "budget" in body
    assert "created_at" in body
    assert "completed_at" in body


# ---------------------------------------------------------------------------
# Scenario 16: Run detail — unknown run_id → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_detail_unknown_run_id_returns_404(client: AsyncClient) -> None:
    """GET /api/v1/runs/{run_id} returns 404 with error_code for unknown id."""
    unknown_id = str(uuid.uuid4())
    session = _make_single_session(None)
    app.dependency_overrides[get_db] = _override_db(session)

    try:
        response = await client.get(f"/api/v1/runs/{unknown_id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404
    body = response.json()
    detail = body["detail"]
    assert detail["error_code"] == "RUN_NOT_FOUND"
    assert unknown_id in detail["message"]


# ---------------------------------------------------------------------------
# Scenario 17: Run list — paginated response shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_list_returns_paginated_shape(client: AsyncClient) -> None:
    """GET /api/v1/runs returns items, total, page, page_size."""
    runs = [_make_run(run_id=str(uuid.uuid4())) for _ in range(3)]
    session = _make_list_session(runs, total=3)
    app.dependency_overrides[get_db] = _override_db(session)

    try:
        response = await client.get("/api/v1/runs")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert "page_size" in body
    assert body["total"] == 3
    assert body["page"] == 1
    assert len(body["items"]) == 3


# ---------------------------------------------------------------------------
# Scenario 18: Run list — page_size parameter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_list_page_size_parameter_respected(client: AsyncClient) -> None:
    """GET /api/v1/runs?page_size=2 returns at most 2 items."""
    runs = [_make_run(run_id=str(uuid.uuid4())) for _ in range(2)]
    session = _make_list_session(runs, total=10)
    app.dependency_overrides[get_db] = _override_db(session)

    try:
        response = await client.get("/api/v1/runs", params={"page_size": 2})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["page_size"] == 2
    assert len(body["items"]) <= 2
    assert body["total"] == 10


# ---------------------------------------------------------------------------
# Scenario 19: Run list — status filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_list_status_filter_returns_matching_runs(
    client: AsyncClient,
) -> None:
    """GET /api/v1/runs?status=completed returns only completed runs."""
    completed_runs = [
        _make_run(run_id=str(uuid.uuid4()), status="completed") for _ in range(2)
    ]
    session = _make_list_session(completed_runs, total=2)
    app.dependency_overrides[get_db] = _override_db(session)

    try:
        response = await client.get("/api/v1/runs", params={"status": "completed"})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    for item in body["items"]:
        assert item["status"] == "completed"


# ---------------------------------------------------------------------------
# Scenario 20: Run list — invalid status filter → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_list_invalid_status_filter_returns_422(
    client: AsyncClient,
) -> None:
    """GET /api/v1/runs?status=invalid returns 422 with error_code."""
    # The list endpoint uses a mock session but the validation happens before DB
    session = _make_list_session([], total=0)
    app.dependency_overrides[get_db] = _override_db(session)

    try:
        response = await client.get("/api/v1/runs", params={"status": "invalid_status"})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
    detail = body["detail"]
    assert detail["error_code"] == "INVALID_STATUS_FILTER"


# ---------------------------------------------------------------------------
# Scenario 21: Full flow — submit → run appears in list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_flow_submit_then_run_appears_in_list(
    client: AsyncClient,
) -> None:
    """Submit an optimization run, then verify it appears in the run list."""
    # Step 1: Submit
    write_session = _make_write_session()
    app.dependency_overrides[get_db] = _override_db(write_session)

    submitted_run_id: str = ""
    try:
        with patch(
            "app.workers.tasks.run_optimization_task.apply_async"
        ) as mock_task:
            mock_task.return_value = MagicMock()
            submit_response = await client.post(
                "/api/v1/optimize",
                json={
                    "tickers": ["AAPL", "MSFT"],
                    "budget": 75_000.0,
                    "run_quantum": False,
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert submit_response.status_code == 202
    submitted_run_id = submit_response.json()["run_id"]
    assert len(submitted_run_id) > 0

    # Step 2: Verify run appears in list (mock the DB to return it)
    pending_run = _make_run(
        run_id=submitted_run_id,
        status="pending",
        tickers=["AAPL", "MSFT"],
        budget=75_000.0,
    )
    pending_run.completed_at = None

    list_session = _make_list_session([pending_run], total=1)
    app.dependency_overrides[get_db] = _override_db(list_session)

    try:
        list_response = await client.get("/api/v1/runs")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["total"] == 1
    assert len(list_body["items"]) == 1
    assert list_body["items"][0]["run_id"] == submitted_run_id
    assert list_body["items"][0]["status"] == "pending"


# ---------------------------------------------------------------------------
# Scenario 22: Prometheus /metrics endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_text(client: AsyncClient) -> None:
    """GET /metrics returns text/plain content with Prometheus metric names."""
    response = await client.get("/metrics")

    # /metrics may not be available if prometheus-fastapi-instrumentator is not
    # installed; in that case the endpoint simply doesn't exist (404).
    if response.status_code == 404:
        pytest.skip("Prometheus instrumentation not installed — /metrics unavailable")

    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert "text/plain" in content_type, (
        f"Expected text/plain content-type, got: {content_type}"
    )
    text = response.text
    # Standard Prometheus metric names that the instrumentator exposes
    assert "http_requests_total" in text or "http_request" in text, (
        "Expected Prometheus metric names in /metrics response"
    )


# ---------------------------------------------------------------------------
# Scenario 23: OpenAPI schema documents key routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_openapi_schema_documents_key_routes(client: AsyncClient) -> None:
    """GET /openapi.json documents /health, /api/v1/optimize, /api/v1/runs."""
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    body = response.json()
    assert "paths" in body
    paths = body["paths"]
    assert "/health" in paths, "Expected /health in OpenAPI paths"
    assert "/api/v1/optimize" in paths, "Expected /api/v1/optimize in OpenAPI paths"
    assert "/api/v1/runs" in paths, "Expected /api/v1/runs in OpenAPI paths"
    assert "/api/v1/assets/search" in paths, (
        "Expected /api/v1/assets/search in OpenAPI paths"
    )


@pytest.mark.asyncio
async def test_openapi_schema_has_info_block(client: AsyncClient) -> None:
    """GET /openapi.json has info.title and info.version fields."""
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    body = response.json()
    assert "info" in body
    assert "title" in body["info"]
    assert "version" in body["info"]
    assert len(body["info"]["title"]) > 0


# ---------------------------------------------------------------------------
# Scenario 24: CORS headers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cors_preflight_returns_allow_origin_header(
    client: AsyncClient,
) -> None:
    """OPTIONS /health returns Access-Control-Allow-Origin header."""
    response = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    # CORS preflight returns 200 or 204
    assert response.status_code in (200, 204)
    assert "access-control-allow-origin" in response.headers, (
        "Expected Access-Control-Allow-Origin header in CORS preflight response"
    )


# ---------------------------------------------------------------------------
# Scenario 25: Concurrent submits — unique run_ids
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_submits_return_unique_run_ids(
    client: AsyncClient,
) -> None:
    """N concurrent POST /api/v1/optimize requests all return unique run_ids."""
    concurrency = 10

    def _make_fresh_write_session() -> AsyncMock:
        session = AsyncMock(spec=AsyncSession)
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.close = AsyncMock()
        return session

    async def _dep():
        yield _make_fresh_write_session()

    app.dependency_overrides[get_db] = _dep

    try:
        with patch(
            "app.workers.tasks.run_optimization_task.apply_async"
        ) as mock_task:
            mock_task.return_value = MagicMock()

            async def _submit() -> str:
                resp = await client.post(
                    "/api/v1/optimize",
                    json={
                        "tickers": ["AAPL", "MSFT"],
                        "budget": 10_000.0,
                        "run_quantum": False,
                    },
                )
                assert resp.status_code == 202
                return resp.json()["run_id"]

            run_ids = await asyncio.gather(*[_submit() for _ in range(concurrency)])
    finally:
        app.dependency_overrides.pop(get_db, None)

    # All run_ids must be unique
    assert len(set(run_ids)) == concurrency, (
        f"Expected {concurrency} unique run_ids, got {len(set(run_ids))} unique "
        f"out of {concurrency}: {run_ids}"
    )

    # All run_ids must be valid UUIDs
    for run_id in run_ids:
        try:
            uuid.UUID(run_id)
        except ValueError:
            pytest.fail(f"run_id '{run_id}' is not a valid UUID")


# ---------------------------------------------------------------------------
# Bonus: Run list items have correct summary fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_list_items_have_summary_fields(client: AsyncClient) -> None:
    """GET /api/v1/runs items have run_id, status, tickers, budget, created_at."""
    run = _make_run(
        run_id=str(uuid.uuid4()),
        status="completed",
        tickers=["AAPL", "MSFT"],
        budget=50_000.0,
        classical_sharpe=1.15,
    )
    session = _make_list_session([run], total=1)
    app.dependency_overrides[get_db] = _override_db(session)

    try:
        response = await client.get("/api/v1/runs")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    item = body["items"][0]
    assert "run_id" in item
    assert "status" in item
    assert "tickers" in item
    assert "budget" in item
    assert "created_at" in item
    assert item["status"] == "completed"
    assert item["tickers"] == ["AAPL", "MSFT"]
    assert item["budget"] == pytest.approx(50_000.0)
    assert item["classical_sharpe"] == pytest.approx(1.15)


@pytest.mark.asyncio
async def test_run_detail_failed_run_has_error_message(client: AsyncClient) -> None:
    """GET /api/v1/runs/{run_id} for a failed run includes error_message."""
    run_id = str(uuid.uuid4())
    run = _make_run(
        run_id=run_id,
        status="failed",
        error_message="Data fetch failed: yfinance timeout",
    )

    session = _make_single_session(run)
    app.dependency_overrides[get_db] = _override_db(session)

    try:
        response = await client.get(f"/api/v1/runs/{run_id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_message"] == "Data fetch failed: yfinance timeout"


@pytest.mark.asyncio
async def test_optimize_submit_negative_budget_returns_422(
    client: AsyncClient,
) -> None:
    """POST /api/v1/optimize with negative budget returns 422."""
    response = await client.post(
        "/api/v1/optimize",
        json={"tickers": ["AAPL", "MSFT"], "budget": -1000.0},
    )

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body


@pytest.mark.asyncio
async def test_run_status_completed_run_has_completed_at(
    client: AsyncClient,
) -> None:
    """GET /api/v1/runs/{run_id}/status for completed run has non-null completed_at."""
    run_id = str(uuid.uuid4())
    run = _make_run(run_id=run_id, status="completed")

    session = _make_single_session(run)
    app.dependency_overrides[get_db] = _override_db(session)

    try:
        response = await client.get(f"/api/v1/runs/{run_id}/status")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["completed_at"] is not None


@pytest.mark.asyncio
async def test_run_list_empty_returns_zero_total(client: AsyncClient) -> None:
    """GET /api/v1/runs with no runs returns total=0 and empty items list."""
    session = _make_list_session([], total=0)
    app.dependency_overrides[get_db] = _override_db(session)

    try:
        response = await client.get("/api/v1/runs")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []
