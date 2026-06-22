"""Integration tests for GET /api/v1/runs endpoints.

Tests cover:
1. GET /api/v1/runs — empty list returns 200 with empty items
2. GET /api/v1/runs — returns paginated list with correct shape
3. GET /api/v1/runs — status filter returns only matching runs
4. GET /api/v1/runs — invalid status filter returns 422
5. GET /api/v1/runs — page/page_size pagination works
6. GET /api/v1/runs/{run_id} — returns full detail for existing run
7. GET /api/v1/runs/{run_id} — 404 for unknown run_id
8. GET /api/v1/runs/{run_id} — 404 error body has error_code field
9. GET /api/v1/runs/{run_id}/status — returns lightweight status
10. GET /api/v1/runs/{run_id}/status — 404 for unknown run_id
11. GET /api/v1/runs/{run_id}/status — completed run has completed_at
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.db.models import OptimizationRun
from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(
    run_id: str | None = None,
    status: str = "completed",
    tickers: list[str] | None = None,
    budget: float = 100_000.0,
    classical_sharpe: float | None = 1.25,
    quantum_sharpe: float | None = None,
    classical_result: dict | None = None,
    quantum_result: dict | None = None,
    comparison: dict | None = None,
    llm_explanation: str | None = None,
    error_message: str | None = None,
    completed_at: datetime | None = None,
) -> OptimizationRun:
    """Build a minimal OptimizationRun ORM object for testing."""
    run = OptimizationRun()
    run.run_id = run_id or str(uuid.uuid4())
    run.status = status
    run.tickers = tickers or ["AAPL", "MSFT", "GOOGL"]
    run.budget = budget
    run.request_params = {}
    run.classical_sharpe = classical_sharpe
    run.quantum_sharpe = quantum_sharpe
    run.classical_result = classical_result
    run.quantum_result = quantum_result
    run.comparison = comparison
    run.llm_explanation = llm_explanation
    run.error_message = error_message
    run.created_at = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    run.completed_at = completed_at or (
        datetime(2024, 1, 15, 10, 5, 0, tzinfo=UTC) if status == "completed" else None
    )
    return run


def _make_mock_session_for_runs(
    runs: list[OptimizationRun],
    total: int | None = None,
) -> AsyncMock:
    """Create a mock session that returns the given runs for list queries."""
    session = AsyncMock(spec=AsyncSession)

    # We need to handle two execute calls:
    # 1. count query → returns scalar_one() = total
    # 2. rows query → returns scalars().all() = runs

    count_result = MagicMock()
    count_result.scalar_one.return_value = total if total is not None else len(runs)

    rows_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = runs
    rows_result.scalars.return_value = scalars_mock

    # scalar_one_or_none for single-run queries
    single_result = MagicMock()
    single_result.scalar_one_or_none.return_value = runs[0] if runs else None

    # Return different results on successive calls
    session.execute = AsyncMock(
        side_effect=[count_result, rows_result]
    )

    return session


def _make_mock_session_for_single_run(run: OptimizationRun | None) -> AsyncMock:
    """Create a mock session that returns a single run for detail queries."""
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = run
    session.execute = AsyncMock(return_value=result)
    return session


# ---------------------------------------------------------------------------
# GET /api/v1/runs tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_runs_empty_returns_200() -> None:
    """Empty database returns 200 with empty items list."""
    session = _make_mock_session_for_runs(runs=[], total=0)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/runs")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["page"] == 1


@pytest.mark.asyncio
async def test_list_runs_returns_correct_shape() -> None:
    """List endpoint returns PaginatedRunsResponse with correct fields."""
    run = _make_run()
    session = _make_mock_session_for_runs(runs=[run], total=1)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/runs")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()

    # Top-level pagination fields
    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert "page_size" in body
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 20

    # Item fields
    item = body["items"][0]
    assert item["run_id"] == run.run_id
    assert item["status"] == "completed"
    assert set(item["tickers"]) == {"AAPL", "MSFT", "GOOGL"}
    assert item["budget"] == 100_000.0
    assert item["classical_sharpe"] == 1.25


@pytest.mark.asyncio
async def test_list_runs_status_filter_accepted() -> None:
    """Status filter query param is accepted and forwarded to DB query."""
    run = _make_run(status="pending", classical_sharpe=None, completed_at=None)
    session = _make_mock_session_for_runs(runs=[run], total=1)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/runs?status=pending")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_list_runs_invalid_status_returns_422() -> None:
    """Invalid status filter returns HTTP 422 with INVALID_STATUS_FILTER error code."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/runs?status=invalid_status")

    assert response.status_code == 422
    body = response.json()
    # The error detail should contain our custom error_code
    detail = body.get("detail", {})
    if isinstance(detail, dict):
        assert detail.get("error_code") == "INVALID_STATUS_FILTER"


@pytest.mark.asyncio
async def test_list_runs_pagination_params() -> None:
    """Custom page and page_size params are reflected in response."""
    runs = [_make_run() for _ in range(5)]
    session = _make_mock_session_for_runs(runs=runs, total=50)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/runs?page=2&page_size=5")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 2
    assert body["page_size"] == 5
    assert body["total"] == 50
    assert len(body["items"]) == 5


@pytest.mark.asyncio
async def test_list_runs_page_zero_returns_422() -> None:
    """page=0 is invalid (must be >= 1) and returns 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/runs?page=0")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_runs_page_size_over_100_returns_422() -> None:
    """page_size > 100 is invalid and returns 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/runs?page_size=101")

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/runs/{run_id} tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_run_detail_returns_200() -> None:
    """Existing run returns 200 with full detail shape."""
    run_id = str(uuid.uuid4())
    run = _make_run(
        run_id=run_id,
        classical_result={
            "weights": [{"ticker": "AAPL", "weight": 0.6, "allocation": 60000.0}],
            "metrics": {
                "expected_return": 0.12,
                "volatility": 0.18,
                "sharpe_ratio": 1.25,
                "max_drawdown": -0.15,
                "num_assets": 1,
            },
            "solver_status": "optimal",
            "solve_time_ms": 42.5,
        },
        llm_explanation="This portfolio is well-diversified.",
    )
    session = _make_mock_session_for_single_run(run)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/v1/runs/{run_id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["status"] == "completed"
    assert body["llm_explanation"] == "This portfolio is well-diversified."
    assert body["classical_result"] is not None
    assert body["classical_result"]["solver_status"] == "optimal"


@pytest.mark.asyncio
async def test_get_run_detail_not_found_returns_404() -> None:
    """Unknown run_id returns HTTP 404."""
    session = _make_mock_session_for_single_run(None)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/v1/runs/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_run_detail_404_has_error_code() -> None:
    """404 response body contains structured error_code field."""
    session = _make_mock_session_for_single_run(None)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/v1/runs/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404
    body = response.json()
    detail = body.get("detail", {})
    assert isinstance(detail, dict)
    assert detail.get("error_code") == "RUN_NOT_FOUND"
    assert "message" in detail


@pytest.mark.asyncio
async def test_get_run_detail_pending_run_has_null_results() -> None:
    """Pending run returns 200 with null result fields."""
    run_id = str(uuid.uuid4())
    run = _make_run(
        run_id=run_id,
        status="pending",
        classical_sharpe=None,
        classical_result=None,
        quantum_result=None,
        comparison=None,
        llm_explanation=None,
        completed_at=None,
    )
    session = _make_mock_session_for_single_run(run)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/v1/runs/{run_id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["classical_result"] is None
    assert body["quantum_result"] is None
    assert body["comparison"] is None
    assert body["llm_explanation"] is None
    assert body["completed_at"] is None


@pytest.mark.asyncio
async def test_get_run_detail_failed_run_has_error_message() -> None:
    """Failed run returns 200 with error_message populated."""
    run_id = str(uuid.uuid4())
    run = _make_run(
        run_id=run_id,
        status="failed",
        classical_sharpe=None,
        classical_result=None,
        error_message="Data fetch failed: yfinance timeout",
        completed_at=datetime(2024, 1, 15, 10, 2, 0, tzinfo=UTC),
    )
    session = _make_mock_session_for_single_run(run)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/v1/runs/{run_id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_message"] == "Data fetch failed: yfinance timeout"


# ---------------------------------------------------------------------------
# GET /api/v1/runs/{run_id}/status tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_run_status_returns_200() -> None:
    """Existing run status endpoint returns 200 with lightweight fields."""
    run_id = str(uuid.uuid4())
    run = _make_run(run_id=run_id, status="running", completed_at=None)
    session = _make_mock_session_for_single_run(run)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/v1/runs/{run_id}/status")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["status"] == "running"
    assert "created_at" in body
    assert body["completed_at"] is None


@pytest.mark.asyncio
async def test_get_run_status_not_found_returns_404() -> None:
    """Unknown run_id on status endpoint returns HTTP 404."""
    session = _make_mock_session_for_single_run(None)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/v1/runs/{uuid.uuid4()}/status")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404
    body = response.json()
    detail = body.get("detail", {})
    assert isinstance(detail, dict)
    assert detail.get("error_code") == "RUN_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_run_status_completed_has_completed_at() -> None:
    """Completed run status response includes completed_at timestamp."""
    run_id = str(uuid.uuid4())
    completed_time = datetime(2024, 3, 20, 14, 30, 0, tzinfo=UTC)
    run = _make_run(run_id=run_id, status="completed", completed_at=completed_time)
    session = _make_mock_session_for_single_run(run)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/v1/runs/{run_id}/status")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["completed_at"] is not None
    # Verify it's a parseable datetime string
    from datetime import datetime as dt
    parsed = dt.fromisoformat(body["completed_at"].replace("Z", "+00:00"))
    assert parsed.year == 2024
