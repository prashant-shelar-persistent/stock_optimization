"""Load tests for the Portfolio Optimizer API.

These tests verify that the application handles concurrent requests correctly
without race conditions, resource leaks, or degraded responses.

Load scenarios tested:
1.  Concurrent health checks — N simultaneous GET /health requests all succeed
2.  Concurrent asset searches — N simultaneous GET /api/v1/assets/search requests
3.  Concurrent optimization submits — N simultaneous POST /api/v1/optimize requests
4.  Concurrent run status polls — N simultaneous GET /api/v1/runs/{id}/status
5.  Concurrent run list queries — N simultaneous GET /api/v1/runs requests
6.  Mixed concurrent load — health + search + optimize simultaneously
7.  Unique run_ids under concurrent submits — no ID collisions
8.  Concurrent 404 requests — all return structured error bodies
9.  Concurrent validation errors — all return 422 with detail fields
10. Sequential burst — rapid sequential requests without delay

Design notes:
    - All tests use asyncio.gather() to fire requests concurrently.
    - No real DB/Redis/Celery connections are used — all external dependencies
      are mocked to isolate the application's concurrency handling.
    - Tests verify BOTH that all requests succeed AND that response bodies
      have the correct shape (not just status codes).
    - Concurrency level is kept at 10-20 to be fast and deterministic in CI.
"""

import asyncio
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
# Concurrency level
# ---------------------------------------------------------------------------

# Number of concurrent requests per load test scenario.
# Kept at 10 for fast, deterministic CI execution.
CONCURRENCY = 10


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Async HTTP client wired to the FastAPI app via ASGI transport."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


def _make_write_session() -> AsyncMock:
    """Mock DB session for write operations."""
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
    """Mock DB session for list queries."""
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
) -> OptimizationRun:
    """Build a minimal OptimizationRun ORM object for testing."""
    run = OptimizationRun()
    run.run_id = run_id or str(uuid.uuid4())
    run.status = status
    run.tickers = tickers or ["AAPL", "MSFT"]
    run.budget = budget
    run.request_params = {"tickers": run.tickers, "budget": budget, "run_quantum": False}
    run.classical_sharpe = 1.25
    run.quantum_sharpe = None
    run.classical_result = None
    run.quantum_result = None
    run.comparison = None
    run.llm_explanation = None
    run.error_message = None
    run.created_at = datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)
    run.completed_at = (
        datetime(2024, 6, 1, 10, 5, 0, tzinfo=UTC)
        if status in ("completed", "failed")
        else None
    )
    return run


def _override_db_factory():
    """Return a new mock DB session for each request (thread-safe)."""

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

    return _dep


def _override_db_list_factory(runs: list[OptimizationRun], total: int) -> Any:
    """Return a DB override that serves list queries."""

    async def _dep():
        session = AsyncMock(spec=AsyncSession)

        count_result = MagicMock()
        count_result.scalar_one.return_value = total

        rows_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = runs
        rows_result.scalars.return_value = scalars_mock

        session.execute = AsyncMock(side_effect=[count_result, rows_result])
        yield session

    return _dep


def _override_db_single_factory(run: OptimizationRun | None) -> Any:
    """Return a DB override that serves single-row lookup queries."""

    async def _dep():
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.scalar_one_or_none.return_value = run
        session.execute = AsyncMock(return_value=result)
        yield session

    return _dep


# ---------------------------------------------------------------------------
# Load test 1: Concurrent health checks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_health_checks_all_succeed(client: AsyncClient) -> None:
    """N concurrent GET /health requests all return 200."""
    with (
        patch("app.api.health._check_database", return_value="up"),
        patch("app.api.health._check_redis", return_value="up"),
        patch("app.api.health._check_celery", return_value="up"),
    ):
        responses = await asyncio.gather(
            *[client.get("/health") for _ in range(CONCURRENCY)]
        )

    assert len(responses) == CONCURRENCY
    for response in responses:
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_concurrent_health_checks_all_return_healthy(
    client: AsyncClient,
) -> None:
    """N concurrent GET /health requests all return status='healthy'."""
    with (
        patch("app.api.health._check_database", return_value="up"),
        patch("app.api.health._check_redis", return_value="up"),
        patch("app.api.health._check_celery", return_value="up"),
    ):
        responses = await asyncio.gather(
            *[client.get("/health") for _ in range(CONCURRENCY)]
        )

    for response in responses:
        body = response.json()
        assert body["status"] == "healthy"
        assert "version" in body
        assert "services" in body


@pytest.mark.asyncio
async def test_concurrent_health_checks_degraded_all_return_200(
    client: AsyncClient,
) -> None:
    """N concurrent GET /health requests with one service down all return 200."""
    with (
        patch("app.api.health._check_database", return_value="up"),
        patch("app.api.health._check_redis", return_value="down"),
        patch("app.api.health._check_celery", return_value="up"),
    ):
        responses = await asyncio.gather(
            *[client.get("/health") for _ in range(CONCURRENCY)]
        )

    for response in responses:
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"


# ---------------------------------------------------------------------------
# Load test 2: Concurrent asset searches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_asset_searches_all_succeed(client: AsyncClient) -> None:
    """N concurrent GET /api/v1/assets/search?q=AAPL all return 200."""
    responses = await asyncio.gather(
        *[
            client.get("/api/v1/assets/search", params={"q": "AAPL"})
            for _ in range(CONCURRENCY)
        ]
    )

    assert len(responses) == CONCURRENCY
    for response in responses:
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_concurrent_asset_searches_all_return_results(
    client: AsyncClient,
) -> None:
    """N concurrent asset searches all return non-empty result lists."""
    responses = await asyncio.gather(
        *[
            client.get("/api/v1/assets/search", params={"q": "AAPL"})
            for _ in range(CONCURRENCY)
        ]
    )

    for response in responses:
        body = response.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        assert body[0]["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_concurrent_asset_searches_different_queries(
    client: AsyncClient,
) -> None:
    """N concurrent asset searches with different queries all return 200."""
    queries = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "JPM", "JNJ", "XOM", "V", "MA"]
    responses = await asyncio.gather(
        *[
            client.get("/api/v1/assets/search", params={"q": q})
            for q in queries[:CONCURRENCY]
        ]
    )

    assert len(responses) == CONCURRENCY
    for response in responses:
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) >= 1


@pytest.mark.asyncio
async def test_concurrent_asset_searches_results_are_consistent(
    client: AsyncClient,
) -> None:
    """N concurrent searches for the same ticker return identical results."""
    responses = await asyncio.gather(
        *[
            client.get("/api/v1/assets/search", params={"q": "MSFT"})
            for _ in range(CONCURRENCY)
        ]
    )

    # All responses should be identical (deterministic in-memory lookup)
    first_body = responses[0].json()
    for response in responses[1:]:
        assert response.json() == first_body


# ---------------------------------------------------------------------------
# Load test 3: Concurrent optimization submits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_optimize_submits_all_return_202(
    client: AsyncClient,
) -> None:
    """N concurrent POST /api/v1/optimize requests all return 202."""
    app.dependency_overrides[get_db] = _override_db_factory()

    try:
        with patch(
            "app.workers.tasks.run_optimization_task.apply_async"
        ) as mock_task:
            mock_task.return_value = MagicMock()
            responses = await asyncio.gather(
                *[
                    client.post(
                        "/api/v1/optimize",
                        json={
                            "tickers": ["AAPL", "MSFT"],
                            "budget": 50_000.0,
                            "run_quantum": False,
                        },
                    )
                    for _ in range(CONCURRENCY)
                ]
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert len(responses) == CONCURRENCY
    for response in responses:
        assert response.status_code == 202


@pytest.mark.asyncio
async def test_concurrent_optimize_submits_all_return_run_id(
    client: AsyncClient,
) -> None:
    """N concurrent POST /api/v1/optimize requests all return a run_id."""
    app.dependency_overrides[get_db] = _override_db_factory()

    try:
        with patch(
            "app.workers.tasks.run_optimization_task.apply_async"
        ) as mock_task:
            mock_task.return_value = MagicMock()
            responses = await asyncio.gather(
                *[
                    client.post(
                        "/api/v1/optimize",
                        json={
                            "tickers": ["AAPL", "MSFT"],
                            "budget": 50_000.0,
                            "run_quantum": False,
                        },
                    )
                    for _ in range(CONCURRENCY)
                ]
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    for response in responses:
        body = response.json()
        assert "run_id" in body
        assert len(body["run_id"]) > 0


@pytest.mark.asyncio
async def test_concurrent_optimize_submits_produce_unique_run_ids(
    client: AsyncClient,
) -> None:
    """N concurrent POST /api/v1/optimize requests produce unique run_ids.

    This is the critical concurrency test: verifies that UUID generation
    under concurrent load produces no collisions.
    """
    app.dependency_overrides[get_db] = _override_db_factory()

    try:
        with patch(
            "app.workers.tasks.run_optimization_task.apply_async"
        ) as mock_task:
            mock_task.return_value = MagicMock()
            responses = await asyncio.gather(
                *[
                    client.post(
                        "/api/v1/optimize",
                        json={
                            "tickers": ["AAPL", "MSFT"],
                            "budget": 50_000.0,
                            "run_quantum": False,
                        },
                    )
                    for _ in range(CONCURRENCY)
                ]
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    run_ids = [r.json()["run_id"] for r in responses]
    # All run_ids must be unique — no collisions under concurrent load
    assert len(set(run_ids)) == CONCURRENCY, (
        f"Expected {CONCURRENCY} unique run_ids, got {len(set(run_ids))}. "
        f"Duplicates: {[rid for rid in run_ids if run_ids.count(rid) > 1]}"
    )


@pytest.mark.asyncio
async def test_concurrent_optimize_submits_run_ids_are_valid_uuids(
    client: AsyncClient,
) -> None:
    """N concurrent POST /api/v1/optimize requests all produce valid UUIDs."""
    app.dependency_overrides[get_db] = _override_db_factory()

    try:
        with patch(
            "app.workers.tasks.run_optimization_task.apply_async"
        ) as mock_task:
            mock_task.return_value = MagicMock()
            responses = await asyncio.gather(
                *[
                    client.post(
                        "/api/v1/optimize",
                        json={
                            "tickers": ["AAPL", "MSFT"],
                            "budget": 50_000.0,
                            "run_quantum": False,
                        },
                    )
                    for _ in range(CONCURRENCY)
                ]
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    for response in responses:
        run_id = response.json()["run_id"]
        # Must be parseable as UUID
        parsed = uuid.UUID(run_id)
        assert str(parsed) == run_id


# ---------------------------------------------------------------------------
# Load test 4: Concurrent run status polls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_run_status_polls_all_return_200(
    client: AsyncClient,
) -> None:
    """N concurrent GET /api/v1/runs/{id}/status requests all return 200."""
    run_id = str(uuid.uuid4())
    run = _make_run(run_id=run_id, status="running")
    app.dependency_overrides[get_db] = _override_db_single_factory(run)

    try:
        responses = await asyncio.gather(
            *[
                client.get(f"/api/v1/runs/{run_id}/status")
                for _ in range(CONCURRENCY)
            ]
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert len(responses) == CONCURRENCY
    for response in responses:
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_concurrent_run_status_polls_all_return_correct_status(
    client: AsyncClient,
) -> None:
    """N concurrent status polls all return the same run status."""
    run_id = str(uuid.uuid4())
    run = _make_run(run_id=run_id, status="running")
    app.dependency_overrides[get_db] = _override_db_single_factory(run)

    try:
        responses = await asyncio.gather(
            *[
                client.get(f"/api/v1/runs/{run_id}/status")
                for _ in range(CONCURRENCY)
            ]
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    for response in responses:
        body = response.json()
        assert body["run_id"] == run_id
        assert body["status"] == "running"
        assert "created_at" in body


@pytest.mark.asyncio
async def test_concurrent_run_status_polls_404_all_return_structured_error(
    client: AsyncClient,
) -> None:
    """N concurrent status polls for unknown run_id all return 404 with error_code."""
    app.dependency_overrides[get_db] = _override_db_single_factory(None)

    try:
        unknown_id = str(uuid.uuid4())
        responses = await asyncio.gather(
            *[
                client.get(f"/api/v1/runs/{unknown_id}/status")
                for _ in range(CONCURRENCY)
            ]
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    for response in responses:
        assert response.status_code == 404
        body = response.json()
        assert "detail" in body
        assert body["detail"]["error_code"] == "RUN_NOT_FOUND"


# ---------------------------------------------------------------------------
# Load test 5: Concurrent run list queries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_run_list_queries_all_return_200(
    client: AsyncClient,
) -> None:
    """N concurrent GET /api/v1/runs requests all return 200."""
    runs = [_make_run(run_id=str(uuid.uuid4())) for _ in range(3)]
    app.dependency_overrides[get_db] = _override_db_list_factory(runs, total=3)

    try:
        responses = await asyncio.gather(
            *[client.get("/api/v1/runs") for _ in range(CONCURRENCY)]
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert len(responses) == CONCURRENCY
    for response in responses:
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_concurrent_run_list_queries_all_return_correct_shape(
    client: AsyncClient,
) -> None:
    """N concurrent GET /api/v1/runs requests all return paginated shape."""
    runs = [_make_run(run_id=str(uuid.uuid4())) for _ in range(2)]
    app.dependency_overrides[get_db] = _override_db_list_factory(runs, total=2)

    try:
        responses = await asyncio.gather(
            *[client.get("/api/v1/runs") for _ in range(CONCURRENCY)]
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    for response in responses:
        body = response.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert "page_size" in body
        assert body["total"] == 2


# ---------------------------------------------------------------------------
# Load test 6: Mixed concurrent load
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mixed_concurrent_load_all_succeed(client: AsyncClient) -> None:
    """Mixed concurrent load: health + search + optimize all succeed simultaneously."""
    run = _make_run(run_id=str(uuid.uuid4()), status="pending")
    app.dependency_overrides[get_db] = _override_db_factory()

    try:
        with (
            patch("app.api.health._check_database", return_value="up"),
            patch("app.api.health._check_redis", return_value="up"),
            patch("app.api.health._check_celery", return_value="up"),
            patch(
                "app.workers.tasks.run_optimization_task.apply_async"
            ) as mock_task,
        ):
            mock_task.return_value = MagicMock()

            # Fire health, search, and optimize requests concurrently
            health_coros = [client.get("/health") for _ in range(5)]
            search_coros = [
                client.get("/api/v1/assets/search", params={"q": "AAPL"})
                for _ in range(5)
            ]
            optimize_coros = [
                client.post(
                    "/api/v1/optimize",
                    json={
                        "tickers": ["AAPL", "MSFT"],
                        "budget": 50_000.0,
                        "run_quantum": False,
                    },
                )
                for _ in range(5)
            ]

            all_responses = await asyncio.gather(
                *health_coros, *search_coros, *optimize_coros
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    # All 15 requests should succeed
    assert len(all_responses) == 15

    health_responses = all_responses[:5]
    search_responses = all_responses[5:10]
    optimize_responses = all_responses[10:15]

    for r in health_responses:
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    for r in search_responses:
        assert r.status_code == 200
        assert len(r.json()) >= 1

    for r in optimize_responses:
        assert r.status_code == 202
        assert "run_id" in r.json()


# ---------------------------------------------------------------------------
# Load test 7: Concurrent validation errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_validation_errors_all_return_422(
    client: AsyncClient,
) -> None:
    """N concurrent invalid POST /api/v1/optimize requests all return 422."""
    responses = await asyncio.gather(
        *[
            client.post(
                "/api/v1/optimize",
                json={"tickers": ["AAPL"], "budget": 50_000.0},  # Only 1 ticker
            )
            for _ in range(CONCURRENCY)
        ]
    )

    assert len(responses) == CONCURRENCY
    for response in responses:
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_concurrent_validation_errors_all_have_detail_field(
    client: AsyncClient,
) -> None:
    """N concurrent invalid requests all return 422 with 'detail' field."""
    responses = await asyncio.gather(
        *[
            client.post(
                "/api/v1/optimize",
                json={"tickers": ["AAPL"], "budget": -100.0},  # Negative budget
            )
            for _ in range(CONCURRENCY)
        ]
    )

    for response in responses:
        assert response.status_code == 422
        body = response.json()
        assert "detail" in body
        assert isinstance(body["detail"], list)
        assert len(body["detail"]) > 0


# ---------------------------------------------------------------------------
# Load test 8: Sequential burst
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sequential_burst_health_checks(client: AsyncClient) -> None:
    """Rapid sequential GET /health requests all succeed without degradation."""
    with (
        patch("app.api.health._check_database", return_value="up"),
        patch("app.api.health._check_redis", return_value="up"),
        patch("app.api.health._check_celery", return_value="up"),
    ):
        responses = []
        for _ in range(20):
            response = await client.get("/health")
            responses.append(response)

    assert len(responses) == 20
    for response in responses:
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_sequential_burst_asset_searches(client: AsyncClient) -> None:
    """Rapid sequential asset searches all succeed without degradation."""
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] * 4  # 20 searches

    responses = []
    for ticker in tickers:
        response = await client.get(
            "/api/v1/assets/search", params={"q": ticker}
        )
        responses.append(response)

    assert len(responses) == 20
    for response in responses:
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) >= 1


# ---------------------------------------------------------------------------
# Load test 9: Concurrent run detail queries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_run_detail_queries_all_return_200(
    client: AsyncClient,
) -> None:
    """N concurrent GET /api/v1/runs/{id} requests all return 200."""
    run_id = str(uuid.uuid4())
    run = _make_run(run_id=run_id, status="completed")
    app.dependency_overrides[get_db] = _override_db_single_factory(run)

    try:
        responses = await asyncio.gather(
            *[client.get(f"/api/v1/runs/{run_id}") for _ in range(CONCURRENCY)]
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert len(responses) == CONCURRENCY
    for response in responses:
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_concurrent_run_detail_queries_all_return_correct_run_id(
    client: AsyncClient,
) -> None:
    """N concurrent GET /api/v1/runs/{id} requests all return the correct run_id."""
    run_id = str(uuid.uuid4())
    run = _make_run(run_id=run_id, status="completed")
    app.dependency_overrides[get_db] = _override_db_single_factory(run)

    try:
        responses = await asyncio.gather(
            *[client.get(f"/api/v1/runs/{run_id}") for _ in range(CONCURRENCY)]
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    for response in responses:
        body = response.json()
        assert body["run_id"] == run_id
        assert body["status"] == "completed"


# ---------------------------------------------------------------------------
# Load test 10: Concurrent 404 requests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_404_requests_all_return_structured_error(
    client: AsyncClient,
) -> None:
    """N concurrent requests for unknown run_id all return 404 with error_code."""
    app.dependency_overrides[get_db] = _override_db_single_factory(None)

    try:
        unknown_id = str(uuid.uuid4())
        responses = await asyncio.gather(
            *[
                client.get(f"/api/v1/runs/{unknown_id}")
                for _ in range(CONCURRENCY)
            ]
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    for response in responses:
        assert response.status_code == 404
        body = response.json()
        assert "detail" in body
        assert body["detail"]["error_code"] == "RUN_NOT_FOUND"
        assert "message" in body["detail"]


@pytest.mark.asyncio
async def test_concurrent_404_requests_error_messages_are_consistent(
    client: AsyncClient,
) -> None:
    """N concurrent 404 requests all return the same error message structure."""
    app.dependency_overrides[get_db] = _override_db_single_factory(None)

    try:
        unknown_id = str(uuid.uuid4())
        responses = await asyncio.gather(
            *[
                client.get(f"/api/v1/runs/{unknown_id}")
                for _ in range(CONCURRENCY)
            ]
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    # All error responses should have the same structure
    first_body = responses[0].json()
    for response in responses[1:]:
        body = response.json()
        assert body["detail"]["error_code"] == first_body["detail"]["error_code"]
        assert "message" in body["detail"]


# ---------------------------------------------------------------------------
# Load test 11: Concurrent OpenAPI schema requests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_openapi_schema_requests_all_return_200(
    client: AsyncClient,
) -> None:
    """N concurrent GET /openapi.json requests all return 200."""
    responses = await asyncio.gather(
        *[client.get("/openapi.json") for _ in range(CONCURRENCY)]
    )

    assert len(responses) == CONCURRENCY
    for response in responses:
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_concurrent_openapi_schema_requests_all_return_same_schema(
    client: AsyncClient,
) -> None:
    """N concurrent GET /openapi.json requests all return identical schemas."""
    responses = await asyncio.gather(
        *[client.get("/openapi.json") for _ in range(CONCURRENCY)]
    )

    # The OpenAPI schema is deterministic — all responses should be identical
    first_body = responses[0].json()
    for response in responses[1:]:
        body = response.json()
        assert body["info"]["title"] == first_body["info"]["title"]
        assert set(body["paths"].keys()) == set(first_body["paths"].keys())


# ---------------------------------------------------------------------------
# Load test 12: Concurrent Prometheus metrics requests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_metrics_requests_all_succeed(client: AsyncClient) -> None:
    """N concurrent GET /metrics requests all return 200 or 404."""
    responses = await asyncio.gather(
        *[client.get("/metrics") for _ in range(CONCURRENCY)]
    )

    assert len(responses) == CONCURRENCY
    for response in responses:
        # /metrics returns 200 if prometheus-fastapi-instrumentator is installed
        # or 404 if not installed
        assert response.status_code in (200, 404)


# ---------------------------------------------------------------------------
# Load test 13: Concurrent mixed valid/invalid requests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_mixed_valid_invalid_optimize_requests(
    client: AsyncClient,
) -> None:
    """Concurrent mix of valid and invalid optimize requests handled correctly."""
    app.dependency_overrides[get_db] = _override_db_factory()

    try:
        with patch(
            "app.workers.tasks.run_optimization_task.apply_async"
        ) as mock_task:
            mock_task.return_value = MagicMock()

            valid_coros = [
                client.post(
                    "/api/v1/optimize",
                    json={
                        "tickers": ["AAPL", "MSFT"],
                        "budget": 50_000.0,
                        "run_quantum": False,
                    },
                )
                for _ in range(5)
            ]
            invalid_coros = [
                client.post(
                    "/api/v1/optimize",
                    json={"tickers": ["AAPL"], "budget": 50_000.0},  # 1 ticker
                )
                for _ in range(5)
            ]

            all_responses = await asyncio.gather(*valid_coros, *invalid_coros)
    finally:
        app.dependency_overrides.pop(get_db, None)

    valid_responses = all_responses[:5]
    invalid_responses = all_responses[5:]

    for r in valid_responses:
        assert r.status_code == 202
        assert "run_id" in r.json()

    for r in invalid_responses:
        assert r.status_code == 422
        assert "detail" in r.json()
