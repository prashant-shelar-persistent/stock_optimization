"""Run history endpoints.

Endpoints:
    GET /api/v1/runs                    — Paginated list of past runs
    GET /api/v1/runs/{run_id}           — Full detail of a specific run
    GET /api/v1/runs/{run_id}/status    — Lightweight status-only query

Design notes:
    - All queries use SQLAlchemy async session via the ``DbDep`` dependency.
    - The ``/status`` endpoint is intentionally lightweight — it returns only
      the lifecycle fields without deserialising the full JSON result blobs,
      making it suitable for efficient polling from the frontend.
    - 404 responses include a structured ``error_code`` field for consistent
      error handling on the frontend.
"""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.core.dependencies import DbDep
from app.core.logging import get_logger
from app.db.models import OptimizationRun
from app.schemas.responses import (
    OptimizationRunDetail,
    OptimizationRunSummary,
    PaginatedRunsResponse,
    RunStatusResponse,
)


logger = get_logger(__name__)
router = APIRouter(tags=["runs"])


@router.get(
    "/runs",
    response_model=PaginatedRunsResponse,
    summary="List optimization run history",
    description=(
        "Returns a paginated list of past optimization runs, newest first. "
        "Each item includes summary metrics (Sharpe ratios) without the full "
        "result payload. Use GET /api/v1/runs/{run_id} for full details."
    ),
)
async def list_runs(
    db: DbDep,
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        default=20, ge=1, le=100, description="Items per page (max 100)"
    ),
    status: str | None = Query(
        default=None,
        description=(
            "Filter by run status: pending | running | completed | failed. "
            "Omit to return all statuses."
        ),
    ),
) -> "PaginatedRunsResponse":
    """Return paginated run history, optionally filtered by status."""
    offset = (page - 1) * page_size

    # Build base queries
    base_query = select(OptimizationRun)
    count_query = select(func.count(OptimizationRun.id))

    # Apply optional status filter
    if status is not None:
        valid_statuses = {"pending", "running", "completed", "failed"}
        if status not in valid_statuses:
            raise HTTPException(
                status_code=422,
                detail={
                    "error_code": "INVALID_STATUS_FILTER",
                    "message": (
                        f"Invalid status filter '{status}'. "
                        f"Must be one of: {', '.join(sorted(valid_statuses))}"
                    ),
                    "details": {"status": status, "valid_values": sorted(valid_statuses)},
                },
            )
        base_query = base_query.where(OptimizationRun.status == status)
        count_query = count_query.where(OptimizationRun.status == status)

    # Total count (without pagination)
    count_result = await db.execute(count_query)
    total: int = count_result.scalar_one()

    # Paginated rows ordered by newest first
    rows_result = await db.execute(
        base_query
        .order_by(OptimizationRun.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    runs = list(rows_result.scalars().all())

    logger.debug(
        "list_runs",
        page=page,
        page_size=page_size,
        total=total,
        status_filter=status,
        returned=len(runs),
    )

    return PaginatedRunsResponse(
        items=[OptimizationRunSummary.model_validate(r) for r in runs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/runs/{run_id}/status",
    response_model=RunStatusResponse,
    summary="Get optimization run status",
    description=(
        "Returns the lightweight lifecycle status of a specific run. "
        "Suitable for efficient polling — does not deserialise the full "
        "result payload. Use GET /api/v1/runs/{run_id} for full details."
    ),
)
async def get_run_status(
    run_id: str,
    db: DbDep,
) -> "RunStatusResponse":
    """Return the current status of a specific run without full result data.

    This endpoint is optimised for polling: it returns only the lifecycle
    fields (run_id, status, created_at, completed_at) without loading the
    full JSON result blobs from the database.
    """
    result = await db.execute(
        select(OptimizationRun).where(OptimizationRun.run_id == run_id)
    )
    run = result.scalar_one_or_none()

    if run is None:
        logger.warning("run_status_not_found", run_id=run_id)
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "RUN_NOT_FOUND",
                "message": f"Optimization run '{run_id}' not found.",
                "details": {"run_id": run_id},
            },
        )

    logger.debug("run_status_fetched", run_id=run_id, status=run.status)

    return RunStatusResponse(
        run_id=run.run_id,
        status=run.status,  # type: ignore[arg-type]
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


@router.get(
    "/runs/{run_id}",
    response_model=OptimizationRunDetail,
    summary="Get optimization run detail",
    description=(
        "Returns the full result of a specific optimization run, including "
        "classical and quantum portfolio weights, metrics, comparison summary, "
        "and LLM-generated explanation. For pending/running runs, result fields "
        "will be null."
    ),
)
async def get_run(
    run_id: str,
    db: DbDep,
) -> "OptimizationRunDetail":
    """Return the full detail of a specific run.

    For runs that are still pending or running, the result fields
    (classical_result, quantum_result, comparison, llm_explanation) will
    be null. The client should poll the /status endpoint or use the
    WebSocket to wait for completion.
    """
    result = await db.execute(
        select(OptimizationRun).where(OptimizationRun.run_id == run_id)
    )
    run = result.scalar_one_or_none()

    if run is None:
        logger.warning("run_not_found", run_id=run_id)
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "RUN_NOT_FOUND",
                "message": f"Optimization run '{run_id}' not found.",
                "details": {"run_id": run_id},
            },
        )

    logger.debug("run_detail_fetched", run_id=run_id, status=run.status)

    return OptimizationRunDetail.model_validate(run)
