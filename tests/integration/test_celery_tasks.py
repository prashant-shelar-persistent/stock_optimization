"""Integration tests for Celery task: run_optimization_task.

Tests cover:
1.  publish_progress publishes to correct Redis channel (run:{run_id}:progress)
2.  publish_progress message has required fields: type, run_id, node, status, message, timestamp
3.  publish_progress silently swallows Redis exceptions
4.  publish_result publishes to correct Redis channel
5.  publish_result message has required fields: type, run_id, result
6.  publish_result silently swallows Redis exceptions
7.  publish_error publishes to correct Redis channel
8.  publish_error message has required fields: type, run_id, error_code, message, timestamp
9.  publish_error silently swallows Redis exceptions
10. Channel name follows pattern: run:{run_id}:progress
11. run_optimization_task is registered in Celery app
12. Task has correct fully-qualified name
13. Task has max_retries=3
14. Task has acks_late=True
15. Celery app has 'default' queue configured
16. Celery app has 'quantum' queue configured
17. Celery app uses JSON serializer
18. Celery app timezone is UTC
19. Worker prefetch multiplier is 1
20. redis_client property creates client lazily on first access
21. redis_client property reuses the same client on subsequent calls
22. publish_progress timestamp is a valid ISO-8601 string
23. publish_error timestamp is a valid ISO-8601 string
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
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


def _get_published_message(task: OptimizationTask) -> dict:
    """Extract and parse the JSON payload from the last publish call."""
    _, payload = task._redis_client.publish.call_args[0]
    return json.loads(payload)


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
    channel, _ = task._redis_client.publish.call_args[0]
    assert channel == f"run:{run_id}:progress"


def test_publish_progress_message_has_required_fields() -> None:
    """Progress message JSON has all required fields with correct values."""
    task = _make_task_instance()
    run_id = str(uuid.uuid4())

    task.publish_progress(
        run_id=run_id,
        node="classical_optimization",
        status="completed",
        message="Classical optimization complete.",
    )

    msg = _get_published_message(task)

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

    # Must not raise
    task.publish_progress(
        run_id=run_id,
        node="data_fetch",
        status="started",
        message="Fetching…",
    )


def test_publish_progress_timestamp_is_iso8601() -> None:
    """publish_progress timestamp is a valid ISO-8601 datetime string."""
    task = _make_task_instance()
    run_id = str(uuid.uuid4())

    task.publish_progress(
        run_id=run_id,
        node="comparison",
        status="started",
        message="Comparing results…",
    )

    msg = _get_published_message(task)
    timestamp = msg["timestamp"]
    # Must not raise — must be parseable as ISO-8601
    parsed = datetime.fromisoformat(timestamp)
    assert parsed is not None


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
    channel, _ = task._redis_client.publish.call_args[0]
    assert channel == f"run:{run_id}:progress"


def test_publish_result_message_has_required_fields() -> None:
    """Result message JSON has type, run_id, and result fields."""
    task = _make_task_instance()
    run_id = str(uuid.uuid4())
    result_data = {
        "run_id": run_id,
        "status": "completed",
        "classical_sharpe": 1.5,
    }

    task.publish_result(run_id=run_id, result=result_data)

    msg = _get_published_message(task)

    assert msg["type"] == "result"
    assert msg["run_id"] == run_id
    assert "result" in msg
    assert msg["result"]["classical_sharpe"] == 1.5
    assert msg["result"]["status"] == "completed"


def test_publish_result_swallows_redis_exception() -> None:
    """publish_result does not raise when Redis publish fails."""
    task = _make_task_instance()
    task._redis_client.publish.side_effect = ConnectionError("Redis unavailable")
    run_id = str(uuid.uuid4())

    # Must not raise
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
    channel, _ = task._redis_client.publish.call_args[0]
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

    msg = _get_published_message(task)

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

    # Must not raise
    task.publish_error(
        run_id=run_id,
        error_code="AGENT_EXECUTION_ERROR",
        message="Error occurred.",
    )


def test_publish_error_timestamp_is_iso8601() -> None:
    """publish_error timestamp is a valid ISO-8601 datetime string."""
    task = _make_task_instance()
    run_id = str(uuid.uuid4())

    task.publish_error(
        run_id=run_id,
        error_code="DATA_FETCH_ERROR",
        message="Failed to fetch data.",
    )

    msg = _get_published_message(task)
    timestamp = msg["timestamp"]
    # Must not raise — must be parseable as ISO-8601
    parsed = datetime.fromisoformat(timestamp)
    assert parsed is not None


# ---------------------------------------------------------------------------
# Channel naming
# ---------------------------------------------------------------------------


def test_progress_channel_name_format() -> None:
    """Channel name follows the exact pattern run:{run_id}:progress."""
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


def test_result_channel_name_format() -> None:
    """Result channel name follows the exact pattern run:{run_id}:progress."""
    task = _make_task_instance()
    run_id = "xyz-789"

    task.publish_result(run_id=run_id, result={"status": "completed"})

    channel, _ = task._redis_client.publish.call_args[0]
    assert channel == "run:xyz-789:progress"


def test_error_channel_name_format() -> None:
    """Error channel name follows the exact pattern run:{run_id}:progress."""
    task = _make_task_instance()
    run_id = "err-run-001"

    task.publish_error(
        run_id=run_id,
        error_code="INTERNAL_ERROR",
        message="Unexpected failure.",
    )

    channel, _ = task._redis_client.publish.call_args[0]
    assert channel == "run:err-run-001:progress"


# ---------------------------------------------------------------------------
# Celery task registration
# ---------------------------------------------------------------------------


def test_task_is_registered_in_celery_app() -> None:
    """run_optimization_task is registered in the Celery app."""
    task_name = "app.workers.tasks.run_optimization_task"
    assert task_name in celery_app.tasks, (
        f"Task '{task_name}' not found in celery_app.tasks. "
        f"Registered tasks: {list(celery_app.tasks.keys())}"
    )


def test_task_has_correct_fully_qualified_name() -> None:
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
# Celery app configuration
# ---------------------------------------------------------------------------


def test_celery_app_has_default_queue() -> None:
    """Celery app has 'default' queue configured."""
    queues = celery_app.conf.task_queues
    assert "default" in queues, (
        f"'default' queue not found. Queues: {list(queues.keys())}"
    )


def test_celery_app_has_quantum_queue() -> None:
    """Celery app has 'quantum' queue configured."""
    queues = celery_app.conf.task_queues
    assert "quantum" in queues, (
        f"'quantum' queue not found. Queues: {list(queues.keys())}"
    )


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
    """Global task_acks_late is True for reliability."""
    assert celery_app.conf.task_acks_late is True


def test_celery_app_reject_on_worker_lost_is_true() -> None:
    """reject_on_worker_lost is True so crashed tasks are re-queued."""
    assert celery_app.conf.task_reject_on_worker_lost is True


# ---------------------------------------------------------------------------
# OptimizationTask.redis_client lazy init
# ---------------------------------------------------------------------------


def test_redis_client_is_none_before_first_access() -> None:
    """redis_client is None before first access (lazy init)."""
    task = OptimizationTask()
    assert task._redis_client is None


def test_redis_client_lazy_init_on_first_access() -> None:
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
