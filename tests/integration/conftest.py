"""Shared pytest fixtures for integration tests.

Provides:
- AsyncClient fixture backed by the FastAPI app (no real DB/Redis needed)
- Mock DB session factory for endpoints that require database access
- Mock Celery task dispatch to avoid real broker connections
- Reusable OptimizationRun ORM objects for run-history tests
- Reusable OptimizationRequest payloads for optimize endpoint tests
- AgentState builder helpers for agent graph tests
"""

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.db.models import OptimizationRun
from app.main import app


# ---------------------------------------------------------------------------
# HTTP client fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Async HTTP client wired to the FastAPI app via ASGI transport.

    Uses ``ASGITransport`` so no real network socket is opened.
    The client is created fresh for each test to avoid state leakage.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Mock DB session helpers
# ---------------------------------------------------------------------------


def make_mock_session() -> AsyncMock:
    """Return a fully-mocked AsyncSession that no-ops on all DB operations.

    Suitable for endpoints that write to the DB (e.g., POST /optimize).
    """
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


def make_mock_session_for_list(
    runs: list[OptimizationRun],
    total: int | None = None,
) -> AsyncMock:
    """Return a mock session that serves paginated list queries.

    The session handles two consecutive ``execute`` calls:
    1. COUNT query → returns ``total`` (or ``len(runs)`` if not given)
    2. Rows query  → returns ``runs`` via ``scalars().all()``
    """
    session = AsyncMock(spec=AsyncSession)

    count_result = MagicMock()
    count_result.scalar_one.return_value = total if total is not None else len(runs)

    rows_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = runs
    rows_result.scalars.return_value = scalars_mock

    session.execute = AsyncMock(side_effect=[count_result, rows_result])
    return session


def make_mock_session_for_single(run: OptimizationRun | None) -> AsyncMock:
    """Return a mock session that serves a single-row lookup query.

    The session's ``execute`` returns a result whose
    ``scalar_one_or_none()`` yields ``run`` (or ``None`` for 404 tests).
    """
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = run
    session.execute = AsyncMock(return_value=result)
    return session


# ---------------------------------------------------------------------------
# OptimizationRun factory
# ---------------------------------------------------------------------------


def make_run(
    run_id: str | None = None,
    status: str = "completed",
    tickers: list[str] | None = None,
    budget: float = 100_000.0,
    classical_sharpe: float | None = 1.25,
    quantum_sharpe: float | None = None,
    classical_result: dict[str, Any] | None = None,
    quantum_result: dict[str, Any] | None = None,
    comparison: dict[str, Any] | None = None,
    llm_explanation: str | None = None,
    error_message: str | None = None,
    completed_at: datetime | None = None,
) -> OptimizationRun:
    """Build a minimal ``OptimizationRun`` ORM object for testing.

    Does NOT persist to a real database — used only for mock session returns.
    """
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
    run.quantum_result = quantum_result
    run.comparison = comparison
    run.llm_explanation = llm_explanation
    run.error_message = error_message
    run.created_at = datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)
    run.completed_at = completed_at or (
        datetime(2024, 6, 1, 10, 5, 0, tzinfo=UTC)
        if status in ("completed", "failed")
        else None
    )
    return run


# ---------------------------------------------------------------------------
# Standard request payloads
# ---------------------------------------------------------------------------


MINIMAL_REQUEST: dict[str, Any] = {
    "tickers": ["AAPL", "MSFT"],
    "budget": 50_000.0,
    "run_quantum": False,
}

STANDARD_REQUEST: dict[str, Any] = {
    "tickers": ["AAPL", "MSFT", "GOOGL"],
    "budget": 100_000.0,
    "run_quantum": False,
}

QUANTUM_REQUEST: dict[str, Any] = {
    "tickers": ["AAPL", "MSFT", "GOOGL"],
    "budget": 100_000.0,
    "run_quantum": True,
}

FULL_REQUEST: dict[str, Any] = {
    "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN"],
    "budget": 200_000.0,
    "run_quantum": False,
    "min_return": 0.08,
    "max_volatility": 0.25,
    "max_weight_per_asset": 0.4,
    "sector_constraints": [
        {"sector": "Technology", "max_weight": 0.6},
    ],
    "num_assets_to_select": 3,
    "lookback_days": 365,
}


# ---------------------------------------------------------------------------
# Minimal classical result fixture (for agent graph tests)
# ---------------------------------------------------------------------------


MINIMAL_CLASSICAL_RESULT: dict[str, Any] = {
    "weights": [
        {
            "ticker": "AAPL",
            "weight": 0.6,
            "allocation": 60_000.0,
            "sector": "Technology",
        },
        {
            "ticker": "MSFT",
            "weight": 0.4,
            "allocation": 40_000.0,
            "sector": "Technology",
        },
    ],
    "metrics": {
        "expected_return": 0.11,
        "volatility": 0.17,
        "sharpe_ratio": 1.30,
        "max_drawdown": -0.12,
        "num_assets": 2,
    },
    "solver_status": "optimal",
    "solve_time_ms": 35.0,
}

MINIMAL_COMPARISON_SUMMARY: dict[str, Any] = {
    "sharpe_improvement_qaoa": None,
    "sharpe_improvement_vqe": None,
    "return_diff_qaoa": None,
    "return_diff_vqe": None,
    "volatility_diff_qaoa": None,
    "volatility_diff_vqe": None,
    "recommendation": "Classical portfolio recommended — quantum not run.",
}


# ---------------------------------------------------------------------------
# DB override helpers
# ---------------------------------------------------------------------------


def override_db_with(session: AsyncMock):
    """Return an async generator dependency override that yields ``session``."""

    async def _override():
        yield session

    return _override


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Fixture: a no-op mock DB session for write endpoints."""
    return make_mock_session()


@pytest.fixture
def db_override(mock_db_session: AsyncMock):
    """Fixture: installs and tears down the mock DB override on the app."""
    app.dependency_overrides[get_db] = override_db_with(mock_db_session)
    yield mock_db_session
    app.dependency_overrides.pop(get_db, None)
