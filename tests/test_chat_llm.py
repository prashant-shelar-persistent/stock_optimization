"""Unit tests for app.chat.llm — LLMSlotFiller.

Tests cover:
1. extract_slots returns fallback clarifying question when no API key is set
2. extract_slots returns fallback with all required slots present (no LLM call)
3. extract_slots calls OpenAI and returns clarifying question when slots missing
4. extract_slots calls OpenAI and returns slots when all required slots present
5. extract_slots raises ChatSlotExtractionError when OpenAI call fails
6. extract_slots raises ChatSlotExtractionError when response is invalid JSON
7. extract_slots raises ChatSlotExtractionError when response fails schema validation
8. extract_slots raises ChatSlotExtractionError when response content is None
9. _build_openai_messages prepends system message and maps conversation turns
10. _build_openai_messages handles dict-based messages
11. _build_openai_messages skips unknown roles
12. _parse_response returns LLMSlotFillerOutput for valid clarifying question JSON
13. _parse_response returns LLMSlotFillerOutput for valid slots JSON
14. _parse_response raises ChatSlotExtractionError for invalid JSON
15. _parse_response raises ChatSlotExtractionError for schema validation failure
16. get_slot_filler returns a singleton LLMSlotFiller instance
17. Fallback path: missing tickers generates clarifying question
18. Fallback path: missing budget generates clarifying question
19. Fallback path: both tickers and budget missing generates combined question
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.chat.llm import DEFAULT_MODEL, LLMSlotFiller, get_slot_filler
from app.chat.schemas import ChatMessage, ExtractedSlots, LLMSlotFillerOutput
from app.core.exceptions import ChatSlotExtractionError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_openai_client(response_content: str) -> MagicMock:
    """Build a mock AsyncOpenAI client that returns the given content string."""
    mock_choice = MagicMock()
    mock_choice.message.content = response_content
    mock_choice.finish_reason = "stop"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_completions = MagicMock()
    mock_completions.create = AsyncMock(return_value=mock_response)

    mock_chat = MagicMock()
    mock_chat.completions = mock_completions

    mock_client = MagicMock()
    mock_client.chat = mock_chat

    return mock_client


def _clarifying_json(question: str = "What is your budget?") -> str:
    """Return a valid clarifying-question JSON string."""
    return json.dumps(
        {
            "clarifying_question": question,
            "slots": None,
            "confidence": 0.9,
        }
    )


def _slots_json(
    tickers: list[str] | None = None,
    budget: float | None = None,
) -> str:
    """Return a valid slots JSON string."""
    tickers = tickers or ["AAPL", "MSFT"]
    budget = budget or 50000.0
    return json.dumps(
        {
            "clarifying_question": None,
            "slots": {
                "tickers": tickers,
                "budget": budget,
            },
            "confidence": 0.95,
        }
    )


def _user_messages(content: str = "Optimize AAPL, MSFT") -> list[ChatMessage]:
    return [ChatMessage(role="user", content=content)]


# ---------------------------------------------------------------------------
# 1. Fallback when no API key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_slots_no_api_key_returns_clarifying_question() -> None:
    """When OPENAI_API_KEY is empty and slots are missing, returns clarifying question."""
    filler = LLMSlotFiller(client=None)

    with patch("app.chat.llm.get_settings") as mock_settings:
        mock_settings.return_value.OPENAI_API_KEY = ""
        result = await filler.extract_slots(
            messages=_user_messages("I want to invest"),
            existing_slots={},
        )

    assert isinstance(result, LLMSlotFillerOutput)
    assert result.clarifying_question is not None
    assert len(result.clarifying_question) > 0
    assert result.slots is None


@pytest.mark.asyncio
async def test_extract_slots_no_api_key_with_complete_slots_returns_slots() -> None:
    """When OPENAI_API_KEY is empty but all required slots are present, returns slots."""
    filler = LLMSlotFiller(client=None)

    with patch("app.chat.llm.get_settings") as mock_settings:
        mock_settings.return_value.OPENAI_API_KEY = ""
        result = await filler.extract_slots(
            messages=_user_messages("Optimize AAPL, MSFT with $50k"),
            existing_slots={"tickers": ["AAPL", "MSFT"], "budget": 50000.0},
        )

    assert isinstance(result, LLMSlotFillerOutput)
    # With complete slots, fallback returns slots (not a clarifying question)
    assert result.slots is not None
    assert result.clarifying_question is None


# ---------------------------------------------------------------------------
# 2. Successful OpenAI call — clarifying question
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_slots_returns_clarifying_question_from_llm() -> None:
    """When LLM returns a clarifying question, it is returned as-is."""
    question = "What is your total investment budget in USD?"
    mock_client = _make_mock_openai_client(_clarifying_json(question))
    filler = LLMSlotFiller(client=mock_client)

    result = await filler.extract_slots(
        messages=_user_messages("I want AAPL and MSFT"),
        existing_slots={},
    )

    assert isinstance(result, LLMSlotFillerOutput)
    assert result.clarifying_question == question
    assert result.slots is None
    assert result.confidence == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# 3. Successful OpenAI call — complete slots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_slots_returns_slots_from_llm() -> None:
    """When LLM returns complete slots, they are parsed and returned."""
    mock_client = _make_mock_openai_client(_slots_json(["AAPL", "MSFT"], 50000.0))
    filler = LLMSlotFiller(client=mock_client)

    result = await filler.extract_slots(
        messages=_user_messages("Optimize AAPL, MSFT with $50k"),
        existing_slots={},
    )

    assert isinstance(result, LLMSlotFillerOutput)
    assert result.slots is not None
    assert result.clarifying_question is None
    assert result.slots.tickers == ["AAPL", "MSFT"]
    assert result.slots.budget == pytest.approx(50000.0)
    assert result.confidence == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# 4. OpenAI API error raises ChatSlotExtractionError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_slots_openai_error_raises_chat_slot_extraction_error() -> None:
    """When the OpenAI API call raises an exception, ChatSlotExtractionError is raised."""
    mock_completions = MagicMock()
    mock_completions.create = AsyncMock(side_effect=RuntimeError("API timeout"))

    mock_chat = MagicMock()
    mock_chat.completions = mock_completions

    mock_client = MagicMock()
    mock_client.chat = mock_chat

    filler = LLMSlotFiller(client=mock_client)

    with pytest.raises(ChatSlotExtractionError) as exc_info:
        await filler.extract_slots(
            messages=_user_messages("Optimize AAPL, MSFT with $50k"),
            existing_slots={},
        )

    assert "temporarily unavailable" in str(exc_info.value)
    assert exc_info.value.error_code == "CHAT_SLOT_EXTRACTION_ERROR"


# ---------------------------------------------------------------------------
# 5. Invalid JSON response raises ChatSlotExtractionError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_slots_invalid_json_raises_chat_slot_extraction_error() -> None:
    """When the LLM returns invalid JSON, ChatSlotExtractionError is raised."""
    mock_client = _make_mock_openai_client("this is not json {{{")
    filler = LLMSlotFiller(client=mock_client)

    with pytest.raises(ChatSlotExtractionError) as exc_info:
        await filler.extract_slots(
            messages=_user_messages("Optimize AAPL, MSFT with $50k"),
            existing_slots={},
        )

    assert "invalid JSON" in str(exc_info.value).lower() or "JSON" in str(exc_info.value)
    assert exc_info.value.error_code == "CHAT_SLOT_EXTRACTION_ERROR"
    assert exc_info.value.raw_response == "this is not json {{{"


# ---------------------------------------------------------------------------
# 6. Schema validation failure raises ChatSlotExtractionError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_slots_schema_validation_failure_raises_error() -> None:
    """When the LLM returns JSON that fails Pydantic validation, ChatSlotExtractionError is raised."""
    # confidence must be 0-1; this violates the constraint
    bad_json = json.dumps(
        {
            "clarifying_question": None,
            "slots": None,
            "confidence": 999.0,  # out of range
        }
    )
    mock_client = _make_mock_openai_client(bad_json)
    filler = LLMSlotFiller(client=mock_client)

    with pytest.raises(ChatSlotExtractionError) as exc_info:
        await filler.extract_slots(
            messages=_user_messages("Optimize AAPL, MSFT with $50k"),
            existing_slots={},
        )

    assert exc_info.value.error_code == "CHAT_SLOT_EXTRACTION_ERROR"


# ---------------------------------------------------------------------------
# 7. None content from OpenAI raises ChatSlotExtractionError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_slots_none_content_raises_error() -> None:
    """When the LLM returns None content, ChatSlotExtractionError is raised."""
    mock_client = _make_mock_openai_client(None)  # type: ignore[arg-type]
    filler = LLMSlotFiller(client=mock_client)

    with pytest.raises(ChatSlotExtractionError) as exc_info:
        await filler.extract_slots(
            messages=_user_messages("Optimize AAPL, MSFT with $50k"),
            existing_slots={},
        )

    assert "empty response" in str(exc_info.value).lower() or "None" in str(exc_info.value)
    assert exc_info.value.error_code == "CHAT_SLOT_EXTRACTION_ERROR"


# ---------------------------------------------------------------------------
# 8. _build_openai_messages — system message prepended
# ---------------------------------------------------------------------------


def test_build_openai_messages_prepends_system_message() -> None:
    """The first message in the built array is always the system message."""
    filler = LLMSlotFiller(client=MagicMock())
    messages = [ChatMessage(role="user", content="Hello")]
    result = filler._build_openai_messages(messages, existing_slots={})

    assert len(result) >= 1
    assert result[0]["role"] == "system"
    assert len(result[0]["content"]) > 0


def test_build_openai_messages_maps_user_and_assistant_turns() -> None:
    """User and assistant messages are mapped to the correct roles."""
    filler = LLMSlotFiller(client=MagicMock())
    messages = [
        ChatMessage(role="user", content="Optimize AAPL"),
        ChatMessage(role="assistant", content="What is your budget?"),
        ChatMessage(role="user", content="$50k"),
    ]
    result = filler._build_openai_messages(messages, existing_slots={})

    # First is system, then user, assistant, user
    assert result[0]["role"] == "system"
    assert result[1]["role"] == "user"
    assert result[1]["content"] == "Optimize AAPL"
    assert result[2]["role"] == "assistant"
    assert result[2]["content"] == "What is your budget?"
    assert result[3]["role"] == "user"
    assert result[3]["content"] == "$50k"


def test_build_openai_messages_handles_dict_messages() -> None:
    """Dict-based messages (with role/content keys) are handled correctly."""
    filler = LLMSlotFiller(client=MagicMock())
    messages = [
        {"role": "user", "content": "Optimize AAPL, MSFT"},
        {"role": "assistant", "content": "What is your budget?"},
    ]
    result = filler._build_openai_messages(messages, existing_slots={})

    assert result[0]["role"] == "system"
    assert result[1]["role"] == "user"
    assert result[1]["content"] == "Optimize AAPL, MSFT"
    assert result[2]["role"] == "assistant"


def test_build_openai_messages_skips_system_role_in_history() -> None:
    """System messages in the conversation history are skipped."""
    filler = LLMSlotFiller(client=MagicMock())
    messages = [
        {"role": "system", "content": "You are a bot"},
        {"role": "user", "content": "Hello"},
    ]
    result = filler._build_openai_messages(messages, existing_slots={})

    # Only system (prepended) + user
    roles = [m["role"] for m in result]
    assert roles.count("system") == 1
    assert roles.count("user") == 1


def test_build_openai_messages_injects_existing_slots_into_system_prompt() -> None:
    """When existing_slots is non-empty, the system message includes them."""
    filler = LLMSlotFiller(client=MagicMock())
    messages = [ChatMessage(role="user", content="Add GOOGL")]
    existing_slots = {"tickers": ["AAPL", "MSFT"], "budget": 50000.0}
    result = filler._build_openai_messages(messages, existing_slots=existing_slots)

    system_content = result[0]["content"]
    assert "AAPL" in system_content
    assert "50000" in system_content


# ---------------------------------------------------------------------------
# 9. _parse_response — valid clarifying question
# ---------------------------------------------------------------------------


def test_parse_response_valid_clarifying_question() -> None:
    """_parse_response correctly parses a clarifying question response."""
    filler = LLMSlotFiller(client=MagicMock())
    raw = _clarifying_json("What is your budget?")
    result = filler._parse_response(raw)

    assert isinstance(result, LLMSlotFillerOutput)
    assert result.clarifying_question == "What is your budget?"
    assert result.slots is None


def test_parse_response_valid_slots() -> None:
    """_parse_response correctly parses a complete slots response."""
    filler = LLMSlotFiller(client=MagicMock())
    raw = _slots_json(["AAPL", "MSFT", "GOOGL"], 100000.0)
    result = filler._parse_response(raw)

    assert isinstance(result, LLMSlotFillerOutput)
    assert result.slots is not None
    assert result.slots.tickers == ["AAPL", "MSFT", "GOOGL"]
    assert result.slots.budget == pytest.approx(100000.0)
    assert result.clarifying_question is None


def test_parse_response_invalid_json_raises_error() -> None:
    """_parse_response raises ChatSlotExtractionError for invalid JSON."""
    filler = LLMSlotFiller(client=MagicMock())

    with pytest.raises(ChatSlotExtractionError) as exc_info:
        filler._parse_response("not valid json")

    assert exc_info.value.error_code == "CHAT_SLOT_EXTRACTION_ERROR"
    assert exc_info.value.raw_response == "not valid json"


def test_parse_response_schema_validation_error_raises_error() -> None:
    """_parse_response raises ChatSlotExtractionError when schema validation fails."""
    filler = LLMSlotFiller(client=MagicMock())
    # Negative budget violates the gt=0 constraint on ExtractedSlots.budget
    bad_json = json.dumps(
        {
            "clarifying_question": None,
            "slots": {
                "tickers": ["AAPL", "MSFT"],
                "budget": -100.0,
            },
            "confidence": 0.9,
        }
    )

    with pytest.raises(ChatSlotExtractionError) as exc_info:
        filler._parse_response(bad_json)

    assert exc_info.value.error_code == "CHAT_SLOT_EXTRACTION_ERROR"


# ---------------------------------------------------------------------------
# 10. get_slot_filler singleton
# ---------------------------------------------------------------------------


def test_get_slot_filler_returns_llm_slot_filler_instance() -> None:
    """get_slot_filler returns an LLMSlotFiller instance."""
    get_slot_filler.cache_clear()
    try:
        with patch("app.chat.llm.get_settings") as mock_settings:
            mock_settings.return_value.OPENAI_API_KEY = ""
            filler = get_slot_filler()
        assert isinstance(filler, LLMSlotFiller)
    finally:
        get_slot_filler.cache_clear()


def test_get_slot_filler_returns_same_instance_on_repeated_calls() -> None:
    """get_slot_filler returns the same cached instance on repeated calls."""
    get_slot_filler.cache_clear()
    try:
        with patch("app.chat.llm.get_settings") as mock_settings:
            mock_settings.return_value.OPENAI_API_KEY = ""
            filler1 = get_slot_filler()
            filler2 = get_slot_filler()
        assert filler1 is filler2
    finally:
        get_slot_filler.cache_clear()


# ---------------------------------------------------------------------------
# 11. Fallback path — missing tickers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_missing_tickers_generates_clarifying_question() -> None:
    """Fallback path generates a clarifying question when tickers are missing."""
    filler = LLMSlotFiller(client=None)

    with patch("app.chat.llm.get_settings") as mock_settings:
        mock_settings.return_value.OPENAI_API_KEY = ""
        result = await filler.extract_slots(
            messages=_user_messages("I have $50,000 to invest"),
            existing_slots={"budget": 50000.0},
        )

    assert result.clarifying_question is not None
    assert result.slots is None
    # The question should mention tickers
    assert "ticker" in result.clarifying_question.lower() or "stock" in result.clarifying_question.lower()


# ---------------------------------------------------------------------------
# 12. Fallback path — missing budget
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_missing_budget_generates_clarifying_question() -> None:
    """Fallback path generates a clarifying question when budget is missing."""
    filler = LLMSlotFiller(client=None)

    with patch("app.chat.llm.get_settings") as mock_settings:
        mock_settings.return_value.OPENAI_API_KEY = ""
        result = await filler.extract_slots(
            messages=_user_messages("Optimize AAPL and MSFT"),
            existing_slots={"tickers": ["AAPL", "MSFT"]},
        )

    assert result.clarifying_question is not None
    assert result.slots is None
    # The question should mention budget
    assert "budget" in result.clarifying_question.lower() or "invest" in result.clarifying_question.lower()


# ---------------------------------------------------------------------------
# 13. Fallback path — both tickers and budget missing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_both_missing_generates_combined_question() -> None:
    """Fallback path generates a question mentioning both missing fields."""
    filler = LLMSlotFiller(client=None)

    with patch("app.chat.llm.get_settings") as mock_settings:
        mock_settings.return_value.OPENAI_API_KEY = ""
        result = await filler.extract_slots(
            messages=_user_messages("I want to optimize my portfolio"),
            existing_slots={},
        )

    assert result.clarifying_question is not None
    assert result.slots is None
    # Should mention both tickers and budget
    question_lower = result.clarifying_question.lower()
    assert "ticker" in question_lower or "stock" in question_lower
    assert "budget" in question_lower or "invest" in question_lower


# ---------------------------------------------------------------------------
# 14. Multi-turn: existing slots injected into system prompt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_slots_passes_existing_slots_to_openai() -> None:
    """Existing slots are injected into the system message sent to OpenAI."""
    captured_messages: list[Any] = []

    async def capture_create(**kwargs: Any) -> Any:
        captured_messages.extend(kwargs.get("messages", []))
        mock_choice = MagicMock()
        mock_choice.message.content = _clarifying_json("What else do you need?")
        mock_choice.finish_reason = "stop"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        return mock_response

    mock_completions = MagicMock()
    mock_completions.create = capture_create

    mock_chat = MagicMock()
    mock_chat.completions = mock_completions

    mock_client = MagicMock()
    mock_client.chat = mock_chat

    filler = LLMSlotFiller(client=mock_client)
    existing_slots = {"tickers": ["AAPL", "MSFT"], "budget": 75000.0}

    await filler.extract_slots(
        messages=_user_messages("Add GOOGL to the list"),
        existing_slots=existing_slots,
    )

    # The system message should contain the existing slots
    assert len(captured_messages) > 0
    system_msg = captured_messages[0]
    assert system_msg["role"] == "system"
    assert "AAPL" in system_msg["content"]
    assert "75000" in system_msg["content"]


# ---------------------------------------------------------------------------
# 15. Tickers normalised to uppercase in extracted slots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_slots_tickers_normalised_to_uppercase() -> None:
    """Tickers returned by the LLM are normalised to uppercase."""
    raw = json.dumps(
        {
            "clarifying_question": None,
            "slots": {
                "tickers": ["aapl", "msft", "googl"],
                "budget": 50000.0,
            },
            "confidence": 0.9,
        }
    )
    mock_client = _make_mock_openai_client(raw)
    filler = LLMSlotFiller(client=mock_client)

    result = await filler.extract_slots(
        messages=_user_messages("Optimize aapl, msft, googl with $50k"),
        existing_slots={},
    )

    assert result.slots is not None
    assert result.slots.tickers == ["AAPL", "MSFT", "GOOGL"]


# ---------------------------------------------------------------------------
# 16. Model attribute is set correctly
# ---------------------------------------------------------------------------


def test_llm_slot_filler_uses_default_model() -> None:
    """LLMSlotFiller uses DEFAULT_MODEL when no model is specified."""
    filler = LLMSlotFiller(client=MagicMock())
    assert filler._model == DEFAULT_MODEL


def test_llm_slot_filler_accepts_custom_model() -> None:
    """LLMSlotFiller accepts a custom model string."""
    filler = LLMSlotFiller(client=MagicMock(), model="gpt-4o-mini")
    assert filler._model == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Round 4 — new tests: budget clamping, ticker filtering, safe error messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_budget_above_one_trillion_is_rejected() -> None:
    """Fallback parser rejects budgets above 1 trillion and returns clarify status."""
    filler = LLMSlotFiller(client=None)

    with patch("app.chat.llm.get_settings") as mock_settings:
        mock_settings.return_value.OPENAI_API_KEY = ""
        result = await filler.extract_slots(
            messages=_user_messages("invest AAPL MSFT with budget $9999999999999"),
            existing_slots={},
        )

    # Budget is out of range — should be discarded, triggering clarify path
    assert result.clarifying_question is not None
    assert result.slots is None or result.slots.budget is None


@pytest.mark.asyncio
async def test_ticker_fallback_rejects_non_ticker_words() -> None:
    """Fallback parser excludes common words (USD, ETF) from ticker extraction."""
    filler = LLMSlotFiller(client=None)

    with patch("app.chat.llm.get_settings") as mock_settings:
        mock_settings.return_value.OPENAI_API_KEY = ""
        result = await filler.extract_slots(
            messages=_user_messages("invest USD ETF AAPL MSFT with budget $50000"),
            existing_slots={},
        )

    # USD and ETF should be excluded; only AAPL and MSFT should be extracted
    assert result.slots is not None
    assert result.slots.tickers is not None
    assert "USD" not in result.slots.tickers
    assert "ETF" not in result.slots.tickers
    assert "AAPL" in result.slots.tickers
    assert "MSFT" in result.slots.tickers


@pytest.mark.asyncio
async def test_openai_error_returns_safe_message() -> None:
    """When OpenAI raises an error, the exception message does NOT contain raw error details."""
    # Simulate an OpenAI-like timeout error
    class FakeAPITimeoutError(Exception):
        """Simulated openai.APITimeoutError."""

    mock_completions = MagicMock()
    mock_completions.create = AsyncMock(
        side_effect=FakeAPITimeoutError("Connection timed out to api.openai.com:443")
    )
    mock_chat = MagicMock()
    mock_chat.completions = mock_completions
    mock_client = MagicMock()
    mock_client.chat = mock_chat

    filler = LLMSlotFiller(client=mock_client)

    with pytest.raises(ChatSlotExtractionError) as exc_info:
        await filler.extract_slots(
            messages=_user_messages("Optimize AAPL, MSFT with $50k"),
            existing_slots={},
        )

    error_message = str(exc_info.value)
    # The raw exception string must NOT appear in the user-facing message
    assert "Connection timed out" not in error_message
    assert "api.openai.com" not in error_message
    # The message should be user-friendly
    assert "temporarily unavailable" in error_message
