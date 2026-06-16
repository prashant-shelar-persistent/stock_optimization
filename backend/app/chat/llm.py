"""LLM slot-filler service for the Chat Assistant.

This module implements :class:`LLMSlotFiller`, which calls GPT-4o with
structured outputs (``response_format={"type": "json_schema"}``) to
extract ``OptimizationRequest`` slot values from natural-language
conversation messages.

Design decisions
----------------
- Uses the ``openai`` SDK directly (``AsyncOpenAI``) rather than
  LangChain so that the structured-output ``response_format`` parameter
  can be passed verbatim without any LangChain abstraction layer.
- The ``LLMSlotFiller`` class accepts an optional ``AsyncOpenAI`` client
  in its constructor so that unit tests can inject a mock without
  patching module-level globals.
- When no ``OPENAI_API_KEY`` is configured, the filler raises
  :class:`~app.core.exceptions.ChatSlotExtractionError` immediately
  rather than making a network call that would fail anyway.
- All OpenAI SDK exceptions are caught and re-raised as
  :class:`~app.core.exceptions.ChatSlotExtractionError` so that callers
  never need to import ``openai`` exception types.
- A module-level singleton is provided via :func:`get_slot_filler` for
  use by the service layer.  The singleton is cached with
  ``functools.lru_cache`` so the ``AsyncOpenAI`` client is created only
  once per process.
- The fallback path (no API key) returns a deterministic clarifying
  question using :func:`~app.chat.prompts.format_missing_fields_description`
  so that the service layer can still function in test / dry-run mode.

Multi-turn slot filling
-----------------------
The filler receives the **full conversation history** on every call, not
just the latest message.  This allows GPT-4o to see the entire context
and correctly merge new information with previously extracted values.

The ``existing_slots`` dict is injected into the system prompt via
:func:`~app.chat.prompts.build_system_message` so the model knows what
has already been extracted and avoids re-asking for it.

Structured output schema
------------------------
The JSON schema sent to GPT-4o is built by
:func:`~app.chat.prompts.build_response_schema` and mirrors the
:class:`~app.chat.schemas.LLMSlotFillerOutput` Pydantic model:

.. code-block:: json

    {
      "clarifying_question": "<string or null>",
      "slots": { ... ExtractedSlots fields ... } | null,
      "confidence": <number 0-1 or null>
    }

The parsed JSON is validated through
:class:`~app.chat.schemas.LLMSlotFillerOutput` before being returned to
the caller.
"""

from __future__ import annotations

import functools
import json
from typing import TYPE_CHECKING, Any

from app.chat.prompts import (
    CLARIFY_HINT_TEMPLATE,
    build_response_schema,
    build_system_message,
    format_missing_fields_description,
)
from app.chat.schemas import ExtractedSlots, LLMSlotFillerOutput
from app.core.config import get_settings
from app.core.exceptions import ChatSlotExtractionError
from app.core.logging import get_logger


if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

#: Default GPT-4o model variant that supports structured outputs.
#: Using the dated variant for reproducibility; update when a newer
#: stable version is available.
DEFAULT_MODEL: str = "gpt-4o-2024-08-06"

#: Maximum tokens to request in the completion.  Slot-filling responses
#: are compact JSON objects; 1 024 tokens is more than sufficient.
MAX_TOKENS: int = 1_024

#: Temperature for the slot-filling call.  Low temperature (0.1) keeps
#: the model deterministic and reduces hallucination of ticker symbols.
TEMPERATURE: float = 0.1


# ── LLMSlotFiller ─────────────────────────────────────────────────────────────


class LLMSlotFiller:
    """GPT-4o structured-output slot filler for portfolio optimization.

    Extracts ``OptimizationRequest`` slot values from natural-language
    conversation messages using GPT-4o's structured-output feature.

    Supports multi-turn conversations: the full message history is sent
    on every call so the model can see the complete context.

    Args:
        client: Optional pre-constructed ``AsyncOpenAI`` client.  When
            ``None``, a client is lazily created from the configured
            ``OPENAI_API_KEY`` on the first call to
            :meth:`extract_slots`.  Inject a mock client in tests.
        model: GPT-4o model variant to use.  Defaults to
            :data:`DEFAULT_MODEL`.

    Example::

        filler = LLMSlotFiller()
        result = await filler.extract_slots(
            messages=[ChatMessage(role="user", content="Optimize AAPL, MSFT with $50k")],
            existing_slots={},
        )
        if result.slots is not None:
            print(result.slots.tickers)  # ["AAPL", "MSFT"]
        else:
            print(result.clarifying_question)
    """

    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._client: AsyncOpenAI | None = client
        self._model: str = model

    # ── Public API ────────────────────────────────────────────────────────────

    async def extract_slots(
        self,
        messages: list[Any],
        existing_slots: dict[str, Any],
    ) -> LLMSlotFillerOutput:
        """Extract slot values from the conversation history.

        Sends the full conversation history to GPT-4o with a structured-
        output schema and returns the parsed :class:`LLMSlotFillerOutput`.

        When all required slots (``tickers`` and ``budget``) are present,
        the returned object has ``slots`` populated and
        ``clarifying_question`` set to ``None``.

        When required slots are missing, the returned object has
        ``clarifying_question`` populated and ``slots`` set to ``None``.

        Args:
            messages: Full conversation history as a list of objects with
                ``role`` and ``content`` attributes (or dicts with those
                keys).  Typically a list of
                :class:`~app.chat.schemas.ChatMessage` instances.
            existing_slots: Dict of slot values already extracted in
                earlier turns.  Injected into the system prompt so the
                model avoids re-asking for known information.

        Returns:
            A :class:`~app.chat.schemas.LLMSlotFillerOutput` instance
            with either ``slots`` or ``clarifying_question`` populated.

        Raises:
            ChatSlotExtractionError: When ``OPENAI_API_KEY`` is not
                configured, when the OpenAI API call fails, or when the
                model returns a response that cannot be parsed into the
                expected schema.

        Note:
            This method is idempotent with respect to the conversation
            history — calling it multiple times with the same messages
            and existing_slots will produce the same result (modulo
            model non-determinism at temperature > 0).
        """
        settings = get_settings()

        # ── Ensure we have an API key ─────────────────────────────────────────
        if self._client is None:
            api_key = settings.OPENAI_API_KEY
            if not api_key:
                logger.warning(
                    "chat_slot_filler_no_api_key",
                    message="OPENAI_API_KEY not configured; using fallback clarifying question",
                )
                return self._fallback_response(existing_slots)

            # Lazy-import to avoid loading the openai package at module
            # import time (keeps startup fast when the key is not set).
            try:
                from openai import AsyncOpenAI  # noqa: PLC0415
            except ImportError as exc:
                raise ChatSlotExtractionError(
                    "The 'openai' package is not installed. "
                    "Install it with: pip install openai",
                    raw_response=None,
                ) from exc

            self._client = AsyncOpenAI(api_key=api_key)

        # ── Build the messages array ──────────────────────────────────────────
        openai_messages = self._build_openai_messages(messages, existing_slots)

        # ── Call GPT-4o with structured outputs ───────────────────────────────
        raw_content = await self._call_openai(openai_messages)

        # ── Parse and validate the response ──────────────────────────────────
        return self._parse_response(raw_content)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_openai_messages(
        self,
        messages: list[Any],
        existing_slots: dict[str, Any],
    ) -> list[dict[str, str]]:
        """Build the ``messages`` array for the OpenAI API call.

        Prepends the system message (which includes the existing slots
        context) and maps each conversation turn to the OpenAI message
        format.

        Args:
            messages: Conversation history (ChatMessage objects or dicts).
            existing_slots: Currently extracted slot values.

        Returns:
            List of ``{"role": ..., "content": ...}`` dicts.
        """
        system_content = build_system_message(existing_slots)
        openai_messages: list[dict[str, str]] = [
            {"role": "system", "content": system_content}
        ]

        for msg in messages:
            # Support both attribute-based (ChatMessage) and dict-based access.
            if hasattr(msg, "role") and hasattr(msg, "content"):
                role = str(msg.role)
                content = str(msg.content)
            elif isinstance(msg, dict):
                role = str(msg.get("role", "user"))
                content = str(msg.get("content", ""))
            else:
                logger.warning(
                    "chat_slot_filler_unknown_message_type",
                    message_type=type(msg).__name__,
                )
                continue

            # Skip system messages from the conversation history — the
            # system prompt is already prepended above.
            if role == "system":
                continue

            # Only include user and assistant roles.
            if role not in ("user", "assistant"):
                logger.debug(
                    "chat_slot_filler_skipping_unknown_role",
                    role=role,
                )
                continue

            if content.strip():
                openai_messages.append({"role": role, "content": content})

        return openai_messages

    async def _call_openai(
        self,
        openai_messages: list[dict[str, str]],
    ) -> str:
        """Call the OpenAI Chat Completions API with structured outputs.

        Args:
            openai_messages: The messages array to send.

        Returns:
            The raw JSON string from the model's response.

        Raises:
            ChatSlotExtractionError: On any OpenAI API error.
        """
        assert self._client is not None, "Client must be initialised before calling"

        response_schema = build_response_schema()

        logger.info(
            "chat_slot_filler_calling_gpt4o",
            model=self._model,
            num_messages=len(openai_messages),
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=openai_messages,  # type: ignore[arg-type]
                response_format={
                    "type": "json_schema",
                    "json_schema": response_schema,
                },
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )
        except Exception as exc:
            # Catch all OpenAI SDK exceptions (AuthenticationError,
            # RateLimitError, APIConnectionError, etc.) and translate
            # them to ChatSlotExtractionError so callers don't need to
            # import openai exception types.
            error_type = type(exc).__name__
            logger.error(
                "chat_slot_filler_openai_error",
                error_type=error_type,
                error=str(exc),
            )
            raise ChatSlotExtractionError(
                f"OpenAI API call failed: {error_type}: {exc}",
                raw_response=None,
            ) from exc

        # Extract the content string from the response.
        choice = response.choices[0]
        raw_content = choice.message.content

        if raw_content is None:
            raise ChatSlotExtractionError(
                "GPT-4o returned an empty response (content is None). "
                "This may indicate a content-filter refusal.",
                raw_response=None,
            )

        logger.info(
            "chat_slot_filler_gpt4o_succeeded",
            model=self._model,
            finish_reason=choice.finish_reason,
            response_length=len(raw_content),
        )

        return raw_content

    def _parse_response(self, raw_content: str) -> LLMSlotFillerOutput:
        """Parse and validate the raw JSON response from GPT-4o.

        Args:
            raw_content: The raw JSON string from the model's response.

        Returns:
            A validated :class:`~app.chat.schemas.LLMSlotFillerOutput`.

        Raises:
            ChatSlotExtractionError: When the JSON cannot be parsed or
                does not match the expected schema.
        """
        # ── JSON parsing ──────────────────────────────────────────────────────
        try:
            parsed: dict[str, Any] = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            logger.error(
                "chat_slot_filler_json_parse_error",
                error=str(exc),
                raw_content_preview=raw_content[:200],
            )
            raise ChatSlotExtractionError(
                f"GPT-4o returned invalid JSON: {exc}",
                raw_response=raw_content,
            ) from exc

        # ── Pydantic validation ───────────────────────────────────────────────
        try:

            result = LLMSlotFillerOutput.model_validate(parsed)
        except Exception as exc:
            # Catch both Pydantic ValidationError and any unexpected errors.
            logger.error(
                "chat_slot_filler_validation_error",
                error=str(exc),
                parsed_keys=list(parsed.keys()) if isinstance(parsed, dict) else [],
            )
            raise ChatSlotExtractionError(
                f"GPT-4o response failed schema validation: {exc}",
                raw_response=raw_content,
            ) from exc

        # ── Log the extraction result ─────────────────────────────────────────
        if result.slots is not None:
            missing = result.slots.missing_required_slots()
            logger.info(
                "chat_slot_filler_extraction_complete",
                has_required_slots=result.slots.has_required_slots,
                missing_slots=missing,
                confidence=result.confidence,
            )
        else:
            logger.info(
                "chat_slot_filler_clarifying_question",
                question_preview=(
                    result.clarifying_question[:80]
                    if result.clarifying_question
                    else None
                ),
                confidence=result.confidence,
            )

        return result

    def _fallback_response(
        self,
        existing_slots: dict[str, Any],
    ) -> LLMSlotFillerOutput:
        """Generate a deterministic fallback response when no API key is set.

        Used in test / dry-run mode when ``OPENAI_API_KEY`` is not
        configured.  Checks the existing slots to determine what is
        missing and returns an appropriate clarifying question.

        Args:
            existing_slots: Currently extracted slot values.

        Returns:
            A :class:`~app.chat.schemas.LLMSlotFillerOutput` with a
            clarifying question based on the missing required slots.
        """
        # Build a partial ExtractedSlots to check what's missing.
        try:
            partial = ExtractedSlots.model_validate(existing_slots)
        except Exception:
            partial = ExtractedSlots()

        missing = partial.missing_required_slots()

        if not missing:
            # All required slots are present — return the slots as-is.
            logger.info(
                "chat_slot_filler_fallback_slots_complete",
                message="All required slots present; returning without LLM call",
            )
            return LLMSlotFillerOutput(
                clarifying_question=None,
                slots=partial,
                confidence=None,
            )

        # Generate a clarifying question for the missing fields.
        missing_description = format_missing_fields_description(missing)
        question = CLARIFY_HINT_TEMPLATE.format(
            missing_fields_description=missing_description
        )

        logger.info(
            "chat_slot_filler_fallback_clarifying",
            missing_slots=missing,
        )

        return LLMSlotFillerOutput(
            clarifying_question=question,
            slots=None,
            confidence=None,
        )


# ── Module-level singleton factory ────────────────────────────────────────────


@functools.lru_cache(maxsize=1)
def get_slot_filler() -> LLMSlotFiller:
    """Return a cached singleton :class:`LLMSlotFiller` instance.

    The singleton is created once per process and reuses the same
    ``AsyncOpenAI`` client across all requests.  This avoids the
    overhead of creating a new HTTP connection pool on every request.

    In tests, call ``get_slot_filler.cache_clear()`` before injecting
    a mock, or construct a :class:`LLMSlotFiller` directly with a mock
    client instead of using this factory.

    Returns:
        A :class:`LLMSlotFiller` instance configured with the default
        model (:data:`DEFAULT_MODEL`).

    Example::

        # In production code (service layer):
        filler = get_slot_filler()
        result = await filler.extract_slots(messages, existing_slots)

        # In tests:
        filler = LLMSlotFiller(client=mock_async_openai_client)
        result = await filler.extract_slots(messages, existing_slots)
    """
    settings = get_settings()
    api_key = settings.OPENAI_API_KEY

    if api_key:
        try:
            from openai import AsyncOpenAI  # noqa: PLC0415

            client: AsyncOpenAI | None = AsyncOpenAI(api_key=api_key)
        except ImportError:
            logger.warning(
                "chat_slot_filler_openai_not_installed",
                message=(
                    "The 'openai' package is not installed. "
                    "Slot filler will use fallback mode."
                ),
            )
            client = None
    else:
        client = None

    return LLMSlotFiller(client=client, model=DEFAULT_MODEL)
