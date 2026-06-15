"""Integration tests for GET /api/v1/runs endpoints.

Tests cover:
1.  GET /api/v1/runs — empty DB returns 200 with empty items list
2.  GET /api/v1/runs — returns PaginatedRunsResponse with correct shape
3.  GET /api/v1/runs — item fields match the OptimizationRun record
4.  GET /api/v1/runs — status filter 'pending' is accepted
5.  GET /api/v1/runs — invalid status filter returns 422 with INVALID_STATUS_FILTER
6.  GET /api/v1/runs — custom page and page_size are reflected in response
7.  GET /api/v1/runs — page=0 returns 422
8.  GET /api/v1/runs — page_size=101 returns 422
9.  GET /api/v1/runs/{run_id} — returns 200 with full detail for existing run
10. GET /api/v1/runs/{run_id} — 404 for unknown run_id
11. GET /api/v1/runs/{run_id} — 404 body has error_code=RUN_NOT_FOUND
12. GET /api/v1/runs/{run_id} — classical_result is included when present
13. GET /api/v1/runs/{run_id} — llm_explanation is included when present
14. GET /api/v1/runs/{run_id}/status — returns lightweight status for existing run
15. GET /api/v1/runs/{run_id}/status — 404 for unknown run_id
16. GET /api/v1/runs/{run_id}/status — 404 body has error_code=RUN_NOT_FOUND
17. GET /api/v1/runs/{run_id}/status — completed run has completed_at timestamp
18. GET /api/v1/runs/{run_id}/status — running run has completed_at=null
19. GET /api/v1/runs/{run_id} — failed run has error_message field
20. GET /api/v1/runs — total count is correct
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.core.dependencies import get_db
from app.main import app

from tests.integration.conftest import (
    make_mock_session_for_list,
    make_mock_session_for_single,
    make_run,
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
# GET /api/v1/runs — list endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_runs_empty_returns_200_with_empty_items(
    client: AsyncClient,
) -> None:
    """Empty database returns 200 with empty items list."""
    session = make_mock_session_for_list(runs=[], total=0)
    _install_db_override(session)

    try:
        response = await client.get("/api/v1/runs")
    finally:
        _remove_db_override()

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["page"] == 1


@pytest.mark.asyncio
async def test_list_runs_returns_paginated_response_shape(
    client: AsyncClient,
) -> None:
    """List endpoint returns PaginatedRunsResponse with all required fields."""
    run = make_run()
    session = make_mock_session_for_list(runs=[run], total=1)
    _install_db_override(session)

    try:
        response = await client.get("/api/v1/runs")
    finally:
        _remove_db_override()

    assert response.status_code == 200
    body = response.json()

    # Top-level pagination fields
    assert "items" in body, "Missing 'items' field"
    assert "total" in body, "Missing 'total' field"
    assert "page" in body, "Missing 'page' field"
    assert "page_size" in body, "Missing 'page_size' field"
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 20  # default


@pytest.mark.asyncio
async def test_list_runs_item_fields_match_run_record(client: AsyncClient) -> None:
    """Item fields in the list response match the OptimizationRun record."""
    run_id = str(uuid.uuid4())
    run = make_run(
        run_id=run_id,
        status="completed",
        tickers=["AAPL", "MSFT", "GOOGL"],
        budget=100_000.0,
        classical_sharpe=1.25,
    )
    session = make_mock_session_for_list(runs=[run], total=1)
    _install_db_override(session)

    try:
        response = await client.get("/api/v1/runs")
    finally:
        _remove_db_override()

    assert response.status_code == 200
    item = response.json()["items"][0]

    assert item["run_id"] == run_id
    assert item["status"] == "completed"
    assert set(item["tickers"]) == {"AAPL", "MSFT", "GOOGL"}
    assert item["budget"] == 100_000.0
    assert item["classical_sharpe"] == 1.25


@pytest.mark.asyncio
async def test_list_runs_status_filter_pending_accepted(client: AsyncClient) -> None:
    """Status filter 'pending' is accepted and returns matching runs."""
    run = make_run(status="pending", classical_sharpe=None, completed_at=None)
    session = make_mock_session_for_list(runs=[run], total=1)
    _install_db_override(session)

    try:
        response = await client.get("/api/v1/runs?status=pending")
    finally:
        _remove_db_override()

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_list_runs_invalid_status_returns_422(client: AsyncClient) -> None:
    """Invalid status filter returns HTTP 422 with INVALID_STATUS_FILTER error code."""
    response = await client.get("/api/v1/runs?status=invalid_status")

    assert response.status_code == 422
    body = response.json()
    detail = body.get("detail", {})
    if isinstance(detail, dict):
        assert detail.get("error_code") == "INVALID_STATUS_FILTER"


@pytest.mark.asyncio
async def test_list_runs_custom_pagination_reflected(client: AsyncClient) -> None:
    """Custom page and page_size params are reflected in the response."""
    runs = [make_run() for _ in range(5)]
    session = make_mock_session_for_list(runs=runs, total=50)
    _install_db_override(session)

    try:
        response = await client.get("/api/v1/runs?page=2&page_size=5")
    finally:
        _remove_db_override()

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 2
    assert body["page_size"] == 5
    assert body["total"] == 50
    assert len(body["items"]) == 5


@pytest.mark.asyncio
async def test_list_runs_page_zero_returns_422(client: AsyncClient) -> None:
    """page=0 is invalid (must be >= 1) and returns 422."""
    response = await client.get("/api/v1/runs?page=0")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_runs_page_size_over_100_returns_422(client: AsyncClient) -> None:
    """page_size=101 is invalid (max 100) and returns 422."""
    response = await client.get("/api/v1/runs?page_size=101")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_runs_total_count_is_correct(client: AsyncClient) -> None:
    """total field reflects the actual count, not just the page size."""
    runs = [make_run() for _ in range(3)]
    session = make_mock_session_for_list(runs=runs, total=42)
    _install_db_override(session)

    try:
        response = await client.get("/api/v1/runs?page_size=3")
    finally:
        _remove_db_override()

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 42
    assert len(body["items"]) == 3


# ---------------------------------------------------------------------------
# GET /api/v1/runs/{run_id} — detail endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_run_detail_returns_200(client: AsyncClient) -> None:
    """Existing run returns HTTP 200 with full detail."""
    run_id = str(uuid.uuid4())
    run = make_run(run_id=run_id)
    session = make_mock_session_for_single(run)
    _install_db_override(session)

    try:
        response = await client.get(f"/api/v1/runs/{run_id}")
    finally:
        _remove_db_override()

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_run_detail_body_has_required_fields(client: AsyncClient) -> None:
    """Run detail response has all required fields."""
    run_id = str(uuid.uuid4())
    run = make_run(run_id=run_id)
    session = make_mock_session_for_single(run)
    _install_db_override(session)

    try:
        response = await client.get(f"/api/v1/runs/{run_id}")
    finally:
        _remove_db_override()

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert "status" in body
    assert "tickers" in body
    assert "budget" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_get_run_detail_not_found_returns_404(client: AsyncClient) -> None:
    """Unknown run_id returns HTTP 404."""
    session = make_mock_session_for_single(None)
    _install_db_override(session)

    try:
        response = await client.get(f"/api/v1/runs/{uuid.uuid4()}")
    finally:
        _remove_db_override()

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_run_detail_404_has_error_code(client: AsyncClient) -> None:
    """404 response body has error_code=RUN_NOT_FOUND."""
    session = make_mock_session_for_single(None)
    _install_db_override(session)

    try:
        response = await client.get(f"/api/v1/runs/{uuid.uuid4()}")
    finally:
        _remove_db_override()

    assert response.status_code == 404
    body = response.json()
    detail = body.get("detail", {})
    assert isinstance(detail, dict), f"Expected dict detail, got: {detail!r}"
    assert detail.get("error_code") == "RUN_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_run_detail_includes_classical_result(client: AsyncClient) -> None:
    """classical_result is included in the response when present."""
    run_id = str(uuid.uuid4())
    classical_result = {
        "weights": [
            {"ticker": "AAPL", "weight": 0.6, "allocation": 60_000.0, "sector": None},
        ],
        "metrics": {
            "expected_return": 0.12,
            "volatility": 0.18,
            "sharpe_ratio": 1.25,
            "max_drawdown": -0.15,
            "num_assets": 1,
        },
        "solver_status": "optimal",
        "solve_time_ms": 42.5,
    }
    run = make_run(run_id=run_id, classical_result=classical_result)
    session = make_mock_session_for_single(run)
    _install_db_override(session)

    try:
        response = await client.get(f"/api/v1/runs/{run_id}")
    finally:
        _remove_db_override()

    assert response.status_code == 200
    body = response.json()
    assert body["classical_result"] is not None
    assert body["classical_result"]["solver_status"] == "optimal"
    assert body["classical_result"]["metrics"]["sharpe_ratio"] == 1.25


@pytest.mark.asyncio
async def test_get_run_detail_includes_llm_explanation(client: AsyncClient) -> None:
    """llm_explanation is included in the response when present."""
    run_id = str(uuid.uuid4())
    explanation = "This portfolio is well-diversified across sectors."
    run = make_run(run_id=run_id, llm_explanation=explanation)
    session = make_mock_session_for_single(run)
    _install_db_override(session)

    try:
        response = await client.get(f"/api/v1/runs/{run_id}")
    finally:
        _remove_db_override()

    assert response.status_code == 200
    body = response.json()
    assert body["llm_explanation"] == explanation


@pytest.mark.asyncio
async def test_get_run_detail_failed_run_has_error_message(
    client: AsyncClient,
) -> None:
    """Failed run includes error_message in the response."""
    run_id = str(uuid.uuid4())
    run = make_run(
        run_id=run_id,
        status="failed",
        error_message="[data_fetch] yfinance connection timeout",
        classical_sharpe=None,
    )
    session = make_mock_session_for_single(run)
    _install_db_override(session)

    try:
        response = await client.get(f"/api/v1/runs/{run_id}")
    finally:
        _remove_db_override()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_message"] is not None
    assert "data_fetch" in body["error_message"]


# ---------------------------------------------------------------------------
# GET /api/v1/runs/{run_id}/status — status endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_run_status_returns_200(client: AsyncClient) -> None:
    """Existing run returns HTTP 200 on the status endpoint."""
    run_id = str(uuid.uuid4())
    run = make_run(run_id=run_id, status="running", completed_at=None)
    session = make_mock_session_for_single(run)
    _install_db_override(session)

    try:
        response = await client.get(f"/api/v1/runs/{run_id}/status")
    finally:
        _remove_db_override()

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_run_status_body_has_required_fields(client: AsyncClient) -> None:
    """Status response has run_id, status, created_at, completed_at fields."""
    run_id = str(uuid.uuid4())
    run = make_run(run_id=run_id, status="running", completed_at=None)
    session = make_mock_session_for_single(run)
    _install_db_override(session)

    try:
        response = await client.get(f"/api/v1/runs/{run_id}/status")
    finally:
        _remove_db_override()

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["status"] == "running"
    assert "created_at" in body
    assert "completed_at" in body


@pytest.mark.asyncio
async def test_get_run_status_not_found_returns_404(client: AsyncClient) -> None:
    """Unknown run_id on status endpoint returns HTTP 404."""
    session = make_mock_session_for_single(None)
    _install_db_override(session)

    try:
        response = await client.get(f"/api/v1/runs/{uuid.uuid4()}/status")
    finally:
        _remove_db_override()

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_run_status_404_has_error_code(client: AsyncClient) -> None:
    """404 on status endpoint has error_code=RUN_NOT_FOUND."""
    session = make_mock_session_for_single(None)
    _install_db_override(session)

    try:
        response = await client.get(f"/api/v1/runs/{uuid.uuid4()}/status")
    finally:
        _remove_db_override()

    assert response.status_code == 404
    body = response.json()
    detail = body.get("detail", {})
    assert isinstance(detail, dict)
    assert detail.get("error_code") == "RUN_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_run_status_completed_has_completed_at(client: AsyncClient) -> None:
    """Completed run status response includes a non-null completed_at timestamp."""
    run_id = str(uuid.uuid4())
    completed_time = datetime(2024, 3, 20, 14, 30, 0, tzinfo=UTC)
    run = make_run(run_id=run_id, status="completed", completed_at=completed_time)
    session = make_mock_session_for_single(run)
    _install_db_override(session)

    try:
        response = await client.get(f"/api/v1/runs/{run_id}/status")
    finally:
        _remove_db_override()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["completed_at"] is not None

    # Verify it's a parseable datetime string
    parsed = datetime.fromisoformat(
        body["completed_at"].replace("Z", "+00:00")
    )
    assert parsed.year == 2024
    assert parsed.month == 3
    assert parsed.day == 20


@pytest.mark.asyncio
async def test_get_run_status_running_has_null_completed_at(
    client: AsyncClient,
) -> None:
    """Running run status response has completed_at=null."""
    run_id = str(uuid.uuid4())
    run = make_run(run_id=run_id, status="running", completed_at=None)
    session = make_mock_session_for_single(run)
    _install_db_override(session)

    try:
        response = await client.get(f"/api/v1/runs/{run_id}/status")
    finally:
        _remove_db_override()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["completed_at"] is None
