"""LLM prompt templates for the portfolio optimization agent.

This module centralises all prompt strings and prompt-building logic used
by the LLM explanation node (``app.agents.explainer``).

Separating prompts from the explainer module makes it easy to:
- Iterate on prompt wording without touching business logic
- Unit-test prompt construction independently
- Reuse prompts across multiple callers

Prompt design principles:
    - The system prompt establishes GPT-4o's role as a quantitative
      portfolio analyst speaking to a sophisticated (but non-technical)
      investment professional.
    - The human message is structured as a readable data summary — NOT
      raw JSON — so the model can focus on interpretation rather than
      parsing.
    - Implementation details (CVXPY, QAOA, VQE, LangGraph, etc.) are
      explicitly excluded from the output to keep explanations accessible.
    - Plain text output is requested (no markdown) for easy frontend
      rendering.
    - Token budget is kept tight (≤ 400 tokens output) to minimise
      latency and cost.
"""

from __future__ import annotations

from typing import Any


# ── System prompt ──────────────────────────────────────────────────────────────

PORTFOLIO_EXPLANATION_SYSTEM_PROMPT: str = """\
You are a quantitative portfolio analyst at a leading asset management firm. \
Your role is to explain portfolio optimization results clearly and concisely \
to sophisticated investment professionals who understand finance but are not \
familiar with the underlying computational methods.

Guidelines:
- Write in plain, professional English. No markdown, no bullet points, no \
  headers — continuous prose only.
- Keep your response to 2–3 paragraphs and no more than 250 words.
- Focus on what matters to the investor: risk-adjusted returns (Sharpe ratio), \
  expected return, volatility, and portfolio composition.
- When quantum optimization results are available, compare them objectively \
  against the classical baseline and state which approach is recommended.
- Highlight any constraint trade-offs or warnings the investor should be aware of.
- Do NOT mention implementation details such as CVXPY, QAOA, VQE, PennyLane, \
  Qiskit, LangGraph, QUBO, or any other technical library or algorithm name.
- Do NOT use phrases like "the model", "the algorithm", or "the system". \
  Refer to "the classical optimizer" and "the quantum optimizer" if needed.
- Be specific: cite actual numbers (Sharpe ratios, returns, volatilities) \
  from the data provided.
- End with a clear, actionable recommendation.\
"""


# ── Human message builder ──────────────────────────────────────────────────────

def build_portfolio_explanation_prompt(
    tickers: list[str],
    budget: float,
    classical_result: dict[str, Any] | None,
    quantum_result: dict[str, Any] | None,
    comparison_summary: dict[str, Any] | None,
    constraint_warnings: list[str],
) -> str:
    """Build the human message for the GPT-4o portfolio explanation call.

    Formats all relevant optimization data as a structured, readable text
    summary (not raw JSON). The model receives this as the human turn in a
    two-turn conversation (system + human).

    Args:
        tickers: List of ticker symbols in the optimization universe.
        budget: Total investment budget in USD.
        classical_result: Serialised ``ClassicalResult`` dict, or ``None``
            if classical optimization did not run.
        quantum_result: Serialised ``QuantumResult`` dict, or ``None`` if
            quantum optimization was skipped or failed.
        comparison_summary: Serialised ``ComparisonSummary`` dict, or
            ``None`` if comparison was not computed.
        constraint_warnings: List of constraint warning messages emitted
            during the validation phase.

    Returns:
        A formatted string to be used as the human message content.
    """
    sections: list[str] = []

    # ── Portfolio universe ─────────────────────────────────────────────────────
    sections.append(
        f"PORTFOLIO UNIVERSE\n"
        f"Tickers: {', '.join(tickers)}\n"
        f"Budget: ${budget:,.0f}\n"
        f"Number of assets in universe: {len(tickers)}"
    )

    # ── Classical optimization result ──────────────────────────────────────────
    sections.append(_format_classical_section(classical_result))

    # ── Quantum optimization result ────────────────────────────────────────────
    quantum_section = _format_quantum_section(quantum_result)
    if quantum_section:
        sections.append(quantum_section)
    else:
        sections.append(
            "QUANTUM OPTIMIZATION\n"
            "Quantum optimization was not run for this configuration."
        )

    # ── Comparison summary ─────────────────────────────────────────────────────
    comparison_section = _format_comparison_section(comparison_summary)
    if comparison_section:
        sections.append(comparison_section)

    # ── Constraint warnings ────────────────────────────────────────────────────
    warnings_section = _format_warnings_section(constraint_warnings)
    if warnings_section:
        sections.append(warnings_section)

    # ── Instruction ────────────────────────────────────────────────────────────
    sections.append(
        "TASK\n"
        "Please provide a concise, professional explanation of these results "
        "in 2–3 paragraphs. Cite specific numbers. End with a clear recommendation."
    )

    return "\n\n".join(sections)


# ── Private section formatters ─────────────────────────────────────────────────

def _format_classical_section(classical_result: dict[str, Any] | None) -> str:
    """Format the classical optimization result as a readable text block."""
    if not classical_result:
        return (
            "CLASSICAL OPTIMIZATION (Markowitz MVO)\n"
            "Result: Not available."
        )

    metrics = classical_result.get("metrics", {})
    expected_return = float(metrics.get("expected_return", 0.0))
    volatility = float(metrics.get("volatility", 0.0))
    sharpe_ratio = float(metrics.get("sharpe_ratio", 0.0))
    num_assets = int(metrics.get("num_assets", 0))
    solver_status = classical_result.get("solver_status", "unknown")
    solve_time_ms = float(classical_result.get("solve_time_ms", 0.0))

    # Top 5 holdings by weight
    weights: list[dict[str, Any]] = classical_result.get("weights", [])
    top_holdings = sorted(weights, key=lambda w: float(w.get("weight", 0)), reverse=True)[:5]
    holdings_lines = [
        f"  {w['ticker']}: {float(w['weight']):.1%} "
        f"(${float(w.get('allocation', 0)):,.0f}"
        + (f", {w['sector']}" if w.get("sector") else "")
        + ")"
        for w in top_holdings
    ]
    holdings_str = "\n".join(holdings_lines) if holdings_lines else "  N/A"

    lines = [
        "CLASSICAL OPTIMIZATION (Markowitz Mean-Variance)",
        f"Expected Annual Return: {expected_return:.2%}",
        f"Annual Volatility: {volatility:.2%}",
        f"Sharpe Ratio: {sharpe_ratio:.4f}",
        f"Number of Assets Selected: {num_assets}",
        f"Solver Status: {solver_status}",
        f"Solve Time: {solve_time_ms:.0f} ms",
        "Top Holdings:",
        holdings_str,
    ]
    return "\n".join(lines)


def _format_quantum_section(quantum_result: dict[str, Any] | None) -> str:
    """Format the quantum optimization result as a readable text block.

    Returns an empty string if no quantum result is available.
    """
    if not quantum_result:
        return ""

    parts: list[str] = []

    qaoa = quantum_result.get("qaoa")
    if qaoa:
        parts.append(_format_single_quantum_result("QAOA (Quantum Approximate Optimization)", qaoa))

    vqe = quantum_result.get("vqe")
    if vqe:
        parts.append(_format_single_quantum_result("VQE-style (Variational Quantum Eigensolver)", vqe))

    if not parts:
        return ""

    header = "QUANTUM OPTIMIZATION"
    return header + "\n" + "\n\n".join(parts)


def _format_single_quantum_result(label: str, result: dict[str, Any]) -> str:
    """Format a single quantum algorithm result (QAOA or VQE)."""
    metrics = result.get("metrics", {})
    expected_return = float(metrics.get("expected_return", 0.0))
    volatility = float(metrics.get("volatility", 0.0))
    sharpe_ratio = float(metrics.get("sharpe_ratio", 0.0))
    num_assets = int(metrics.get("num_assets", 0))
    selected_assets: list[str] = result.get("selected_assets", [])
    solve_time_ms = float(result.get("solve_time_ms", 0.0))

    # Circuit/qubit info (QAOA has circuit_depth, both have num_qubits)
    num_qubits = int(result.get("num_qubits", 0))
    circuit_depth = result.get("circuit_depth")

    lines = [
        f"{label}:",
        f"  Expected Annual Return: {expected_return:.2%}",
        f"  Annual Volatility: {volatility:.2%}",
        f"  Sharpe Ratio: {sharpe_ratio:.4f}",
        f"  Number of Assets Selected: {num_assets}",
    ]

    if selected_assets:
        lines.append(f"  Selected Assets: {', '.join(selected_assets)}")

    if num_qubits:
        lines.append(f"  Qubits Used: {num_qubits}")
    if circuit_depth is not None:
        lines.append(f"  Circuit Depth: {circuit_depth}")

    lines.append(f"  Solve Time: {solve_time_ms:.0f} ms")

    return "\n".join(lines)


def _format_comparison_section(comparison_summary: dict[str, Any] | None) -> str:
    """Format the comparison summary as a readable text block.

    Returns an empty string if no comparison summary is available.
    """
    if not comparison_summary:
        return ""

    lines = ["COMPARISON (Quantum vs Classical)"]

    sharpe_qaoa = comparison_summary.get("sharpe_improvement_qaoa")
    sharpe_vqe = comparison_summary.get("sharpe_improvement_vqe")
    return_diff_qaoa = comparison_summary.get("return_diff_qaoa")
    return_diff_vqe = comparison_summary.get("return_diff_vqe")
    volatility_diff_qaoa = comparison_summary.get("volatility_diff_qaoa")
    volatility_diff_vqe = comparison_summary.get("volatility_diff_vqe")
    recommendation = comparison_summary.get("recommendation", "")

    if sharpe_qaoa is not None:
        lines.append(
            f"QAOA Sharpe improvement vs classical: {float(sharpe_qaoa):+.4f}"
        )
    if return_diff_qaoa is not None:
        lines.append(
            f"QAOA return difference vs classical: {float(return_diff_qaoa):+.2%}"
        )
    if volatility_diff_qaoa is not None:
        lines.append(
            f"QAOA volatility difference vs classical: {float(volatility_diff_qaoa):+.2%}"
        )

    if sharpe_vqe is not None:
        lines.append(
            f"VQE Sharpe improvement vs classical: {float(sharpe_vqe):+.4f}"
        )
    if return_diff_vqe is not None:
        lines.append(
            f"VQE return difference vs classical: {float(return_diff_vqe):+.2%}"
        )
    if volatility_diff_vqe is not None:
        lines.append(
            f"VQE volatility difference vs classical: {float(volatility_diff_vqe):+.2%}"
        )

    if recommendation:
        lines.append(f"System recommendation: {recommendation}")

    return "\n".join(lines)


def _format_warnings_section(constraint_warnings: list[str]) -> str:
    """Format constraint warnings as a readable text block.

    Filters out internal technical warnings (e.g. quantum timeout messages)
    that are not meaningful to the investment professional.

    Returns an empty string if there are no user-facing warnings.
    """
    if not constraint_warnings:
        return ""

    # Filter out purely technical warnings that are not investor-relevant
    user_warnings = [
        w for w in constraint_warnings
        if not w.startswith("Quantum optimization failed:")
        and not w.startswith("Quantum timeout:")
    ]

    if not user_warnings:
        return ""

    lines = [f"CONSTRAINT WARNINGS ({len(user_warnings)} detected)"]
    for i, warning in enumerate(user_warnings[:5], start=1):
        lines.append(f"  {i}. {warning}")

    if len(user_warnings) > 5:
        lines.append(f"  ... and {len(user_warnings) - 5} more warning(s).")

    return "\n".join(lines)
