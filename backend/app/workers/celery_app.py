"""Celery application factory.

Creates and configures the Celery application instance used by both
the worker process and the FastAPI app (for task dispatch).

The Celery app is a module-level singleton. Import it as::

    from app.workers.celery_app import celery_app

Queue design:
    default  — Classical-only optimization runs (fast, ~5–15 seconds)
    quantum  — Runs that include QAOA/VQE (slow, up to QUANTUM_TIMEOUT_SECONDS)

Both queues are consumed by the same worker process (``--queues=quantum,default``).
The ``quantum`` queue has lower concurrency to prevent resource exhaustion from
simultaneous quantum simulations.
"""

from __future__ import annotations

from celery import Celery
from celery.signals import worker_ready, worker_shutdown

from app.core.config import get_settings
from app.core.logging import get_logger


logger = get_logger(__name__)
_settings = get_settings()

celery_app = Celery(
    "portfolio_optimizer",
    broker=_settings.CELERY_BROKER_URL,
    backend=_settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

# ── Celery configuration ──────────────────────────────────────────────────────

celery_app.conf.update(
    # ── Serialisation ──────────────────────────────────────────────────────
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # ── Timezone ───────────────────────────────────────────────────────────
    timezone="UTC",
    enable_utc=True,

    # ── Task routing ───────────────────────────────────────────────────────
    # Quantum runs go to the ``quantum`` queue; classical-only to ``default``.
    # The routing key is set in ``optimize.py`` via ``apply_async(queue=...)``.
    task_routes={
        "app.workers.tasks.run_optimization_task": {
            "queue": "default",
        },
    },
    task_queues={
        "default": {"exchange": "default", "routing_key": "default"},
        "quantum": {"exchange": "quantum", "routing_key": "quantum"},
    },
    task_default_queue="default",

    # ── Result expiry ──────────────────────────────────────────────────────
    # Keep Celery task results in Redis for 24 hours. The authoritative run
    # record lives in PostgreSQL; the Celery result is a secondary cache.
    result_expires=86400,

    # ── Task time limits ───────────────────────────────────────────────────
    # soft_time_limit fires SoftTimeLimitExceeded (catchable) to allow clean
    # shutdown. hard time_limit sends SIGKILL after an additional 60 seconds.
    task_soft_time_limit=_settings.QUANTUM_TIMEOUT_SECONDS + 60,
    task_time_limit=_settings.QUANTUM_TIMEOUT_SECONDS + 120,

    # ── Reliability ────────────────────────────────────────────────────────
    # acks_late=True: acknowledge the message only after the task completes,
    # so that if the worker crashes mid-task the message is re-queued.
    # reject_on_worker_lost=True: if the worker process is killed, the task
    # is rejected (not acknowledged) and re-queued for another worker.
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # ── Worker settings ────────────────────────────────────────────────────
    # prefetch_multiplier=1: fetch only one task at a time per worker process.
    # Quantum jobs are CPU-intensive; fetching multiple tasks would cause
    # resource contention and unpredictable timeouts.
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,

    # ── Task state tracking ────────────────────────────────────────────────
    # task_track_started=True: Celery updates the task state to STARTED when
    # a worker picks it up. This allows the API to distinguish between
    # "queued but not started" (PENDING) and "actively running" (STARTED).
    task_track_started=True,

    # ── Beat schedule ──────────────────────────────────────────────────────
    # Placeholder for future scheduled tasks (e.g., daily cache warm-up,
    # stale run cleanup). Empty dict means no scheduled tasks are active.
    beat_schedule={},
)


# ── Worker lifecycle signals ──────────────────────────────────────────────────


@worker_ready.connect
def on_worker_ready(**kwargs: object) -> None:  # type: ignore[misc]
    """Log when the Celery worker is ready to accept tasks."""
    logger.info(
        "celery_worker_ready",
        broker=_settings.CELERY_BROKER_URL,
        queues=["quantum", "default"],
    )


@worker_shutdown.connect
def on_worker_shutdown(**kwargs: object) -> None:  # type: ignore[misc]
    """Log when the Celery worker is shutting down."""
    logger.info("celery_worker_shutdown")
