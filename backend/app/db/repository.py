"""Data access layer (repository pattern) for OptimizationRun records.

This module provides all database CRUD operations for the optimization_runs
table. Keeping SQL queries here (rather than scattered across API handlers
and Celery tasks) makes the data access layer testable and maintainable.

All public functions accept an ``AsyncSession`` and return ORM model instances
or None. Callers are responsible for committing/rolling back transactions.

Usage example::

    async with AsyncSessionLocal() as session:
        run = await create_run(session, run_id="...", request=req)
        await session.commit()
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OptimizationRun
from app.schemas.requests import OptimizationRequest


# ── Create ────────────────────────────────────────────────────────────────────


async def create_run(
    session: AsyncSession,
    *,
    run_id: str | None = None,
    request: OptimizationRequest,
    status: str = "pending",
) -> OptimizationRun:
    """Create and persist a new OptimizationRun record.

    The run is added to the session but NOT committed. The caller must
    call ``await session.commit()`` to persist the record.

    Args:
        session: Active async SQLAlchemy session.
        run_id: UUID string for the run. Auto-generated if not provided.
        request: The validated OptimizationRequest from the API.
        status: Initial status. Defaults to 'pending'.

    Returns:
        The newly created (but not yet committed) OptimizationRun instance.
    """
    run = OptimizationRun(
        run_id=run_id or str(uuid.uuid4()),
        status=status,
        tickers=request.tickers,
        budget=request.budget,
        request_params=request.model_dump(mode="json"),
    )
    session.add(run)
    return run


# ── Read ──────────────────────────────────────────────────────────────────────


async def get_run_by_id(
    session: AsyncSession,
    run_id: str,
) -> OptimizationRun | None:
    """Fetch a single OptimizationRun by its public UUID.

    Args:
        session: Active async SQLAlchemy session.
        run_id: The public UUID string of the run.

    Returns:
        The OptimizationRun instance, or None if not found.
    """
    result = await session.execute(
        select(OptimizationRun).where(OptimizationRun.run_id == run_id)
    )
    return result.scalar_one_or_none()


async def get_run_by_id_or_raise(
    session: AsyncSession,
    run_id: str,
) -> OptimizationRun:
    """Fetch a single OptimizationRun by its public UUID, raising if not found.

    Args:
        session: Active async SQLAlchemy session.
        run_id: The public UUID string of the run.

    Returns:
        The OptimizationRun instance.

    Raises:
        ValueError: If no run with the given run_id exists.
    """
    run = await get_run_by_id(session, run_id)
    if run is None:
        raise ValueError(f"OptimizationRun with run_id={run_id!r} not found")
    return run


async def list_runs(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
) -> tuple[list[OptimizationRun], int]:
    """Return a paginated list of OptimizationRun records, newest first.

    Args:
        session: Active async SQLAlchemy session.
        page: 1-based page number.
        page_size: Number of records per page (max 100).
        status_filter: Optional status to filter by (e.g. 'completed').

    Returns:
        A tuple of (list of runs, total count).
    """
    page_size = min(page_size, 100)  # Hard cap to prevent runaway queries
    offset = (page - 1) * page_size

    # Build base query
    base_query = select(OptimizationRun)
    count_query = select(func.count(OptimizationRun.id))

    if status_filter is not None:
        base_query = base_query.where(OptimizationRun.status == status_filter)
        count_query = count_query.where(OptimizationRun.status == status_filter)

    # Total count (without pagination)
    count_result = await session.execute(count_query)
    total = count_result.scalar_one()

    # Paginated rows ordered by newest first
    result = await session.execute(
        base_query
        .order_by(OptimizationRun.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    runs = list(result.scalars().all())

    return runs, total


# ── Update ────────────────────────────────────────────────────────────────────


async def update_run_status(
    session: AsyncSession,
    run_id: str,
    status: str,
) -> OptimizationRun:
    """Update the status of an existing run.

    Args:
        session: Active async SQLAlchemy session.
        run_id: The public UUID string of the run.
        status: New status value.

    Returns:
        The updated OptimizationRun instance.

    Raises:
        ValueError: If no run with the given run_id exists.
    """
    run = await get_run_by_id_or_raise(session, run_id)
    run.status = status
    return run


async def mark_run_running(
    session: AsyncSession,
    run_id: str,
) -> OptimizationRun:
    """Transition a run to 'running' status.

    Args:
        session: Active async SQLAlchemy session.
        run_id: The public UUID string of the run.

    Returns:
        The updated OptimizationRun instance.

    Raises:
        ValueError: If no run with the given run_id exists.
    """
    run = await get_run_by_id_or_raise(session, run_id)
    run.mark_running()
    return run


async def mark_run_completed(
    session: AsyncSession,
    run_id: str,
    *,
    classical_result: dict[str, Any] | None = None,
    quantum_result: dict[str, Any] | None = None,
    comparison: dict[str, Any] | None = None,
    llm_explanation: str | None = None,
    classical_sharpe: float | None = None,
    quantum_sharpe: float | None = None,
    completed_at: datetime | None = None,
) -> OptimizationRun:
    """Persist the final results and transition a run to 'completed' status.

    Args:
        session: Active async SQLAlchemy session.
        run_id: The public UUID string of the run.
        classical_result: Serialised ClassicalResult dict.
        quantum_result: Serialised QuantumResult dict.
        comparison: Serialised ComparisonSummary dict.
        llm_explanation: LLM-generated explanation text.
        classical_sharpe: Denormalised classical Sharpe ratio.
        quantum_sharpe: Denormalised quantum Sharpe ratio.
        completed_at: Completion timestamp. Defaults to current UTC time.

    Returns:
        The updated OptimizationRun instance.

    Raises:
        ValueError: If no run with the given run_id exists.
    """
    run = await get_run_by_id_or_raise(session, run_id)

    if classical_result is not None:
        run.classical_result = classical_result
    if quantum_result is not None:
        run.quantum_result = quantum_result
    if comparison is not None:
        run.comparison = comparison
    if llm_explanation is not None:
        run.llm_explanation = llm_explanation
    if classical_sharpe is not None:
        run.classical_sharpe = classical_sharpe
    if quantum_sharpe is not None:
        run.quantum_sharpe = quantum_sharpe

    run.mark_completed(completed_at=completed_at)
    return run


async def mark_run_failed(
    session: AsyncSession,
    run_id: str,
    error_message: str,
    completed_at: datetime | None = None,
) -> OptimizationRun:
    """Persist the error and transition a run to 'failed' status.

    Args:
        session: Active async SQLAlchemy session.
        run_id: The public UUID string of the run.
        error_message: Human-readable description of the failure.
        completed_at: Failure timestamp. Defaults to current UTC time.

    Returns:
        The updated OptimizationRun instance.

    Raises:
        ValueError: If no run with the given run_id exists.
    """
    run = await get_run_by_id_or_raise(session, run_id)
    run.mark_failed(
        error_message=error_message,
        completed_at=completed_at,
    )
    return run


# ── Delete ────────────────────────────────────────────────────────────────────


async def delete_run(
    session: AsyncSession,
    run_id: str,
) -> bool:
    """Delete an OptimizationRun record.

    Args:
        session: Active async SQLAlchemy session.
        run_id: The public UUID string of the run.

    Returns:
        True if the run was found and deleted, False if not found.
    """
    run = await get_run_by_id(session, run_id)
    if run is None:
        return False
    await session.delete(run)
    return True


# ── Aggregates ────────────────────────────────────────────────────────────────


async def count_runs_by_status(
    session: AsyncSession,
) -> dict[str, int]:
    """Return a count of runs grouped by status.

    Useful for health/monitoring dashboards.

    Args:
        session: Active async SQLAlchemy session.

    Returns:
        Dict mapping status → count, e.g. {'completed': 42, 'failed': 3}.
    """
    result = await session.execute(
        select(OptimizationRun.status, func.count(OptimizationRun.id))
        .group_by(OptimizationRun.status)
    )
    return {row[0]: row[1] for row in result.all()}


async def get_recent_runs(
    session: AsyncSession,
    limit: int = 10,
) -> list[OptimizationRun]:
    """Return the most recent N optimization runs.

    Args:
        session: Active async SQLAlchemy session.
        limit: Maximum number of runs to return.

    Returns:
        List of OptimizationRun instances ordered by created_at DESC.
    """
    result = await session.execute(
        select(OptimizationRun)
        .order_by(OptimizationRun.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
