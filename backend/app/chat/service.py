"""Chat service — session lifecycle management and orchestration.

This module implements :class:`ChatService`, the central orchestrator for
the chat assistant feature.  It manages the full lifecycle of a
:class:`~app.db.models.ChatSession`:

1. **Create** — Persist a new ``ChatSession`` in ``collecting`` state.
   If an ``initial_message`` is provided, immediately invoke the LLM slot
   filler and return the assistant's first response.

2. **Send message** — Append the user's message to the conversation history,
   call the LLM slot filler with the full history, append the assistant reply,
   and transition the session to ``pending_confirmation`` when all required
   slots have been extracted.

3. **Confirm** — Validate that the session is in ``pending_confirmation``
   state, apply any last-minute slot overrides, build an
   :class:`~app.schemas.requests.OptimizationRequest`, dispatch the
   optimization run via the existing Celery task, and transition the session
   to ``confirmed``.

4. **Get** — Fetch a session by UUID, performing a lazy expiry check.

Design decisions
----------------
- The service is a **plain async class** (not a FastAPI dependency itself).
  The FastAPI router constructs it with the injected ``AsyncSession`` on
  each request.  This keeps the service testable without FastAPI machinery.
- All database mutations are performed on the caller-supplied
  ``AsyncSession``.  The caller (router) is responsible for committing or
  rolling back the transaction.  The service never calls ``session.commit()``
  directly.
- The service calls the existing ``run_optimization_task.apply_async`` to
  dispatch the Celery task, mirroring the pattern in
  ``app.api.v1.optimize``.  This avoids duplicating the dispatch logic.
- Session TTL defaults to 24 hours and is configurable via the
  ``CHAT_SESSION_TTL_HOURS`` environment variable (added to
  :class:`~app.core.config.Settings`).  If the setting is absent, the
  service falls back to 24 hours.
- Lazy expiry: when a session is fetched and its ``expires_at`` has passed,
  the service transitions it to ``expired`` before raising
  :class:`~app.core.exceptions.ChatSessionExpiredError`.  This avoids a
  separate background sweep job.
- Slot overrides in the confirm endpoint are applied by merging the override
  dict on top of the stored ``extracted_slots`` dict before constructing the
  ``OptimizationRequest``.  Pydantic validation is then re-run on the merged
  dict so invalid overrides are rejected with a clear error.

Error handling
--------------
All domain errors are raised as subclasses of
:class:`~app.core.exceptions.PortfolioOptimizerError` so that the FastAPI
exception handler in ``main.py`` converts them to structured JSON responses
with the correct HTTP status codes.

Mapping:
    ``ChatSessionNotFoundError``         → HTTP 404
    ``ChatSessionExpiredError``          → HTTP 410
    ``ChatSessionAlreadyConfirmedError`` → HTTP 409
    ``ChatInvalidStateError``            → HTTP 409
    ``ChatSlotExtractionError``          → HTTP 502
    ``ChatTooManyMessagesError``         → HTTP 422
    ``ChatSlotOverrideError``            → HTTP 422
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.llm import LLMSlotFiller, get_slot_filler
from app.chat.schemas import (
    ChatMessage,
    ChatSessionResponse,
    ConfirmSessionResponse,
    ExtractedSlots,
    SendMessageResponse,
)
from app.core.config import get_settings
from app.core.exceptions import (
    ChatInvalidStateError,
    ChatSessionAlreadyConfirmedError,
    ChatSessionExpiredError,
    ChatSessionNotFoundError,
    ChatSlotOverrideError,
    ChatTooManyMessagesError,
)
from app.core.logging import get_logger
from app.db.models import ChatSession
from app.schemas.requests import OptimizationRequest


logger = get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

#: Default session TTL in hours.  Sessions that have not been confirmed within
#: this window are considered expired and will no longer accept new messages.
#: The actual value is read from ``Settings.CHAT_SESSION_TTL_HOURS`` at
#: service construction time; this constant is the fallback for tests that
#: construct :class:`ChatService` without a settings object.
DEFAULT_SESSION_TTL_HOURS: int = 24

#: Default maximum number of messages (user + assistant combined) per session.
#: The actual value is read from ``Settings.CHAT_MAX_MESSAGES_PER_SESSION``.
DEFAULT_MAX_MESSAGES_PER_SESSION: int = 50

#: Default maximum number of keys allowed in ``slot_overrides``.
#: The actual value is read from ``Settings.CHAT_MAX_SLOT_OVERRIDE_KEYS``.
DEFAULT_MAX_SLOT_OVERRIDE_KEYS: int = 20

#: The set of valid field names that may appear in ``slot_overrides``.
#: Derived from :class:`~app.chat.schemas.ExtractedSlots` model fields so
#: that any future schema additions are automatically reflected here.
VALID_SLOT_OVERRIDE_KEYS: frozenset[str] = frozenset(
    ExtractedSlots.model_fields.keys()
)

#: Greeting message sent by the assistant when a new session is created
#: without an initial user message.
WELCOME_MESSAGE: str = (
    "Hello! I'm your portfolio optimization assistant. "
    "Tell me about the portfolio you'd like to optimize — "
    "for example, which stocks you're interested in and your investment budget."
)


# ── ChatService ────────────────────────────────────────────────────────────────


class ChatService:
    """Orchestrates the chat session lifecycle for the portfolio assistant.

    Each instance is bound to a single ``AsyncSession`` and is intended to
    be constructed per-request by the FastAPI router.

    Args:
        db:          Async SQLAlchemy session (injected by the router).
        slot_filler: Optional :class:`~app.chat.llm.LLMSlotFiller` instance.
                     When ``None``, the module-level singleton returned by
                     :func:`~app.chat.llm.get_slot_filler` is used.  Inject
                     a mock in tests.
        session_ttl_hours: Session TTL in hours.  When ``None`` (default),
                           the value is read from
                           ``Settings.CHAT_SESSION_TTL_HOURS``.
        max_messages_per_session: Maximum total messages (user + assistant)
                           allowed per session before
                           :class:`~app.core.exceptions.ChatTooManyMessagesError`
                           is raised.  When ``None`` (default), the value is
                           read from ``Settings.CHAT_MAX_MESSAGES_PER_SESSION``.
        max_slot_override_keys: Maximum number of keys allowed in the
                           ``slot_overrides`` dict on the confirm endpoint.
                           When ``None`` (default), the value is read from
                           ``Settings.CHAT_MAX_SLOT_OVERRIDE_KEYS``.

    Example::

        service = ChatService(db=session)
        chat_session = await service.create_session(initial_message="Optimize AAPL, MSFT")
        response = await service.send_message(
            session_id=chat_session.session_id,
            content="My budget is $50,000",
        )
    """

    def __init__(
        self,
        db: AsyncSession,
        slot_filler: LLMSlotFiller | None = None,
        session_ttl_hours: int | None = None,
        max_messages_per_session: int | None = None,
        max_slot_override_keys: int | None = None,
    ) -> None:
        self._db = db
        self._slot_filler: LLMSlotFiller = slot_filler or get_slot_filler()

        # Read limits from config, falling back to the module-level defaults.
        # Callers (and tests) may override individual limits by passing them
        # explicitly; ``None`` means "use the configured value".
        _settings = get_settings()
        self._session_ttl_hours: int = (
            session_ttl_hours
            if session_ttl_hours is not None
            else _settings.CHAT_SESSION_TTL_HOURS
        )
        self._max_messages_per_session: int = (
            max_messages_per_session
            if max_messages_per_session is not None
            else _settings.CHAT_MAX_MESSAGES_PER_SESSION
        )
        self._max_slot_override_keys: int = (
            max_slot_override_keys
            if max_slot_override_keys is not None
            else _settings.CHAT_MAX_SLOT_OVERRIDE_KEYS
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    async def create_session(
        self,
        initial_message: str | None = None,
    ) -> "ChatSessionResponse":
        """Create a new chat session and optionally process the first message.

        If ``initial_message`` is provided, the LLM slot filler is invoked
        immediately and the assistant's first response is included in the
        returned session.  This saves one round-trip for clients that want to
        send the first message at session creation time.

        If ``initial_message`` is ``None``, the session is created in
        ``collecting`` state with a welcome message from the assistant.

        Args:
            initial_message: Optional first user message text.

        Returns:
            A :class:`~app.chat.schemas.ChatSessionResponse` representing
            the newly created session.

        Raises:
            ChatSlotExtractionError: If the LLM call fails when
                ``initial_message`` is provided.
        """
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=self._session_ttl_hours)
        session_id = str(uuid.uuid4())

        session = ChatSession(
            session_id=session_id,
            status="collecting",
            messages=[],
            extracted_slots=None,
            run_id=None,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
        self._db.add(session)
        # Flush so the row exists in the DB within the current transaction
        # before we potentially call the LLM (which may take a few seconds).
        await self._db.flush()

        logger.info(
            "chat_session_created",
            session_id=session_id,
            has_initial_message=initial_message is not None,
        )

        if initial_message is not None:
            # Process the initial message inline — this appends the user
            # message, calls the LLM, and appends the assistant reply.
            await self._process_message(session, content=initial_message)
        else:
            # No initial message — send a welcome greeting from the assistant.
            session.append_message("assistant", WELCOME_MESSAGE)

        return self._to_response(session)

    async def send_message(
        self,
        session_id: str,
        content: str,
    ) -> "SendMessageResponse":
        """Append a user message and return the assistant's reply.

        Fetches the session, validates it is in an active state, appends the
        user message, calls the LLM slot filler, appends the assistant reply,
        and transitions the session to ``pending_confirmation`` when all
        required slots have been extracted.

        Args:
            session_id: UUID of the target session.
            content:    The user's message text.

        Returns:
            A :class:`~app.chat.schemas.SendMessageResponse` containing the
            updated session state and the assistant's reply.

        Raises:
            ChatSessionNotFoundError:  If no session with ``session_id`` exists.
            ChatSessionExpiredError:   If the session has expired.
            ChatInvalidStateError:     If the session is in a terminal state
                                       (``confirmed`` or ``expired``).
            ChatSlotExtractionError:   If the LLM call fails.
        """
        session = await self._get_session_or_raise(session_id)
        self._assert_accepting_messages(session)

        await self._process_message(session, content=content)

        # Build the response
        session_response = self._to_response(session)
        reply = session_response.assistant_message or ""
        payload_preview = (
            session_response.extracted_slots
            if session.status == "pending_confirmation"
            else None
        )

        return SendMessageResponse(
            session=session_response,
            reply=reply,
            payload_preview=payload_preview,
        )

    async def confirm_session(
        self,
        session_id: str,
        slot_overrides: dict[str, Any] | None = None,
    ) -> "ConfirmSessionResponse":
        """Confirm the extracted payload and dispatch the optimization run.

        Validates that the session is in ``pending_confirmation`` state,
        applies any last-minute slot overrides, constructs an
        :class:`~app.schemas.requests.OptimizationRequest`, persists a
        pending :class:`~app.db.models.OptimizationRun` record, dispatches
        the Celery task, and transitions the session to ``confirmed``.

        Args:
            session_id:     UUID of the session to confirm.
            slot_overrides: Optional dict of slot values to override before
                            dispatching.  Applied on top of the stored
                            ``extracted_slots``.

        Returns:
            A :class:`~app.chat.schemas.ConfirmSessionResponse` with the
            ``session_id`` and the newly dispatched ``run_id``.

        Raises:
            ChatSessionNotFoundError:          If no session exists.
            ChatSessionExpiredError:           If the session has expired.
            ChatSessionAlreadyConfirmedError:  If the session is already confirmed.
            ChatInvalidStateError:             If the session is not in
                                               ``pending_confirmation`` state.
            ValueError:                        If the merged slots cannot be
                                               parsed into a valid
                                               ``OptimizationRequest``.
        """
        session = await self._get_session_or_raise(session_id)

        # Guard: already confirmed
        if session.status == "confirmed":
            raise ChatSessionAlreadyConfirmedError(
                session_id=session_id,
                run_id=session.run_id,
            )

        # Guard: expired
        if session.status == "expired" or session.is_expired:
            if not session.is_terminal:
                session.mark_expired()
            raise ChatSessionExpiredError(session_id=session_id)

        # Guard: must be in pending_confirmation state
        if session.status != "pending_confirmation":
            raise ChatInvalidStateError(
                session_id=session_id,
                current_status=session.status,
                required_status="pending_confirmation",
            )

        # Build the OptimizationRequest from stored slots + overrides
        optimization_request = self._build_optimization_request(
            session=session,
            slot_overrides=slot_overrides,
        )

        # Dispatch the optimization run.
        # On failure: revert session status to "pending_confirmation" so the
        # user can retry, then re-raise as a service error.
        try:
            run_id = await self._dispatch_optimization_run(optimization_request)
        except Exception as exc:
            # Revert session status so the user can retry
            session.status = "pending_confirmation"
            logger.error(
                "chat_dispatch_failed_reverting_status",
                session_id=session_id,
                error=str(exc),
            )
            raise ChatInvalidStateError(
                session_id=session_id,
                current_status="pending_confirmation",
                required_status="pending_confirmation",
            ) from exc

        # Transition session to confirmed
        session.mark_confirmed(run_id=run_id)

        logger.info(
            "chat_session_confirmed",
            session_id=session_id,
            run_id=run_id,
            tickers=optimization_request.tickers,
            budget=optimization_request.budget,
        )

        # Generate a short-lived HMAC token for WebSocket authentication
        ws_token: str | None = None
        try:
            from app.core.config import get_settings as _get_settings  # noqa: PLC0415
            from app.core.security import create_ws_token  # noqa: PLC0415

            _settings = _get_settings()
            ws_token = create_ws_token(run_id=run_id, secret_key=_settings.SECRET_KEY)
        except Exception as exc:
            logger.warning(
                "chat_ws_token_generation_failed",
                session_id=session_id,
                run_id=run_id,
                error=str(exc),
            )

        return ConfirmSessionResponse(
            session_id=session_id,
            run_id=run_id,
            status="confirmed",
            ws_token=ws_token,
        )

    async def get_session(self, session_id: str) -> "ChatSessionResponse":
        """Fetch a session by UUID, performing a lazy expiry check.

        If the session's ``expires_at`` has passed and it is not already in
        a terminal state, it is transitioned to ``expired`` before the
        response is returned.

        Args:
            session_id: UUID of the session to fetch.

        Returns:
            A :class:`~app.chat.schemas.ChatSessionResponse`.

        Raises:
            ChatSessionNotFoundError: If no session with ``session_id`` exists.
        """
        session = await self._get_session_or_raise(session_id)
        # Lazy expiry: mark expired if TTL has elapsed (but don't raise here —
        # GET is a read operation and should return the current state).
        if not session.is_terminal and session.is_expired:
            session.mark_expired()
            logger.info(
                "chat_session_lazily_expired",
                session_id=session_id,
            )
        return self._to_response(session)

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _get_session_or_raise(self, session_id: str) -> "ChatSession":
        """Fetch a ``ChatSession`` by UUID or raise ``ChatSessionNotFoundError``.

        Args:
            session_id: UUID string of the session.

        Returns:
            The :class:`~app.db.models.ChatSession` ORM instance.

        Raises:
            ChatSessionNotFoundError: If no matching session exists.
        """
        result = await self._db.execute(
            select(ChatSession).where(ChatSession.session_id == session_id)
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise ChatSessionNotFoundError(session_id=session_id)
        return session

    def _assert_accepting_messages(self, session: ChatSession) -> "None":
        """Raise an appropriate exception if the session cannot accept messages.

        A session accepts messages only when it is in ``collecting`` or
        ``pending_confirmation`` state and has not expired.

        Args:
            session: The :class:`~app.db.models.ChatSession` to check.

        Raises:
            ChatSessionExpiredError:  If the session has expired (either by
                                      status or by TTL).
            ChatSessionAlreadyConfirmedError: If the session is confirmed.
            ChatInvalidStateError:    If the session is in any other terminal
                                      state.
        """
        # Lazy expiry check
        if session.is_expired and not session.is_terminal:
            session.mark_expired()

        if session.status == "expired":
            raise ChatSessionExpiredError(session_id=session.session_id)

        if session.status == "confirmed":
            raise ChatSessionAlreadyConfirmedError(
                session_id=session.session_id,
                run_id=session.run_id,
            )

        # Any other terminal state (future-proofing)
        if session.is_terminal:
            raise ChatInvalidStateError(
                session_id=session.session_id,
                current_status=session.status,
                required_status=["collecting", "pending_confirmation"],
            )

    async def _process_message(
        self,
        session: ChatSession,
        content: str,
    ) -> "None":
        """Append a user message, call the LLM, and append the assistant reply.

        This is the core slot-filling loop:

        1. Append the user message to the conversation history.
        2. Build the ``existing_slots`` dict from the session's current
           ``extracted_slots`` (or empty dict if none yet).
        3. Call the LLM slot filler with the full conversation history.
        4. Merge newly extracted slots with existing slots.
        5. If all required slots are present, transition to
           ``pending_confirmation`` and append a confirmation prompt.
        6. Otherwise, append the LLM's clarifying question.

        Args:
            session: The :class:`~app.db.models.ChatSession` to update.
            content: The user's message text.

        Raises:
            ChatTooManyMessagesError: If the session has already reached the
                                      configured maximum message count.
            ChatSlotExtractionError: If the LLM call fails or returns an
                                     unparseable response.
        """
        # Step 0: Enforce the per-session message limit.
        # Count existing messages *before* appending the new user turn so
        # that the limit check is consistent regardless of whether the
        # assistant reply is counted.  We check against the current count
        # plus 2 (the incoming user message + the forthcoming assistant
        # reply) to ensure we never exceed the limit after this call.
        current_count = len(session.messages or [])
        if current_count + 2 > self._max_messages_per_session:
            logger.warning(
                "chat_session_message_limit_reached",
                session_id=session.session_id,
                current_count=current_count,
                max_messages=self._max_messages_per_session,
            )
            raise ChatTooManyMessagesError(
                session_id=session.session_id,
                message_count=current_count,
                max_messages=self._max_messages_per_session,
            )

        # Step 1: Append user message
        session.append_message("user", content)

        # Step 2: Build existing slots context
        existing_slots: dict[str, Any] = session.extracted_slots or {}

        # Step 3: Call the LLM slot filler
        # Convert stored message dicts to ChatMessage objects for the filler.
        chat_messages = [
            ChatMessage(role=msg["role"], content=msg["content"])
            for msg in (session.messages or [])
            if msg.get("role") in ("user", "assistant")
        ]

        logger.debug(
            "chat_slot_filler_invoked",
            session_id=session.session_id,
            num_messages=len(chat_messages),
            existing_slots=list(existing_slots.keys()),
        )

        llm_output = await self._slot_filler.extract_slots(
            messages=chat_messages,
            existing_slots=existing_slots,
        )

        # Step 4: Merge newly extracted slots with existing slots
        if llm_output.slots is not None:
            session.extracted_slots = self._merge_slots(
                existing=existing_slots,
                new_slots=llm_output.slots,
            )

        # Step 5: Determine the assistant reply and next state
        # Re-validate the merged slots to check completeness
        try:
            current_slots = ExtractedSlots.model_validate(
                session.extracted_slots or {}
            )
        except Exception:
            current_slots = ExtractedSlots()

        if current_slots.has_required_slots:
            # All required slots are present — transition to pending_confirmation
            if session.status != "pending_confirmation":
                session.mark_pending_confirmation(
                    extracted_slots=session.extracted_slots or {}
                )
                logger.info(
                    "chat_session_pending_confirmation",
                    session_id=session.session_id,
                    tickers=current_slots.tickers,
                    budget=current_slots.budget,
                )

            # Build a confirmation prompt summarising the extracted payload
            assistant_reply = self._build_confirmation_prompt(current_slots)
        # Still collecting — use the LLM's clarifying question
        elif llm_output.clarifying_question:
            assistant_reply = llm_output.clarifying_question
        else:
            # Fallback: generate a generic clarifying question
            missing = current_slots.missing_required_slots()
            assistant_reply = self._build_fallback_clarifying_question(missing)

        # Step 6: Append the assistant reply
        session.append_message("assistant", assistant_reply)

        logger.debug(
            "chat_message_processed",
            session_id=session.session_id,
            session_status=session.status,
            has_required_slots=current_slots.has_required_slots,
        )

    def _merge_slots(
        self,
        existing: dict[str, Any],
        new_slots: ExtractedSlots,
    ) -> dict[str, Any]:
        """Merge newly extracted slots into the existing slot dict.

        New non-null values overwrite existing values.  Existing values are
        preserved when the new extraction returns ``None`` for a field.

        Args:
            existing:  The current ``extracted_slots`` dict from the session.
            new_slots: The :class:`~app.chat.schemas.ExtractedSlots` returned
                       by the LLM slot filler.

        Returns:
            A new dict with the merged slot values.
        """
        # Start from the existing slots
        merged = dict(existing)

        # Overwrite with non-None values from the new extraction
        new_dict = new_slots.model_dump(exclude_none=True)
        merged.update(new_dict)

        return merged

    def _build_confirmation_prompt(self, slots: ExtractedSlots) -> str:
        """Build a human-readable confirmation prompt from the extracted slots.

        Summarises the key parameters so the user can review them before
        confirming the optimization run.

        Args:
            slots: The fully-populated :class:`~app.chat.schemas.ExtractedSlots`.

        Returns:
            A multi-line string describing the extracted parameters.
        """
        lines: list[str] = [
            "Great! I've gathered all the information needed. "
            "Here's a summary of your optimization request:",
            "",
        ]

        if slots.tickers:
            lines.append(f"• **Tickers**: {', '.join(slots.tickers)}")

        if slots.budget is not None:
            lines.append(f"• **Budget**: ${slots.budget:,.2f}")

        if slots.min_return is not None:
            lines.append(f"• **Minimum return**: {slots.min_return * 100:.1f}%")

        if slots.max_volatility is not None:
            lines.append(f"• **Maximum volatility**: {slots.max_volatility * 100:.1f}%")

        if slots.max_weight_per_asset is not None:
            lines.append(
                f"• **Max weight per asset**: {slots.max_weight_per_asset * 100:.0f}%"
            )

        if slots.min_weight_per_asset is not None:
            lines.append(
                f"• **Min weight per asset**: {slots.min_weight_per_asset * 100:.0f}%"
            )

        if slots.num_assets_to_select is not None:
            lines.append(f"• **Assets to select**: {slots.num_assets_to_select}")

        if slots.lookback_days is not None:
            lines.append(f"• **Lookback period**: {slots.lookback_days} days")

        if slots.run_quantum is not None:
            quantum_str = "Yes" if slots.run_quantum else "No"
            lines.append(f"• **Quantum optimization**: {quantum_str}")

        if slots.sector_constraints:
            sector_strs = [
                f"{sc.sector} ≤ {sc.max_weight * 100:.0f}%"
                for sc in slots.sector_constraints
            ]
            lines.append(f"• **Sector constraints**: {', '.join(sector_strs)}")

        lines.extend([
            "",
            "Would you like to proceed with this optimization? "
            "Reply **confirm** to start, or let me know if you'd like to change anything.",
        ])

        return "\n".join(lines)

    @staticmethod
    def _build_fallback_clarifying_question(missing: list[str]) -> str:
        """Build a generic clarifying question for missing required slots.

        Used when the LLM slot filler returns neither a clarifying question
        nor a complete slot set.

        Args:
            missing: List of required slot names that are still missing.

        Returns:
            A natural-language question asking for the missing information.
        """
        if not missing:
            return (
                "I have all the information I need. "
                "Would you like to proceed with the optimization?"
            )

        field_descriptions: dict[str, str] = {
            "tickers": "the stock tickers you'd like to include (e.g. AAPL, MSFT, GOOGL)",
            "budget": "your total investment budget in USD",
        }

        missing_descriptions = [
            field_descriptions.get(f, f) for f in missing
        ]

        if len(missing_descriptions) == 1:
            return f"Could you please tell me {missing_descriptions[0]}?"
        else:
            joined = ", ".join(missing_descriptions[:-1])
            last = missing_descriptions[-1]
            return f"Could you please tell me {joined} and {last}?"

    def _validate_slot_overrides(
        self,
        session_id: str,
        slot_overrides: dict[str, Any],
    ) -> "None":
        """Validate the ``slot_overrides`` dict before applying it.

        Enforces two safety rules:

        1. **Key count limit** — the number of override keys must not exceed
           ``self._max_slot_override_keys`` (configured via
           ``Settings.CHAT_MAX_SLOT_OVERRIDE_KEYS``).  This prevents
           excessively large payloads from being accepted.

        2. **Key name allowlist** — every key must be a recognised field name
           from :class:`~app.chat.schemas.ExtractedSlots`.  Unknown keys are
           rejected to prevent injection of arbitrary data into the
           ``OptimizationRequest`` construction path.

        Args:
            session_id:     UUID of the session (for error context).
            slot_overrides: The override dict to validate.

        Raises:
            ChatSlotOverrideError: If the key count exceeds the limit or if
                                   any key is not a recognised slot field.
        """
        num_keys = len(slot_overrides)
        if num_keys > self._max_slot_override_keys:
            logger.warning(
                "chat_slot_override_too_many_keys",
                session_id=session_id,
                num_keys=num_keys,
                max_keys=self._max_slot_override_keys,
            )
            raise ChatSlotOverrideError(
                session_id=session_id,
                message=(
                    f"slot_overrides contains {num_keys} keys, which exceeds "
                    f"the maximum of {self._max_slot_override_keys}."
                ),
                max_keys=self._max_slot_override_keys,
            )

        invalid_keys = [
            key for key in slot_overrides if key not in VALID_SLOT_OVERRIDE_KEYS
        ]
        if invalid_keys:
            logger.warning(
                "chat_slot_override_invalid_keys",
                session_id=session_id,
                invalid_keys=invalid_keys,
                valid_keys=sorted(VALID_SLOT_OVERRIDE_KEYS),
            )
            raise ChatSlotOverrideError(
                session_id=session_id,
                message=(
                    f"slot_overrides contains unrecognised field names: "
                    f"{invalid_keys!r}. "
                    f"Allowed fields: {sorted(VALID_SLOT_OVERRIDE_KEYS)!r}."
                ),
                invalid_keys=invalid_keys,
                max_keys=self._max_slot_override_keys,
            )

    def _build_optimization_request(
        self,
        session: ChatSession,
        slot_overrides: dict[str, Any] | None = None,
    ) -> "OptimizationRequest":
        """Build an :class:`~app.schemas.requests.OptimizationRequest` from session slots.

        Merges the session's ``extracted_slots`` with any provided overrides
        and validates the result through Pydantic.

        Args:
            session:        The confirmed :class:`~app.db.models.ChatSession`.
            slot_overrides: Optional dict of slot values to override.

        Returns:
            A validated :class:`~app.schemas.requests.OptimizationRequest`.

        Raises:
            ChatInvalidStateError:  If the session has no extracted slots.
            ChatSlotOverrideError:  If ``slot_overrides`` contains too many
                                    keys or unrecognised field names.
            ValueError:             If the merged slots fail Pydantic validation.
        """
        if not session.extracted_slots:
            raise ChatInvalidStateError(
                session_id=session.session_id,
                current_status=session.status,
                required_status="pending_confirmation",
                details={"reason": "No extracted slots found in session"},
            )

        # Validate slot_overrides before applying them.
        if slot_overrides:
            self._validate_slot_overrides(
                session_id=session.session_id,
                slot_overrides=slot_overrides,
            )

        # Start from the stored extracted slots
        slots_dict: dict[str, Any] = dict(session.extracted_slots)

        # Apply overrides (if any)
        if slot_overrides:
            slots_dict.update(slot_overrides)

        # Set sensible defaults for optional fields not extracted by the LLM
        slots_dict.setdefault("lookback_days", 365)
        slots_dict.setdefault("run_quantum", True)

        # Validate through OptimizationRequest (raises ValueError on failure)
        try:
            request = OptimizationRequest.model_validate(slots_dict)
        except Exception as exc:
            logger.warning(
                "chat_optimization_request_validation_failed",
                session_id=session.session_id,
                error=str(exc),
                slots_dict=slots_dict,
            )
            raise

        return request

    async def _dispatch_optimization_run(
        self,
        request: OptimizationRequest,
    ) -> str:
        """Persist a pending run record and dispatch the Celery task.

        Mirrors the dispatch logic in ``app.api.v1.optimize`` to ensure
        consistent behaviour.

        Args:
            request: The validated :class:`~app.schemas.requests.OptimizationRequest`.

        Returns:
            The UUID string of the newly created optimization run.
        """
        from app.db.models import OptimizationRun  # noqa: PLC0415
        from app.workers.tasks import run_optimization_task  # noqa: PLC0415

        run_id = str(uuid.uuid4())

        # Persist the pending run record within the current transaction
        run = OptimizationRun(
            run_id=run_id,
            status="pending",
            tickers=request.tickers,
            budget=request.budget,
            request_params=request.model_dump(mode="json"),
        )
        self._db.add(run)
        await self._db.flush()

        logger.info(
            "chat_optimization_dispatched",
            run_id=run_id,
            tickers=request.tickers,
            budget=request.budget,
            run_quantum=request.run_quantum,
        )

        # Dispatch the Celery task (fire-and-forget)
        run_optimization_task.apply_async(
            kwargs={
                "run_id": run_id,
                "request_dict": request.model_dump(mode="json"),
            },
            task_id=run_id,
            queue="quantum" if request.run_quantum else "default",
        )

        return run_id

    @staticmethod
    def _to_response(session: ChatSession) -> "ChatSessionResponse":
        """Convert a :class:`~app.db.models.ChatSession` ORM instance to a response schema.

        Uses ``model_validate`` with ``from_attributes=True`` (configured on
        :class:`~app.chat.schemas.ChatSessionResponse`) to map ORM attributes
        to Pydantic fields.

        Args:
            session: The ORM instance to convert.

        Returns:
            A :class:`~app.chat.schemas.ChatSessionResponse`.
        """
        return ChatSessionResponse.model_validate(session)


# ── Module-level factory ───────────────────────────────────────────────────────


def get_chat_service(
    db: AsyncSession,
    slot_filler: LLMSlotFiller | None = None,
    session_ttl_hours: int | None = None,
    max_messages_per_session: int | None = None,
    max_slot_override_keys: int | None = None,
) -> "ChatService":
    """Construct a :class:`ChatService` instance.

    This factory is provided as a convenience for the FastAPI router.  It
    accepts the same arguments as :class:`ChatService.__init__` and returns
    a new instance bound to the given ``AsyncSession``.

    In tests, pass a mock ``slot_filler`` to avoid real LLM calls::

        service = get_chat_service(
            db=mock_session,
            slot_filler=MockLLMSlotFiller(),
        )

    Args:
        db:                       Async SQLAlchemy session.
        slot_filler:              Optional mock slot filler for testing.
        session_ttl_hours:        Session TTL in hours.  ``None`` reads from
                                  ``Settings.CHAT_SESSION_TTL_HOURS``.
        max_messages_per_session: Max messages per session.  ``None`` reads
                                  from ``Settings.CHAT_MAX_MESSAGES_PER_SESSION``.
        max_slot_override_keys:   Max slot override keys.  ``None`` reads from
                                  ``Settings.CHAT_MAX_SLOT_OVERRIDE_KEYS``.

    Returns:
        A new :class:`ChatService` instance.
    """
    return ChatService(
        db=db,
        slot_filler=slot_filler,
        session_ttl_hours=session_ttl_hours,
        max_messages_per_session=max_messages_per_session,
        max_slot_override_keys=max_slot_override_keys,
    )
