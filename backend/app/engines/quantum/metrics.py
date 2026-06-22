"""Quantum portfolio metrics computation.

This module provides metrics functions specific to the quantum optimization
engine, including:

1. **Quantum solution quality metrics** — approximation ratio, QUBO energy
   gap, and cardinality satisfaction rate.
2. **Portfolio metrics for quantum-selected portfolios** — computes standard
   portfolio performance metrics (return, volatility, Sharpe) for equal-weight
   portfolios selected by quantum algorithms.
3. **Comparison utilities** — functions to compare quantum vs. classical
   results and compute improvement metrics.

Re-exports
----------
Core portfolio metrics functions from :mod:`app.data.metrics` are re-exported
here for convenience so callers can import from one place.

Usage::

    from app.engines.quantum.metrics import (
        compute_quantum_portfolio_metrics,
        compute_quantum_solution_quality,
        compute_classical_vs_quantum_comparison,
    )
    import numpy as np

    # Compute metrics for a quantum-selected portfolio
    metrics = compute_quantum_portfolio_metrics(
        selected_indices=[0, 2],
        tickers=["AAPL", "MSFT", "GOOGL"],
        expected_returns=mu,
        covariance_matrix=sigma,
        budget=100_000.0,
        risk_free_rate=0.02,
    )
    print(f"Sharpe: {metrics.sharpe_ratio:.4f}")
"""

from typing import Any

import numpy as np

# Re-export core metrics functions so callers can import from one place
from app.data.metrics import (  # noqa: F401
    PortfolioMetricsResult,
    annualise_returns,
    annualise_volatility,
    compute_cvar,
    compute_max_drawdown,
    compute_portfolio_metrics,
    compute_sharpe_ratio,
    compute_var,
)
from app.engines.quantum.schemas import QuantumPortfolioMetrics


# Trading days per year
TRADING_DAYS_PER_YEAR = 252


def compute_quantum_portfolio_metrics(
    selected_indices: list[int],
    tickers: list[str],
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    budget: float,
    risk_free_rate: float = 0.02,
    qubo_matrix: np.ndarray | None = None,
    x_binary: np.ndarray | None = None,
) -> "QuantumPortfolioMetrics":
    """Compute portfolio metrics for a quantum-selected equal-weight portfolio.

    Constructs equal-weight allocations for the selected assets and computes
    standard portfolio performance metrics.

    Args:
        selected_indices: Indices of selected assets in the tickers list.
            Must be non-empty.
        tickers: All asset ticker symbols, length n.
        expected_returns: Annualised expected returns, shape (n,).
        covariance_matrix: Annualised covariance matrix, shape (n, n).
        budget: Total investment budget in USD (used for dollar allocations).
        risk_free_rate: Annual risk-free rate for Sharpe ratio computation.
            Defaults to 0.02.
        qubo_matrix: Optional QUBO matrix for computing the QUBO energy of
            the selected solution. If ``None``, ``qubo_energy`` is not set.
        x_binary: Optional binary selection vector, shape (n,). If provided
            along with ``qubo_matrix``, the QUBO energy is computed.

    Returns:
        :class:`~app.engines.quantum.schemas.QuantumPortfolioMetrics` with
        expected return, volatility, Sharpe ratio, and number of assets.

    Raises:
        ValueError: If ``selected_indices`` is empty.

    Example::

        metrics = compute_quantum_portfolio_metrics(
            selected_indices=[0, 2],
            tickers=["AAPL", "MSFT", "GOOGL"],
            expected_returns=np.array([0.12, 0.10, 0.09]),
            covariance_matrix=sigma,
            budget=100_000.0,
        )
    """
    if not selected_indices:
        raise ValueError("selected_indices must be non-empty")

    n = len(tickers)
    mu = np.asarray(expected_returns, dtype=float)
    sigma = np.asarray(covariance_matrix, dtype=float)

    # Equal-weight allocation
    weights_arr = np.zeros(n)
    weight_per_asset = 1.0 / len(selected_indices)
    for i in selected_indices:
        weights_arr[i] = weight_per_asset

    # Portfolio metrics
    port_return = float(mu @ weights_arr)
    port_variance = float(weights_arr @ sigma @ weights_arr)
    port_vol = float(np.sqrt(max(port_variance, 0.0)))
    sharpe = (
        (port_return - risk_free_rate) / port_vol
        if port_vol > 1e-10
        else 0.0
    )

    # QUBO energy (optional)
    qubo_energy_val: float | None = None
    if qubo_matrix is not None and x_binary is not None:
        x = np.asarray(x_binary, dtype=float)
        qubo_energy_val = float(x @ qubo_matrix @ x)

    return QuantumPortfolioMetrics(
        expected_return=port_return,
        volatility=port_vol,
        sharpe_ratio=sharpe,
        num_assets=len(selected_indices),
        qubo_energy=qubo_energy_val,
    )


def compute_quantum_solution_quality(
    qubo_matrix: np.ndarray,
    quantum_x: np.ndarray,
    num_assets_to_select: int,
    brute_force_limit: int = 12,
) -> dict[str, Any]:
    """Compute quality metrics for a quantum solution vs. the classical optimum.

    For small problems (n ≤ brute_force_limit), enumerates all feasible
    solutions to find the true optimum and computes the approximation ratio.
    For larger problems, only the QUBO energy and cardinality satisfaction
    are reported.

    Args:
        qubo_matrix: QUBO matrix, shape (n, n).
        quantum_x: Binary solution vector from the quantum solver, shape (n,).
        num_assets_to_select: Target number of assets k.
        brute_force_limit: Maximum n for brute-force enumeration.
            Defaults to 12.

    Returns:
        Dictionary with keys:
        - ``"qubo_energy"``: QUBO energy of the quantum solution (float).
        - ``"cardinality_satisfied"``: Whether exactly k assets are selected (bool).
        - ``"num_selected"``: Actual number of selected assets (int).
        - ``"optimal_energy"``: Optimal QUBO energy (float or None).
        - ``"approximation_ratio"``: Ratio in [0, 1] (float or None).
        - ``"energy_gap"``: Difference between quantum and optimal energy (float or None).

    Example::

        quality = compute_quantum_solution_quality(Q, x_opt, k=2)
        print(f"Approximation ratio: {quality['approximation_ratio']:.4f}")
    """
    from app.engines.quantum.qubo import (  # noqa: PLC0415
        compute_approximation_ratio,
        enumerate_all_solutions,
    )

    n = qubo_matrix.shape[0]
    x = np.asarray(quantum_x, dtype=float)

    # QUBO energy of the quantum solution
    quantum_energy = float(x @ qubo_matrix @ x)

    # Cardinality check
    num_selected = int(np.round(x).sum())
    cardinality_satisfied = num_selected == num_assets_to_select

    # Brute-force optimal (only for small problems)
    optimal_energy: float | None = None
    approximation_ratio: float | None = None
    energy_gap: float | None = None

    if n <= brute_force_limit:
        try:
            solutions = enumerate_all_solutions(qubo_matrix, num_assets_to_select)
            if solutions:
                _, optimal_energy = solutions[0]
                approximation_ratio = compute_approximation_ratio(
                    quantum_energy, optimal_energy
                )
                energy_gap = quantum_energy - optimal_energy
        except Exception:
            pass  # Brute force failed; skip quality metrics

    return {
        "qubo_energy": round(quantum_energy, 6),
        "cardinality_satisfied": cardinality_satisfied,
        "num_selected": num_selected,
        "optimal_energy": round(optimal_energy, 6) if optimal_energy is not None else None,
        "approximation_ratio": round(approximation_ratio, 4) if approximation_ratio is not None else None,
        "energy_gap": round(energy_gap, 6) if energy_gap is not None else None,
    }


def compute_classical_vs_quantum_comparison(
    classical_return: float,
    classical_volatility: float,
    classical_sharpe: float,
    quantum_return: float,
    quantum_volatility: float,
    quantum_sharpe: float,
    algorithm_name: str = "Quantum",
) -> dict[str, Any]:
    """Compute comparison metrics between classical and quantum portfolios.

    Computes absolute and relative differences between classical Markowitz
    MVO and a quantum-selected portfolio.

    Args:
        classical_return: Annualised expected return of the classical portfolio.
        classical_volatility: Annualised volatility of the classical portfolio.
        classical_sharpe: Sharpe ratio of the classical portfolio.
        quantum_return: Annualised expected return of the quantum portfolio.
        quantum_volatility: Annualised volatility of the quantum portfolio.
        quantum_sharpe: Sharpe ratio of the quantum portfolio.
        algorithm_name: Name of the quantum algorithm (e.g. ``"QAOA"``).

    Returns:
        Dictionary with keys:
        - ``"algorithm"``: Algorithm name (str).
        - ``"sharpe_improvement"``: Quantum Sharpe - Classical Sharpe (float).
        - ``"sharpe_improvement_pct"``: Percentage improvement in Sharpe (float).
        - ``"return_diff"``: Quantum return - Classical return (float).
        - ``"volatility_diff"``: Quantum volatility - Classical volatility (float).
        - ``"quantum_better"``: Whether quantum Sharpe > classical Sharpe (bool).
        - ``"recommendation"``: Human-readable recommendation string.

    Example::

        comparison = compute_classical_vs_quantum_comparison(
            classical_return=0.12, classical_volatility=0.15, classical_sharpe=0.67,
            quantum_return=0.10, quantum_volatility=0.12, quantum_sharpe=0.67,
            algorithm_name="QAOA",
        )
    """
    sharpe_improvement = quantum_sharpe - classical_sharpe
    sharpe_improvement_pct = (
        (sharpe_improvement / abs(classical_sharpe)) * 100.0
        if abs(classical_sharpe) > 1e-10
        else 0.0
    )
    return_diff = quantum_return - classical_return
    volatility_diff = quantum_volatility - classical_volatility
    quantum_better = quantum_sharpe > classical_sharpe

    # Build recommendation
    if quantum_better:
        recommendation = (
            f"{algorithm_name} outperforms classical Markowitz by "
            f"{sharpe_improvement:.4f} Sharpe ratio points "
            f"({sharpe_improvement_pct:+.1f}%). "
            f"Consider the {algorithm_name} portfolio for better risk-adjusted returns."
        )
    elif abs(sharpe_improvement) < 0.01:
        recommendation = (
            f"{algorithm_name} and classical Markowitz produce similar risk-adjusted "
            f"returns (Sharpe difference: {sharpe_improvement:.4f}). "
            "Either portfolio is a reasonable choice."
        )
    else:
        recommendation = (
            f"Classical Markowitz outperforms {algorithm_name} by "
            f"{-sharpe_improvement:.4f} Sharpe ratio points. "
            "The classical portfolio offers better risk-adjusted returns for this universe."
        )

    return {
        "algorithm": algorithm_name,
        "sharpe_improvement": round(sharpe_improvement, 6),
        "sharpe_improvement_pct": round(sharpe_improvement_pct, 2),
        "return_diff": round(return_diff, 6),
        "volatility_diff": round(volatility_diff, 6),
        "quantum_better": quantum_better,
        "recommendation": recommendation,
    }


def select_best_quantum_result(
    qaoa_sharpe: float | None,
    vqe_sharpe: float | None,
) -> tuple[str, float] | None:
    """Select the best quantum algorithm by Sharpe ratio.

    Args:
        qaoa_sharpe: Sharpe ratio of the QAOA result, or ``None`` if QAOA failed.
        vqe_sharpe: Sharpe ratio of the VQE result, or ``None`` if VQE failed.

    Returns:
        Tuple of (algorithm_name, sharpe_ratio) for the best result,
        or ``None`` if both QAOA and VQE failed.

    Example::

        best = select_best_quantum_result(qaoa_sharpe=0.8, vqe_sharpe=0.75)
        # ("QAOA", 0.8)
    """
    candidates: list[tuple[str, float]] = []

    if qaoa_sharpe is not None:
        candidates.append(("QAOA", qaoa_sharpe))
    if vqe_sharpe is not None:
        candidates.append(("VQE", vqe_sharpe))

    if not candidates:
        return None

    return max(candidates, key=lambda c: c[1])
