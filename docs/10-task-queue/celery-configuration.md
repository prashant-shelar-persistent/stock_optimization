# Celery Configuration

The Portfolio Optimizer uses [Celery](https://docs.celeryq.dev/) as its distributed task queue to execute long-running optimization pipelines asynchronously. This page documents the Celery application factory, all configuration knobs, environment variables, and the beat scheduler setup.

The Celery application is defined in `backend/app/workers/celery_app.py` and is a module-level singleton imported by both the FastAPI application (for task dispatch) and the worker processes (for task execution).

## Application Factory

```python
# backend/app/workers/celery_app.py
from celery import Celery
from app.core.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "portfolio_optimizer",
    broker=_settings.CELERY_BROKER_URL,
    backend=_settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)
```

The `include` list tells Celery where to auto-discover task definitions. Only `app.workers.tasks` is registered — all optimization logic lives in that single module.

## Redis Database Allocation

Redis is used for three distinct purposes, each on a separate logical database to prevent key collisions:

| Redis DB | URL (default) | Purpose |
|----------|---------------|---------|
| `db 0` | `redis://localhost:6379/0` | Application cache (market data, sector classifications) |
| `db 1` | `redis://localhost:6379/1` | **Celery broker** — task message queue |
| `db 2` | `redis://localhost:6379/2` | **Celery result backend** — task state and return values |

These are configured via environment variables:

```bash
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
```

> **Why separate databases?** Using distinct Redis databases prevents Celery's internal keys (e.g., `celery-task-meta-*`) from colliding with application cache keys. It also allows independent `FLUSHDB` operations during development without wiping broker messages.

## Serialization Settings

All task arguments and results are serialized as JSON:

```python
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)
```

JSON serialization is chosen over the default `pickle` for security (no arbitrary code execution via crafted payloads) and interoperability. Task arguments (`run_id`, `request_dict`) are plain Python dicts and strings, so JSON is sufficient.

## Task Routing Configuration

Two queues are defined to separate fast classical runs from slow quantum runs:

```python
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
```

The static route in `task_routes` sets the fallback queue to `default`. At dispatch time, `optimize.py` overrides this per-request:

```python
# backend/app/api/v1/optimize.py
run_optimization_task.apply_async(
    kwargs={"run_id": run_id, "request_dict": request.model_dump(mode="json")},
    task_id=run_id,
    queue="quantum" if request.run_quantum else "default",
)
```

This means the routing decision is made at the API layer based on the `run_quantum` flag in the request body. See [Queue Routing](queue-routing.md) for the full rationale.

## Reliability Settings

### `acks_late=True`

```python
task_acks_late=True,
task_reject_on_worker_lost=True,
```

With `acks_late=True`, Celery acknowledges the broker message **only after** the task function returns (success or failure). If the worker process is killed mid-task, the message is **not** acknowledged and Redis re-queues it for another worker.

`task_reject_on_worker_lost=True` extends this: if the OS kills the worker process (e.g., OOM killer), the task is explicitly rejected rather than silently dropped.

> **Trade-off**: `acks_late` means a task can be executed more than once if the worker crashes after completing the work but before acknowledging. The task implementation is designed to be idempotent — re-running a completed task will overwrite the DB record with the same result.

### `worker_prefetch_multiplier=1`

```python
worker_prefetch_multiplier=1,
```

Each worker process fetches **exactly one task** at a time from the broker. Without this setting, Celery's default prefetch of 4 would cause a worker to hold multiple tasks in memory simultaneously. For CPU-intensive quantum simulations, this would cause resource contention and unpredictable timeouts.

Combined with `--concurrency=N`, this gives `N` truly-parallel tasks with no hidden queuing inside the worker.

### `worker_max_tasks_per_child=100`

```python
worker_max_tasks_per_child=100,
```

Each prefork child process is recycled after executing 100 tasks. This prevents memory leaks from accumulating over long worker lifetimes, particularly important for quantum simulation libraries that may not release all memory between runs.

## Time Limits

```python
task_soft_time_limit=_settings.QUANTUM_TIMEOUT_SECONDS + 60,
task_time_limit=_settings.QUANTUM_TIMEOUT_SECONDS + 120,
```

Two time limits are configured:

| Limit | Value | Behavior |
|-------|-------|----------|
| `task_soft_time_limit` | `QUANTUM_TIMEOUT_SECONDS + 60` | Raises `SoftTimeLimitExceeded` (catchable) |
| `task_time_limit` | `QUANTUM_TIMEOUT_SECONDS + 120` | Sends `SIGKILL` to the worker process |

The soft limit fires first, giving the task 60 seconds to clean up (publish an error event, persist the failure to the database). If the task ignores the soft limit, the hard limit kills the process after an additional 60 seconds.

`QUANTUM_TIMEOUT_SECONDS` defaults to `60` and can be raised up to `600` for larger quantum circuits.

## Task State Tracking

```python
task_track_started=True,
```

When a worker picks up a task, Celery immediately updates the task state to `STARTED` in the result backend. This allows the API to distinguish between:

- `PENDING` — task is queued but no worker has picked it up yet
- `STARTED` — a worker is actively executing the task
- `SUCCESS` / `FAILURE` — terminal states

## Result Expiry

```python
result_expires=86400,  # 24 hours
```

Celery task results are kept in Redis for 24 hours. The authoritative run record lives in PostgreSQL; the Celery result is a secondary cache used for quick status lookups. After 24 hours, Redis automatically evicts the result key.

## Concurrency Environment Variables

Worker concurrency is controlled at container startup via environment variables, without requiring a code change or image rebuild:

| Variable | Default | Description |
|----------|---------|-------------|
| `CELERY_DEFAULT_CONCURRENCY` | `4` | Number of parallel prefork processes for the `default` (classical) worker |
| `CELERY_QUANTUM_CONCURRENCY` | `2` | Number of parallel prefork processes for the `quantum` worker |

These are passed to the `--concurrency` flag in the Docker Compose command:

```yaml
# docker-compose.yml
worker:
  command: >
    celery -A app.workers.celery_app worker
    --concurrency=${CELERY_DEFAULT_CONCURRENCY:-4}
    --queues=default
    -n default-worker@%h

worker-quantum:
  command: >
    celery -A app.workers.celery_app worker
    --concurrency=${CELERY_QUANTUM_CONCURRENCY:-2}
    --queues=quantum
    -n quantum-worker@%h
```

To scale up classical throughput without restarting:

```bash
# Restart only the default worker with higher concurrency
CELERY_DEFAULT_CONCURRENCY=8 docker compose up -d --no-deps worker
```

## Beat Scheduler Setup

The `celery-beat` service runs the Celery periodic task scheduler:

```yaml
# docker-compose.yml
celery-beat:
  command: >
    celery -A app.workers.celery_app beat
    --loglevel=info
    --scheduler celery.beat:PersistentScheduler
```

The `PersistentScheduler` stores the schedule state in `backend/celerybeat-schedule` (a shelve file) so that beat does not re-fire tasks that already ran when it restarts.

The current beat schedule is empty:

```python
beat_schedule={},
```

This is a placeholder for future periodic tasks such as:
- Daily market data cache warm-up
- Stale run cleanup (purging `pending` runs older than 24 hours)
- Scheduled portfolio rebalancing alerts

> **Important**: Only run **one** `celery-beat` instance at a time. Running multiple beat processes against the same schedule file causes duplicate task firing.

## Worker Lifecycle Signals

The Celery app registers two signal handlers for observability:

```python
@worker_ready.connect
def on_worker_ready(**kwargs):
    logger.info(
        "celery_worker_ready",
        broker=_settings.CELERY_BROKER_URL,
        queues=["quantum", "default"],
    )

@worker_shutdown.connect
def on_worker_shutdown(**kwargs):
    logger.info("celery_worker_shutdown")
```

These emit structured log events when a worker comes online or shuts down, making it easy to detect worker restarts in log aggregation tools.

## Complete Configuration Reference

```python
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task routing
    task_routes={"app.workers.tasks.run_optimization_task": {"queue": "default"}},
    task_queues={
        "default": {"exchange": "default", "routing_key": "default"},
        "quantum": {"exchange": "quantum", "routing_key": "quantum"},
    },
    task_default_queue="default",

    # Result expiry
    result_expires=86400,

    # Time limits (based on QUANTUM_TIMEOUT_SECONDS)
    task_soft_time_limit=QUANTUM_TIMEOUT_SECONDS + 60,
    task_time_limit=QUANTUM_TIMEOUT_SECONDS + 120,

    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,

    # State tracking
    task_track_started=True,

    # Beat schedule (empty — placeholder for future tasks)
    beat_schedule={},
)
```

## Related Pages

- [Optimization Task](optimization-task.md) — `run_optimization_task` implementation, retry policy, and lifecycle
- [Queue Routing](queue-routing.md) — `default` vs `quantum` queue design and worker separation
- [Progress Events](progress-events.md) — Redis pub/sub channel naming and message schemas
- [Environment Variables](../01-getting-started/environment-variables.md) — Full list of configurable settings
