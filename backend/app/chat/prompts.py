"""Prompt templates and schema builders for the GPT-4o chat slot-filler.

This module centralises all prompt strings and JSON-schema construction
logic used by :class:`~app.chat.llm.LLMSlotFiller`.  Keeping prompts
separate from the LLM-call logic makes it easy to:

- Iterate on prompt wording without touching business logic.
- Unit-test prompt construction independently.
- Reuse prompt fragments across multiple callers.

Prompt design principles
------------------------
- The system prompt establishes GPT-4o's role as a portfolio optimization
  assistant that extracts structured slot values from natural language.
- The model is instructed to return a JSON object that matches the
  ``LLMSlotFillerOutput`` schema: either a ``clarifying_question`` (when
  required slots are missing) or a populated ``slots`` object (when all
  required information is present).
- A few-shot example block is embedded in the system prompt to anchor the
  model's output format and reduce hallucination.
- The ``existing_slots`` dict is injected into the system prompt so the
  model can see what has already been extracted and avoid re-asking for
  information the user already provided.
- Ticker symbols are always normalised to uppercase in the prompt
  instructions to prevent case-sensitivity issues.
- The model is explicitly told NOT to invent ticker symbols — it should
  only use symbols the user explicitly mentioned.
"""

import json
from typing import Any


# ── Public constants ──────────────────────────────────────────────────────────

#: The system prompt sent to GPT-4o as the first message in every
#: slot-filling conversation.  It is a multi-line string that:
#:
#: 1. Establishes the model's role.
#: 2. Describes the two possible output shapes.
#: 3. Lists all extractable slot fields with their types and constraints.
#: 4. Provides a few-shot example of each output shape.
#: 5. Instructs the model on how to handle partial information.
CHAT_SYSTEM_PROMPT: str = """\
You are a portfolio optimization assistant. Your job is to extract structured \
parameters for a portfolio optimization request from the user's natural language \
messages.

## Your task

Analyse the conversation history and extract the following parameters:

REQUIRED (must be present before you can return a complete payload):
  - tickers: list of stock ticker symbols (e.g. ["AAPL", "MSFT", "GOOGL"]).
    Always normalise to UPPERCASE. Minimum 2 tickers required.
  - budget: total investment budget in USD (must be a positive number).

OPTIONAL (extract if mentioned, otherwise omit):
  - min_return: minimum acceptable annualised return as a decimal (e.g. 0.10 for 10%).
    Range: 0.0 to 5.0.
  - max_volatility: maximum acceptable annualised volatility as a decimal.
    Range: 0.0 to 5.0.
  - max_weight_per_asset: maximum portfolio weight for any single asset (0.0 to 1.0).
  - min_weight_per_asset: minimum portfolio weight for any included asset (0.0 to 1.0).
  - num_assets_to_select: integer number of assets to select (2 to 50).
  - lookback_days: historical data lookback period in calendar days (30 to 3650).
  - run_quantum: boolean — whether to run quantum optimization (QAOA + VQE).
    Default is true unless the user explicitly says to skip quantum.
  - sector_constraints: list of sector allocation limits, each with:
      { "sector": "<sector name>", "max_weight": <0.0 to 1.0> }
  - objectives: list of business objectives, each with:
      { "name": "<return|volatility|sharpe|max_drawdown|diversification_hhi|esg_score|sector_concentration>",
        "direction": "<maximize|minimize>",
        "weight": <0.0 to 1.0>,
        "target": <optional float or null>,
        "threshold": <optional float or null>,
        "enabled": true }
  - frontier: efficient-frontier sweep configuration:
      { "enabled": <bool>, "x_measure": "<measure>", "y_measure": "<measure>", "num_points": <5 to 100> }

## Output format

You MUST return a JSON object with EXACTLY this structure:

When required slots are MISSING:
{
  "clarifying_question": "<a single, specific question asking for the missing information>",
  "slots": null,
  "confidence": <0.0 to 1.0 or null>
}

When ALL required slots are present:
{
  "clarifying_question": null,
  "slots": {
    "tickers": ["AAPL", "MSFT"],
    "budget": 100000.0,
    ... (all other extracted optional fields)
  },
  "confidence": <0.0 to 1.0 or null>
}

## Rules

1. NEVER invent ticker symbols. Only use symbols the user explicitly mentioned.
2. If the user mentions a company name (e.g. "Apple"), convert it to the correct \
   ticker symbol (e.g. "AAPL").
3. When asking a clarifying question, ask for ONE piece of missing information at \
   a time. Start with tickers if missing, then budget.
4. Merge new information with the existing extracted slots shown below — do not \
   discard previously extracted values.
5. If the user provides a budget as a verbal description (e.g. "fifty thousand \
   dollars"), convert it to a numeric value (50000.0).
6. Return "clarifying_question" as null when all required slots are present.
7. Return "slots" as null when asking a clarifying question.
8. The "confidence" field is optional — set it to a value between 0.0 and 1.0 \
   reflecting your confidence in the extraction, or null if uncertain.

## Few-shot examples

### Example 1 — Missing budget (clarify)

User: "I want to optimize a portfolio with Apple, Microsoft, and Google."

Output:
{
  "clarifying_question": "What is your total investment budget in USD?",
  "slots": null,
  "confidence": 0.95
}

### Example 2 — Missing tickers (clarify)

User: "I have $50,000 to invest."

Output:
{
  "clarifying_question": "Which stock tickers would you like to include in your portfolio? \
Please provide at least 2 ticker symbols (e.g. AAPL, MSFT, GOOGL).",
  "slots": null,
  "confidence": 0.98
}

### Example 3 — All required slots present (ready)

User: "Optimize AAPL, MSFT, NVDA with a $100,000 budget. \
I want at least 12% annual return and no more than 20% volatility."

Output:
{
  "clarifying_question": null,
  "slots": {
    "tickers": ["AAPL", "MSFT", "NVDA"],
    "budget": 100000.0,
    "min_return": 0.12,
    "max_volatility": 0.20
  },
  "confidence": 0.97
}

### Example 4 — Multi-turn with existing slots

Existing extracted slots: {"tickers": ["AAPL", "MSFT"], "budget": 50000.0}
User: "Actually, add Tesla to the list and increase the budget to $75,000."

Output:
{
  "clarifying_question": null,
  "slots": {
    "tickers": ["AAPL", "MSFT", "TSLA"],
    "budget": 75000.0
  },
  "confidence": 0.99
}

### Example 5 — Quantum flag

User: "Run AAPL, GOOGL, AMZN with $200k budget. Skip the quantum stuff."

Output:
{
  "clarifying_question": null,
  "slots": {
    "tickers": ["AAPL", "GOOGL", "AMZN"],
    "budget": 200000.0,
    "run_quantum": false
  },
  "confidence": 0.98
}
"""

#: Template used to inject the current extracted slots into the system prompt.
#: The ``{existing_slots_json}`` placeholder is replaced at call time.
EXISTING_SLOTS_TEMPLATE: str = (
    "\n\n## Currently extracted slots\n\n"
    "The following slot values have already been extracted from earlier turns "
    "in this conversation. Merge any new information with these values — do not "
    "discard them:\n\n"
    "```json\n{existing_slots_json}\n```\n"
)

#: Fallback clarifying question used when no OpenAI API key is configured
#: and the slot filler is running in dry-run / test mode.
CLARIFY_HINT_TEMPLATE: str = (
    "I need a few more details to set up your portfolio optimization. "
    "Could you please tell me: {missing_fields_description}?"
)

__all__ = [
    "CHAT_SYSTEM_PROMPT",
    "CLARIFY_HINT_TEMPLATE",
    "EXISTING_SLOTS_TEMPLATE",
    "build_response_schema",
    "build_system_message",
]


# ── Prompt builders ───────────────────────────────────────────────────────────


def build_system_message(existing_slots: dict[str, Any]) -> str:
    """Build the full system message for the slot-filling call.

    Combines the base :data:`CHAT_SYSTEM_PROMPT` with a section that
    shows the model the slot values already extracted in earlier turns.
    This prevents the model from re-asking for information the user
    already provided.

    Args:
        existing_slots: Dict of slot values extracted so far.  May be
            empty (``{}``) for the first turn of a new session.

    Returns:
        The complete system message string to pass as the first element
        of the ``messages`` array in the OpenAI API call.

    Example::

        msg = build_system_message({"tickers": ["AAPL"], "budget": None})
        # Returns CHAT_SYSTEM_PROMPT + existing-slots section
    """
    if not existing_slots:
        # No existing slots — return the base prompt unchanged.
        return CHAT_SYSTEM_PROMPT

    # Filter out None values to keep the injected JSON clean.
    non_null_slots = {k: v for k, v in existing_slots.items() if v is not None}

    if not non_null_slots:
        return CHAT_SYSTEM_PROMPT

    existing_slots_json = json.dumps(non_null_slots, indent=2, default=str)
    slots_section = EXISTING_SLOTS_TEMPLATE.format(
        existing_slots_json=existing_slots_json
    )
    return CHAT_SYSTEM_PROMPT + slots_section


def build_response_schema() -> dict[str, Any]:
    """Build the JSON schema for GPT-4o structured outputs.

    Returns the ``json_schema`` dict to pass as
    ``response_format={"type": "json_schema", "json_schema": <this>}``
    in the OpenAI API call.

    The schema enforces the ``LLMSlotFillerOutput`` structure:

    .. code-block:: json

        {
          "clarifying_question": "<string or null>",
          "slots": { ... ExtractedSlots fields ... } | null,
          "confidence": <number 0-1 or null>
        }

    The ``slots`` sub-schema mirrors :class:`~app.chat.schemas.ExtractedSlots`
    with all fields optional (since partial extractions are valid).

    Returns:
        A dict suitable for use as the ``json_schema`` value in the
        OpenAI ``response_format`` parameter.

    Note:
        ``additionalProperties: false`` is set on the top-level object
        and on all nested objects to prevent the model from inventing
        extra fields.  This is required for OpenAI strict structured
        outputs (``"strict": true``).
    """
    # ── Nested object schemas ─────────────────────────────────────────────────

    sector_constraint_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "sector": {
                "type": "string",
                "description": "Sector name (e.g. 'Technology', 'Healthcare')",
            },
            "max_weight": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Maximum allocation fraction for this sector",
            },
        },
        "required": ["sector", "max_weight"],
        "additionalProperties": False,
    }

    business_objective_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "enum": [
                    "return",
                    "volatility",
                    "sharpe",
                    "max_drawdown",
                    "diversification_hhi",
                    "esg_score",
                    "sector_concentration",
                ],
                "description": "Canonical business-objective measure name",
            },
            "direction": {
                "type": "string",
                "enum": ["maximize", "minimize"],
                "description": "Whether to maximise or minimise this measure",
            },
            "weight": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Relative importance (0.0-1.0)",
            },
            "target": {
                "anyOf": [{"type": "number"}, {"type": "null"}],
                "description": "Optional target value (soft anchor)",
            },
            "threshold": {
                "anyOf": [{"type": "number"}, {"type": "null"}],
                "description": "Optional hard limit",
            },
            "enabled": {
                "type": "boolean",
                "description": "Whether this objective is active",
            },
        },
        "required": ["name", "direction", "weight", "target", "threshold", "enabled"],
        "additionalProperties": False,
    }

    frontier_config_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "description": "Whether to compute an efficient frontier",
            },
            "x_measure": {
                "type": "string",
                "enum": [
                    "return",
                    "volatility",
                    "sharpe",
                    "max_drawdown",
                    "diversification_hhi",
                    "esg_score",
                    "sector_concentration",
                ],
                "description": "Measure on the X-axis",
            },
            "y_measure": {
                "type": "string",
                "enum": [
                    "return",
                    "volatility",
                    "sharpe",
                    "max_drawdown",
                    "diversification_hhi",
                    "esg_score",
                    "sector_concentration",
                ],
                "description": "Measure on the Y-axis",
            },
            "num_points": {
                "type": "integer",
                "minimum": 5,
                "maximum": 100,
                "description": "Number of parametric solves",
            },
        },
        "required": ["enabled", "x_measure", "y_measure", "num_points"],
        "additionalProperties": False,
    }

    # ── ExtractedSlots sub-schema ─────────────────────────────────────────────

    extracted_slots_schema: dict[str, Any] = {
        "type": "object",
        "description": "Partial or complete OptimizationRequest fields",
        "properties": {
            "tickers": {
                "anyOf": [
                    {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "description": "List of uppercase ticker symbols",
                    },
                    {"type": "null"},
                ],
            },
            "budget": {
                "anyOf": [
                    {
                        "type": "number",
                        "exclusiveMinimum": 0.0,
                        "description": "Investment budget in USD",
                    },
                    {"type": "null"},
                ],
            },
            "min_return": {
                "anyOf": [
                    {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 5.0,
                        "description": "Minimum annualised return (decimal)",
                    },
                    {"type": "null"},
                ],
            },
            "max_volatility": {
                "anyOf": [
                    {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 5.0,
                        "description": "Maximum annualised volatility (decimal)",
                    },
                    {"type": "null"},
                ],
            },
            "max_weight_per_asset": {
                "anyOf": [
                    {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Maximum weight for any single asset",
                    },
                    {"type": "null"},
                ],
            },
            "min_weight_per_asset": {
                "anyOf": [
                    {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Minimum weight for any included asset",
                    },
                    {"type": "null"},
                ],
            },
            "num_assets_to_select": {
                "anyOf": [
                    {
                        "type": "integer",
                        "minimum": 2,
                        "maximum": 50,
                        "description": "Number of assets to select",
                    },
                    {"type": "null"},
                ],
            },
            "lookback_days": {
                "anyOf": [
                    {
                        "type": "integer",
                        "minimum": 30,
                        "maximum": 3650,
                        "description": "Historical lookback in calendar days",
                    },
                    {"type": "null"},
                ],
            },
            "run_quantum": {
                "anyOf": [
                    {
                        "type": "boolean",
                        "description": "Whether to run quantum optimization",
                    },
                    {"type": "null"},
                ],
            },
            "sector_constraints": {
                "anyOf": [
                    {
                        "type": "array",
                        "items": sector_constraint_schema,
                        "maxItems": 20,
                        "description": "Sector-level allocation constraints",
                    },
                    {"type": "null"},
                ],
            },
            "objectives": {
                "anyOf": [
                    {
                        "type": "array",
                        "items": business_objective_schema,
                        "maxItems": 20,
                        "description": "Multi-objective matrix rows",
                    },
                    {"type": "null"},
                ],
            },
            "frontier": {
                "anyOf": [
                    frontier_config_schema,
                    {"type": "null"},
                ],
                "description": "Efficient-frontier sweep configuration",
            },
        },
        # All fields are optional — partial extractions are valid.
        "required": [],
        "additionalProperties": False,
    }

    # ── Top-level LLMSlotFillerOutput schema ──────────────────────────────────

    top_level_schema: dict[str, Any] = {
        "type": "object",
        "description": "Slot-filling response from the portfolio optimization assistant",
        "properties": {
            "clarifying_question": {
                "anyOf": [
                    {
                        "type": "string",
                        "maxLength": 1000,
                        "description": (
                            "Question to ask the user when required slots are missing. "
                            "Null when all required slots are present."
                        ),
                    },
                    {"type": "null"},
                ],
            },
            "slots": {
                "anyOf": [
                    extracted_slots_schema,
                    {"type": "null"},
                ],
                "description": (
                    "Extracted OptimizationRequest fields. "
                    "Null when a clarifying question is returned."
                ),
            },
            "confidence": {
                "anyOf": [
                    {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Confidence score for the extraction (0-1)",
                    },
                    {"type": "null"},
                ],
            },
        },
        "required": ["clarifying_question", "slots", "confidence"],
        "additionalProperties": False,
    }

    return {
        "name": "slot_filling_response",
        "description": (
            "Structured output for the portfolio optimization slot-filling assistant. "
            "Returns either a clarifying question or extracted slot values."
        ),
        "strict": True,
        "schema": top_level_schema,
    }


def format_missing_fields_description(missing_fields: list[str]) -> str:
    """Format a human-readable description of missing required fields.

    Used by the fallback (no-API-key) path to construct a clarifying
    question without calling the LLM.

    Args:
        missing_fields: List of field names that are still missing.

    Returns:
        A human-readable comma-separated description of the missing fields.

    Example::

        format_missing_fields_description(["tickers", "budget"])
        # → "the stock tickers you want to include and your investment budget"
    """
    field_descriptions: dict[str, str] = {
        "tickers": "the stock tickers you want to include (at least 2 symbols)",
        "budget": "your total investment budget in USD",
    }
    descriptions = [
        field_descriptions.get(f, f.replace("_", " ")) for f in missing_fields
    ]
    if not descriptions:
        return "additional details"
    if len(descriptions) == 1:
        return descriptions[0]
    return ", ".join(descriptions[:-1]) + " and " + descriptions[-1]
