"""POST /api/v1/optimize — Submit a new portfolio optimization run.

Accepts optimization constraints, persists a pending run record to the
database, enqueues a Celery task for long-running quantum jobs, and returns
the run_id immediately. Progress is streamed via the WebSocket endpoint at
/ws/runs/{run_id}/progress.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.core.dependencies import DbDep
from app.core.logging import get_logger
from app.db.models import OptimizationRun
from app.schemas.requests import OptimizationRequest
from app.schemas.responses import OptimizationSubmitResponse


logger = get_logger(__name__)
router = APIRouter(tags=["optimization"])


@router.post(
    "/optimize",
    response_model=OptimizationSubmitResponse,
    status_code=202,
    summary="Submit portfolio optimization run",
    description=(
        "Accepts portfolio constraints and enqueues an optimization run. "
        "Persists a pending run record immediately so the client can poll "
        "for status. Returns a run_id immediately. Use the WebSocket endpoint "
        "/ws/runs/{run_id}/progress to stream real-time agent progress, or "
        "poll GET /api/v1/runs/{run_id}/status for lightweight status checks."
    ),
)
async def submit_optimization(
    request: OptimizationRequest,
    db: DbDep,
) -> OptimizationSubmitResponse:
    """Submit a new optimization run.

    The full agent graph (data fetch → classical opt → quantum opt →
    comparison → LLM explanation) is executed asynchronously via Celery.

    A pending ``OptimizationRun`` record is persisted to the database
    *before* the Celery task is dispatched. This guarantees that the record
    exists when the client immediately polls ``GET /api/v1/runs/{run_id}``
    or connects to the WebSocket.
    """
    run_id = str(uuid.uuid4())

    # ── Persist pending run record ────────────────────────────────────────────
    # Create the DB record first so the client can poll immediately after
    # receiving the 202 response.
    run = OptimizationRun(
        run_id=run_id,
        status="pending",
        tickers=request.tickers,
        budget=request.budget,
        request_params=request.model_dump(mode="json"),
    )
    db.add(run)
    await db.flush()  # Flush to DB within the current transaction

    logger.info(
        "optimization_submitted",
        run_id=run_id,
        tickers=request.tickers,
        budget=request.budget,
        run_quantum=request.run_quantum,
        num_tickers=len(request.tickers),
    )

    # ── Dispatch Celery task ──────────────────────────────────────────────────
    # Import lazily to avoid circular imports and to allow the worker module
    # to be developed independently.
    from app.workers.tasks import run_optimization_task  # noqa: PLC0415

    run_optimization_task.apply_async(
        kwargs={
            "run_id": run_id,
            "request_dict": request.model_dump(mode="json"),
        },
        task_id=run_id,
        queue="quantum" if request.run_quantum else "default",
    )

    return OptimizationSubmitResponse(run_id=run_id)
