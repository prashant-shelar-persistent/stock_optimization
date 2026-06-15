"""Portfolio Optimizer — Celery workers package.

Public API:
    celery_app — The configured Celery application instance.
                 Import this to dispatch tasks or inspect worker state.

    run_optimization_task — The Celery task that executes the full
                            LangGraph agent pipeline for a single
                            optimization run.

Usage::

    from app.workers import celery_app
    from app.workers import run_optimization_task

    # Dispatch a task
    run_optimization_task.apply_async(
        kwargs={"run_id": run_id, "request_dict": request_dict},
        task_id=run_id,
        queue="quantum",
    )

    # Inspect worker health
    result = celery_app.control.ping(timeout=2.0)
"""

from __future__ import annotations

from app.workers.celery_app import celery_app
from app.workers.tasks import run_optimization_task

__all__ = [
    "celery_app",
    "run_optimization_task",
]
