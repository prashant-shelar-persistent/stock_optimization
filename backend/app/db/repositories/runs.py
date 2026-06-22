"""Class-based repository for OptimizationRun records.

This module provides ``RunsRepository``, an object-oriented data access
layer for the ``optimization_runs`` table. It wraps the same SQLAlchemy
async session used throughout the application and exposes a clean,
type-safe interface for all CRUD operations.

Design decisions:
    - The repository holds a reference to an ``AsyncSession`` injected at
      construction time, making it straightforward to mock in unit tests.
    - All write operations (create, update_*) mutate the ORM object and
      add it to the session but do NOT commit. The caller (API handler or
      Celery task) is responsible for committing or rolling back, giving
      full control over transaction boundaries.
    - ``get_by_id`` returns ``None`` on miss; ``get_by_id_or_raise`` raises
      ``RunNotFoundError`` (a subclass of ``ValueError``) for ergonomic use
      in API handlers that need a 404 response.
    - Pagination is capped at 100 items per page to prevent runaway queries.
    - Denormalised Sharpe ratio columns (``classical_sharpe``,
      ``quantum_sharpe``) are updated by ``mark_completed`` so that list
      queries never need to deserialise JSON blobs.

Example usage in a FastAPI handler::

    from app.db.repositories import RunsRepository
    from app.core.dependencies import DbDep

    @router.get("/runs/{run_id}")
    async def get_run(run_id: str, db: DbDep) -> "OptimizationRunDetail":
        repo = RunsRepository(db)
        run = await repo.get_by_id_or_raise(run_id)
        return OptimizationRunDetail.model_validate(run)

Example usage in a Celery task (sync wrapper around async)::

    async with AsyncSessionLocal() as session:
        repo = RunsRepository(session)
        await repo.mark_running(run_id)
        await session.commit()
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OptimizationRun
from app.schemas.requests import OptimizationRequest


# ── Custom exception ──────────────────────────────────────────────────────────


class RunNotFoundError(ValueError):
    """Raised when an OptimizationRun with the given run_id does not exist.

    Inherits from ``ValueError`` so that existing callers that catch
    ``ValueError`` continue to work without modification.

    Attributes:
        run_id: The UUID string that was not found.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"OptimizationRun with run_id={run_id!r} not found")


# ── Repository ────────────────────────────────────────────────────────────────


class RunsRepository:
    """Data access layer for the ``optimization_runs`` table.

    All methods are ``async`` and operate on the ``AsyncSession`` provided
    at construction time. Write methods mutate ORM objects and add them to
    the session but do NOT commit — the caller controls transaction boundaries.

    Args:
        session: An active ``AsyncSession`` bound to the database engine.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ────────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        run_id: str | None = None,
        request: OptimizationRequest,
        status: str = "pending",
    ) -> "OptimizationRun":
        """Create and stage a new OptimizationRun record.

        The record is added to the session but NOT committed. Call
        ``await session.commit()`` after this method to persist it.

        Args:
            run_id: UUID string for the run. Auto-generated if not provided.
            request: The validated ``OptimizationRequest`` from the API.
            status: Initial lifecycle status. Defaults to ``'pending'``.

        Returns:
            The newly created (uncommitted) ``OptimizationRun`` instance.
        """
        run = OptimizationRun(
            run_id=run_id or str(uuid.uuid4()),
            status=status,
            tickers=request.tickers,
            budget=request.budget,
            request_params=request.model_dump(mode="json"),
        )
        self._session.add(run)
        return run

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_by_id(self, run_id: str) -> OptimizationRun | None:
        """Fetch a single run by its public UUID.

        Args:
            run_id: The public UUID string of the run.

        Returns:
            The ``OptimizationRun`` instance, or ``None`` if not found.
        """
        result = await self._session.execute(
            select(OptimizationRun).where(OptimizationRun.run_id == run_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_or_raise(self, run_id: str) -> "OptimizationRun":
        """Fetch a single run by its public UUID, raising if not found.

        Args:
            run_id: The public UUID string of the run.

        Returns:
            The ``OptimizationRun`` instance.

        Raises:
            RunNotFoundError: If no run with the given ``run_id`` exists.
        """
        run = await self.get_by_id(run_id)
        if run is None:
            raise RunNotFoundError(run_id)
        return run

    async def list(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status_filter: str | None = None,
    ) -> tuple[list[OptimizationRun], int]:
        """Return a paginated list of runs ordered by newest first.

        Args:
            page: 1-based page number. Must be >= 1.
            page_size: Number of records per page. Capped at 100.
            status_filter: Optional status to filter by (e.g. ``'completed'``).
                           Pass ``None`` to return runs of all statuses.

        Returns:
            A tuple of ``(runs, total)`` where ``runs`` is the page of
            ``OptimizationRun`` instances and ``total`` is the unfiltered
            (or filtered, if ``status_filter`` is set) row count.
        """
        page_size = min(max(page_size, 1), 100)  # Clamp to [1, 100]
        offset = (max(page, 1) - 1) * page_size

        base_query = select(OptimizationRun)
        count_query = select(func.count(OptimizationRun.id))

        if status_filter is not None:
            base_query = base_query.where(
                OptimizationRun.status == status_filter
            )
            count_query = count_query.where(
                OptimizationRun.status == status_filter
            )

        # Total count (without pagination)
        count_result = await self._session.execute(count_query)
        total: int = count_result.scalar_one()

        # Paginated rows ordered by newest first
        rows_result = await self._session.execute(
            base_query
            .order_by(OptimizationRun.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        runs = list(rows_result.scalars().all())

        return runs, total

    async def get_recent(self, limit: int = 10) -> list[OptimizationRun]:
        """Return the most recent N optimization runs.

        Args:
            limit: Maximum number of runs to return. Must be >= 1.

        Returns:
            List of ``OptimizationRun`` instances ordered by
            ``created_at DESC``.
        """
        limit = max(limit, 1)
        result = await self._session.execute(
            select(OptimizationRun)
            .order_by(OptimizationRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_status(self) -> dict[str, int]:
        """Return a count of runs grouped by status.

        Useful for health/monitoring dashboards and admin views.

        Returns:
            Dict mapping status → count, e.g.
            ``{'completed': 42, 'running': 1, 'failed': 3, 'pending': 0}``.
            Statuses with zero runs are omitted from the result.
        """
        result = await self._session.execute(
            select(OptimizationRun.status, func.count(OptimizationRun.id))
            .group_by(OptimizationRun.status)
        )
        return {row[0]: row[1] for row in result.all()}

    # ── Update ────────────────────────────────────────────────────────────────

    async def update_status(
        self,
        run_id: str,
        status: str,
    ) -> "OptimizationRun":
        """Update the lifecycle status of an existing run.

        Args:
            run_id: The public UUID string of the run.
            status: New status value (``'pending'``, ``'running'``,
                    ``'completed'``, or ``'failed'``).

        Returns:
            The updated ``OptimizationRun`` instance (not yet committed).

        Raises:
            RunNotFoundError: If no run with the given ``run_id`` exists.
        """
        run = await self.get_by_id_or_raise(run_id)
        run.status = status
        return run

    async def mark_running(self, run_id: str) -> "OptimizationRun":
        """Transition a run to ``'running'`` status.

        Delegates to the ORM model's ``mark_running()`` helper to keep
        status-transition logic in one place.

        Args:
            run_id: The public UUID string of the run.

        Returns:
            The updated ``OptimizationRun`` instance (not yet committed).

        Raises:
            RunNotFoundError: If no run with the given ``run_id`` exists.
        """
        run = await self.get_by_id_or_raise(run_id)
        run.mark_running()
        return run

    async def mark_completed(
        self,
        run_id: str,
        *,
        classical_result: dict[str, Any] | None = None,
        quantum_result: dict[str, Any] | None = None,
        comparison: dict[str, Any] | None = None,
        llm_explanation: str | None = None,
        classical_sharpe: float | None = None,
        quantum_sharpe: float | None = None,
        completed_at: datetime | None = None,
    ) -> "OptimizationRun":
        """Persist the final results and transition a run to ``'completed'``.

        Only non-``None`` keyword arguments are written to the record,
        allowing partial updates (e.g. when quantum was skipped).

        Args:
            run_id: The public UUID string of the run.
            classical_result: Serialised ``ClassicalResult`` dict.
            quantum_result: Serialised ``QuantumResult`` dict.
            comparison: Serialised ``ComparisonSummary`` dict.
            llm_explanation: LLM-generated explanation text.
            classical_sharpe: Denormalised classical Sharpe ratio for fast
                              list queries (avoids JSON deserialisation).
            quantum_sharpe: Denormalised quantum Sharpe ratio (QAOA preferred,
                            else VQE) for fast list queries.
            completed_at: Completion timestamp. Defaults to current UTC time.

        Returns:
            The updated ``OptimizationRun`` instance (not yet committed).

        Raises:
            RunNotFoundError: If no run with the given ``run_id`` exists.
        """
        run = await self.get_by_id_or_raise(run_id)

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

    async def mark_failed(
        self,
        run_id: str,
        error_message: str,
        *,
        completed_at: datetime | None = None,
    ) -> "OptimizationRun":
        """Persist the error and transition a run to ``'failed'`` status.

        Args:
            run_id: The public UUID string of the run.
            error_message: Human-readable description of the failure.
            completed_at: Failure timestamp. Defaults to current UTC time.

        Returns:
            The updated ``OptimizationRun`` instance (not yet committed).

        Raises:
            RunNotFoundError: If no run with the given ``run_id`` exists.
        """
        run = await self.get_by_id_or_raise(run_id)
        run.mark_failed(
            error_message=error_message,
            completed_at=completed_at,
        )
        return run

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete(self, run_id: str) -> bool:
        """Delete an OptimizationRun record.

        Args:
            run_id: The public UUID string of the run.

        Returns:
            ``True`` if the run was found and staged for deletion,
            ``False`` if no run with the given ``run_id`` exists.
        """
        run = await self.get_by_id(run_id)
        if run is None:
            return False
        await self._session.delete(run)
        return True

    # ── Convenience helpers ───────────────────────────────────────────────────

    async def exists(self, run_id: str) -> bool:
        """Return ``True`` if a run with the given UUID exists.

        Uses a lightweight ``COUNT`` query rather than fetching the full row.

        Args:
            run_id: The public UUID string of the run.

        Returns:
            ``True`` if the run exists, ``False`` otherwise.
        """
        result = await self._session.execute(
            select(func.count(OptimizationRun.id)).where(
                OptimizationRun.run_id == run_id
            )
        )
        return result.scalar_one() > 0

    async def get_status(self, run_id: str) -> str | None:
        """Return the current status of a run without fetching the full row.

        Useful for lightweight polling (e.g. from a Celery task) where only
        the status field is needed.

        Args:
            run_id: The public UUID string of the run.

        Returns:
            The status string (``'pending'``, ``'running'``, ``'completed'``,
            or ``'failed'``), or ``None`` if the run does not exist.
        """
        result = await self._session.execute(
            select(OptimizationRun.status).where(
                OptimizationRun.run_id == run_id
            )
        )
        return result.scalar_one_or_none()
