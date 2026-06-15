"""Quantum optimization dispatcher for the engines layer.

Orchestrates the full quantum optimization pipeline:
1. Validates the asset count against the quantum complexity limit.
2. Builds the QUBO matrix from expected returns and covariance.
3. Dispatches to both QAOA (Qiskit) and VQE (PennyLane) solvers.
4. Returns a combined :class:`~app.engines.quantum.schemas.QuantumOptimizationResult`.

Design decisions
----------------
- Both QAOA and VQE are always attempted (unless disabled via constraints).
  If one fails, the other's result is still returned. This maximises the
  information available to the comparison and explanation nodes.
- The QUBO is built once and shared between both solvers to ensure they
  are solving the same problem.
- Asset count is capped at ``MAX_QUANTUM_ASSETS`` (default: 8) because
  QAOA/VQE complexity grows exponentially with the number of qubits.
  If the asset list is too large, a
  :class:`~app.core.exceptions.QuantumAssetLimitError` is raised so the
  caller can truncate the list or skip quantum optimization.
- The dispatcher is the primary entry point for the agent layer and API
  layer. The individual solver classes (QAOASolver, VQESolver) can also
  be used directly for testing or custom workflows.

Usage::

    from app.engines.quantum.dispatcher import QuantumDispatcher
    from app.engines.quantum.schemas import QuantumOptimizationInput, QuantumOptimizationConstraints
    import numpy as np

    dispatcher = QuantumDispatcher()
    result = dispatcher.optimize(
        QuantumOptimizationInput(
            tickers=["AAPL", "MSFT", "GOOGL", "AMZN"],
            expected_returns=[0.12, 0.10, 0.09, 0.15],
            cov_matrix=sigma.tolist(),
            constraints=QuantumOptimizationConstraints(num_assets_to_select=2),
            budget=100_000.0,
        )
    )
    if result.qaoa:
        print("QAOA Sharpe:", result.qaoa.metrics.sharpe_ratio)
    if result.vqe:
        print("VQE Sharpe:", result.vqe.metrics.sharpe_ratio)
    print("Best algorithm:", result.best_algorithm)
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from app.core.config import get_settings
from app.core.exceptions import QuantumAssetLimitError
from app.core.logging import get_logger
from app.engines.quantum.metrics import select_best_quantum_result
from app.engines.quantum.qaoa_qiskit import QAOASolver
from app.engines.quantum.qubo import build_qubo
from app.engines.quantum.schemas import (
    QuantumAssetResult,
    QuantumOptimizationInput,
    QuantumOptimizationResult,
)
from app.engines.quantum.vqe_pennylane import VQESolver


logger = get_logger(__name__)

# Default fraction of assets to select when not specified in constraints.
# E.g. for 6 assets, selects max(2, int(6 * 0.5)) = 3 assets.
_DEFAULT_ASSETS_TO_SELECT_FRACTION = 0.5


class QuantumDispatcher:
    """Orchestrates the quantum optimization pipeline.

    Builds the QUBO matrix and dispatches to QAOA and VQE solvers.
    Returns a combined result with both solver outputs and comparison metadata.

    Attributes:
        settings: Application settings (used for asset limits and timeouts).
    """

    def __init__(self) -> None:
        """Initialise the dispatcher."""
        self.settings = get_settings()

    def optimize(
        self,
        input_data: QuantumOptimizationInput,
    ) -> QuantumOptimizationResult:
        """Run the full quantum optimization pipeline.

        Validates inputs, builds the QUBO matrix, dispatches to QAOA and VQE
        solvers, and returns a combined result.

        Args:
            input_data: Validated :class:`QuantumOptimizationInput` containing
                tickers, expected returns, covariance matrix, sector tags,
                constraints, and budget.

        Returns:
            :class:`QuantumOptimizationResult` with:
            - ``qaoa``: QAOA result (or ``None`` if QAOA was disabled or failed).
            - ``vqe``: VQE result (or ``None`` if VQE was disabled or failed).
            - ``best_algorithm``: Name of the algorithm with the highest Sharpe.
            - ``best_sharpe``: Sharpe ratio of the best algorithm.
            - ``num_assets_universe``: Total number of assets in the universe.
            - ``num_assets_selected``: Number of assets selected (= k).
            - ``qubo_shape``: Shape of the QUBO matrix as [n, n].
            - ``total_solve_time_ms``: Total wall-clock time for both solvers.
            - ``extra``: QUBO statistics and other metadata.

        Raises:
            QuantumAssetLimitError: If ``len(tickers) > MAX_QUANTUM_ASSETS``.
                The caller should truncate the asset list or skip quantum
                optimization for large universes.
        """
        tickers = input_data.tickers
        n = len(tickers)
        constraints = input_data.constraints
        start_time = time.perf_counter()

        # ── Validate asset count ──────────────────────────────────────────────
        if n > self.settings.MAX_QUANTUM_ASSETS:
            raise QuantumAssetLimitError(
                num_assets=n,
                max_assets=self.settings.MAX_QUANTUM_ASSETS,
            )

        # ── Determine number of assets to select ──────────────────────────────
        num_assets_to_select = self._resolve_num_assets_to_select(
            n=n,
            requested=constraints.num_assets_to_select,
        )

        logger.info(
            "quantum_dispatch_started",
            num_tickers=n,
            num_assets_to_select=num_assets_to_select,
            lambda_return=constraints.lambda_return,
            lambda_risk=constraints.lambda_risk,
            lambda_cardinality=constraints.lambda_cardinality,
            qaoa_p=constraints.qaoa_p,
            vqe_layers=constraints.vqe_layers,
            vqe_max_iter=constraints.vqe_max_iterations,
            run_qaoa=constraints.run_qaoa,
            run_vqe=constraints.run_vqe,
        )

        # ── Convert inputs to numpy arrays ────────────────────────────────────
        expected_returns = np.asarray(input_data.expected_returns, dtype=float)
        covariance_matrix = np.asarray(input_data.cov_matrix, dtype=float)

        # ── Build QUBO matrix (shared between both solvers) ───────────────────
        qubo_matrix, qubo_meta = build_qubo(
            expected_returns=expected_returns,
            covariance_matrix=covariance_matrix,
            num_assets_to_select=num_assets_to_select,
            lambda_return=constraints.lambda_return,
            lambda_risk=constraints.lambda_risk,
            lambda_cardinality=constraints.lambda_cardinality,
        )

        logger.debug(
            "qubo_built",
            shape=list(qubo_matrix.shape),
            min_val=round(qubo_meta.min_val, 6),
            max_val=round(qubo_meta.max_val, 6),
            frobenius_norm=round(qubo_meta.frobenius_norm, 4),
            num_nonzero=qubo_meta.num_nonzero,
        )

        # ── Run QAOA ──────────────────────────────────────────────────────────
        qaoa_result: QuantumAssetResult | None = None
        if constraints.run_qaoa:
            qaoa_result = self._run_solver(
                solver=QAOASolver(),
                tickers=tickers,
                qubo_matrix=qubo_matrix,
                expected_returns=expected_returns,
                covariance_matrix=covariance_matrix,
                budget=input_data.budget,
                num_assets_to_select=num_assets_to_select,
                sector_tags=input_data.sector_tags,
                p=constraints.qaoa_p,
            )
        else:
            logger.info("qaoa_skipped", reason="run_qaoa=False")

        # ── Run VQE ───────────────────────────────────────────────────────────
        vqe_result: QuantumAssetResult | None = None
        if constraints.run_vqe:
            vqe_result = self._run_solver(
                solver=VQESolver(),
                tickers=tickers,
                qubo_matrix=qubo_matrix,
                expected_returns=expected_returns,
                covariance_matrix=covariance_matrix,
                budget=input_data.budget,
                num_assets_to_select=num_assets_to_select,
                sector_tags=input_data.sector_tags,
                num_layers=constraints.vqe_layers,
                max_iterations=constraints.vqe_max_iterations,
            )
        else:
            logger.info("vqe_skipped", reason="run_vqe=False")

        total_solve_time_ms = (time.perf_counter() - start_time) * 1000.0

        # ── Determine best algorithm ──────────────────────────────────────────
        qaoa_sharpe = qaoa_result.metrics.sharpe_ratio if qaoa_result else None
        vqe_sharpe = vqe_result.metrics.sharpe_ratio if vqe_result else None
        best = select_best_quantum_result(qaoa_sharpe, vqe_sharpe)
        best_algorithm: str | None = best[0] if best else None
        best_sharpe: float | None = best[1] if best else None

        logger.info(
            "quantum_dispatch_complete",
            qaoa_ok=qaoa_result is not None,
            vqe_ok=vqe_result is not None,
            best_algorithm=best_algorithm,
            best_sharpe=round(best_sharpe, 4) if best_sharpe is not None else None,
            total_solve_time_ms=round(total_solve_time_ms, 1),
        )

        return QuantumOptimizationResult(
            qaoa=qaoa_result,
            vqe=vqe_result,
            best_algorithm=best_algorithm,
            best_sharpe=best_sharpe,
            num_assets_universe=n,
            num_assets_selected=num_assets_to_select,
            qubo_shape=[n, n],
            total_solve_time_ms=total_solve_time_ms,
            extra=qubo_meta.to_dict(),
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _resolve_num_assets_to_select(
        n: int,
        requested: int | None,
    ) -> int:
        """Resolve the number of assets to select.

        Args:
            n: Total number of assets in the universe.
            requested: Explicitly requested k, or ``None`` to use the default.

        Returns:
            Resolved k, clamped to [1, n].
        """
        if requested is not None:
            return max(1, min(requested, n))
        # Default: select half the assets (at least 2)
        return max(2, int(n * _DEFAULT_ASSETS_TO_SELECT_FRACTION))

    @staticmethod
    def _run_solver(
        solver: QAOASolver | VQESolver,
        tickers: list[str],
        qubo_matrix: np.ndarray,
        expected_returns: np.ndarray,
        covariance_matrix: np.ndarray,
        budget: float,
        num_assets_to_select: int,
        sector_tags: dict[str, str],
        **solver_kwargs: Any,
    ) -> QuantumAssetResult | None:
        """Run a single quantum solver with error isolation.

        Wraps the solver call in a try/except so that a failure in one
        solver does not prevent the other from running.

        Args:
            solver: Instantiated solver (QAOASolver or VQESolver).
            tickers: Asset ticker symbols.
            qubo_matrix: QUBO matrix.
            expected_returns: Expected returns array.
            covariance_matrix: Covariance matrix.
            budget: Investment budget.
            num_assets_to_select: Target number of assets k.
            sector_tags: Ticker → sector mapping.
            **solver_kwargs: Algorithm-specific parameters.

        Returns:
            :class:`QuantumAssetResult` or ``None`` if the solver failed.
        """
        try:
            result = solver.solve(
                tickers=tickers,
                qubo_matrix=qubo_matrix,
                expected_returns=expected_returns,
                covariance_matrix=covariance_matrix,
                budget=budget,
                num_assets_to_select=num_assets_to_select,
                sector_tags=sector_tags,
                **solver_kwargs,
            )
            logger.info(
                f"{solver.name.lower()}_succeeded",
                sharpe=round(result.metrics.sharpe_ratio, 4),
                selected=result.selected_assets,
                solve_time_ms=round(result.solve_time_ms, 1),
                fallback_used=result.fallback_used,
            )
            return result
        except Exception as exc:
            logger.error(
                f"{solver.name.lower()}_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            return None


def run_quantum_optimization(
    tickers: list[str],
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    budget: float,
    constraints: dict[str, Any] | None = None,
    sector_tags: dict[str, str] | None = None,
) -> QuantumOptimizationResult:
    """Convenience function to run quantum optimization without instantiating the dispatcher.

    Creates a :class:`QuantumDispatcher` instance and calls
    :meth:`~QuantumDispatcher.optimize`.

    This function provides a dict-based interface compatible with the
    agent layer's constraint format.

    Args:
        tickers: Asset ticker symbols, length n. Must satisfy
            n ≤ MAX_QUANTUM_ASSETS.
        expected_returns: Annualised expected returns, shape (n,).
        covariance_matrix: Annualised covariance matrix, shape (n, n).
        budget: Total investment budget in USD.
        constraints: Optional constraint dict. Recognised keys:
            - ``num_assets_to_select`` (int): Target number of assets k.
            - ``lambda_return`` (float): QUBO return weight. Default: 1.0.
            - ``lambda_risk`` (float): QUBO risk weight. Default: 1.0.
            - ``lambda_cardinality`` (float): QUBO cardinality penalty. Default: 5.0.
            - ``qaoa_p`` (int): QAOA circuit depth. Default: 2.
            - ``vqe_layers`` (int): VQE ansatz layers. Default: 2.
            - ``vqe_max_iter`` (int): VQE max iterations. Default: 100.
            - ``run_qaoa`` (bool): Whether to run QAOA. Default: True.
            - ``run_vqe`` (bool): Whether to run VQE. Default: True.
        sector_tags: Optional mapping of ticker → GICS sector name.

    Returns:
        :class:`QuantumOptimizationResult` with QAOA and VQE results.

    Raises:
        QuantumAssetLimitError: If ``len(tickers) > MAX_QUANTUM_ASSETS``.

    Example::

        result = run_quantum_optimization(
            tickers=["AAPL", "MSFT", "GOOGL", "AMZN"],
            expected_returns=mu,
            covariance_matrix=sigma,
            budget=100_000.0,
            constraints={"num_assets_to_select": 2, "qaoa_p": 2},
        )
    """
    from app.engines.quantum.schemas import (  # noqa: PLC0415
        QuantumOptimizationConstraints,
        QuantumOptimizationInput,
    )

    c = constraints or {}

    quantum_constraints = QuantumOptimizationConstraints(
        num_assets_to_select=c.get("num_assets_to_select"),
        lambda_return=float(c.get("lambda_return", 1.0)),
        lambda_risk=float(c.get("lambda_risk", 1.0)),
        lambda_cardinality=float(c.get("lambda_cardinality", 5.0)),
        qaoa_p=int(c.get("qaoa_p", 2)),
        vqe_layers=int(c.get("vqe_layers", 2)),
        vqe_max_iterations=int(c.get("vqe_max_iter", 100)),
        run_qaoa=bool(c.get("run_qaoa", True)),
        run_vqe=bool(c.get("run_vqe", True)),
    )

    input_data = QuantumOptimizationInput(
        tickers=tickers,
        expected_returns=expected_returns.tolist(),
        cov_matrix=covariance_matrix.tolist(),
        sector_tags=sector_tags or {},
        constraints=quantum_constraints,
        budget=budget,
    )

    dispatcher = QuantumDispatcher()
    return dispatcher.optimize(input_data)
