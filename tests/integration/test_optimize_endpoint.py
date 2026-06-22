"""Integration tests for POST /api/v1/optimize endpoint.

Tests cover:
1.  Valid request returns HTTP 202 Accepted
2.  Response body contains run_id field
3.  run_id is a valid UUID string
4.  Missing tickers field returns 422
5.  Missing budget field returns 422
6.  Single ticker (< 2) returns 422
7.  Negative budget returns 422
8.  Zero budget returns 422
9.  Celery task is dispatched exactly once
10. task_id in apply_async matches the returned run_id
11. run_quantum=False routes task to 'default' queue
12. run_quantum=True routes task to 'quantum' queue
13. Duplicate tickers are deduplicated (request succeeds)
14. Lowercase tickers are normalised to uppercase
15. Request with sector constraints is accepted
16. Request with all optional fields is accepted
17. DB session add() is called with an OptimizationRun record
18. DB session flush() is awaited
19. OptimizationRun record has status='pending'
20. num_assets_to_select > len(tickers) returns 422
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from app.core.dependencies import get_db
from app.db.models import OptimizationRun
from app.main import app

from tests.integration.conftest import (
    FULL_REQUEST,
    MINIMAL_REQUEST,
    QUANTUM_REQUEST,
    STANDARD_REQUEST,
    make_mock_session,
    override_db_with,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _install_db_override(session):
    """Install a mock DB session override on the app."""
    app.dependency_overrides[get_db] = override_db_with(session)


def _remove_db_override():
    """Remove the mock DB session override from the app."""
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Happy path — 202 + run_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimize_valid_request_returns_202(client: AsyncClient) -> None:
    """Valid optimization request returns HTTP 202 Accepted."""
    session = make_mock_session()
    _install_db_override(session)

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            response = await client.post("/api/v1/optimize", json=STANDARD_REQUEST)
    finally:
        _remove_db_override()

    assert response.status_code == 202


@pytest.mark.asyncio
async def test_optimize_response_contains_run_id(client: AsyncClient) -> None:
    """Response body contains a 'run_id' field."""
    session = make_mock_session()
    _install_db_override(session)

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            response = await client.post("/api/v1/optimize", json=STANDARD_REQUEST)
    finally:
        _remove_db_override()

    assert response.status_code == 202
    body = response.json()
    assert "run_id" in body, f"Missing 'run_id' in response: {body}"


@pytest.mark.asyncio
async def test_optimize_run_id_is_valid_uuid(client: AsyncClient) -> None:
    """run_id in response is a valid UUID string."""
    session = make_mock_session()
    _install_db_override(session)

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            response = await client.post("/api/v1/optimize", json=STANDARD_REQUEST)
    finally:
        _remove_db_override()

    assert response.status_code == 202
    run_id = response.json()["run_id"]
    assert isinstance(run_id, str)
    # Must not raise — must be a valid UUID
    parsed = uuid.UUID(run_id)
    assert str(parsed) == run_id


# ---------------------------------------------------------------------------
# Validation errors — 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimize_missing_tickers_returns_422(client: AsyncClient) -> None:
    """Request without tickers returns HTTP 422 validation error."""
    response = await client.post("/api/v1/optimize", json={"budget": 100_000.0})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_optimize_missing_budget_returns_422(client: AsyncClient) -> None:
    """Request without budget returns HTTP 422 validation error."""
    response = await client.post(
        "/api/v1/optimize",
        json={"tickers": ["AAPL", "MSFT"]},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_optimize_single_ticker_returns_422(client: AsyncClient) -> None:
    """Request with only one ticker returns HTTP 422 (min 2 required)."""
    response = await client.post(
        "/api/v1/optimize",
        json={"tickers": ["AAPL"], "budget": 100_000.0},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_optimize_negative_budget_returns_422(client: AsyncClient) -> None:
    """Request with negative budget returns HTTP 422 validation error."""
    response = await client.post(
        "/api/v1/optimize",
        json={"tickers": ["AAPL", "MSFT"], "budget": -1_000.0},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_optimize_zero_budget_returns_422(client: AsyncClient) -> None:
    """Request with zero budget returns HTTP 422 (must be > 0)."""
    response = await client.post(
        "/api/v1/optimize",
        json={"tickers": ["AAPL", "MSFT"], "budget": 0.0},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_optimize_num_assets_exceeds_tickers_returns_422(
    client: AsyncClient,
) -> None:
    """num_assets_to_select > len(tickers) returns HTTP 422."""
    response = await client.post(
        "/api/v1/optimize",
        json={
            "tickers": ["AAPL", "MSFT"],
            "budget": 100_000.0,
            "num_assets_to_select": 5,  # > 2 tickers
        },
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Celery task dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimize_celery_task_dispatched_once(client: AsyncClient) -> None:
    """Celery task apply_async is called exactly once per request."""
    session = make_mock_session()
    _install_db_override(session)

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            response = await client.post("/api/v1/optimize", json=STANDARD_REQUEST)
    finally:
        _remove_db_override()

    assert response.status_code == 202
    mock_task.apply_async.assert_called_once()


@pytest.mark.asyncio
async def test_optimize_task_id_matches_run_id(client: AsyncClient) -> None:
    """task_id passed to apply_async matches the run_id returned in the response."""
    session = make_mock_session()
    _install_db_override(session)

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            response = await client.post("/api/v1/optimize", json=STANDARD_REQUEST)
    finally:
        _remove_db_override()

    assert response.status_code == 202
    run_id = response.json()["run_id"]

    call_kwargs = mock_task.apply_async.call_args
    # task_id may be in positional or keyword args
    task_id = (
        call_kwargs.kwargs.get("task_id")
        or (call_kwargs[1].get("task_id") if call_kwargs[1] else None)
    )
    assert task_id == run_id, (
        f"task_id={task_id!r} does not match run_id={run_id!r}"
    )


@pytest.mark.asyncio
async def test_optimize_run_quantum_false_uses_default_queue(
    client: AsyncClient,
) -> None:
    """run_quantum=False dispatches task to 'default' queue."""
    session = make_mock_session()
    _install_db_override(session)

    request = {**STANDARD_REQUEST, "run_quantum": False}

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            response = await client.post("/api/v1/optimize", json=request)
    finally:
        _remove_db_override()

    assert response.status_code == 202
    call_kwargs = mock_task.apply_async.call_args
    queue = (
        call_kwargs.kwargs.get("queue")
        or (call_kwargs[1].get("queue") if call_kwargs[1] else None)
    )
    assert queue == "default", f"Expected queue='default', got {queue!r}"


@pytest.mark.asyncio
async def test_optimize_run_quantum_true_uses_quantum_queue(
    client: AsyncClient,
) -> None:
    """run_quantum=True dispatches task to 'quantum' queue."""
    session = make_mock_session()
    _install_db_override(session)

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            response = await client.post("/api/v1/optimize", json=QUANTUM_REQUEST)
    finally:
        _remove_db_override()

    assert response.status_code == 202
    call_kwargs = mock_task.apply_async.call_args
    queue = (
        call_kwargs.kwargs.get("queue")
        or (call_kwargs[1].get("queue") if call_kwargs[1] else None)
    )
    assert queue == "quantum", f"Expected queue='quantum', got {queue!r}"


# ---------------------------------------------------------------------------
# Ticker normalisation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimize_duplicate_tickers_deduplicated(client: AsyncClient) -> None:
    """Duplicate tickers are deduplicated — request succeeds with 202."""
    session = make_mock_session()
    _install_db_override(session)

    request = {
        "tickers": ["AAPL", "MSFT", "AAPL", "MSFT"],  # duplicates
        "budget": 100_000.0,
        "run_quantum": False,
    }

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            response = await client.post("/api/v1/optimize", json=request)
    finally:
        _remove_db_override()

    assert response.status_code == 202


@pytest.mark.asyncio
async def test_optimize_lowercase_tickers_normalised(client: AsyncClient) -> None:
    """Lowercase tickers are normalised to uppercase — request succeeds."""
    session = make_mock_session()
    _install_db_override(session)

    request = {
        "tickers": ["aapl", "msft"],
        "budget": 100_000.0,
        "run_quantum": False,
    }

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            response = await client.post("/api/v1/optimize", json=request)
    finally:
        _remove_db_override()

    assert response.status_code == 202


# ---------------------------------------------------------------------------
# Optional fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimize_with_sector_constraints_accepted(client: AsyncClient) -> None:
    """Request with sector constraints is accepted and returns 202."""
    session = make_mock_session()
    _install_db_override(session)

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            response = await client.post("/api/v1/optimize", json=FULL_REQUEST)
    finally:
        _remove_db_override()

    assert response.status_code == 202
    body = response.json()
    assert "run_id" in body


@pytest.mark.asyncio
async def test_optimize_minimal_request_accepted(client: AsyncClient) -> None:
    """Minimal request (only tickers + budget) is accepted and returns 202."""
    session = make_mock_session()
    _install_db_override(session)

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            response = await client.post("/api/v1/optimize", json=MINIMAL_REQUEST)
    finally:
        _remove_db_override()

    assert response.status_code == 202


# ---------------------------------------------------------------------------
# DB interaction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimize_db_add_called_with_optimization_run(
    client: AsyncClient,
) -> None:
    """DB session add() is called with an OptimizationRun instance."""
    session = make_mock_session()
    _install_db_override(session)

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            response = await client.post("/api/v1/optimize", json=STANDARD_REQUEST)
    finally:
        _remove_db_override()

    assert response.status_code == 202
    session.add.assert_called_once()
    added_obj = session.add.call_args[0][0]
    assert isinstance(added_obj, OptimizationRun), (
        f"Expected OptimizationRun, got {type(added_obj).__name__}"
    )


@pytest.mark.asyncio
async def test_optimize_db_record_has_pending_status(client: AsyncClient) -> None:
    """The OptimizationRun record added to DB has status='pending'."""
    session = make_mock_session()
    _install_db_override(session)

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            response = await client.post("/api/v1/optimize", json=STANDARD_REQUEST)
    finally:
        _remove_db_override()

    assert response.status_code == 202
    added_obj = session.add.call_args[0][0]
    assert added_obj.status == "pending", (
        f"Expected status='pending', got {added_obj.status!r}"
    )


@pytest.mark.asyncio
async def test_optimize_db_record_has_correct_tickers(client: AsyncClient) -> None:
    """The OptimizationRun record has the correct tickers from the request."""
    session = make_mock_session()
    _install_db_override(session)

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            response = await client.post("/api/v1/optimize", json=STANDARD_REQUEST)
    finally:
        _remove_db_override()

    assert response.status_code == 202
    added_obj = session.add.call_args[0][0]
    assert set(added_obj.tickers) == {"AAPL", "MSFT", "GOOGL"}


@pytest.mark.asyncio
async def test_optimize_db_flush_awaited(client: AsyncClient) -> None:
    """DB session flush() is awaited to persist the record within the transaction."""
    session = make_mock_session()
    _install_db_override(session)

    try:
        with patch("app.workers.tasks.run_optimization_task") as mock_task:
            mock_task.apply_async = MagicMock()
            response = await client.post("/api/v1/optimize", json=STANDARD_REQUEST)
    finally:
        _remove_db_override()

    assert response.status_code == 202
    session.flush.assert_awaited_once()
