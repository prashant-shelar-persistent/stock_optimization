"""Integration tests for WebSocket endpoint: WS /ws/runs/{run_id}/progress.

Tests cover:
1. WebSocket connection is accepted
2. Progress message forwarded from Redis pub/sub to WebSocket client
3. Result message terminates the stream
4. Error message terminates the stream
5. Invalid JSON from Redis is silently skipped
6. _safe_send_json swallows send errors without raising
7. WebSocket channel name follows pattern: run:{run_id}:progress
8. Multiple progress messages are forwarded in order
9. Non-message Redis events (subscribe confirmations) are ignored
"""

from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.websocket import _safe_send_json
from app.main import app


# ---------------------------------------------------------------------------
# _safe_send_json unit tests (no WebSocket server needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_safe_send_json_sends_data() -> None:
    """_safe_send_json calls websocket.send_json with the data."""
    mock_ws = AsyncMock()
    data = {"type": "ping", "run_id": "test-123"}

    await _safe_send_json(mock_ws, data)

    mock_ws.send_json.assert_awaited_once_with(data)


@pytest.mark.asyncio
async def test_safe_send_json_swallows_exception() -> None:
    """_safe_send_json does not raise when send_json fails."""
    mock_ws = AsyncMock()
    mock_ws.send_json.side_effect = RuntimeError("Connection closed")

    # Should not raise
    await _safe_send_json(mock_ws, {"type": "ping"})


@pytest.mark.asyncio
async def test_safe_send_json_swallows_disconnect_error() -> None:
    """_safe_send_json does not raise on WebSocketDisconnect."""
    from fastapi import WebSocketDisconnect

    mock_ws = AsyncMock()
    mock_ws.send_json.side_effect = WebSocketDisconnect(code=1001)

    # Should not raise
    await _safe_send_json(mock_ws, {"type": "result", "run_id": "abc"})


# ---------------------------------------------------------------------------
# Helpers for WebSocket endpoint tests
# ---------------------------------------------------------------------------


def _make_mock_pubsub(messages: list[dict]) -> MagicMock:
    """Create a mock Redis pubsub that yields the given messages then raises TimeoutError.

    pubsub() is called synchronously in the source code (redis_client.pubsub()),
    so we use MagicMock (not AsyncMock) for the pubsub object itself.
    subscribe/unsubscribe/aclose are awaited, so they use AsyncMock.
    get_message is awaited, so it uses an async function.
    """
    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.aclose = AsyncMock()

    # Build a sequence: each call to get_message returns the next message.
    # After all messages are consumed, raise TimeoutError (no more messages).
    message_iter = iter(messages)

    async def get_message(ignore_subscribe_messages=True):
        try:
            return next(message_iter)
        except StopIteration:
            raise asyncio.TimeoutError()

    pubsub.get_message = get_message
    return pubsub


def _make_redis_message(data: dict) -> dict:
    """Wrap a dict as a Redis pub/sub message."""
    return {
        "type": "message",
        "channel": "run:test:progress",
        "data": json.dumps(data),
    }


def _make_mock_redis(pubsub: MagicMock) -> MagicMock:
    """Create a mock Redis client that returns the given pubsub on .pubsub()."""
    # redis_client.pubsub() is a synchronous call, so use MagicMock
    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = pubsub
    mock_redis.aclose = AsyncMock()
    return mock_redis


# ---------------------------------------------------------------------------
# WebSocket endpoint tests using TestClient
# ---------------------------------------------------------------------------


def test_websocket_connection_accepted() -> None:
    """WebSocket connection is accepted (101 Switching Protocols)."""
    run_id = str(uuid.uuid4())

    result_msg = _make_redis_message({
        "type": "result",
        "run_id": run_id,
        "result": {"status": "completed"},
    })
    mock_pubsub = _make_mock_pubsub([result_msg])
    mock_redis = _make_mock_redis(mock_pubsub)

    with patch("app.api.websocket.aioredis.from_url", return_value=mock_redis):
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/runs/{run_id}/progress") as ws:
                data = ws.receive_json()
                assert data["type"] == "result"
                assert data["run_id"] == run_id


def test_websocket_forwards_progress_message() -> None:
    """Progress messages from Redis are forwarded to the WebSocket client."""
    run_id = str(uuid.uuid4())

    progress_msg = _make_redis_message({
        "type": "progress",
        "run_id": run_id,
        "node": "data_fetch",
        "status": "started",
        "message": "Fetching market data…",
        "timestamp": "2024-01-15T10:00:00+00:00",
    })
    result_msg = _make_redis_message({
        "type": "result",
        "run_id": run_id,
        "result": {"status": "completed"},
    })
    mock_pubsub = _make_mock_pubsub([progress_msg, result_msg])
    mock_redis = _make_mock_redis(mock_pubsub)

    with patch("app.api.websocket.aioredis.from_url", return_value=mock_redis):
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/runs/{run_id}/progress") as ws:
                # First message: progress
                msg1 = ws.receive_json()
                assert msg1["type"] == "progress"
                assert msg1["node"] == "data_fetch"
                assert msg1["status"] == "started"

                # Second message: result (terminates)
                msg2 = ws.receive_json()
                assert msg2["type"] == "result"


def test_websocket_result_message_terminates_stream() -> None:
    """Receiving a 'result' message closes the WebSocket stream."""
    run_id = str(uuid.uuid4())

    result_msg = _make_redis_message({
        "type": "result",
        "run_id": run_id,
        "result": {"status": "completed", "classical_sharpe": 1.5},
    })
    mock_pubsub = _make_mock_pubsub([result_msg])
    mock_redis = _make_mock_redis(mock_pubsub)

    received = []
    with patch("app.api.websocket.aioredis.from_url", return_value=mock_redis):
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/runs/{run_id}/progress") as ws:
                msg = ws.receive_json()
                received.append(msg)

    assert len(received) == 1
    assert received[0]["type"] == "result"
    assert received[0]["result"]["classical_sharpe"] == 1.5


def test_websocket_error_message_terminates_stream() -> None:
    """Receiving an 'error' message closes the WebSocket stream."""
    run_id = str(uuid.uuid4())

    error_msg = _make_redis_message({
        "type": "error",
        "run_id": run_id,
        "error_code": "AGENT_EXECUTION_ERROR",
        "message": "Data fetch failed.",
    })
    mock_pubsub = _make_mock_pubsub([error_msg])
    mock_redis = _make_mock_redis(mock_pubsub)

    received = []
    with patch("app.api.websocket.aioredis.from_url", return_value=mock_redis):
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/runs/{run_id}/progress") as ws:
                msg = ws.receive_json()
                received.append(msg)

    assert len(received) == 1
    assert received[0]["type"] == "error"
    assert received[0]["error_code"] == "AGENT_EXECUTION_ERROR"


def test_websocket_multiple_progress_messages_forwarded_in_order() -> None:
    """Multiple progress messages are forwarded in the correct order."""
    run_id = str(uuid.uuid4())

    nodes = ["data_fetch", "constraint_validation", "classical_optimization"]
    messages = [
        _make_redis_message({
            "type": "progress",
            "run_id": run_id,
            "node": node,
            "status": "completed",
            "message": f"{node} done",
            "timestamp": "2024-01-15T10:00:00+00:00",
        })
        for node in nodes
    ]
    messages.append(_make_redis_message({
        "type": "result",
        "run_id": run_id,
        "result": {"status": "completed"},
    }))

    mock_pubsub = _make_mock_pubsub(messages)
    mock_redis = _make_mock_redis(mock_pubsub)

    received = []
    with patch("app.api.websocket.aioredis.from_url", return_value=mock_redis):
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/runs/{run_id}/progress") as ws:
                for _ in range(len(messages)):
                    msg = ws.receive_json()
                    received.append(msg)

    assert len(received) == 4
    assert received[0]["node"] == "data_fetch"
    assert received[1]["node"] == "constraint_validation"
    assert received[2]["node"] == "classical_optimization"
    assert received[3]["type"] == "result"


def test_websocket_non_message_redis_events_ignored() -> None:
    """Redis subscribe confirmation events (type != 'message') are ignored."""
    run_id = str(uuid.uuid4())

    # Subscribe confirmation (should be ignored)
    subscribe_event = {
        "type": "subscribe",
        "channel": f"run:{run_id}:progress",
        "data": 1,
    }
    result_msg = _make_redis_message({
        "type": "result",
        "run_id": run_id,
        "result": {"status": "completed"},
    })

    mock_pubsub = _make_mock_pubsub([subscribe_event, result_msg])
    mock_redis = _make_mock_redis(mock_pubsub)

    received = []
    with patch("app.api.websocket.aioredis.from_url", return_value=mock_redis):
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/runs/{run_id}/progress") as ws:
                msg = ws.receive_json()
                received.append(msg)

    # Only the result message should be received (subscribe event was ignored)
    assert len(received) == 1
    assert received[0]["type"] == "result"


def test_websocket_invalid_json_from_redis_is_skipped() -> None:
    """Invalid JSON data from Redis is silently skipped."""
    run_id = str(uuid.uuid4())

    # Invalid JSON message
    invalid_msg = {
        "type": "message",
        "channel": f"run:{run_id}:progress",
        "data": "this is not valid json {{{",
    }
    result_msg = _make_redis_message({
        "type": "result",
        "run_id": run_id,
        "result": {"status": "completed"},
    })

    mock_pubsub = _make_mock_pubsub([invalid_msg, result_msg])
    mock_redis = _make_mock_redis(mock_pubsub)

    received = []
    with patch("app.api.websocket.aioredis.from_url", return_value=mock_redis):
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/runs/{run_id}/progress") as ws:
                msg = ws.receive_json()
                received.append(msg)

    # Invalid JSON was skipped; only the result message was forwarded
    assert len(received) == 1
    assert received[0]["type"] == "result"
