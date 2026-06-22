"""Comparison logic for classical vs quantum optimization results.

Computes side-by-side metrics and generates a recommendation string
based on Sharpe ratio, return, and volatility differences.

The comparison is intentionally deterministic — it does not call any
external services. The LLM explanation node uses the comparison summary
as context for generating a natural-language narrative.
"""

from typing import Any

from app.core.logging import get_logger
from app.schemas.responses import ComparisonSummary


logger = get_logger(__name__)

# Threshold for "significant" Sharpe ratio improvement
_SIGNIFICANT_SHARPE_DELTA = 0.05

# Threshold for "marginal" Sharpe ratio improvement
_MARGINAL_SHARPE_DELTA = 0.0


def compute_comparison(
    classical_result: dict[str, Any] | None,
    quantum_result: dict[str, Any] | None,
) -> "ComparisonSummary":
    """Compute comparison metrics between classical and quantum results.

    Computes per-algorithm (QAOA, VQE) differences in Sharpe ratio,
    expected return, and volatility relative to the classical baseline.
    Generates a human-readable recommendation string.

    Args:
        classical_result: Serialised ClassicalResult dict (or None).
        quantum_result: Serialised QuantumResult dict (or None).

    Returns:
        ComparisonSummary with improvement metrics and recommendation.
        All difference fields are ``None`` if the corresponding quantum
        algorithm did not produce a result.
    """
    if classical_result is None:
        logger.warning("comparison_no_classical_result")
        return ComparisonSummary(
            recommendation=(
                "Classical optimization did not produce a result. "
                "Please review your constraints and try again."
            )
        )

    classical_metrics = classical_result.get("metrics", {})
    classical_sharpe = float(classical_metrics.get("sharpe_ratio", 0.0))
    classical_return = float(classical_metrics.get("expected_return", 0.0))
    classical_vol = float(classical_metrics.get("volatility", 0.0))

    sharpe_improvement_qaoa: float | None = None
    sharpe_improvement_vqe: float | None = None
    return_diff_qaoa: float | None = None
    return_diff_vqe: float | None = None
    volatility_diff_qaoa: float | None = None
    volatility_diff_vqe: float | None = None

    if quantum_result:
        qaoa = quantum_result.get("qaoa")
        if qaoa:
            qaoa_metrics = qaoa.get("metrics", {})
            qaoa_sharpe = float(qaoa_metrics.get("sharpe_ratio", 0.0))
            qaoa_return = float(qaoa_metrics.get("expected_return", 0.0))
            qaoa_vol = float(qaoa_metrics.get("volatility", 0.0))

            sharpe_improvement_qaoa = qaoa_sharpe - classical_sharpe
            return_diff_qaoa = qaoa_return - classical_return
            volatility_diff_qaoa = qaoa_vol - classical_vol

            logger.debug(
                "comparison_qaoa_computed",
                sharpe_improvement=round(sharpe_improvement_qaoa, 4),
                return_diff=round(return_diff_qaoa, 4),
                volatility_diff=round(volatility_diff_qaoa, 4),
            )

        vqe = quantum_result.get("vqe")
        if vqe:
            vqe_metrics = vqe.get("metrics", {})
            vqe_sharpe = float(vqe_metrics.get("sharpe_ratio", 0.0))
            vqe_return = float(vqe_metrics.get("expected_return", 0.0))
            vqe_vol = float(vqe_metrics.get("volatility", 0.0))

            sharpe_improvement_vqe = vqe_sharpe - classical_sharpe
            return_diff_vqe = vqe_return - classical_return
            volatility_diff_vqe = vqe_vol - classical_vol

            logger.debug(
                "comparison_vqe_computed",
                sharpe_improvement=round(sharpe_improvement_vqe, 4),
                return_diff=round(return_diff_vqe, 4),
                volatility_diff=round(volatility_diff_vqe, 4),
            )

    recommendation = _generate_recommendation(
        classical_sharpe=classical_sharpe,
        classical_return=classical_return,
        classical_vol=classical_vol,
        sharpe_improvement_qaoa=sharpe_improvement_qaoa,
        sharpe_improvement_vqe=sharpe_improvement_vqe,
        return_diff_qaoa=return_diff_qaoa,
        return_diff_vqe=return_diff_vqe,
        has_quantum=quantum_result is not None,
    )

    logger.info(
        "comparison_complete",
        has_qaoa=sharpe_improvement_qaoa is not None,
        has_vqe=sharpe_improvement_vqe is not None,
        best_quantum_sharpe_delta=_best_improvement(
            sharpe_improvement_qaoa, sharpe_improvement_vqe
        ),
    )

    return ComparisonSummary(
        sharpe_improvement_qaoa=sharpe_improvement_qaoa,
        sharpe_improvement_vqe=sharpe_improvement_vqe,
        return_diff_qaoa=return_diff_qaoa,
        return_diff_vqe=return_diff_vqe,
        volatility_diff_qaoa=volatility_diff_qaoa,
        volatility_diff_vqe=volatility_diff_vqe,
        recommendation=recommendation,
    )


def _best_improvement(
    sharpe_improvement_qaoa: float | None,
    sharpe_improvement_vqe: float | None,
) -> float | None:
    """Return the best (highest) Sharpe improvement across QAOA and VQE."""
    candidates = [
        v for v in [sharpe_improvement_qaoa, sharpe_improvement_vqe]
        if v is not None
    ]
    if not candidates:
        return None
    return max(candidates)


def _generate_recommendation(
    classical_sharpe: float,
    classical_return: float,
    classical_vol: float,
    sharpe_improvement_qaoa: float | None,
    sharpe_improvement_vqe: float | None,
    return_diff_qaoa: float | None,
    return_diff_vqe: float | None,
    has_quantum: bool,
) -> str:
    """Generate a human-readable recommendation string.

    The recommendation is based on the best Sharpe ratio improvement
    across QAOA and VQE. It also notes return and volatility trade-offs
    when the quantum approach offers a different risk/return profile.

    Args:
        classical_sharpe: Sharpe ratio of the classical portfolio.
        classical_return: Expected return of the classical portfolio.
        classical_vol: Volatility of the classical portfolio.
        sharpe_improvement_qaoa: QAOA Sharpe minus classical Sharpe (or None).
        sharpe_improvement_vqe: VQE Sharpe minus classical Sharpe (or None).
        return_diff_qaoa: QAOA return minus classical return (or None).
        return_diff_vqe: VQE return minus classical return (or None).
        has_quantum: Whether quantum optimization was attempted.

    Returns:
        A human-readable recommendation string.
    """
    if not has_quantum:
        return (
            f"The classical Markowitz MVO portfolio achieves a Sharpe ratio of "
            f"{classical_sharpe:.3f} (expected return: {classical_return:.1%}, "
            f"volatility: {classical_vol:.1%}). "
            "Quantum optimization was not run for this configuration."
        )

    best_improvement = _best_improvement(sharpe_improvement_qaoa, sharpe_improvement_vqe)

    if best_improvement is None:
        # Quantum was attempted but both QAOA and VQE failed
        return (
            f"The classical Markowitz MVO portfolio achieves a Sharpe ratio of "
            f"{classical_sharpe:.3f}. "
            "Quantum optimization was attempted but did not produce a valid result. "
            "The classical portfolio is recommended."
        )

    # Determine which algorithm achieved the best improvement
    best_algo = _best_algorithm(sharpe_improvement_qaoa, sharpe_improvement_vqe)
    best_return_diff = (
        return_diff_qaoa
        if best_algo == "QAOA"
        else return_diff_vqe
    )

    if best_improvement > _SIGNIFICANT_SHARPE_DELTA:
        return_note = _return_note(best_return_diff)
        return (
            f"Quantum optimization ({best_algo}) outperforms classical by "
            f"{best_improvement:+.3f} Sharpe ratio points "
            f"(classical: {classical_sharpe:.3f}, {best_algo}: "
            f"{classical_sharpe + best_improvement:.3f}). "
            f"{return_note}"
            f"The quantum portfolio is recommended for this asset universe."
        )

    elif best_improvement > _MARGINAL_SHARPE_DELTA:
        return (
            f"Quantum optimization ({best_algo}) shows a marginal improvement of "
            f"{best_improvement:+.3f} Sharpe ratio points over classical "
            f"(classical: {classical_sharpe:.3f}). "
            "Both approaches are viable; classical is more reliable at scale."
        )

    elif best_improvement < -_SIGNIFICANT_SHARPE_DELTA:
        return (
            f"Classical optimization outperforms quantum by "
            f"{-best_improvement:.3f} Sharpe ratio points "
            f"(classical: {classical_sharpe:.3f}, best quantum: "
            f"{classical_sharpe + best_improvement:.3f}). "
            "The classical Markowitz portfolio is recommended."
        )

    else:
        return (
            f"Classical and quantum approaches produce comparable results "
            f"(Sharpe ratio difference: {best_improvement:+.3f}). "
            f"Classical Sharpe: {classical_sharpe:.3f}. "
            "The classical portfolio is recommended for production use due to "
            "its deterministic and scalable nature."
        )


def _best_algorithm(
    sharpe_improvement_qaoa: float | None,
    sharpe_improvement_vqe: float | None,
) -> str:
    """Return the name of the algorithm with the best Sharpe improvement."""
    if sharpe_improvement_qaoa is None and sharpe_improvement_vqe is None:
        return "quantum"
    if sharpe_improvement_qaoa is None:
        return "VQE"
    if sharpe_improvement_vqe is None:
        return "QAOA"
    return "QAOA" if sharpe_improvement_qaoa >= sharpe_improvement_vqe else "VQE"


def _return_note(return_diff: float | None) -> str:
    """Generate a note about return difference for the recommendation."""
    if return_diff is None:
        return ""
    if return_diff > 0.01:
        return (
            f"The quantum portfolio also offers a higher expected return "
            f"({return_diff:+.1%} vs classical). "
        )
    elif return_diff < -0.01:
        return (
            f"Note: the quantum portfolio has a lower expected return "
            f"({return_diff:+.1%} vs classical) but better risk-adjusted performance. "
        )
    return ""
