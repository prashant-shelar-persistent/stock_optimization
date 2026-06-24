"""Quantum optimization dispatcher.

Orchestrates the full quantum optimization pipeline:
1. Validates the asset count against the quantum complexity limit.
2. Builds the QUBO matrix from expected returns and covariance.
3. Dispatches to both QAOA (Qiskit) and VQE (PennyLane) solvers.
4. Returns a combined :class:`~app.schemas.responses.QuantumResult`.

Design decisions
----------------
- Both QAOA and VQE are always attempted. If one fails, the other's
  result is still returned. This maximises the information available
  to the comparison and explanation nodes.
- The QUBO is built once and shared between both solvers to ensure
  they are solving the same problem.
- Asset count is capped at ``MAX_QUANTUM_ASSETS`` (default: 8) because
  QAOA/VQE complexity grows exponentially with the number of qubits.
  If the asset list is too large, a :class:`~app.core.exceptions.QuantumAssetLimitError`
  is raised so the caller can truncate the list or skip quantum optimization.

Usage::

    from app.quantum.dispatcher import run_quantum_optimization

    result = run_quantum_optimization(
        tickers=["AAPL", "MSFT", "GOOGL", "AMZN"],
        expected_returns=mu,
        covariance_matrix=sigma,
        budget=100_000.0,
        constraints={"num_assets_to_select": 2},
    )
    if result.qaoa:
        print("QAOA Sharpe:", result.qaoa.metrics.sharpe_ratio)
    if result.vqe:
        print("VQE Sharpe:", result.vqe.metrics.sharpe_ratio)
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np

from app.core.config import get_settings
from app.core.exceptions import QuantumAssetLimitError
from app.core.logging import get_logger
from app.quantum.qaoa_solver import run_qaoa
from app.quantum.qubo import build_qubo_matrix
from app.quantum.vqe_solver import run_vqe
from app.schemas.responses import QuantumResult


logger = get_logger(__name__)

# Default fraction of assets to select when not specified in constraints.
# E.g. for 6 assets, selects max(2, int(6 * 0.5)) = 3 assets.
_DEFAULT_ASSETS_TO_SELECT_FRACTION = 0.5


def run_quantum_optimization(
    tickers: list[str],
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    budget: float,
    constraints: dict[str, Any],
) -> "QuantumResult":
    """Run QAOA and VQE quantum optimization for portfolio asset selection.

    Builds a QUBO matrix from the provided market data and dispatches to
    both the QAOA (Qiskit) and VQE (PennyLane) solvers. Both results are
    returned in a :class:`~app.schemas.responses.QuantumResult`; either
    may be ``None`` if the corresponding solver failed.

    Args:
        tickers: Asset ticker symbols, length n. Must satisfy n ≤ MAX_QUANTUM_ASSETS.
        expected_returns: Annualised expected returns, shape (n,).
        covariance_matrix: Annualised covariance matrix, shape (n, n).
        budget: Total investment budget in USD.
        constraints: Validated constraint dict from the constraint validation
            node. Recognised keys:
            - ``num_assets_to_select`` (int): Target number of assets k.
              If absent, defaults to ``max(2, int(n * 0.5))``.
            - ``lambda_return`` (float): QUBO return weight. Default: 1.0.
            - ``lambda_risk`` (float): QUBO risk weight. Default: 1.0.
            - ``lambda_cardinality`` (float): QUBO cardinality penalty. Default: 5.0.
            - ``qaoa_p`` (int): QAOA circuit depth. Default: 2.
            - ``vqe_layers`` (int): VQE ansatz layers. Default: 2.
            - ``vqe_max_iter`` (int): VQE max iterations. Default: 100.

    Returns:
        :class:`~app.schemas.responses.QuantumResult` with:
        - ``qaoa``: QAOA result (or ``None`` if QAOA failed).
        - ``vqe``: VQE result (or ``None`` if VQE failed).

    Raises:
        QuantumAssetLimitError: If ``len(tickers) > MAX_QUANTUM_ASSETS``.
            The caller should truncate the asset list or skip quantum
            optimization for large universes.

    Note:
        Both solvers use **equal weighting** among selected assets.
        The QUBO formulation solves the binary asset *selection* problem.
        Continuous weight optimisation is handled by the classical engine.
    """
    settings = get_settings()
    n = len(tickers)

    # ── Validate asset count ──────────────────────────────────────────────────
    if n > settings.MAX_QUANTUM_ASSETS:
        raise QuantumAssetLimitError(
            num_assets=n,
            max_assets=settings.MAX_QUANTUM_ASSETS,
        )

    # ── Determine number of assets to select ─────────────────────────────────
    num_assets_to_select: int = constraints.get("num_assets_to_select") or max(
        2, int(n * _DEFAULT_ASSETS_TO_SELECT_FRACTION)
    )
    num_assets_to_select = max(1, min(num_assets_to_select, n))

    # ── Extract QUBO tuning parameters from constraints ───────────────────────
    lambda_return: float = float(constraints.get("lambda_return", 1.0))
    lambda_risk: float = float(constraints.get("lambda_risk", 1.0))
    lambda_cardinality: float = float(constraints.get("lambda_cardinality", 5.0))
    qaoa_p: int = int(constraints.get("qaoa_p", 2))
    vqe_layers: int = int(constraints.get("vqe_layers", 2))
    vqe_max_iter: int = int(constraints.get("vqe_max_iter", 100))

    logger.info(
        "quantum_dispatch_started",
        num_tickers=n,
        num_assets_to_select=num_assets_to_select,
        lambda_return=lambda_return,
        lambda_risk=lambda_risk,
        lambda_cardinality=lambda_cardinality,
        qaoa_p=qaoa_p,
        vqe_layers=vqe_layers,
        vqe_max_iter=vqe_max_iter,
    )

    # ── Build QUBO matrix (shared between both solvers) ───────────────────────
    qubo_matrix = build_qubo_matrix(
        expected_returns=expected_returns,
        covariance_matrix=covariance_matrix,
        num_assets_to_select=num_assets_to_select,
        lambda_return=lambda_return,
        lambda_risk=lambda_risk,
        lambda_cardinality=lambda_cardinality,
    )

    logger.debug(
        "qubo_built",
        shape=list(qubo_matrix.shape),
        min_val=round(float(qubo_matrix.min()), 6),
        max_val=round(float(qubo_matrix.max()), 6),
        frobenius_norm=round(float(np.linalg.norm(qubo_matrix, "fro")), 4),
    )

    # ── Run QAOA ──────────────────────────────────────────────────────────────
    # Run QAOA and VQE concurrently.
    # Both solvers receive the same QUBO matrix and are fully independent.
    # ThreadPoolExecutor is used (not ProcessPoolExecutor) because Qiskit and
    # PennyLane release the GIL during their C-extension simulation work, so
    # true parallelism is achieved without the overhead of spawning new processes.
    # This halves the quantum stage wall-clock time (e.g. 60s -> 30s).
    qaoa_result = None
    vqe_result = None

    def _run_qaoa() -> Any:
        return run_qaoa(
            tickers=tickers,
            qubo_matrix=qubo_matrix,
            expected_returns=expected_returns,
            covariance_matrix=covariance_matrix,
            budget=budget,
            num_assets_to_select=num_assets_to_select,
            p=qaoa_p,
        )

    def _run_vqe() -> Any:
        return run_vqe(
            tickers=tickers,
            qubo_matrix=qubo_matrix,
            expected_returns=expected_returns,
            covariance_matrix=covariance_matrix,
            budget=budget,
            num_assets_to_select=num_assets_to_select,
            num_layers=vqe_layers,
            max_iterations=vqe_max_iter,
        )

    with ThreadPoolExecutor(max_workers=2) as _pool:
        _future_qaoa = _pool.submit(_run_qaoa)
        _future_vqe = _pool.submit(_run_vqe)

        try:
            qaoa_result = _future_qaoa.result()
            logger.info(
                "qaoa_succeeded",
                sharpe=round(qaoa_result.metrics.sharpe_ratio, 4),
                selected=qaoa_result.selected_assets,
                solve_time_ms=round(qaoa_result.solve_time_ms, 1),
            )
        except Exception as exc:
            logger.error(
                "qaoa_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )

        try:
            vqe_result = _future_vqe.result()
            logger.info(
                "vqe_succeeded",
                sharpe=round(vqe_result.metrics.sharpe_ratio, 4),
                selected=vqe_result.selected_assets,
                solve_time_ms=round(vqe_result.solve_time_ms, 1),
            )
        except Exception as exc:
            logger.error(
                "vqe_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )

    # ── Log summary ───────────────────────────────────────────────────────────
    logger.info(
        "quantum_dispatch_complete",
        qaoa_ok=qaoa_result is not None,
        vqe_ok=vqe_result is not None,
    )

    return QuantumResult(qaoa=qaoa_result, vqe=vqe_result)


def select_best_quantum_result(
    quantum_result: QuantumResult,
) -> tuple[str, float] | None:
    """Select the best quantum result by Sharpe ratio.

    Compares QAOA and VQE results and returns the name and Sharpe ratio
    of the better-performing algorithm. Used by the comparison node to
    determine which quantum approach to highlight.

    Args:
        quantum_result: Combined quantum result from :func:`run_quantum_optimization`.

    Returns:
        Tuple of (algorithm_name, sharpe_ratio) for the best result,
        or ``None`` if both QAOA and VQE failed.

    Example::

        best = select_best_quantum_result(result)
        if best:
            name, sharpe = best
            print(f"Best quantum: {name} with Sharpe {sharpe:.4f}")
    """
    candidates: list[tuple[str, float]] = []

    if quantum_result.qaoa is not None:
        candidates.append(("QAOA", quantum_result.qaoa.metrics.sharpe_ratio))

    if quantum_result.vqe is not None:
        candidates.append(("VQE", quantum_result.vqe.metrics.sharpe_ratio))

    if not candidates:
        return None

    return max(candidates, key=lambda c: c[1])
