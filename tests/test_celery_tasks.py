"""Integration tests for Celery task: run_optimization_task.

Tests cover:
1. OptimizationTask.publish_progress publishes correct JSON to Redis channel
2. OptimizationTask.publish_result publishes correct JSON to Redis channel
3. OptimizationTask.publish_error publishes correct JSON to Redis channel
4. publish_progress silently swallows Redis exceptions (no crash)
5. publish_result silently swallows Redis exceptions (no crash)
6. publish_error silently swallows Redis exceptions (no crash)
7. Progress message has required fields: type, run_id, node, status, message, timestamp
8. Result message has required fields: type, run_id, result
9. Error message has required fields: type, run_id, error_code, message, timestamp
10. Redis channel name follows pattern: run:{run_id}:progress
11. run_optimization_task task is registered in Celery app
12. Task has correct name: app.workers.tasks.run_optimization_task
13. Task has max_retries=3
14. Task has acks_late=True
"""

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.workers.celery_app import celery_app
from app.workers.tasks import OptimizationTask


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task_instance() -> OptimizationTask:
    """Create an OptimizationTask instance with a mocked Redis client."""
    task = OptimizationTask()
    task._redis_client = MagicMock()
    task._redis_client.publish = MagicMock(return_value=1)
    return task


# ---------------------------------------------------------------------------
# publish_progress tests
# ---------------------------------------------------------------------------


def test_publish_progress_publishes_to_correct_channel() -> None:
    """publish_progress publishes to run:{run_id}:progress channel."""
    task = _make_task_instance()
    run_id = str(uuid.uuid4())

    task.publish_progress(
        run_id=run_id,
        node="data_fetch",
        status="started",
        message="Fetching market data…",
    )

    task._redis_client.publish.assert_called_once()
    channel, payload = task._redis_client.publish.call_args[0]
    assert channel == f"run:{run_id}:progress"


def test_publish_progress_message_has_required_fields() -> None:
    """Progress message JSON has all required fields."""
    task = _make_task_instance()
    run_id = str(uuid.uuid4())

    task.publish_progress(
        run_id=run_id,
        node="classical_optimization",
        status="completed",
        message="Classical optimization complete.",
    )

    _, payload = task._redis_client.publish.call_args[0]
    msg = json.loads(payload)

    assert msg["type"] == "progress"
    assert msg["run_id"] == run_id
    assert msg["node"] == "classical_optimization"
    assert msg["status"] == "completed"
    assert msg["message"] == "Classical optimization complete."
    assert "timestamp" in msg
    assert isinstance(msg["timestamp"], str)


def test_publish_progress_swallows_redis_exception() -> None:
    """publish_progress does not raise when Redis publish fails."""
    task = _make_task_instance()
    task._redis_client.publish.side_effect = ConnectionError("Redis unavailable")
    run_id = str(uuid.uuid4())

    # Should not raise
    task.publish_progress(
        run_id=run_id,
        node="data_fetch",
        status="started",
        message="Fetching…",
    )


# ---------------------------------------------------------------------------
# publish_result tests
# ---------------------------------------------------------------------------


def test_publish_result_publishes_to_correct_channel() -> None:
    """publish_result publishes to run:{run_id}:progress channel."""
    task = _make_task_instance()
    run_id = str(uuid.uuid4())
    result = {"run_id": run_id, "status": "completed"}

    task.publish_result(run_id=run_id, result=result)

    task._redis_client.publish.assert_called_once()
    channel, payload = task._redis_client.publish.call_args[0]
    assert channel == f"run:{run_id}:progress"


def test_publish_result_message_has_required_fields() -> None:
    """Result message JSON has type, run_id, and result fields."""
    task = _make_task_instance()
    run_id = str(uuid.uuid4())
    result_data = {"run_id": run_id, "status": "completed", "classical_sharpe": 1.5}

    task.publish_result(run_id=run_id, result=result_data)

    _, payload = task._redis_client.publish.call_args[0]
    msg = json.loads(payload)

    assert msg["type"] == "result"
    assert msg["run_id"] == run_id
    assert "result" in msg
    assert msg["result"]["classical_sharpe"] == 1.5


def test_publish_result_swallows_redis_exception() -> None:
    """publish_result does not raise when Redis publish fails."""
    task = _make_task_instance()
    task._redis_client.publish.side_effect = ConnectionError("Redis unavailable")
    run_id = str(uuid.uuid4())

    # Should not raise
    task.publish_result(run_id=run_id, result={"status": "completed"})


# ---------------------------------------------------------------------------
# publish_error tests
# ---------------------------------------------------------------------------


def test_publish_error_publishes_to_correct_channel() -> None:
    """publish_error publishes to run:{run_id}:progress channel."""
    task = _make_task_instance()
    run_id = str(uuid.uuid4())

    task.publish_error(
        run_id=run_id,
        error_code="AGENT_EXECUTION_ERROR",
        message="Something went wrong.",
    )

    task._redis_client.publish.assert_called_once()
    channel, payload = task._redis_client.publish.call_args[0]
    assert channel == f"run:{run_id}:progress"


def test_publish_error_message_has_required_fields() -> None:
    """Error message JSON has type, run_id, error_code, message, timestamp."""
    task = _make_task_instance()
    run_id = str(uuid.uuid4())

    task.publish_error(
        run_id=run_id,
        error_code="QUANTUM_TIMEOUT",
        message="Quantum optimization timed out.",
    )

    _, payload = task._redis_client.publish.call_args[0]
    msg = json.loads(payload)

    assert msg["type"] == "error"
    assert msg["run_id"] == run_id
    assert msg["error_code"] == "QUANTUM_TIMEOUT"
    assert msg["message"] == "Quantum optimization timed out."
    assert "timestamp" in msg
    assert isinstance(msg["timestamp"], str)


def test_publish_error_swallows_redis_exception() -> None:
    """publish_error does not raise when Redis publish fails."""
    task = _make_task_instance()
    task._redis_client.publish.side_effect = ConnectionError("Redis unavailable")
    run_id = str(uuid.uuid4())

    # Should not raise
    task.publish_error(
        run_id=run_id,
        error_code="AGENT_EXECUTION_ERROR",
        message="Error occurred.",
    )


# ---------------------------------------------------------------------------
# Redis channel naming tests
# ---------------------------------------------------------------------------


def test_progress_channel_name_format() -> None:
    """Channel name follows the pattern run:{run_id}:progress."""
    task = _make_task_instance()
    run_id = "abc123-def456"

    task.publish_progress(
        run_id=run_id,
        node="comparison",
        status="started",
        message="Comparing results…",
    )

    channel, _ = task._redis_client.publish.call_args[0]
    assert channel == "run:abc123-def456:progress"


# ---------------------------------------------------------------------------
# Celery task registration tests
# ---------------------------------------------------------------------------


def test_task_is_registered_in_celery_app() -> None:
    """run_optimization_task is registered in the Celery app."""
    task_name = "app.workers.tasks.run_optimization_task"
    assert task_name in celery_app.tasks, (
        f"Task '{task_name}' not found in celery_app.tasks. "
        f"Registered tasks: {list(celery_app.tasks.keys())}"
    )


def test_task_has_correct_name() -> None:
    """Task name matches the expected fully-qualified name."""
    from app.workers.tasks import run_optimization_task

    assert run_optimization_task.name == "app.workers.tasks.run_optimization_task"


def test_task_has_max_retries_3() -> None:
    """Task is configured with max_retries=3."""
    from app.workers.tasks import run_optimization_task

    assert run_optimization_task.max_retries == 3


def test_task_has_acks_late_true() -> None:
    """Task is configured with acks_late=True for reliability."""
    from app.workers.tasks import run_optimization_task

    assert run_optimization_task.acks_late is True


# ---------------------------------------------------------------------------
# Celery app configuration tests
# ---------------------------------------------------------------------------


def test_celery_app_has_default_queue() -> None:
    """Celery app has 'default' queue configured."""
    queues = celery_app.conf.task_queues
    assert "default" in queues


def test_celery_app_has_quantum_queue() -> None:
    """Celery app has 'quantum' queue configured."""
    queues = celery_app.conf.task_queues
    assert "quantum" in queues


def test_celery_app_uses_json_serializer() -> None:
    """Celery app uses JSON serializer for tasks and results."""
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"


def test_celery_app_timezone_is_utc() -> None:
    """Celery app is configured to use UTC timezone."""
    assert celery_app.conf.timezone == "UTC"
    assert celery_app.conf.enable_utc is True


def test_celery_app_prefetch_multiplier_is_1() -> None:
    """Worker prefetch multiplier is 1 to prevent resource contention."""
    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_celery_app_acks_late_is_true() -> None:
    """Global acks_late is True for reliability."""
    assert celery_app.conf.task_acks_late is True


def test_celery_app_reject_on_worker_lost_is_true() -> None:
    """reject_on_worker_lost is True so crashed tasks are re-queued."""
    assert celery_app.conf.task_reject_on_worker_lost is True


# ---------------------------------------------------------------------------
# OptimizationTask.redis_client lazy init tests
# ---------------------------------------------------------------------------


def test_redis_client_lazy_init() -> None:
    """redis_client property creates client on first access."""
    task = OptimizationTask()
    assert task._redis_client is None

    with patch("app.workers.tasks.redis.from_url") as mock_from_url:
        mock_client = MagicMock()
        mock_from_url.return_value = mock_client

        client = task.redis_client

    assert client is mock_client
    mock_from_url.assert_called_once()


def test_redis_client_reused_on_second_access() -> None:
    """redis_client property returns the same client on subsequent calls."""
    task = OptimizationTask()

    with patch("app.workers.tasks.redis.from_url") as mock_from_url:
        mock_client = MagicMock()
        mock_from_url.return_value = mock_client

        client1 = task.redis_client
        client2 = task.redis_client

    # Should only be called once — client is cached
    mock_from_url.assert_called_once()
    assert client1 is client2
