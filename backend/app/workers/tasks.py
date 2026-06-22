"""Celery task definitions for the Portfolio Optimizer.

Tasks:
    run_optimization_task — Executes the full LangGraph agent pipeline
                            for a single optimization run.

Lifecycle:
    1. API layer creates an ``OptimizationRun`` record with ``status="pending"``
       and dispatches this task via ``apply_async``.
    2. When a worker picks up the task, it transitions the DB record to
       ``status="running"`` and publishes a ``progress`` event.
    3. The LangGraph agent graph runs all nodes (data_fetch →
       constraint_validation → classical_optimization → quantum_dispatch →
       comparison → llm_explanation).
    4. On success: DB record transitions to ``status="completed"`` with all
       result fields populated; a ``result`` event is published.
    5. On ``SoftTimeLimitExceeded``: DB record transitions to
       ``status="failed"`` with ``error_message="Quantum optimization timed
       out"``. The task is NOT retried (timeout is deterministic).
    6. On other transient exceptions: the task retries up to ``max_retries=3``
       times with exponential backoff (30s, 60s, 120s). After all retries are
       exhausted, the DB record transitions to ``status="failed"`` and an
       ``error`` event is published.

Progress events are published to a Redis pub/sub channel so the WebSocket
endpoint can stream them to the frontend in real time.

Channel naming: ``run:{run_id}:progress``

Message format (JSON):
    Progress:  {"type": "progress", "run_id": "...", "node": "...",
                "status": "started|completed|failed", "message": "...",
                "timestamp": "..."}
    Result:    {"type": "result",   "run_id": "...", "result": {...}}
    Error:     {"type": "error",    "run_id": "...", "error_code": "...",
                "message": "..."}
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import redis
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger

from app.core.config import get_settings
from app.workers.celery_app import celery_app


logger = get_task_logger(__name__)

# Exponential backoff base delay in seconds.
# Retry 1: 30s, Retry 2: 60s, Retry 3: 120s
_RETRY_BASE_DELAY_SECONDS = 30


class OptimizationTask(Task):
    """Base task class with Redis publisher for progress events.

    Provides a lazy-initialised synchronous Redis client for pub/sub
    publishing. The client is created once per worker process and reused
    across task invocations to avoid connection overhead.
    """

    _redis_client: redis.Redis | None = None  # type: ignore[type-arg]

    @property
    def redis_client(self) -> redis.Redis:  # type: ignore[type-arg]
        """Lazy-initialised synchronous Redis client for pub/sub publishing."""
        if self._redis_client is None:
            settings = get_settings()
            self._redis_client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
        return self._redis_client

    def publish_progress(
        self,
        run_id: str,
        node: str,
        status: str,
        message: str,
    ) -> "None":
        """Publish a progress event to the Redis pub/sub channel.

        Args:
            run_id: UUID of the optimization run.
            node: Name of the agent node (e.g. "data_fetch").
            status: Node status: "started" | "completed" | "failed".
            message: Human-readable description of the current step.
        """
        channel = f"run:{run_id}:progress"
        payload = json.dumps(
            {
                "type": "progress",
                "run_id": run_id,
                "node": node,
                "status": status,
                "message": message,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        try:
            self.redis_client.publish(channel, payload)
        except Exception as exc:
            logger.warning(
                "Failed to publish progress event",
                extra={"run_id": run_id, "node": node, "error": str(exc)},
            )

    def publish_result(
        self,
        run_id: str,
        result: dict[str, Any],
    ) -> "None":
        """Publish the final result to the Redis pub/sub channel.

        Args:
            run_id: UUID of the optimization run.
            result: Serialised OptimizationRunDetail dict.
        """
        channel = f"run:{run_id}:progress"
        payload = json.dumps(
            {
                "type": "result",
                "run_id": run_id,
                "result": result,
            }
        )
        try:
            self.redis_client.publish(channel, payload)
        except Exception as exc:
            logger.warning(
                "Failed to publish result",
                extra={"run_id": run_id, "error": str(exc)},
            )

    def publish_error(
        self,
        run_id: str,
        error_code: str,
        message: str,
    ) -> "None":
        """Publish an error event to the Redis pub/sub channel.

        Args:
            run_id: UUID of the optimization run.
            error_code: Machine-readable error code (e.g. "AGENT_EXECUTION_ERROR").
            message: Human-readable error description.
        """
        channel = f"run:{run_id}:progress"
        payload = json.dumps(
            {
                "type": "error",
                "run_id": run_id,
                "error_code": error_code,
                "message": message,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        try:
            self.redis_client.publish(channel, payload)
        except Exception as exc:
            logger.warning(
                "Failed to publish error",
                extra={"run_id": run_id, "error": str(exc)},
            )


@celery_app.task(
    bind=True,
    base=OptimizationTask,
    name="app.workers.tasks.run_optimization_task",
    max_retries=3,
    acks_late=True,
    # Do not retry on SoftTimeLimitExceeded — timeout is deterministic
    # and retrying would just time out again.
    throws=(SoftTimeLimitExceeded,),
)
def run_optimization_task(
    self: OptimizationTask,
    run_id: str,
    request_dict: dict[str, Any],
) -> dict[str, Any]:
    """Execute the full portfolio optimization pipeline.

    This task:
    1. Transitions the DB record from ``pending`` to ``running``
    2. Runs the LangGraph agent graph (all 6 nodes)
    3. Publishes progress events at each node via Redis pub/sub
    4. Persists the final result with ``status="completed"`` (or ``"failed"``)
    5. Publishes the final result/error event

    Retry policy:
        - Transient failures (network errors, DB timeouts): retry up to 3
          times with exponential backoff (30s, 60s, 120s).
        - ``SoftTimeLimitExceeded``: no retry; mark as failed immediately.

    Args:
        run_id: UUID of the optimization run.
        request_dict: Serialised OptimizationRequest dict.

    Returns:
        The serialised OptimizationRunDetail dict.

    Raises:
        SoftTimeLimitExceeded: Re-raised after marking the run as failed.
        Exception: Re-raised after scheduling a retry (or after max retries).
    """
    logger.info(f"Starting optimization run {run_id} (attempt {self.request.retries + 1})")

    try:
        # Run the async agent graph in a new event loop.
        # Celery workers are synchronous; we bridge to async here.
        result = asyncio.run(
            _execute_optimization(self, run_id, request_dict)
        )
        return result

    except SoftTimeLimitExceeded:
        # Quantum job exceeded the configured timeout.
        # Mark as failed and do NOT retry — the timeout is deterministic.
        logger.error(
            f"Optimization run {run_id} timed out (SoftTimeLimitExceeded)"
        )
        error_message = (
            "Quantum optimization timed out. "
            "Try reducing the number of assets or disabling quantum optimization."
        )
        self.publish_error(
            run_id=run_id,
            error_code="QUANTUM_TIMEOUT",
            message=error_message,
        )
        asyncio.run(_persist_failure(run_id, error_message))
        # Re-raise so Celery marks the task as FAILURE (not RETRY)
        raise

    except Exception as exc:
        logger.error(
            f"Optimization run {run_id} failed on attempt "
            f"{self.request.retries + 1}/{self.max_retries}: {exc}",
            exc_info=True,
        )

        if self.request.retries < self.max_retries:
            # Exponential backoff: 30s, 60s, 120s
            countdown = _RETRY_BASE_DELAY_SECONDS * (2 ** self.request.retries)
            logger.info(
                f"Scheduling retry {self.request.retries + 1}/{self.max_retries} "
                f"for run {run_id} in {countdown}s"
            )
            # Publish a transient error event so the frontend knows a retry is happening
            self.publish_progress(
                run_id=run_id,
                node="worker",
                status="retrying",
                message=(
                    f"Transient error encountered. Retrying in {countdown}s "
                    f"(attempt {self.request.retries + 1}/{self.max_retries})…"
                ),
            )
            raise self.retry(exc=exc, countdown=countdown)
        else:
            # All retries exhausted — mark as permanently failed
            logger.error(
                f"Optimization run {run_id} permanently failed after "
                f"{self.max_retries} retries"
            )
            self.publish_error(
                run_id=run_id,
                error_code="AGENT_EXECUTION_ERROR",
                message=str(exc),
            )
            asyncio.run(_persist_failure(run_id, str(exc)))
            raise


async def _execute_optimization(
    task: OptimizationTask,
    run_id: str,
    request_dict: dict[str, Any],
) -> dict[str, Any]:
    """Async implementation of the optimization pipeline.

    Imports the agent graph lazily to avoid circular imports and to
    allow the agent layer to be developed independently.

    Args:
        task: The bound Celery task instance (for progress publishing).
        run_id: UUID of the optimization run.
        request_dict: Serialised OptimizationRequest dict.

    Returns:
        Serialised OptimizationRunDetail dict.
    """
    from sqlalchemy import select  # noqa: PLC0415

    from app.db.models import OptimizationRun  # noqa: PLC0415
    from app.db.session import AsyncSessionLocal  # noqa: PLC0415
    from app.schemas.requests import OptimizationRequest  # noqa: PLC0415

    request = OptimizationRequest.model_validate(request_dict)

    # ── Transition run record: pending → running ───────────────────────────
    async with AsyncSessionLocal() as session:
        result_obj = await session.execute(
            select(OptimizationRun).where(OptimizationRun.run_id == run_id)
        )
        run = result_obj.scalar_one_or_none()

        if run is None:
            # The API layer should have created the record before dispatching
            # the task. If it's missing, create it now as a safety net.
            logger.warning(
                f"Run record {run_id} not found in DB; creating it now"
            )
            run = OptimizationRun(
                run_id=run_id,
                status="running",
                tickers=request.tickers,
                budget=request.budget,
                request_params=request_dict,
            )
            session.add(run)
        else:
            run.mark_running()

        await session.commit()

    logger.info(f"Run {run_id} transitioned to status=running")

    # ── Publish initial progress event ────────────────────────────────────
    task.publish_progress(
        run_id=run_id,
        node="data_fetch",
        status="started",
        message="Fetching market data…",
    )

    # ── Execute agent graph ───────────────────────────────────────────────
    from app.agents.graph import run_agent_graph  # noqa: PLC0415

    result_detail = await run_agent_graph(
        run_id=run_id,
        request=request,
        progress_callback=lambda node, status, msg: task.publish_progress(
            run_id=run_id,
            node=node,
            status=status,
            message=msg,
        ),
    )

    # ── Persist completed result ──────────────────────────────────────────
    await _persist_completed_run(run_id, result_detail)

    result_dict = result_detail.model_dump(mode="json")
    task.publish_result(run_id=run_id, result=result_dict)

    logger.info(f"Optimization run {run_id} completed successfully")
    return result_dict


async def _persist_completed_run(
    run_id: str,
    result_detail: Any,
) -> "None":
    """Persist a successfully completed run to the database.

    Populates all result fields and transitions the status to ``"completed"``.

    Args:
        run_id: UUID of the optimization run.
        result_detail: ``OptimizationRunDetail`` Pydantic model instance.
    """
    from sqlalchemy import select  # noqa: PLC0415

    from app.db.models import OptimizationRun  # noqa: PLC0415
    from app.db.session import AsyncSessionLocal  # noqa: PLC0415

    try:
        async with AsyncSessionLocal() as session:
            result_obj = await session.execute(
                select(OptimizationRun).where(OptimizationRun.run_id == run_id)
            )
            run = result_obj.scalar_one_or_none()

            if run is None:
                logger.error(
                    f"Cannot persist completed run {run_id}: record not found"
                )
                return

            run.mark_completed(completed_at=datetime.now(UTC))

            if result_detail.classical_result:
                run.classical_result = result_detail.classical_result.model_dump()
                run.classical_sharpe = result_detail.classical_result.metrics.sharpe_ratio

            if result_detail.quantum_result:
                run.quantum_result = result_detail.quantum_result.model_dump()
                # Prefer QAOA Sharpe; fall back to VQE
                if result_detail.quantum_result.qaoa:
                    run.quantum_sharpe = (
                        result_detail.quantum_result.qaoa.metrics.sharpe_ratio
                    )
                elif result_detail.quantum_result.vqe:
                    run.quantum_sharpe = (
                        result_detail.quantum_result.vqe.metrics.sharpe_ratio
                    )

            if result_detail.comparison:
                run.comparison = result_detail.comparison.model_dump()

            # Persist the optional efficient-frontier bundle.  When the
            # request did not enable the sweep this attribute stays None
            # and the DB column remains null — preserving back-compat
            # with rows created before migration 002.
            if result_detail.frontier_report is not None:
                run.frontier_report = result_detail.frontier_report.model_dump()

            run.llm_explanation = result_detail.llm_explanation

            await session.commit()
            logger.info(f"Run {run_id} persisted as completed")

    except Exception as exc:
        logger.error(
            f"Failed to persist completed run {run_id}: {exc}",
            exc_info=True,
        )
        # Do not re-raise — the result was already published to Redis.
        # A DB persistence failure should not cause the task to retry.


async def _persist_failure(run_id: str, error_message: str) -> "None":
    """Persist a failed run status to the database.

    Transitions the run to ``status="failed"`` and records the error message.

    Args:
        run_id: UUID of the optimization run.
        error_message: Human-readable description of the failure.
    """
    try:
        from sqlalchemy import select  # noqa: PLC0415

        from app.db.models import OptimizationRun  # noqa: PLC0415
        from app.db.session import AsyncSessionLocal  # noqa: PLC0415

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(OptimizationRun).where(OptimizationRun.run_id == run_id)
            )
            run = result.scalar_one_or_none()

            if run is None:
                logger.warning(
                    f"Cannot persist failure for run {run_id}: record not found"
                )
                return

            run.mark_failed(
                error_message=error_message,
                completed_at=datetime.now(UTC),
            )
            await session.commit()
            logger.info(f"Run {run_id} persisted as failed")

    except Exception as exc:
        logger.error(
            f"Failed to persist failure for run {run_id}: {exc}",
            exc_info=True,
        )


async def _update_run_status(run_id: str, status: str) -> "None":
    """Update only the status field of a run record.

    Lightweight helper for intermediate status transitions (e.g., pending → running).

    Args:
        run_id: UUID of the optimization run.
        status: New status value: "pending" | "running" | "completed" | "failed".
    """
    try:
        from sqlalchemy import select  # noqa: PLC0415

        from app.db.models import OptimizationRun  # noqa: PLC0415
        from app.db.session import AsyncSessionLocal  # noqa: PLC0415

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(OptimizationRun).where(OptimizationRun.run_id == run_id)
            )
            run = result.scalar_one_or_none()

            if run is None:
                logger.warning(
                    f"Cannot update status for run {run_id}: record not found"
                )
                return

            run.status = status
            await session.commit()

    except Exception as exc:
        logger.error(
            f"Failed to update status for run {run_id}: {exc}",
            exc_info=True,
        )
