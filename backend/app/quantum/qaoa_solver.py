"""QAOA (Quantum Approximate Optimization Algorithm) solver using Qiskit.

Runs QAOA on the Qiskit Aer statevector simulator to solve the asset
selection QUBO. Returns the best binary solution found and the
corresponding portfolio metrics.

Algorithm overview
------------------
1. Build a ``QuadraticProgram`` from the QUBO matrix.
2. Instantiate QAOA with the Qiskit ``Sampler`` primitive and COBYLA
   classical optimizer.
3. Wrap in ``MinimumEigenOptimizer`` from qiskit-optimization.
4. Solve and extract the binary solution vector.
5. Enforce the cardinality constraint (exactly k assets selected).
6. Compute equal-weight portfolio metrics for the selected assets.

Fallback strategy
-----------------
If Qiskit or qiskit-optimization is not installed (e.g. in lightweight
CI environments), the solver falls back to a greedy selection strategy
that picks the top-k assets by expected return. This ensures the system
degrades gracefully rather than crashing.

Timeout handling
----------------
The solver checks elapsed time before and after the QAOA solve. If the
configured ``QUANTUM_TIMEOUT_SECONDS`` is exceeded, a
:class:`~app.core.exceptions.QuantumTimeoutError` is raised.

Usage::

    from app.quantum.qaoa_solver import run_qaoa

    result = run_qaoa(
        tickers=["AAPL", "MSFT", "GOOGL"],
        qubo_matrix=Q,
        expected_returns=mu,
        covariance_matrix=sigma,
        budget=100_000.0,
        num_assets_to_select=2,
        p=2,  # QAOA circuit depth
    )
    print(result.selected_assets)
    print(result.metrics.sharpe_ratio)
"""

from __future__ import annotations

import time

import numpy as np

from app.core.config import get_settings
from app.core.exceptions import QuantumTimeoutError
from app.core.logging import get_logger
from app.schemas.responses import AssetWeight, PortfolioMetrics, QAOAResult


logger = get_logger(__name__)

TRADING_DAYS_PER_YEAR = 252


def run_qaoa(
    tickers: list[str],
    qubo_matrix: np.ndarray,
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    budget: float,
    num_assets_to_select: int,
    p: int = 2,
) -> QAOAResult:
    """Run QAOA on the Qiskit Aer simulator to solve the asset selection QUBO.

    Attempts to use Qiskit's QAOA implementation with the Sampler primitive.
    Falls back to greedy selection if Qiskit is unavailable or raises an
    unexpected error.

    Args:
        tickers: Asset ticker symbols, length n.
        qubo_matrix: QUBO matrix Q, shape (n, n). Upper-triangular form
            as returned by :func:`~app.quantum.qubo.build_qubo_matrix`.
        expected_returns: Annualised expected returns, shape (n,).
        covariance_matrix: Annualised covariance matrix, shape (n, n).
        budget: Total investment budget in USD. Used to compute dollar
            allocations in the result.
        num_assets_to_select: Target number of assets k to select.
        p: QAOA circuit depth (number of QAOA layers / repetitions).
            Higher p generally improves solution quality at the cost of
            longer circuit execution time. Defaults to 2.

    Returns:
        :class:`~app.schemas.responses.QAOAResult` containing:
        - ``selected_assets``: List of selected ticker symbols.
        - ``weights``: Equal-weight allocations for selected assets.
        - ``metrics``: Portfolio performance metrics.
        - ``circuit_depth``: Estimated circuit depth (2 * p * n).
        - ``num_qubits``: Number of qubits used (= number of assets).
        - ``solve_time_ms``: Wall-clock time for the solve in milliseconds.

    Raises:
        QuantumTimeoutError: If the solver exceeds the configured
            ``QUANTUM_TIMEOUT_SECONDS`` setting.

    Note:
        The returned portfolio uses **equal weighting** among selected
        assets. This is intentional — the QUBO formulation solves the
        binary asset *selection* problem; continuous weight optimisation
        is handled by the classical Markowitz engine.
    """
    settings = get_settings()
    n = len(tickers)
    start_time = time.perf_counter()

    logger.info(
        "qaoa_started",
        num_qubits=n,
        p=p,
        num_assets_to_select=num_assets_to_select,
    )

    x_opt: np.ndarray | None = None

    try:
        # ── Import Qiskit stack (lazy to allow graceful fallback) ─────────────
        from qiskit.primitives import Sampler  # noqa: PLC0415
        from qiskit_algorithms import QAOA  # noqa: PLC0415
        from qiskit_algorithms.optimizers import COBYLA  # noqa: PLC0415
        from qiskit_optimization import QuadraticProgram  # noqa: PLC0415
        from qiskit_optimization.algorithms import MinimumEigenOptimizer  # noqa: PLC0415

        # ── Build QuadraticProgram from QUBO matrix ───────────────────────────
        qp = QuadraticProgram(name="portfolio_selection")
        for i in range(n):
            qp.binary_var(name=f"x{i}")

        # Linear terms (diagonal of Q)
        linear: dict[str, float] = {
            f"x{i}": float(qubo_matrix[i, i]) for i in range(n)
        }

        # Quadratic terms (upper triangle of Q)
        quadratic: dict[tuple[str, str], float] = {}
        for i in range(n):
            for j in range(i + 1, n):
                val = float(qubo_matrix[i, j])
                if abs(val) > 1e-10:
                    quadratic[(f"x{i}", f"x{j}")] = val

        qp.minimize(linear=linear, quadratic=quadratic)

        # ── Check timeout before solving ──────────────────────────────────────
        elapsed = time.perf_counter() - start_time
        if elapsed > settings.QUANTUM_TIMEOUT_SECONDS:
            raise QuantumTimeoutError(
                message="QAOA timed out before solving.",
                timeout_seconds=settings.QUANTUM_TIMEOUT_SECONDS,
            )

        # ── Run QAOA ──────────────────────────────────────────────────────────
        # COBYLA is gradient-free and works well for noisy quantum circuits.
        # maxiter=100 balances solution quality vs. runtime for small n.
        sampler = Sampler()
        optimizer = COBYLA(maxiter=100)
        qaoa = QAOA(sampler=sampler, optimizer=optimizer, reps=p)
        algorithm = MinimumEigenOptimizer(qaoa)

        result = algorithm.solve(qp)
        x_opt = np.array(result.x, dtype=float)

        logger.debug(
            "qaoa_raw_solution",
            x=x_opt.tolist(),
            fval=float(result.fval),
        )

    except QuantumTimeoutError:
        raise
    except Exception as exc:
        logger.warning(
            "qaoa_qiskit_failed_using_greedy_fallback",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        x_opt = _greedy_selection(expected_returns, num_assets_to_select)

    solve_time_ms = (time.perf_counter() - start_time) * 1000

    # ── Check timeout after solve ─────────────────────────────────────────────
    if solve_time_ms / 1000 > settings.QUANTUM_TIMEOUT_SECONDS:
        raise QuantumTimeoutError(
            message=(
                f"QAOA exceeded timeout of {settings.QUANTUM_TIMEOUT_SECONDS}s "
                f"(took {solve_time_ms / 1000:.1f}s)."
            ),
            timeout_seconds=settings.QUANTUM_TIMEOUT_SECONDS,
        )

    # ── Enforce cardinality constraint ────────────────────────────────────────
    # The QUBO solution may select more or fewer than k assets due to
    # approximation errors. Adjust by adding/removing assets by return rank.
    assert x_opt is not None
    x_binary = _enforce_cardinality(x_opt, num_assets_to_select, expected_returns)
    selected_indices = [i for i in range(n) if x_binary[i] > 0.5]
    selected_tickers = [tickers[i] for i in selected_indices]

    # ── Equal-weight allocation among selected assets ─────────────────────────
    weights_arr = np.zeros(n)
    if selected_indices:
        weight_per_asset = 1.0 / len(selected_indices)
        for i in selected_indices:
            weights_arr[i] = weight_per_asset

    # ── Compute portfolio metrics ─────────────────────────────────────────────
    port_return = float(expected_returns @ weights_arr)
    port_variance = float(weights_arr @ covariance_matrix @ weights_arr)
    port_vol = float(np.sqrt(max(port_variance, 0.0)))
    risk_free = settings.RISK_FREE_RATE
    sharpe = (port_return - risk_free) / port_vol if port_vol > 1e-10 else 0.0

    asset_weights = [
        AssetWeight(
            ticker=tickers[i],
            weight=float(weights_arr[i]),
            allocation=float(weights_arr[i] * budget),
        )
        for i in selected_indices
    ]

    metrics = PortfolioMetrics(
        expected_return=port_return,
        volatility=port_vol,
        sharpe_ratio=sharpe,
        num_assets=len(selected_indices),
    )

    # Estimate circuit depth: 2 * p layers × n qubits (rough approximation)
    # Each QAOA layer has a cost unitary (O(n²) gates) and mixer (O(n) gates).
    circuit_depth = 2 * p * n

    logger.info(
        "qaoa_complete",
        selected_tickers=selected_tickers,
        sharpe=round(sharpe, 4),
        expected_return=round(port_return, 4),
        volatility=round(port_vol, 4),
        solve_time_ms=round(solve_time_ms, 1),
        circuit_depth=circuit_depth,
    )

    return QAOAResult(
        selected_assets=selected_tickers,
        weights=asset_weights,
        metrics=metrics,
        circuit_depth=circuit_depth,
        num_qubits=n,
        solve_time_ms=solve_time_ms,
    )


def _greedy_selection(
    expected_returns: np.ndarray,
    k: int,
) -> np.ndarray:
    """Select top-k assets by expected return (fallback when QAOA fails).

    This deterministic greedy strategy is used as a fallback when the
    Qiskit quantum solver is unavailable or raises an error. It provides
    a reasonable baseline solution that satisfies the cardinality constraint.

    Args:
        expected_returns: Annualised expected returns, shape (n,).
        k: Number of assets to select.

    Returns:
        Binary selection vector, shape (n,), with exactly k ones.
    """
    n = len(expected_returns)
    k = min(k, n)
    x = np.zeros(n)
    top_k = np.argsort(expected_returns)[-k:]
    x[top_k] = 1.0
    return x


def _enforce_cardinality(
    x: np.ndarray,
    k: int,
    expected_returns: np.ndarray,
) -> np.ndarray:
    """Ensure exactly k assets are selected in the binary solution.

    The QUBO solver may return a solution that selects more or fewer than
    k assets due to approximation errors or penalty term imbalance. This
    function adjusts the solution by:
    - Removing the lowest-return selected assets if too many are selected.
    - Adding the highest-return unselected assets if too few are selected.

    Args:
        x: Raw binary solution vector from the QUBO solver, shape (n,).
            Values near 1.0 are treated as selected (threshold: 0.5).
        k: Target number of assets to select.
        expected_returns: Annualised expected returns, shape (n,).
            Used to rank assets when adding/removing.

    Returns:
        Adjusted binary vector with exactly k ones, shape (n,).
    """
    x_binary = (np.asarray(x, dtype=float) > 0.5).astype(float)
    selected = int(x_binary.sum())

    if selected == k:
        return x_binary

    if selected > k:
        # Remove lowest-return selected assets until exactly k remain
        selected_indices = np.where(x_binary > 0.5)[0]
        returns_selected = expected_returns[selected_indices]
        remove_count = selected - k
        # Sort by return ascending → remove the worst performers first
        remove_indices = selected_indices[np.argsort(returns_selected)[:remove_count]]
        x_binary[remove_indices] = 0.0
    else:
        # Add highest-return unselected assets until exactly k are selected
        unselected_indices = np.where(x_binary < 0.5)[0]
        returns_unselected = expected_returns[unselected_indices]
        add_count = k - selected
        # Sort by return descending → add the best performers first
        add_indices = unselected_indices[np.argsort(returns_unselected)[-add_count:]]
        x_binary[add_indices] = 1.0

    return x_binary
