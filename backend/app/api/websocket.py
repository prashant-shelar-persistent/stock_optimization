"""WebSocket endpoint for streaming agent progress.

Endpoint: WS /ws/runs/{run_id}/progress?token=<ws_token>

The frontend connects to this endpoint after submitting an optimization run.
The Celery worker publishes progress events to a Redis pub/sub channel
(channel name: ``run:{run_id}:progress``). This endpoint subscribes to that
channel and forwards messages to the WebSocket client.

Security hardening (Phase 2)
-----------------------------
Authentication is enforced **before** ``websocket.accept()`` is called.

The client must supply a ``?token=`` query parameter containing the
``ws_token`` returned by ``POST /api/v1/optimize``.  The token is:

- HMAC-SHA256 signed with the application ``SECRET_KEY``
- Scoped to the specific ``run_id`` (cannot be replayed for a different run)
- Valid for 300 seconds (5 minutes) from issuance

If the token is missing, expired, or has an invalid signature the handler
calls ``websocket.close(code=4001)`` *without* accepting the connection,
so the client receives a WebSocket close frame with code 4001 (Policy
Violation) rather than a successful upgrade.

The ``run_id`` path parameter is validated as a UUID v4 string via the
``_RunId`` annotated type alias, which rejects non-UUID strings before they
reach the handler.

Message format (JSON):
    Progress event:
    {
        "type": "progress",
        "run_id": "...",
        "node": "data_fetch" | "constraint_validation" | ...,
        "status": "started" | "completed" | "failed",
        "message": "Human-readable description",
        "timestamp": "2024-01-01T00:00:00Z"
    }

    Final result:
    {
        "type": "result",
        "run_id": "...",
        "result": { ... OptimizationRunDetail ... }
    }

    Error:
    {
        "type": "error",
        "run_id": "...",
        "error_code": "...",
        "message": "..."
    }

    Keepalive ping (sent every 30 seconds to prevent proxy timeouts):
    {
        "type": "ping",
        "run_id": "..."
    }

Design notes:
    - A dedicated Redis connection is created per WebSocket connection to
      avoid sharing pub/sub state across concurrent connections.
    - The ping keepalive prevents proxy/load balancer timeouts for long-running
      quantum optimization jobs (which can take 60+ seconds).
    - The handler exits cleanly on WebSocketDisconnect without re-raising.
    - A configurable timeout (default 300s) prevents zombie connections from
      accumulating if the client disconnects without sending a close frame.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Path, Query, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import WsTokenError, verify_ws_token


logger = get_logger(__name__)
router = APIRouter(tags=["websocket"])

# Maximum time (seconds) to wait for a run to complete before closing the WS
_WS_TIMEOUT_SECONDS = 300

# Interval (seconds) between keepalive ping messages
_PING_INTERVAL_SECONDS = 30

# How long to wait for a single Redis message poll before looping
_POLL_TIMEOUT_SECONDS = 1.0

# UUID v4 regex — same pattern used in chat.py for session IDs
_UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"

# Annotated path type that validates run_id as a UUID v4 string.
# Rejects non-UUID strings (e.g. path traversal probes) before the handler
# is invoked.
_RunId = Annotated[
    str,
    Path(
        title="Run ID",
        description="UUID v4 of the optimization run",
        min_length=36,
        max_length=36,
        pattern=_UUID_PATTERN,
    ),
]


@router.websocket("/ws/runs/{run_id}/progress")
async def run_progress_websocket(
    websocket: WebSocket,
    run_id: _RunId,
    token: str | None = Query(
        default=None,
        description=(
            "HMAC-signed WebSocket authentication token issued by "
            "POST /api/v1/optimize.  Required.  The token is scoped to "
            "this specific run_id and expires after 300 seconds."
        ),
    ),
) -> "None":
    """Stream agent progress events for a given optimization run.

    Authentication
    --------------
    The ``?token=`` query parameter is verified *before* ``accept()`` is
    called.  If the token is missing, expired, or invalid the connection is
    closed with WebSocket close code 4001 (Policy Violation) without
    upgrading the protocol.

    Streaming
    ---------
    After successful authentication the handler subscribes to the Redis
    pub/sub channel ``run:{run_id}:progress`` and forwards all messages to
    the WebSocket until the run completes, fails, or the connection times out.

    A keepalive ping is sent every 30 seconds to prevent proxy timeouts
    during long-running quantum optimization jobs.
    """
    settings = get_settings()

    # ── Token authentication (BEFORE accept()) ────────────────────────────────
    # Verify the HMAC token before upgrading the WebSocket connection.
    # If verification fails we close without accepting — the client receives
    # a close frame with code 4001 (Policy Violation).
    if token is None:
        logger.warning(
            "websocket_auth_missing_token",
            run_id=run_id,
            client=websocket.client.host if websocket.client else "unknown",
        )
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    try:
        verify_ws_token(
            token=token,
            expected_run_id=run_id,
            secret_key=settings.SECRET_KEY,
        )
    except WsTokenError as exc:
        logger.warning(
            "websocket_auth_failed",
            run_id=run_id,
            reason=exc.reason,
            client=websocket.client.host if websocket.client else "unknown",
        )
        await websocket.close(code=4001, reason="Invalid or expired authentication token")
        return

    # ── Accept the authenticated connection ───────────────────────────────────
    await websocket.accept()
    logger.info(
        "websocket_connected",
        run_id=run_id,
        client=websocket.client.host if websocket.client else "unknown",
    )

    channel = f"run:{run_id}:progress"

    try:
        # Create a dedicated Redis connection for pub/sub.
        # decode_responses=True so message data comes back as str.
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel)

        try:
            _loop = asyncio.get_running_loop()
            deadline = _loop.time() + _WS_TIMEOUT_SECONDS
            last_ping_time = _loop.time()

            while True:
                now = asyncio.get_running_loop().time()

                # ── Check overall timeout ─────────────────────────────────────
                remaining = deadline - now
                if remaining <= 0:
                    logger.warning("websocket_timeout", run_id=run_id)
                    await _safe_send_json(
                        websocket,
                        {
                            "type": "error",
                            "run_id": run_id,
                            "error_code": "WEBSOCKET_TIMEOUT",
                            "message": (
                                "Connection timed out waiting for results. "
                                "The optimization run may still be in progress. "
                                "Poll GET /api/v1/runs/{run_id}/status for updates."
                            ),
                        },
                    )
                    break

                # ── Send keepalive ping if interval elapsed ───────────────────
                if now - last_ping_time >= _PING_INTERVAL_SECONDS:
                    await _safe_send_json(
                        websocket,
                        {
                            "type": "ping",
                            "run_id": run_id,
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    )
                    last_ping_time = now
                    logger.debug("websocket_ping_sent", run_id=run_id)

                # ── Poll for Redis pub/sub messages ───────────────────────────
                poll_timeout = min(_POLL_TIMEOUT_SECONDS, remaining)
                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=poll_timeout,
                    )
                except asyncio.TimeoutError:
                    # No message within poll window — loop back to check ping/timeout
                    continue

                if message is None:
                    continue

                if message["type"] != "message":
                    continue

                data_str = message["data"]
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    logger.warning(
                        "websocket_invalid_message",
                        run_id=run_id,
                        raw=data_str[:200] if isinstance(data_str, str) else repr(data_str)[:200],
                    )
                    continue

                # Forward the message to the WebSocket client
                await _safe_send_json(websocket, data)

                # ── Stop streaming on terminal message ────────────────────────
                msg_type = data.get("type")
                if msg_type in ("result", "error"):
                    logger.info(
                        "websocket_run_complete",
                        run_id=run_id,
                        terminal_type=msg_type,
                    )
                    break

        finally:
            # Always clean up the pub/sub subscription and Redis connection
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            except Exception:
                pass
            try:
                await redis_client.aclose()
            except Exception:
                pass

    except WebSocketDisconnect:
        logger.info("websocket_disconnected", run_id=run_id)
    except Exception as exc:
        logger.error(
            "websocket_error",
            run_id=run_id,
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        await _safe_send_json(
            websocket,
            {
                "type": "error",
                "run_id": run_id,
                "error_code": "WEBSOCKET_ERROR",
                "message": "An internal error occurred in the WebSocket handler.",
            },
        )
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("websocket_closed", run_id=run_id)


async def _safe_send_json(websocket: WebSocket, data: dict) -> None:  # type: ignore[type-arg]
    """Send a JSON message to the WebSocket, swallowing send errors.

    If the client has already disconnected, sending will raise an exception.
    We catch and log it rather than propagating, since the connection is
    already gone and there is nothing useful to do.
    """
    try:
        await websocket.send_json(data)
    except Exception as exc:
        logger.debug(
            "websocket_send_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
