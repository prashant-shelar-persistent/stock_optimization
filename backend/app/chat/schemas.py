"""Pydantic v2 schemas for the Chat Assistant API.

These models define the JSON structure of all chat-related API requests
and responses.  They are used by the FastAPI router for request parsing /
validation and by the service layer for serialisation.

Design decisions:
    - ``ChatMessage`` is a simple value object shared between request and
      response contexts; it is not a DB model.
    - ``ExtractedSlots`` mirrors ``OptimizationRequest`` but makes every
      field optional so that partial extractions can be stored and
      incrementally filled across turns.
    - ``ChatSessionResponse`` is the canonical API representation of a
      ``ChatSession`` ORM row; it is constructed via ``model_validate``
      with ``from_attributes=True``.
    - ``LLMSlotFillerOutput`` is the structured-output schema sent to
      GPT-4o.  It is intentionally separate from ``ExtractedSlots`` so
      that the LLM response can carry a ``clarifying_question`` field
      without polluting the slot data.
    - All timestamp fields are ``datetime`` objects (timezone-aware UTC);
      FastAPI serialises them to ISO-8601 strings automatically.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.requests import (
    BusinessObjective,
    FrontierConfig,
    SectorConstraint,
)


# ── Shared value objects ──────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    """A single turn in a chat conversation.

    Attributes:
        role:    Either ``'user'`` (human) or ``'assistant'`` (AI).
        content: The text content of the message.

    Example::

        ChatMessage(role="user", content="Optimize AAPL, MSFT with $50k budget")
        ChatMessage(role="assistant", content="What minimum return do you need?")
    """

    role: Literal["user", "assistant"] = Field(
        description="Message author: 'user' for human turns, 'assistant' for AI turns",
    )
    content: str = Field(
        min_length=1,
        max_length=8_000,
        description="Text content of the message (max 8 000 characters)",
    )

    model_config = ConfigDict(frozen=True)


# ── Slot extraction schemas ───────────────────────────────────────────────────


class ExtractedSlots(BaseModel):
    """Partial or complete ``OptimizationRequest`` fields extracted by the LLM.

    Every field is optional so that partial extractions can be stored and
    incrementally filled across multiple conversation turns.  When all
    *required* fields (``tickers`` and ``budget``) are present and valid,
    the session can transition to ``pending_confirmation``.

    This model intentionally mirrors ``OptimizationRequest`` but relaxes
    all ``min_length`` / ``gt`` constraints to ``None``-able optionals so
    that incomplete extractions do not raise validation errors.

    Fields:
        tickers              — List of ticker symbols (e.g. ``["AAPL", "MSFT"]``).
        budget               — Total investment budget in USD.
        min_return           — Minimum acceptable annualised return (legacy).
        max_volatility       — Maximum acceptable annualised volatility (legacy).
        max_weight_per_asset — Maximum weight for any single asset (0-1).
        min_weight_per_asset — Minimum weight for any included asset (0-1).
        sector_constraints   — Sector-level maximum allocation constraints.
        num_assets_to_select — Number of assets to select for the portfolio.
        lookback_days        — Historical data lookback period in calendar days.
        run_quantum          — Whether to run quantum optimization.
        objectives           — Multi-objective matrix rows.
        frontier             — Efficient-frontier sweep configuration.
    """

    tickers: list[str] | None = Field(
        default=None,
        description="List of ticker symbols extracted from the conversation",
    )
    budget: float | None = Field(
        default=None,
        gt=0.0,
        description="Investment budget in USD (must be > 0 when provided)",
    )
    min_return: float | None = Field(
        default=None,
        ge=0.0,
        le=5.0,
        description="Minimum acceptable annualised return (0.0-5.0)",
    )
    max_volatility: float | None = Field(
        default=None,
        ge=0.0,
        le=5.0,
        description="Maximum acceptable annualised volatility (0.0-5.0)",
    )
    max_weight_per_asset: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Maximum weight for any single asset (0.0-1.0)",
    )
    min_weight_per_asset: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum weight for any included asset (0.0-1.0)",
    )
    sector_constraints: list[SectorConstraint] | None = Field(
        default=None,
        max_length=20,
        description="Sector-level maximum allocation constraints",
    )
    num_assets_to_select: int | None = Field(
        default=None,
        ge=2,
        le=50,
        description="Number of assets to select for the portfolio",
    )
    lookback_days: int | None = Field(
        default=None,
        ge=30,
        le=3650,
        description="Historical data lookback period in calendar days",
    )
    run_quantum: bool | None = Field(
        default=None,
        description="Whether to run quantum optimization (QAOA + VQE)",
    )
    objectives: list[BusinessObjective] | None = Field(
        default=None,
        max_length=20,
        description="Multi-objective matrix rows",
    )
    frontier: FrontierConfig | None = Field(
        default=None,
        description="Efficient-frontier sweep configuration",
    )

    @field_validator("tickers")
    @classmethod
    def normalise_tickers(cls, v: list[str] | None) -> list[str] | None:
        """Normalise tickers to uppercase and remove duplicates."""
        if v is None:
            return None
        seen: set[str] = set()
        result: list[str] = []
        for ticker in v:
            normalised = ticker.strip().upper()
            if normalised and normalised not in seen:
                seen.add(normalised)
                result.append(normalised)
        return result or None

    @model_validator(mode="after")
    def validate_weight_bounds(self) -> "ExtractedSlots":  # noqa: N804
        """Ensure min_weight < max_weight when both are specified."""
        if (
            self.min_weight_per_asset is not None
            and self.max_weight_per_asset is not None
            and self.min_weight_per_asset >= self.max_weight_per_asset
        ):
            raise ValueError(
                "min_weight_per_asset must be strictly less than max_weight_per_asset"
            )
        return self

    @property
    def has_required_slots(self) -> bool:
        """Return True when the minimum required slots are present.

        The minimum required slots for a valid ``OptimizationRequest`` are
        ``tickers`` (at least 2 symbols) and ``budget`` (positive number).
        """
        return (
            self.tickers is not None
            and len(self.tickers) >= 2
            and self.budget is not None
            and self.budget > 0
        )

    def missing_required_slots(self) -> list[str]:
        """Return a list of required slot names that are still missing.

        Returns:
            A list of field names that must be filled before the session
            can transition to ``pending_confirmation``.  An empty list
            means all required slots are present.
        """
        missing: list[str] = []
        if self.tickers is None or len(self.tickers) < 2:
            missing.append("tickers")
        if self.budget is None or self.budget <= 0:
            missing.append("budget")
        return missing


# ── LLM structured-output schema ──────────────────────────────────────────────


class LLMSlotFillerOutput(BaseModel):
    """Structured output schema for the GPT-4o slot-filling call.

    This is the JSON schema sent to GPT-4o via
    ``response_format={"type": "json_schema"}``.  The LLM must return
    either a ``clarifying_question`` (when required slots are missing) or
    a populated ``slots`` object (when all required information is present).

    Exactly one of ``clarifying_question`` or ``slots`` should be non-null
    in a well-formed response.  The service layer handles the case where
    both are null (treated as an extraction error).

    Fields:
        clarifying_question — A natural-language question to ask the user
                              when required slot values are missing.  Null
                              when all required slots have been extracted.
        slots               — The extracted ``OptimizationRequest`` fields.
                              Null when a clarifying question is returned.
        confidence          — Optional 0-1 confidence score for the extraction.
                              Used for logging and debugging; not surfaced to
                              the end user.
    """

    clarifying_question: str | None = Field(
        default=None,
        max_length=1_000,
        description=(
            "Natural-language clarifying question to ask the user when required "
            "slot values are missing. Null when all required slots are present."
        ),
    )
    slots: ExtractedSlots | None = Field(
        default=None,
        description=(
            "Extracted OptimizationRequest fields. "
            "Null when a clarifying question is returned."
        ),
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional 0-1 confidence score for the extraction (for logging)",
    )

    @model_validator(mode="after")
    def validate_mutual_exclusion(self) -> "LLMSlotFillerOutput":  # noqa: N804
        """Warn (but do not error) when both fields are null.

        A well-formed LLM response should have exactly one of
        ``clarifying_question`` or ``slots`` populated.  We do not raise
        here because the service layer handles the degenerate case
        gracefully by treating it as an extraction error.
        """
        # Both null is handled by the service layer as an extraction error.
        # Both non-null is unusual but acceptable — the service layer will
        # use the slots and ignore the clarifying question.
        return self


# ── API request schemas ───────────────────────────────────────────────────────


class CreateSessionRequest(BaseModel):
    """Request body for ``POST /api/v1/chat/sessions``.

    Creates a new chat session and optionally sends the first user message
    in a single round-trip.

    Fields:
        initial_message — Optional first user message.  When provided, the
                          service will immediately invoke the LLM slot filler
                          and return the assistant's first response.  When
                          omitted, the session is created in ``collecting``
                          state with an empty message history.
    """

    initial_message: str | None = Field(
        default=None,
        min_length=1,
        max_length=8_000,
        description=(
            "Optional first user message. When provided, the LLM slot filler "
            "is invoked immediately and the response includes the assistant reply."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "initial_message": (
                    "I want to optimize a portfolio of AAPL, MSFT, and GOOGL "
                    "with a $100,000 budget, targeting at least 10% annual return."
                )
            }
        }
    )


class SendMessageRequest(BaseModel):
    """Request body for ``POST /api/v1/chat/sessions/{session_id}/messages``.

    Sends a user message to an existing chat session and triggers the LLM
    slot filler to process the updated conversation history.

    Fields:
        content — The user's message text.
    """

    content: str = Field(
        min_length=1,
        max_length=8_000,
        description="The user's message text (1-8 000 characters)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "content": "Actually, make the budget $50,000 and skip quantum optimization."
            }
        }
    )


# ── API response schemas ──────────────────────────────────────────────────────


class ChatSessionResponse(BaseModel):
    """API representation of a ``ChatSession`` ORM row.

    Returned by all chat endpoints that create or modify a session.

    Fields:
        session_id       — UUID of the session.
        status           — Current lifecycle state.
        messages         — Full conversation history (chronological).
        extracted_slots  — Partial or complete extracted slot values.
        run_id           — UUID of the dispatched optimization run (null until confirmed).
        created_at       — UTC timestamp when the session was created.
        updated_at       — UTC timestamp of the last change.
        expires_at       — UTC timestamp after which the session expires.
        assistant_message — The most recent assistant message (convenience field).
                            Null when the session has no assistant turns yet.
    """

    model_config = ConfigDict(from_attributes=True)

    session_id: str = Field(description="UUID of the chat session")
    status: Literal[
        "collecting", "pending_confirmation", "confirmed", "expired"
    ] = Field(description="Current session lifecycle state")
    messages: list[ChatMessage] = Field(
        default_factory=list,
        description="Full conversation history in chronological order",
    )
    extracted_slots: ExtractedSlots | None = Field(
        default=None,
        description="Partial or complete OptimizationRequest fields extracted so far",
    )
    run_id: str | None = Field(
        default=None,
        description="UUID of the dispatched optimization run (null until confirmed)",
    )
    created_at: datetime = Field(description="UTC timestamp when the session was created")
    updated_at: datetime = Field(description="UTC timestamp of the last change")
    expires_at: datetime = Field(
        description="UTC timestamp after which the session is considered expired"
    )
    assistant_message: str | None = Field(
        default=None,
        description=(
            "The most recent assistant message text. "
            "Null when no assistant turns exist yet."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def extract_assistant_message(cls, data: Any) -> "Any":
        """Populate ``assistant_message`` from the last assistant turn.

        This validator runs before field assignment so it works both when
        constructing from a dict and when using ``model_validate`` with an
        ORM object (``from_attributes=True``).
        """
        # When constructing from an ORM object, ``data`` is the ORM instance.
        # We need to handle both dict-like and attribute-based access.
        if hasattr(data, "messages"):
            messages = data.messages
        elif isinstance(data, dict):
            messages = data.get("messages", [])
        else:
            return data

        if messages:
            # Find the last assistant message
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    if isinstance(data, dict):
                        data = {**data, "assistant_message": msg["content"]}
                    else:
                        # ORM object — we can't mutate it, so return a dict
                        # representation with the extra field injected.
                        data = {
                            "session_id": data.session_id,
                            "status": data.status,
                            "messages": data.messages,
                            "extracted_slots": data.extracted_slots,
                            "run_id": data.run_id,
                            "created_at": data.created_at,
                            "updated_at": data.updated_at,
                            "expires_at": data.expires_at,
                            "assistant_message": msg["content"],
                        }
                    break
        return data


class SendMessageResponse(BaseModel):
    """Response for ``POST /api/v1/chat/sessions/{session_id}/messages``.

    Wraps the updated session state with a convenience ``reply`` field
    containing the assistant's response to the user's message.

    Fields:
        session          — Full updated session state.
        reply            — The assistant's reply text (same as
                           ``session.assistant_message`` but surfaced at
                           the top level for convenience).
        payload_preview  — When the session transitions to
                           ``pending_confirmation``, this field contains
                           the full extracted ``OptimizationRequest``-compatible
                           dict for display in the confirmation card.
                           Null in all other states.
    """

    session: ChatSessionResponse = Field(description="Updated session state")
    reply: str = Field(description="The assistant's reply to the user's message")
    payload_preview: ExtractedSlots | None = Field(
        default=None,
        description=(
            "Full extracted payload when status == 'pending_confirmation'. "
            "Null in all other states."
        ),
    )


class ConfirmSessionRequest(BaseModel):
    """Request body for ``POST /api/v1/chat/sessions/{session_id}/confirm``.

    Confirms the extracted payload and triggers the optimization run.
    The request body is intentionally empty (all required data is already
    stored in the session's ``extracted_slots``), but the explicit endpoint
    provides a clear user intent signal and allows future extension (e.g.
    last-minute slot overrides).

    Fields:
        slot_overrides — Optional dict of slot values to override before
                         dispatching the run.  Useful when the user wants
                         to tweak a value on the confirmation card without
                         going back to the chat.
    """

    slot_overrides: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional slot value overrides applied on top of the extracted "
            "slots before dispatching the optimization run."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "slot_overrides": {"budget": 75000.0, "run_quantum": False}
            }
        }
    )


class ConfirmSessionResponse(BaseModel):
    """Response for ``POST /api/v1/chat/sessions/{session_id}/confirm``.

    Fields:
        session_id — UUID of the confirmed session.
        run_id     — UUID of the dispatched optimization run.
        status     — Session status after confirmation (always ``'confirmed'``).
    """

    session_id: str = Field(description="UUID of the confirmed chat session")
    run_id: str = Field(description="UUID of the dispatched optimization run")
    status: Literal["confirmed"] = Field(
        default="confirmed",
        description="Session status after confirmation",
    )


# ── Annotated type aliases (for use in router signatures) ─────────────────────

#: Convenience alias used in router path parameters.
SessionIdPath = Annotated[
    str,
    Field(
        description="UUID of the chat session",
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    ),
]
