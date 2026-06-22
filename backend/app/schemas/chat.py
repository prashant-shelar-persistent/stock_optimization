"""Pydantic v2 schemas for the Chat Assistant API — public re-export module.

This module re-exports all chat-related Pydantic schemas from
``app.chat.schemas`` so that consumers can use the stable, canonical
import path ``from app.schemas.chat import ...`` regardless of the
internal package layout.

Canonical import path (preferred)::

    from app.schemas.chat import (
        ChatMessage,
        ExtractedSlots,
        LLMSlotFillerOutput,
        CreateSessionRequest,
        SendMessageRequest,
        ChatSessionResponse,
        SendMessageResponse,
        ConfirmSessionRequest,
        ConfirmSessionResponse,
        SessionIdPath,
    )

Schema overview
---------------
Request schemas
~~~~~~~~~~~~~~~
``CreateSessionRequest``
    Body for ``POST /api/v1/chat/sessions``.  Carries an optional
    initial user message so the first round-trip can be skipped.

``SendMessageRequest``
    Body for ``POST /api/v1/chat/sessions/{session_id}/messages``.
    Contains the user's next message text.

``ConfirmSessionRequest``
    Body for ``POST /api/v1/chat/sessions/{session_id}/confirm``.
    Optionally carries last-minute slot overrides before the
    optimization run is dispatched.

Response schemas
~~~~~~~~~~~~~~~~
``ChatSessionResponse``
    Full session representation returned by create and GET endpoints.
    Includes the message history, extracted slots, and current status.

``SendMessageResponse``
    Lightweight response for the send-message endpoint.  Returns the
    assistant's reply, the updated session status, and the payload
    preview when the session transitions to ``pending_confirmation``.

``ConfirmSessionResponse``
    Returned after a successful confirmation.  Contains the
    ``session_id`` and the newly dispatched ``run_id``.

Value objects
~~~~~~~~~~~~~
``ChatMessage``
    Immutable (frozen) single conversation turn with ``role`` and
    ``content`` fields.

``ExtractedSlots``
    Partial or complete ``OptimizationRequest`` fields extracted by
    the LLM across one or more conversation turns.  All fields are
    optional to support incremental slot filling.

``LLMSlotFillerOutput``
    Structured-output schema sent to GPT-4o.  Carries either a
    ``clarifying_question`` (when required slots are missing) or a
    populated ``slots`` object.

Type aliases
~~~~~~~~~~~~
``SessionIdPath``
    Annotated ``str`` type for FastAPI path parameters that carry a
    chat session UUID.  Includes regex validation and length bounds.
"""

# Re-export everything from the canonical implementation module.
# Using explicit names (rather than ``import *``) keeps the public
# surface visible to static analysis tools and IDEs.
from app.chat.schemas import (
    ChatMessage,
    ChatSessionResponse,
    ConfirmSessionRequest,
    ConfirmSessionResponse,
    CreateSessionRequest,
    ExtractedSlots,
    LLMSlotFillerOutput,
    SendMessageRequest,
    SendMessageResponse,
    SessionIdPath,
)


__all__ = [
    # Value objects
    "ChatMessage",
    # Response schemas
    "ChatSessionResponse",
    "ConfirmSessionRequest",
    "ConfirmSessionResponse",
    # Request schemas
    "CreateSessionRequest",
    "ExtractedSlots",
    "LLMSlotFillerOutput",
    "SendMessageRequest",
    "SendMessageResponse",
    # Type aliases
    "SessionIdPath",
]
