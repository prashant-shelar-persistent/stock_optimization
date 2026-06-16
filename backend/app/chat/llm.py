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

import contextlib
import functools
import json
import re
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
                    message="OPENAI_API_KEY not configured; using local regex slot extractor",
                )
                return self._fallback_response(messages, existing_slots)

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
        messages: list[Any],
        existing_slots: dict[str, Any],
    ) -> LLMSlotFillerOutput:
        """Generate a response using local regex extraction when no API key is set.

        When ``OPENAI_API_KEY`` is not configured, this method parses the
        full conversation history using regex patterns to extract slot values
        (tickers, budget, min_return, max_volatility, run_quantum) directly
        from the text.  Extracted values are merged with ``existing_slots``
        so that multi-turn conversations accumulate information correctly.

        Args:
            messages:       Full conversation history (ChatMessage objects or dicts).
            existing_slots: Currently extracted slot values from earlier turns.

        Returns:
            A :class:`~app.chat.schemas.LLMSlotFillerOutput` with either
            ``slots`` (when all required fields are present) or a
            ``clarifying_question`` (when required fields are still missing).
        """
        # ── Step 1: collect all user message text ────────────────────────────
        user_text_parts: list[str] = []
        for msg in messages:
            if hasattr(msg, "role") and hasattr(msg, "content"):
                role = str(msg.role)
                content = str(msg.content)
            elif isinstance(msg, dict):
                role = str(msg.get("role", ""))
                content = str(msg.get("content", ""))
            else:
                continue
            if role == "user":
                user_text_parts.append(content)

        combined_text = " ".join(user_text_parts)

        # ── Step 2: start from existing_slots, then overlay regex extractions ─
        merged: dict[str, Any] = dict(existing_slots)

        # ── Tickers ──────────────────────────────────────────────────────────
        # Match individual tickers that look like stock symbols (1-5 uppercase letters).
        # The broader multi-ticker pattern is not needed here because we iterate over
        # all individual matches and filter out common English words below.
        individual_ticker_pattern = re.compile(r"\b([A-Z]{1,5})\b")

        # Known common words to exclude from ticker detection.
        # Named with a leading underscore and lowercase to satisfy pep8-naming (N806)
        # for function-local variables; the uppercase content is intentional because
        # ticker symbols are compared in uppercase.
        _excluded_words = {
            "A", "I", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "IF",
            "IN", "IS", "IT", "ME", "MY", "NO", "OF", "ON", "OR", "SO", "TO",
            "UP", "US", "WE", "AND", "ARE", "BUT", "FOR", "HAS", "NOT", "THE",
            "WITH", "THAT", "THIS", "FROM", "HAVE", "WILL", "TECH", "HEAVY",
            "BUILD", "PORTFOLIO", "BUDGET", "ANNUAL", "RETURN", "LEAST",
            "TARGETING", "MINIMUM", "MAXIMUM", "STOCK", "INVEST", "USD",
            "WANT", "NEED", "LIKE", "MAKE", "SKIP", "ALSO", "JUST", "ONLY",
            "EACH", "BOTH", "SOME", "MORE", "LESS", "THAN", "OVER", "UNDER",
            "INTO", "UPON", "ABOUT", "AFTER", "BEFORE", "DURING", "WHILE",
            "WHEN", "WHERE", "WHICH", "WHO", "HOW", "WHAT", "WHY", "CAN",
            "MAY", "MUST", "SHALL", "SHOULD", "WOULD", "COULD", "MIGHT",
            "PLEASE", "HELP", "GIVE", "SHOW", "TELL", "FIND", "GET", "SET",
            "RUN", "USE", "ADD", "NEW", "OLD", "BIG", "LOW", "HIGH", "GOOD",
            "BEST", "RISK", "SAFE", "PLAN", "GOAL", "YEAR", "MONTH", "DAY",
            "PERCENT", "RATE", "PRICE", "VALUE", "TOTAL", "AMOUNT", "FUND",
            "ASSET", "SECTOR", "MARKET", "EQUITY", "BOND", "ETF", "INDEX",
            "GROWTH", "INCOME", "BLEND", "LARGE", "SMALL", "MID",
            "CAP", "ESG", "SHARPE", "RATIO", "ALPHA", "BETA", "DELTA",
            "QUANTUM", "CLASSIC", "OPTIMIZE", "OPTIMIZATION",
        }

        # Extract tickers from the combined text
        if "tickers" not in merged or not merged.get("tickers"):
            found_tickers: list[str] = []
            seen: set[str] = set()
            for match in individual_ticker_pattern.finditer(combined_text):
                sym = match.group(1).upper()
                if sym not in _excluded_words and sym not in seen and len(sym) >= 2:
                    found_tickers.append(sym)
                    seen.add(sym)
            if len(found_tickers) >= 2:
                merged["tickers"] = found_tickers

        # ── Budget ────────────────────────────────────────────────────────────
        # Match patterns like: $50,000 | $50k | $50K | 50000 dollars | fifty thousand
        if "budget" not in merged or not merged.get("budget"):
            budget_val: float | None = None

            # Pattern: $50,000 or $50000 or $50k or $50K or $50M
            # Use negative lookahead (?!\w) to prevent matching suffix letters
            # that are part of a following word (e.g. "b" from "budget").
            dollar_pattern = re.compile(
                r"\$\s*([\d,]+(?:\.\d+)?)\s*([kKmMbB]?)(?!\w)",
                re.IGNORECASE,
            )
            m = dollar_pattern.search(combined_text)
            if m:
                num_str = m.group(1).replace(",", "")
                suffix = m.group(2).lower()
                try:
                    val = float(num_str)
                    if suffix == "k":
                        val *= 1_000
                    elif suffix == "m":
                        val *= 1_000_000
                    elif suffix == "b":
                        val *= 1_000_000_000
                    budget_val = val
                except ValueError:
                    pass

            # Pattern: "50000 dollars" or "50,000 USD"
            if budget_val is None:
                num_dollar_pattern = re.compile(
                    r"([\d,]+(?:\.\d+)?)\s*(?:dollars?|USD|usd)",
                    re.IGNORECASE,
                )
                m2 = num_dollar_pattern.search(combined_text)
                if m2:
                    with contextlib.suppress(ValueError):
                        budget_val = float(m2.group(1).replace(",", ""))

            # Pattern: verbal amounts like "fifty thousand dollars"
            if budget_val is None:
                verbal_map = {
                    "hundred": 100, "thousand": 1_000, "million": 1_000_000,
                    "billion": 1_000_000_000,
                }
                digit_words = {
                    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
                    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
                    "fourteen": 14, "fifteen": 15, "sixteen": 16,
                    "seventeen": 17, "eighteen": 18, "nineteen": 19,
                    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
                    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
                }
                text_lower = combined_text.lower()
                for multiplier_word, multiplier_val in verbal_map.items():
                    pattern = re.compile(
                        r"(\w+(?:\s+\w+)?)\s+" + multiplier_word,
                        re.IGNORECASE,
                    )
                    vm = pattern.search(text_lower)
                    if vm:
                        prefix = vm.group(1).strip().lower()
                        # Try to parse prefix as a number word
                        base = digit_words.get(prefix)
                        if base is not None:
                            budget_val = float(base * multiplier_val)
                            break
                        # Try compound like "fifty thousand"
                        parts = prefix.split()
                        if len(parts) == 2:
                            p1 = digit_words.get(parts[0], 0)
                            p2 = digit_words.get(parts[1], 0)
                            if p1 and p2:
                                budget_val = float((p1 + p2) * multiplier_val)
                                break

            if budget_val is not None and budget_val > 0:
                merged["budget"] = budget_val

        # ── min_return ────────────────────────────────────────────────────────
        # Match: "at least 12% annual return" | "minimum 10% return" | "12% return"
        if "min_return" not in merged or merged.get("min_return") is None:
            return_pattern = re.compile(
                r"(?:at\s+least|minimum|min(?:imum)?|targeting?|target)\s+"
                r"([\d]+(?:\.\d+)?)\s*%\s*(?:annual(?:ised|ized)?\s+)?return",
                re.IGNORECASE,
            )
            rm = return_pattern.search(combined_text)
            if rm:
                try:
                    pct = float(rm.group(1))
                    # Convert percentage to decimal (e.g. 12 → 0.12)
                    merged["min_return"] = pct / 100.0 if pct > 1.0 else pct
                except ValueError:
                    pass

            # Also match "12% return" without qualifier
            if "min_return" not in merged or merged.get("min_return") is None:
                simple_return_pattern = re.compile(
                    r"([\d]+(?:\.\d+)?)\s*%\s*(?:annual(?:ised|ized)?\s+)?return",
                    re.IGNORECASE,
                )
                srm = simple_return_pattern.search(combined_text)
                if srm:
                    try:
                        pct = float(srm.group(1))
                        merged["min_return"] = pct / 100.0 if pct > 1.0 else pct
                    except ValueError:
                        pass

        # ── max_volatility ────────────────────────────────────────────────────
        if "max_volatility" not in merged or merged.get("max_volatility") is None:
            vol_pattern = re.compile(
                r"(?:max(?:imum)?|no\s+more\s+than|less\s+than|under)\s+"
                r"([\d]+(?:\.\d+)?)\s*%\s*(?:annual(?:ised|ized)?\s+)?volatility",
                re.IGNORECASE,
            )
            vm2 = vol_pattern.search(combined_text)
            if vm2:
                try:
                    pct = float(vm2.group(1))
                    merged["max_volatility"] = pct / 100.0 if pct > 1.0 else pct
                except ValueError:
                    pass

        # ── run_quantum ───────────────────────────────────────────────────────
        if "run_quantum" not in merged:
            text_lower = combined_text.lower()
            if re.search(r"skip\s+quantum|no\s+quantum|without\s+quantum|"
                         r"classical\s+only|disable\s+quantum", text_lower):
                merged["run_quantum"] = False
            elif re.search(r"run\s+quantum|use\s+quantum|with\s+quantum|"
                           r"enable\s+quantum|quantum\s+optimization", text_lower):
                merged["run_quantum"] = True

        # ── Step 3: validate merged slots ─────────────────────────────────────
        try:
            partial = ExtractedSlots.model_validate(merged)
        except Exception:
            try:
                partial = ExtractedSlots.model_validate(existing_slots)
            except Exception:
                partial = ExtractedSlots()

        missing = partial.missing_required_slots()

        logger.info(
            "chat_slot_filler_local_extraction",
            extracted_tickers=partial.tickers,
            extracted_budget=partial.budget,
            extracted_min_return=partial.min_return,
            missing_slots=missing,
        )

        if not missing:
            # All required slots are present — return the slots.
            logger.info(
                "chat_slot_filler_fallback_slots_complete",
                message="All required slots extracted locally; ready for confirmation",
            )
            return LLMSlotFillerOutput(
                clarifying_question=None,
                slots=partial,
                confidence=0.85,
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
