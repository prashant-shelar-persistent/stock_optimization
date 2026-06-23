"""Chat Assistant REST endpoints.

Implements the multi-turn slot-filling chat API that lets users describe
their portfolio optimization goals in natural language.  GPT-4o extracts
structured slot values across conversation turns; once all required slots
are present the session transitions to ``pending_confirmation`` and the
user can confirm to dispatch an optimization run.

Endpoints
---------
POST   /api/v1/chat/sessions
    Create a new chat session.  Optionally accepts an ``initial_message``
    so the first user turn and the assistant's reply are returned in a
    single round-trip.

GET    /api/v1/chat/sessions/{session_id}
    Fetch the full state of an existing session (message history, extracted
    slots, current status).

POST   /api/v1/chat/sessions/{session_id}/messages
    Send a user message to an existing session.  The LLM slot filler is
    invoked and the assistant's reply is returned.  When all required slots
    have been extracted the response includes a ``payload_preview`` and the
    session status transitions to ``pending_confirmation``.

POST   /api/v1/chat/sessions/{session_id}/confirm
    Confirm the extracted payload and dispatch the optimization run.  The
    session must be in ``pending_confirmation`` state.  Optional
    ``slot_overrides`` can be supplied to tweak values on the confirmation
    card without going back to the chat.

Design decisions
----------------
- The router is a **thin HTTP adapter**: it delegates all business logic to
  :class:`~app.chat.service.ChatService`.  No domain logic lives here.
- Each request constructs a fresh :class:`~app.chat.service.ChatService`
  instance bound to the injected ``AsyncSession``.  The session is
  committed/rolled-back by the ``DbDep`` dependency generator in
  ``app.core.dependencies``.
- Domain exceptions raised by the service (subclasses of
  :class:`~app.core.exceptions.PortfolioOptimizerError`) are caught by the
  global exception handler in ``main.py`` and converted to structured JSON
  error responses with the correct HTTP status codes.
- Path parameters that carry a session UUID are typed as ``str`` with a
  regex pattern validator via the ``SessionIdPath`` annotated alias defined
  in ``app.chat.schemas``.
- All endpoints are tagged ``chat`` for OpenAPI grouping.

Security hardening (Phase 2)
-----------------------------
The in-process rate limiter (``_rate_limit_buckets`` / ``_check_rate_limit``)
has been removed.  It was ineffective across multiple Uvicorn workers and
Celery processes because each process maintained its own independent dict.

Rate limiting is now handled globally by ``slowapi`` (Redis-backed) which is
registered in ``main.py`` and works correctly across all processes.  The
``slowapi`` limiter is applied via decorators in Phase 3.
"""

from typing import Annotated

from fastapi import Response, APIRouter, Path, Request

from app.chat.schemas import (
    ChatSessionResponse,
    ConfirmSessionRequest,
    ConfirmSessionResponse,
    CreateSessionRequest,
    SendMessageRequest,
    SendMessageResponse,
)
from app.chat.service import ChatService
from app.core.dependencies import DbDep
from app.core.logging import get_logger
from app.core.rate_limit import RATE_LIMIT_CHAT, RATE_LIMIT_CHAT_CREATE, limiter


logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# ── Path parameter type alias ─────────────────────────────────────────────────
# Validates that the session_id path segment is a well-formed UUID v4 string.
# Using Path() directly here (rather than the SessionIdPath alias) keeps the
# OpenAPI schema clean while still enforcing the regex at the framework level.
_SessionId = Annotated[
    str,
    Path(
        title="Session ID",
        description="UUID of the chat session",
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    ),
]


# ── POST /chat/sessions ───────────────────────────────────────────────────────


@router.post(
    "/sessions",
    response_model=ChatSessionResponse,
    status_code=201,
    summary="Create a new chat session",
    description=(
        "Creates a new chat session for the portfolio optimization assistant. "
        "If ``initial_message`` is provided, the LLM slot filler is invoked "
        "immediately and the assistant's first response is included in the "
        "returned session — saving one round-trip for clients that want to "
        "send the first message at session creation time. "
        "If omitted, the session is created in ``collecting`` state with a "
        "welcome message from the assistant."
    ),
    responses={
        201: {
            "description": "Session created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                        "status": "collecting",
                        "messages": [
                            {
                                "role": "user",
                                "content": "Optimize AAPL, MSFT with $50k budget",
                            },
                            {
                                "role": "assistant",
                                "content": "What minimum annual return are you targeting?",
                            },
                        ],
                        "extracted_slots": {
                            "tickers": ["AAPL", "MSFT"],
                            "budget": 50000.0,
                        },
                        "run_id": None,
                        "created_at": "2026-06-16T10:00:00Z",
                        "updated_at": "2026-06-16T10:00:01Z",
                        "expires_at": "2026-06-17T10:00:00Z",
                        "assistant_message": "What minimum annual return are you targeting?",
                    }
                }
            },
        },
        502: {"description": "LLM slot extraction failed (upstream error)"},
    },
)
@limiter.limit(RATE_LIMIT_CHAT_CREATE)
async def create_session(
    request: Request,
    response: Response,
    body: CreateSessionRequest,
    db: DbDep,
) -> "ChatSessionResponse":
    """Create a new chat session.

    Constructs a :class:`~app.chat.service.ChatService` bound to the
    request-scoped database session and delegates to
    :meth:`~app.chat.service.ChatService.create_session`.

    Args:
        body: Optional ``initial_message`` to process in the same request.
        db:   Injected async SQLAlchemy session (committed on clean exit).

    Returns:
        The newly created :class:`~app.chat.schemas.ChatSessionResponse`.

    Raises:
        ChatSlotExtractionError (→ HTTP 502): If ``initial_message`` is
            provided and the LLM call fails.
    """
    service = ChatService(db=db)

    logger.info(
        "chat_create_session_request",
        has_initial_message=body.initial_message is not None,
    )

    response = await service.create_session(initial_message=body.initial_message)

    logger.info(
        "chat_session_created_response",
        session_id=response.session_id,
        status=response.status,
    )

    return response


# ── GET /chat/sessions/{session_id} ──────────────────────────────────────────


@router.get(
    "/sessions/{session_id}",
    response_model=ChatSessionResponse,
    summary="Get chat session",
    description=(
        "Returns the full state of an existing chat session, including the "
        "complete message history, extracted slot values, and current status. "
        "If the session has passed its TTL and is not already in a terminal "
        "state, it is lazily transitioned to ``expired`` before the response "
        "is returned."
    ),
    responses={
        200: {"description": "Session found and returned"},
        404: {
            "description": "Session not found",
            "content": {
                "application/json": {
                    "example": {
                        "error_code": "CHAT_SESSION_NOT_FOUND",
                        "message": "Chat session 'abc-123' not found.",
                        "details": {"session_id": "abc-123"},
                    }
                }
            },
        },
        410: {
            "description": "Session has expired",
            "content": {
                "application/json": {
                    "example": {
                        "error_code": "CHAT_SESSION_EXPIRED",
                        "message": (
                            "Chat session 'abc-123' has expired and is no longer "
                            "accepting new messages. Please start a new session."
                        ),
                        "details": {"session_id": "abc-123"},
                    }
                }
            },
        },
    },
)
@limiter.limit(RATE_LIMIT_CHAT)
async def get_session(
    request: Request,
    response: Response,
    session_id: _SessionId,
    db: DbDep,
) -> "ChatSessionResponse":
    """Fetch the full state of an existing chat session.

    Args:
        session_id: UUID of the target session (validated by path regex).
        db:         Injected async SQLAlchemy session.

    Returns:
        The :class:`~app.chat.schemas.ChatSessionResponse` for the session.

    Raises:
        ChatSessionNotFoundError (→ HTTP 404): If no session with
            ``session_id`` exists.
        ChatSessionExpiredError (→ HTTP 410): If the session has expired.
    """
    service = ChatService(db=db)

    logger.debug("chat_get_session_request", session_id=session_id)

    response = await service.get_session(session_id=session_id)

    logger.debug(
        "chat_get_session_response",
        session_id=session_id,
        status=response.status,
        message_count=len(response.messages),
    )

    return response


# ── POST /chat/sessions/{session_id}/messages ─────────────────────────────────


@router.post(
    "/sessions/{session_id}/messages",
    response_model=SendMessageResponse,
    status_code=200,
    summary="Send a message to a chat session",
    description=(
        "Appends the user's message to the conversation history and invokes "
        "the LLM slot filler to extract or refine optimization parameters. "
        "The assistant's reply is returned immediately. "
        "When all required slots (tickers + budget) have been extracted, the "
        "session transitions to ``pending_confirmation`` and the response "
        "includes a ``payload_preview`` with the full extracted parameters "
        "for the user to review before confirming."
    ),
    responses={
        200: {
            "description": "Message processed; assistant reply returned",
            "content": {
                "application/json": {
                    "example": {
                        "session": {
                            "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                            "status": "pending_confirmation",
                            "messages": [],
                            "extracted_slots": {
                                "tickers": ["AAPL", "MSFT", "GOOGL"],
                                "budget": 100000.0,
                                "run_quantum": False,
                            },
                            "run_id": None,
                            "created_at": "2026-06-16T10:00:00Z",
                            "updated_at": "2026-06-16T10:00:05Z",
                            "expires_at": "2026-06-17T10:00:00Z",
                            "assistant_message": (
                                "I have all the information I need. Here is the "
                                "optimization request I'll submit — please confirm."
                            ),
                        },
                        "reply": (
                            "I have all the information I need. Here is the "
                            "optimization request I'll submit — please confirm."
                        ),
                        "payload_preview": {
                            "tickers": ["AAPL", "MSFT", "GOOGL"],
                            "budget": 100000.0,
                            "run_quantum": False,
                        },
                    }
                }
            },
        },
        404: {"description": "Session not found"},
        409: {
            "description": "Session is in a terminal state (confirmed or expired)",
            "content": {
                "application/json": {
                    "example": {
                        "error_code": "CHAT_INVALID_STATE",
                        "message": (
                            "Operation requires session status 'collecting' or "
                            "'pending_confirmation', but session 'abc-123' is "
                            "currently 'confirmed'."
                        ),
                        "details": {
                            "session_id": "abc-123",
                            "current_status": "confirmed",
                            "required_status": ["collecting", "pending_confirmation"],
                        },
                    }
                }
            },
        },
        410: {"description": "Session has expired"},
        422: {
            "description": "Session has reached the maximum message count",
            "content": {
                "application/json": {
                    "example": {
                        "error_code": "CHAT_TOO_MANY_MESSAGES",
                        "message": (
                            "Chat session 'abc-123' has reached the maximum "
                            "allowed message count (50). "
                            "Please start a new session to continue."
                        ),
                        "details": {
                            "session_id": "abc-123",
                            "message_count": 50,
                            "max_messages": 50,
                        },
                    }
                }
            },
        },
        502: {"description": "LLM slot extraction failed (upstream error)"},
    },
)
@limiter.limit(RATE_LIMIT_CHAT)
async def send_message(
    request: Request,
    response: Response,
    session_id: _SessionId,
    body: SendMessageRequest,
    db: DbDep,
) -> "SendMessageResponse":
    """Send a user message and receive the assistant's reply.

    Args:
        session_id: UUID of the target session.
        body:       Request body containing the user's ``content`` string.
        db:         Injected async SQLAlchemy session.
    Returns:
        A :class:`~app.chat.schemas.SendMessageResponse` with the assistant
        reply, updated session state, and optional ``payload_preview``.

    Raises:
        ChatSessionNotFoundError (→ HTTP 404): If no session exists.
        ChatSessionExpiredError (→ HTTP 410): If the session has expired.
        ChatInvalidStateError (→ HTTP 409): If the session is in a terminal
            state (``confirmed`` or ``expired``).
        ChatTooManyMessagesError (→ HTTP 422): If the session has reached
            the maximum allowed message count.
        ChatSlotExtractionError (→ HTTP 502): If the LLM call fails.
    """
    service = ChatService(db=db)

    logger.info(
        "chat_send_message_request",
        session_id=session_id,
        content_length=len(body.content),
    )

    response = await service.send_message(
        session_id=session_id,
        content=body.content,
    )

    logger.info(
        "chat_send_message_response",
        session_id=session_id,
        session_status=response.session.status,
        has_payload_preview=response.payload_preview is not None,
    )

    return response


# ── POST /chat/sessions/{session_id}/confirm ──────────────────────────────────


@router.post(
    "/sessions/{session_id}/confirm",
    response_model=ConfirmSessionResponse,
    status_code=200,
    summary="Confirm extracted payload and dispatch optimization run",
    description=(
        "Confirms the extracted optimization parameters and dispatches an "
        "asynchronous optimization run via Celery. "
        "The session must be in ``pending_confirmation`` state. "
        "Optional ``slot_overrides`` can be supplied to tweak individual "
        "parameter values on the confirmation card without going back to the "
        "chat (e.g. adjusting the budget or disabling quantum optimization). "
        "On success, the session transitions to ``confirmed`` and the "
        "``run_id`` of the dispatched run is returned. "
        "Use ``GET /api/v1/runs/{run_id}`` or the WebSocket endpoint "
        "``/ws/runs/{run_id}/progress`` to track the run."
    ),
    responses={
        200: {
            "description": "Optimization run dispatched successfully",
            "content": {
                "application/json": {
                    "example": {
                        "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                        "run_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
                        "status": "confirmed",
                    }
                }
            },
        },
        404: {"description": "Session not found"},
        409: {
            "description": "Session is not in pending_confirmation state, or already confirmed",
            "content": {
                "application/json": {
                    "examples": {
                        "already_confirmed": {
                            "summary": "Session already confirmed",
                            "value": {
                                "error_code": "CHAT_SESSION_ALREADY_CONFIRMED",
                                "message": (
                                    "Chat session 'abc-123' has already been confirmed "
                                    "(run_id='xyz-456'). Each session can only be confirmed once."
                                ),
                                "details": {
                                    "session_id": "abc-123",
                                    "run_id": "xyz-456",
                                },
                            },
                        },
                        "invalid_state": {
                            "summary": "Session still collecting",
                            "value": {
                                "error_code": "CHAT_INVALID_STATE",
                                "message": (
                                    "Operation requires session status "
                                    "'pending_confirmation', but session 'abc-123' "
                                    "is currently 'collecting'."
                                ),
                                "details": {
                                    "session_id": "abc-123",
                                    "current_status": "collecting",
                                    "required_status": "pending_confirmation",
                                },
                            },
                        },
                    }
                }
            },
        },
        410: {"description": "Session has expired"},
        422: {
            "description": (
                "Slot overrides are invalid (too many keys, unrecognised field "
                "names, or the merged slots fail OptimizationRequest validation)"
            ),
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_field": {
                            "summary": "Unrecognised slot override key",
                            "value": {
                                "error_code": "CHAT_SLOT_OVERRIDE_ERROR",
                                "message": (
                                    "slot_overrides contains unrecognised field "
                                    "names: ['unknown_field']."
                                ),
                                "details": {
                                    "session_id": "abc-123",
                                    "invalid_keys": ["unknown_field"],
                                    "max_keys": 20,
                                },
                            },
                        },
                        "too_many_keys": {
                            "summary": "Too many slot override keys",
                            "value": {
                                "error_code": "CHAT_SLOT_OVERRIDE_ERROR",
                                "message": (
                                    "slot_overrides contains 25 keys, which "
                                    "exceeds the maximum of 20."
                                ),
                                "details": {
                                    "session_id": "abc-123",
                                    "invalid_keys": [],
                                    "max_keys": 20,
                                },
                            },
                        },
                        "validation_error": {
                            "summary": "Merged slots fail validation",
                            "value": {
                                "error_code": "INTERNAL_ERROR",
                                "message": "budget: Input should be greater than 0",
                                "details": {},
                            },
                        },
                    }
                }
            },
        },
    },
)
@limiter.limit(RATE_LIMIT_CHAT)
async def confirm_session(
    request: Request,
    response: Response,
    session_id: _SessionId,
    body: ConfirmSessionRequest,
    db: DbDep,
) -> "ConfirmSessionResponse":
    """Confirm the extracted payload and dispatch the optimization run.

    Args:
        session_id: UUID of the session to confirm.
        body:       Optional ``slot_overrides`` dict to apply before dispatch.
        db:         Injected async SQLAlchemy session.

    Returns:
        A :class:`~app.chat.schemas.ConfirmSessionResponse` with the
        ``session_id`` and the newly dispatched ``run_id``.

    Raises:
        ChatSessionNotFoundError (→ HTTP 404): If no session exists.
        ChatSessionExpiredError (→ HTTP 410): If the session has expired.
        ChatSessionAlreadyConfirmedError (→ HTTP 409): If the session has
            already been confirmed.
        ChatInvalidStateError (→ HTTP 409): If the session is not in
            ``pending_confirmation`` state.
        ChatSlotOverrideError (→ HTTP 422): If ``slot_overrides`` contains
            too many keys or unrecognised field names.
        ValueError (→ HTTP 422): If the merged slots cannot be parsed into
            a valid ``OptimizationRequest`` (e.g. invalid slot overrides).
    """
    service = ChatService(db=db)

    logger.info(
        "chat_confirm_session_request",
        session_id=session_id,
        has_slot_overrides=body.slot_overrides is not None,
        slot_override_keys=(
            list(body.slot_overrides.keys()) if body.slot_overrides else []
        ),
    )

    response = await service.confirm_session(
        session_id=session_id,
        slot_overrides=body.slot_overrides,
    )

    logger.info(
        "chat_confirm_session_response",
        session_id=session_id,
        run_id=response.run_id,
        status=response.status,
    )

    return response
