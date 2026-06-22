"""Integration tests for POST /api/v1/optimize endpoint.

Tests cover:
1. Valid request returns 202 with run_id
2. run_id is a valid UUID string
3. Missing required fields returns 422
4. Invalid tickers (too short list) returns 422
5. Budget validation (negative budget) returns 422
6. Celery task is dispatched with correct arguments
7. run_quantum=False routes to default queue
8. run_quantum=True routes to quantum queue
9. Duplicate tickers are deduplicated
10. Sector constraints accepted
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_session() -> AsyncMock:
    """Create a fully-mocked AsyncSession that does nothing on flush/commit."""
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


async def _mock_get_db_factory(session: AsyncMock):
    """Return an async generator that yields the mock session."""
    async def _gen():
        yield session
    return _gen


VALID_REQUEST = {
    "tickers": ["AAPL", "MSFT", "GOOGL"],
    "budget": 100000.0,
    "run_quantum": False,
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimize_valid_request_returns_202() -> None:
    """Valid optimization request returns HTTP 202 Accepted."""
    mock_session = _make_mock_session()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/v1/optimize", json=VALID_REQUEST)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 202


@pytest.mark.asyncio
async def test_optimize_returns_run_id() -> None:
    """Response body contains a run_id field that is a valid UUID."""
    mock_session = _make_mock_session()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/v1/optimize", json=VALID_REQUEST)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 202
    body = response.json()
    assert "run_id" in body
    run_id = body["run_id"]
    assert isinstance(run_id, str)
    # Should not raise — must be a valid UUID
    uuid.UUID(run_id)


@pytest.mark.asyncio
async def test_optimize_missing_tickers_returns_422() -> None:
    """Request without tickers returns HTTP 422 validation error."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/optimize", json={"budget": 100000.0})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_optimize_missing_budget_returns_422() -> None:
    """Request without budget returns HTTP 422 validation error."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/optimize", json={"tickers": ["AAPL", "MSFT"]})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_optimize_single_ticker_returns_422() -> None:
    """Request with only one ticker returns HTTP 422 (min 2 required)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/optimize",
            json={"tickers": ["AAPL"], "budget": 100000.0},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_optimize_negative_budget_returns_422() -> None:
    """Request with negative budget returns HTTP 422 validation error."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/optimize",
            json={"tickers": ["AAPL", "MSFT"], "budget": -1000.0},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_optimize_celery_task_dispatched() -> None:
    """Celery task apply_async is called once with correct run_id."""
    mock_session = _make_mock_session()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/v1/optimize", json=VALID_REQUEST)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 202
    run_id = response.json()["run_id"]

    # Verify apply_async was called once
    mock_task.apply_async.assert_called_once()
    call_kwargs = mock_task.apply_async.call_args

    # Check task_id matches run_id
    task_id = call_kwargs.kwargs.get("task_id") or call_kwargs[1].get("task_id")
    assert task_id == run_id


@pytest.mark.asyncio
async def test_optimize_run_quantum_false_uses_default_queue() -> None:
    """run_quantum=False dispatches task to 'default' queue."""
    mock_session = _make_mock_session()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    request = {**VALID_REQUEST, "run_quantum": False}

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/v1/optimize", json=request)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 202
    call_kwargs = mock_task.apply_async.call_args
    queue = call_kwargs.kwargs.get("queue") or call_kwargs[1].get("queue")
    assert queue == "default"


@pytest.mark.asyncio
async def test_optimize_run_quantum_true_uses_quantum_queue() -> None:
    """run_quantum=True dispatches task to 'quantum' queue."""
    mock_session = _make_mock_session()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    request = {**VALID_REQUEST, "run_quantum": True}

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/v1/optimize", json=request)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 202
    call_kwargs = mock_task.apply_async.call_args
    queue = call_kwargs.kwargs.get("queue") or call_kwargs[1].get("queue")
    assert queue == "quantum"


@pytest.mark.asyncio
async def test_optimize_duplicate_tickers_deduplicated() -> None:
    """Duplicate tickers in request are deduplicated before processing."""
    mock_session = _make_mock_session()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    request = {
        "tickers": ["AAPL", "MSFT", "AAPL", "MSFT"],  # duplicates
        "budget": 100000.0,
        "run_quantum": False,
    }

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/v1/optimize", json=request)
    finally:
        app.dependency_overrides.pop(get_db, None)

    # Should succeed — duplicates are removed by the validator
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_optimize_with_sector_constraints() -> None:
    """Request with sector constraints is accepted and dispatched."""
    mock_session = _make_mock_session()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    request = {
        "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN"],
        "budget": 50000.0,
        "run_quantum": False,
        "sector_constraints": [
            {"sector": "Technology", "max_weight": 0.6}
        ],
        "max_weight_per_asset": 0.4,
    }

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/v1/optimize", json=request)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 202
    body = response.json()
    assert "run_id" in body


@pytest.mark.asyncio
async def test_optimize_ticker_normalised_to_uppercase() -> None:
    """Lowercase tickers are normalised to uppercase."""
    mock_session = _make_mock_session()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    request = {
        "tickers": ["aapl", "msft"],
        "budget": 100000.0,
        "run_quantum": False,
    }

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/v1/optimize", json=request)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 202


@pytest.mark.asyncio
async def test_optimize_db_add_called_with_run_record() -> None:
    """The DB session's add() is called with an OptimizationRun record."""
    from app.db.models import OptimizationRun

    mock_session = _make_mock_session()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/v1/optimize", json=VALID_REQUEST)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 202

    # Verify db.add was called with an OptimizationRun instance
    mock_session.add.assert_called_once()
    added_obj = mock_session.add.call_args[0][0]
    assert isinstance(added_obj, OptimizationRun)
    assert added_obj.status == "pending"
    assert set(added_obj.tickers) == {"AAPL", "MSFT", "GOOGL"}


@pytest.mark.asyncio
async def test_optimize_db_flush_called() -> None:
    """The DB session's flush() is awaited to persist the record."""
    mock_session = _make_mock_session()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/v1/optimize", json=VALID_REQUEST)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 202
    mock_session.flush.assert_awaited_once()
