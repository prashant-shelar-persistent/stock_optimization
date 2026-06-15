"""QAOA (Quantum Approximate Optimization Algorithm) solver using Qiskit.

Implements :class:`QAOASolver`, a concrete :class:`~app.engines.quantum.base.BaseQuantumSolver`
that runs QAOA on the Qiskit Aer statevector simulator to solve the asset
selection QUBO. Returns the best binary solution found and the corresponding
portfolio metrics.

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

    from app.engines.quantum.qaoa_qiskit import QAOASolver

    solver = QAOASolver()
    result = solver.solve(
        tickers=["AAPL", "MSFT", "GOOGL"],
        qubo_matrix=Q,
        expected_returns=mu,
        covariance_matrix=sigma,
        budget=100_000.0,
        num_assets_to_select=2,
        p=2,
    )
    print(result.selected_assets)
    print(result.metrics.sharpe_ratio)
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from app.core.exceptions import QuantumTimeoutError
from app.core.logging import get_logger
from app.engines.quantum.base import BaseQuantumSolver
from app.engines.quantum.schemas import QuantumAssetResult


logger = get_logger(__name__)

# Estimated circuit depth formula: 2 * p * n
# Each QAOA layer has a cost unitary (O(n²) gates) and mixer (O(n) gates).
_CIRCUIT_DEPTH_FACTOR = 2


class QAOASolver(BaseQuantumSolver):
    """QAOA portfolio optimizer backed by Qiskit.

    Uses the Qiskit Aer statevector simulator with the COBYLA classical
    optimizer to solve the asset selection QUBO via QAOA.

    Attributes:
        settings: Application settings (used for timeout and risk-free rate).
    """

    def __init__(self) -> None:
        """Initialise the QAOA solver."""
        from app.core.config import get_settings as _get_settings  # noqa: PLC0415
        self.settings = _get_settings()

    @property
    def name(self) -> str:
        """Algorithm name."""
        return "QAOA"

    def solve(
        self,
        tickers: list[str],
        qubo_matrix: np.ndarray,
        expected_returns: np.ndarray,
        covariance_matrix: np.ndarray,
        budget: float,
        num_assets_to_select: int,
        sector_tags: dict[str, str] | None = None,
        p: int = 2,
        **kwargs: Any,
    ) -> QuantumAssetResult:
        """Run QAOA on the Qiskit Aer simulator to solve the asset selection QUBO.

        Attempts to use Qiskit's QAOA implementation with the Sampler primitive.
        Falls back to greedy selection if Qiskit is unavailable or raises an
        unexpected error.

        Args:
            tickers: Asset ticker symbols, length n.
            qubo_matrix: QUBO matrix Q, shape (n, n). Upper-triangular form
                as returned by :func:`~app.engines.quantum.qubo.build_qubo`.
            expected_returns: Annualised expected returns, shape (n,).
            covariance_matrix: Annualised covariance matrix, shape (n, n).
            budget: Total investment budget in USD.
            num_assets_to_select: Target number of assets k to select.
            sector_tags: Optional mapping of ticker → GICS sector name.
            p: QAOA circuit depth (number of QAOA layers / repetitions).
                Higher p generally improves solution quality at the cost of
                longer circuit execution time. Defaults to 2.
            **kwargs: Additional keyword arguments (ignored).

        Returns:
            :class:`~app.engines.quantum.schemas.QuantumAssetResult` containing:
            - ``selected_assets``: List of selected ticker symbols.
            - ``weights``: Equal-weight allocations for selected assets.
            - ``metrics``: Portfolio performance metrics.
            - ``circuit_depth``: Estimated circuit depth (2 * p * n).
            - ``num_qubits``: Number of qubits used (= number of assets).
            - ``solve_time_ms``: Wall-clock time for the solve in milliseconds.
            - ``fallback_used``: True if greedy fallback was used.

        Raises:
            QuantumTimeoutError: If the solver exceeds the configured
                ``QUANTUM_TIMEOUT_SECONDS`` setting.

        Note:
            The returned portfolio uses **equal weighting** among selected
            assets. This is intentional — the QUBO formulation solves the
            binary asset *selection* problem; continuous weight optimisation
            is handled by the classical Markowitz engine.
        """
        n = len(tickers)
        start_time = time.perf_counter()
        fallback_used = False

        logger.info(
            "qaoa_started",
            num_qubits=n,
            p=p,
            num_assets_to_select=num_assets_to_select,
        )

        x_opt: np.ndarray | None = None

        try:
            # ── Import Qiskit stack (lazy to allow graceful fallback) ──────────
            from qiskit.primitives import Sampler  # noqa: PLC0415
            from qiskit_algorithms import QAOA  # noqa: PLC0415
            from qiskit_algorithms.optimizers import COBYLA  # noqa: PLC0415
            from qiskit_optimization import QuadraticProgram  # noqa: PLC0415
            from qiskit_optimization.algorithms import (  # noqa: PLC0415
                MinimumEigenOptimizer,
            )

            # ── Build QuadraticProgram from QUBO matrix ───────────────────────
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

            # ── Check timeout before solving ──────────────────────────────────
            elapsed = time.perf_counter() - start_time
            if elapsed > self.settings.QUANTUM_TIMEOUT_SECONDS:
                raise QuantumTimeoutError(
                    message="QAOA timed out before solving.",
                    timeout_seconds=self.settings.QUANTUM_TIMEOUT_SECONDS,
                )

            # ── Run QAOA ──────────────────────────────────────────────────────
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
            x_opt = self._greedy_selection(expected_returns, num_assets_to_select)
            fallback_used = True

        solve_time_ms = (time.perf_counter() - start_time) * 1000.0

        # ── Check timeout after solve ─────────────────────────────────────────
        if solve_time_ms / 1000.0 > self.settings.QUANTUM_TIMEOUT_SECONDS:
            raise QuantumTimeoutError(
                message=(
                    f"QAOA exceeded timeout of {self.settings.QUANTUM_TIMEOUT_SECONDS}s "
                    f"(took {solve_time_ms / 1000.0:.1f}s)."
                ),
                timeout_seconds=self.settings.QUANTUM_TIMEOUT_SECONDS,
            )

        # ── Enforce cardinality constraint ────────────────────────────────────
        # The QUBO solution may select more or fewer than k assets due to
        # approximation errors. Adjust by adding/removing assets by return rank.
        assert x_opt is not None
        x_binary = self._enforce_cardinality(
            x_opt, num_assets_to_select, expected_returns
        )
        selected_indices = [i for i in range(n) if x_binary[i] > 0.5]
        selected_tickers = [tickers[i] for i in selected_indices]

        # ── Build equal-weight portfolio ──────────────────────────────────────
        weights_list, metrics = self._build_equal_weight_portfolio(
            tickers=tickers,
            x_binary=x_binary,
            expected_returns=expected_returns,
            covariance_matrix=covariance_matrix,
            budget=budget,
            sector_tags=sector_tags,
            risk_free_rate=self.settings.RISK_FREE_RATE,
        )

        # Compute QUBO energy for the selected solution
        qubo_energy_val = float(x_binary @ qubo_matrix @ x_binary)
        metrics.qubo_energy = qubo_energy_val

        # Estimate circuit depth: 2 * p layers × n qubits
        circuit_depth = _CIRCUIT_DEPTH_FACTOR * p * n

        logger.info(
            "qaoa_complete",
            selected_tickers=selected_tickers,
            sharpe=round(metrics.sharpe_ratio, 4),
            expected_return=round(metrics.expected_return, 4),
            volatility=round(metrics.volatility, 4),
            solve_time_ms=round(solve_time_ms, 1),
            circuit_depth=circuit_depth,
            fallback_used=fallback_used,
        )

        return QuantumAssetResult(
            algorithm="QAOA",
            selected_assets=selected_tickers,
            weights=weights_list,
            metrics=metrics,
            solve_time_ms=solve_time_ms,
            num_qubits=n,
            circuit_depth=circuit_depth,
            solver_used="qiskit_sampler" if not fallback_used else "greedy_fallback",
            fallback_used=fallback_used,
            extra={
                "p": p,
                "qubo_energy": round(qubo_energy_val, 6),
                "num_assets_to_select": num_assets_to_select,
            },
        )


def run_qaoa(
    tickers: list[str],
    qubo_matrix: np.ndarray,
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    budget: float,
    num_assets_to_select: int,
    sector_tags: dict[str, str] | None = None,
    p: int = 2,
) -> QuantumAssetResult:
    """Convenience function to run QAOA without instantiating the solver class.

    Creates a :class:`QAOASolver` instance and calls :meth:`~QAOASolver.solve`.

    Args:
        tickers: Asset ticker symbols, length n.
        qubo_matrix: QUBO matrix Q, shape (n, n).
        expected_returns: Annualised expected returns, shape (n,).
        covariance_matrix: Annualised covariance matrix, shape (n, n).
        budget: Total investment budget in USD.
        num_assets_to_select: Target number of assets k to select.
        sector_tags: Optional mapping of ticker → GICS sector name.
        p: QAOA circuit depth. Defaults to 2.

    Returns:
        :class:`~app.engines.quantum.schemas.QuantumAssetResult`.

    Raises:
        QuantumTimeoutError: If the solver exceeds the configured timeout.
    """
    solver = QAOASolver()
    return solver.solve(
        tickers=tickers,
        qubo_matrix=qubo_matrix,
        expected_returns=expected_returns,
        covariance_matrix=covariance_matrix,
        budget=budget,
        num_assets_to_select=num_assets_to_select,
        sector_tags=sector_tags,
        p=p,
    )
