"""LLM explanation generator for portfolio optimization results.

Uses GPT-4o via LangChain if OPENAI_API_KEY is configured.
Falls back to a deterministic template-based explanation otherwise.

The explanation is intentionally kept concise (≤ 300 words) and
structured for display in the frontend results panel.

Design decisions:
    - The LLM is called with a structured prompt that includes all
      relevant metrics. The prompt explicitly forbids mentioning
      implementation details (CVXPY, QAOA, VQE, etc.) to keep the
      output accessible to non-technical users.
    - The template fallback produces a deterministic, professional
      explanation that covers the same key points as the LLM version.
    - Both paths return a plain string (no markdown) for easy rendering.
"""

from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger


logger = get_logger(__name__)

_EXPLANATION_PROMPT = """\
You are a portfolio management expert. Explain the following portfolio \
optimization results to a non-technical investment professional in 2-3 \
concise paragraphs (≤ 250 words total).

Portfolio Universe: {tickers}
Budget: ${budget:,.0f}

Classical (Markowitz MVO) Result:
- Expected Return: {classical_return:.1%}
- Volatility: {classical_vol:.1%}
- Sharpe Ratio: {classical_sharpe:.3f}
- Number of Assets: {classical_num_assets}
- Top Holdings: {classical_top_holdings}

{quantum_section}

Comparison: {comparison_recommendation}

Constraint Warnings: {warnings}

Focus on:
1. What the classical optimizer recommends and why
2. How quantum optimization compares (if available)
3. Key risks or constraint trade-offs the investor should be aware of

Be specific, professional, and avoid jargon. Do not mention CVXPY, QAOA, \
VQE, LangGraph, or other technical implementation details. \
Do not use markdown formatting — plain text only.\
"""


def generate_explanation(
    tickers: list[str],
    budget: float,
    classical_result: dict[str, Any] | None,
    quantum_result: dict[str, Any] | None,
    comparison_summary: dict[str, Any] | None,
    constraint_warnings: list[str],
) -> str:
    """Generate a natural-language explanation of optimization results.

    Attempts to use GPT-4o if OPENAI_API_KEY is configured. Falls back
    to a deterministic template-based explanation on any failure.

    Args:
        tickers: List of ticker symbols in the universe.
        budget: Investment budget in USD.
        classical_result: Serialised ClassicalResult dict.
        quantum_result: Serialised QuantumResult dict.
        comparison_summary: Serialised ComparisonSummary dict.
        constraint_warnings: List of constraint warning messages.

    Returns:
        A natural-language explanation string (plain text, no markdown).
    """
    settings = get_settings()

    if settings.OPENAI_API_KEY:
        try:
            return _generate_llm_explanation(
                tickers=tickers,
                budget=budget,
                classical_result=classical_result,
                quantum_result=quantum_result,
                comparison_summary=comparison_summary,
                constraint_warnings=constraint_warnings,
            )
        except Exception as exc:
            logger.warning(
                "llm_explanation_failed_falling_back",
                error=str(exc),
                error_type=type(exc).__name__,
            )

    return _generate_template_explanation(
        tickers=tickers,
        budget=budget,
        classical_result=classical_result,
        quantum_result=quantum_result,
        comparison_summary=comparison_summary,
        constraint_warnings=constraint_warnings,
    )


def _generate_llm_explanation(
    tickers: list[str],
    budget: float,
    classical_result: dict[str, Any] | None,
    quantum_result: dict[str, Any] | None,
    comparison_summary: dict[str, Any] | None,
    constraint_warnings: list[str],
) -> str:
    """Call GPT-4o to generate the explanation.

    Args:
        tickers: List of ticker symbols.
        budget: Investment budget in USD.
        classical_result: Serialised ClassicalResult dict.
        quantum_result: Serialised QuantumResult dict.
        comparison_summary: Serialised ComparisonSummary dict.
        constraint_warnings: List of constraint warning messages.

    Returns:
        LLM-generated explanation string.

    Raises:
        Exception: Any exception from the LangChain/OpenAI call.
    """
    from langchain_core.messages import HumanMessage  # noqa: PLC0415
    from langchain_openai import ChatOpenAI  # noqa: PLC0415

    settings = get_settings()

    # ── Build prompt context ──────────────────────────────────────────────────
    classical_metrics = (classical_result or {}).get("metrics", {})
    classical_return = float(classical_metrics.get("expected_return", 0.0))
    classical_vol = float(classical_metrics.get("volatility", 0.0))
    classical_sharpe = float(classical_metrics.get("sharpe_ratio", 0.0))
    classical_num_assets = int(classical_metrics.get("num_assets", 0))

    # Top 3 holdings by weight
    classical_weights = (classical_result or {}).get("weights", [])
    top_holdings = sorted(
        classical_weights, key=lambda w: w.get("weight", 0), reverse=True
    )[:3]
    top_holdings_str = ", ".join(
        f"{w['ticker']} ({w['weight']:.1%})" for w in top_holdings
    ) or "N/A"

    # ── Quantum section ───────────────────────────────────────────────────────
    quantum_section = _build_quantum_section(quantum_result)

    # ── Comparison recommendation ─────────────────────────────────────────────
    comparison_recommendation = ""
    if comparison_summary:
        comparison_recommendation = comparison_summary.get("recommendation", "")

    prompt = _EXPLANATION_PROMPT.format(
        tickers=", ".join(tickers),
        budget=budget,
        classical_return=classical_return,
        classical_vol=classical_vol,
        classical_sharpe=classical_sharpe,
        classical_num_assets=classical_num_assets,
        classical_top_holdings=top_holdings_str,
        quantum_section=quantum_section or "Quantum optimization was not run.",
        comparison_recommendation=comparison_recommendation or "N/A",
        warnings=", ".join(constraint_warnings) if constraint_warnings else "None",
    )

    llm = ChatOpenAI(
        model="gpt-4o",
        api_key=settings.OPENAI_API_KEY,
        temperature=0.3,
        max_tokens=400,
    )

    logger.info("llm_explanation_calling_gpt4o")
    response = llm.invoke([HumanMessage(content=prompt)])
    explanation = str(response.content).strip()

    logger.info(
        "llm_explanation_gpt4o_succeeded",
        explanation_length=len(explanation),
    )

    return explanation


def _build_quantum_section(quantum_result: dict[str, Any] | None) -> str:
    """Build the quantum results section of the LLM prompt."""
    if not quantum_result:
        return ""

    lines: list[str] = []

    qaoa = quantum_result.get("qaoa")
    if qaoa:
        qaoa_metrics = qaoa.get("metrics", {})
        qaoa_selected = qaoa.get("selected_assets", [])
        lines.append("Quantum (QAOA) Result:")
        lines.append(
            f"- Expected Return: {float(qaoa_metrics.get('expected_return', 0)):.1%}"
        )
        lines.append(
            f"- Volatility: {float(qaoa_metrics.get('volatility', 0)):.1%}"
        )
        lines.append(
            f"- Sharpe Ratio: {float(qaoa_metrics.get('sharpe_ratio', 0)):.3f}"
        )
        if qaoa_selected:
            lines.append(f"- Selected Assets: {', '.join(qaoa_selected)}")

    vqe = quantum_result.get("vqe")
    if vqe:
        vqe_metrics = vqe.get("metrics", {})
        vqe_selected = vqe.get("selected_assets", [])
        if lines:
            lines.append("")
        lines.append("Quantum (VQE) Result:")
        lines.append(
            f"- Expected Return: {float(vqe_metrics.get('expected_return', 0)):.1%}"
        )
        lines.append(
            f"- Volatility: {float(vqe_metrics.get('volatility', 0)):.1%}"
        )
        lines.append(
            f"- Sharpe Ratio: {float(vqe_metrics.get('sharpe_ratio', 0)):.3f}"
        )
        if vqe_selected:
            lines.append(f"- Selected Assets: {', '.join(vqe_selected)}")

    return "\n".join(lines)


def _generate_template_explanation(
    tickers: list[str],
    budget: float,
    classical_result: dict[str, Any] | None,
    quantum_result: dict[str, Any] | None,
    comparison_summary: dict[str, Any] | None,
    constraint_warnings: list[str],
) -> str:
    """Generate a deterministic template-based explanation.

    Produces a professional, structured explanation without calling any
    external services. Used as the primary path when OPENAI_API_KEY is
    not configured, and as the fallback when the LLM call fails.

    Args:
        tickers: List of ticker symbols.
        budget: Investment budget in USD.
        classical_result: Serialised ClassicalResult dict.
        quantum_result: Serialised QuantumResult dict.
        comparison_summary: Serialised ComparisonSummary dict.
        constraint_warnings: List of constraint warning messages.

    Returns:
        Template-based explanation string.
    """
    paragraphs: list[str] = []

    # ── Paragraph 1: Classical result summary ─────────────────────────────────
    if classical_result:
        metrics = classical_result.get("metrics", {})
        ret = float(metrics.get("expected_return", 0.0))
        vol = float(metrics.get("volatility", 0.0))
        sharpe = float(metrics.get("sharpe_ratio", 0.0))
        num_assets = int(metrics.get("num_assets", 0))

        # Top 3 holdings by weight
        weights = sorted(
            classical_result.get("weights", []),
            key=lambda w: w.get("weight", 0),
            reverse=True,
        )[:3]
        top_str = ", ".join(
            f"{w['ticker']} ({w['weight']:.1%})" for w in weights
        )

        paragraphs.append(
            f"The portfolio optimizer selected {num_assets} assets from a universe "
            f"of {len(tickers)} tickers with a ${budget:,.0f} budget. "
            f"The optimized portfolio targets an annualised return of {ret:.1%} "
            f"with {vol:.1%} volatility, achieving a Sharpe ratio of {sharpe:.3f}. "
            + (f"Top holdings: {top_str}." if top_str else "")
        )
    else:
        paragraphs.append(
            "Classical optimization did not produce a result. "
            "Please review your constraints and try again."
        )

    # ── Paragraph 2: Quantum comparison ───────────────────────────────────────
    if quantum_result and comparison_summary:
        recommendation = comparison_summary.get("recommendation", "")
        if recommendation:
            paragraphs.append(recommendation)
        else:
            # Build a basic quantum summary
            qaoa = quantum_result.get("qaoa")
            vqe = quantum_result.get("vqe")
            quantum_parts: list[str] = []
            if qaoa:
                qaoa_sharpe = float(qaoa.get("metrics", {}).get("sharpe_ratio", 0))
                quantum_parts.append(f"QAOA (Sharpe: {qaoa_sharpe:.3f})")
            if vqe:
                vqe_sharpe = float(vqe.get("metrics", {}).get("sharpe_ratio", 0))
                quantum_parts.append(f"VQE (Sharpe: {vqe_sharpe:.3f})")
            if quantum_parts:
                paragraphs.append(
                    f"Quantum optimization results: {', '.join(quantum_parts)}. "
                    "Compare these results with the classical baseline above."
                )
    elif quantum_result and not comparison_summary:
        # Quantum ran but comparison failed — provide basic quantum info
        qaoa = quantum_result.get("qaoa")
        vqe = quantum_result.get("vqe")
        if qaoa or vqe:
            parts: list[str] = []
            if qaoa:
                q_sharpe = float(qaoa.get("metrics", {}).get("sharpe_ratio", 0))
                parts.append(f"QAOA Sharpe: {q_sharpe:.3f}")
            if vqe:
                v_sharpe = float(vqe.get("metrics", {}).get("sharpe_ratio", 0))
                parts.append(f"VQE Sharpe: {v_sharpe:.3f}")
            paragraphs.append(
                f"Quantum optimization was also run. Results: {', '.join(parts)}."
            )
    elif quantum_result is None:
        paragraphs.append(
            "Quantum optimization was not run for this configuration. "
            "Enable quantum optimization to compare results against the "
            "classical baseline."
        )

    # ── Paragraph 3: Constraint warnings ──────────────────────────────────────
    if constraint_warnings:
        # Filter out quantum failure warnings for the user-facing explanation
        user_warnings = [
            w for w in constraint_warnings
            if not w.startswith("Quantum optimization failed:")
        ]
        if user_warnings:
            warning_text = "; ".join(user_warnings[:3])
            if len(user_warnings) > 3:
                warning_text += f" (and {len(user_warnings) - 3} more)"
            paragraphs.append(
                f"Note: {len(user_warnings)} constraint warning(s) were detected: "
                f"{warning_text}. "
                "Consider relaxing these constraints if the results seem suboptimal."
            )

    return "\n\n".join(paragraphs)
