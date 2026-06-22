"""Abstract base class for quantum optimization solvers.

Defines the interface that all quantum solvers (QAOA, VQE) must implement.
This enables the dispatcher to treat solvers polymorphically and makes it
easy to add new quantum backends in the future.

Design notes
------------
- The base class uses Python's ``abc`` module to enforce the interface.
- Each solver receives a pre-built QUBO matrix (not raw market data) so
  that the QUBO formulation logic is centralised in the dispatcher.
- Solvers return a :class:`~app.engines.quantum.schemas.QuantumAssetResult`
  which is a rich, JSON-serialisable result type.
- The ``name`` property identifies the algorithm for logging and comparison.

Usage::

    from app.engines.quantum.base import BaseQuantumSolver
    from app.engines.quantum.schemas import QuantumAssetResult
    import numpy as np

    class MyQuantumSolver(BaseQuantumSolver):
        @property
        def name(self) -> str:
            return "MyAlgorithm"

        def solve(
            self,
            tickers,
            qubo_matrix,
            expected_returns,
            covariance_matrix,
            budget,
            num_assets_to_select,
            **kwargs,
        ) -> "QuantumAssetResult":
            ...
"""

from abc import ABC, abstractmethod
from typing import Any

import numpy as np

from app.engines.quantum.schemas import QuantumAssetResult


class BaseQuantumSolver(ABC):
    """Abstract base class for quantum portfolio optimization solvers.

    All quantum solvers (QAOA, VQE, and future backends) must inherit from
    this class and implement the :meth:`solve` and :meth:`name` members.

    The base class provides:
    - A common interface for the dispatcher to call solvers uniformly.
    - Shared helper methods for cardinality enforcement and equal-weight
      portfolio construction.
    - Structured logging via :func:`~app.core.logging.get_logger`.

    Subclasses should:
    - Override :meth:`name` to return a unique algorithm identifier.
    - Override :meth:`solve` to implement the quantum optimization logic.
    - Call :meth:`_enforce_cardinality` to ensure exactly k assets are selected.
    - Call :meth:`_build_equal_weight_portfolio` to construct the result.
    """

    # ── Abstract interface ────────────────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable algorithm name (e.g. ``"QAOA"`` or ``"VQE"``)."""
        ...

    @abstractmethod
    def solve(
        self,
        tickers: list[str],
        qubo_matrix: np.ndarray,
        expected_returns: np.ndarray,
        covariance_matrix: np.ndarray,
        budget: float,
        num_assets_to_select: int,
        **kwargs: Any,
    ) -> "QuantumAssetResult":
        """Run the quantum optimization and return the result.

        Args:
            tickers: Asset ticker symbols, length n. Must satisfy
                n ≤ MAX_QUANTUM_ASSETS.
            qubo_matrix: QUBO matrix Q, shape (n, n). Upper-triangular form
                as returned by :func:`~app.engines.quantum.qubo.build_qubo_matrix`.
            expected_returns: Annualised expected returns, shape (n,).
            covariance_matrix: Annualised covariance matrix, shape (n, n).
            budget: Total investment budget in USD. Used to compute dollar
                allocations in the result.
            num_assets_to_select: Target number of assets k to select.
            **kwargs: Algorithm-specific parameters (e.g. ``p`` for QAOA,
                ``num_layers`` for VQE).

        Returns:
            :class:`~app.engines.quantum.schemas.QuantumAssetResult` with
            the selected assets, weights, metrics, and solver metadata.

        Raises:
            QuantumTimeoutError: If the solver exceeds the configured
                ``QUANTUM_TIMEOUT_SECONDS`` setting.
        """
        ...

    # ── Shared helper methods ─────────────────────────────────────────────────

    @staticmethod
    def _enforce_cardinality(
        x: np.ndarray,
        k: int,
        expected_returns: np.ndarray,
    ) -> np.ndarray:
        """Ensure exactly k assets are selected in the binary solution.

        The quantum solver may return a solution that selects more or fewer
        than k assets due to approximation errors or penalty term imbalance.
        This method adjusts the solution by:
        - Removing the lowest-return selected assets if too many are selected.
        - Adding the highest-return unselected assets if too few are selected.

        Args:
            x: Raw binary solution vector from the quantum solver, shape (n,).
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
            remove_indices = selected_indices[
                np.argsort(returns_selected)[:remove_count]
            ]
            x_binary[remove_indices] = 0.0
        else:
            # Add highest-return unselected assets until exactly k are selected
            unselected_indices = np.where(x_binary < 0.5)[0]
            returns_unselected = expected_returns[unselected_indices]
            add_count = k - selected
            # Sort by return descending → add the best performers first
            add_indices = unselected_indices[
                np.argsort(returns_unselected)[-add_count:]
            ]
            x_binary[add_indices] = 1.0

        return x_binary

    @staticmethod
    def _greedy_selection(
        expected_returns: np.ndarray,
        k: int,
    ) -> np.ndarray:
        """Select top-k assets by expected return (fallback when quantum fails).

        This deterministic greedy strategy is used as a fallback when the
        quantum solver is unavailable or raises an error. It provides a
        reasonable baseline solution that satisfies the cardinality constraint.

        Args:
            expected_returns: Annualised expected returns, shape (n,).
            k: Number of assets to select.

        Returns:
            Binary selection vector, shape (n,), with exactly k ones.
        """
        n = len(expected_returns)
        k = max(1, min(k, n))
        x = np.zeros(n)
        top_k = np.argsort(expected_returns)[-k:]
        x[top_k] = 1.0
        return x

    @staticmethod
    def _build_equal_weight_portfolio(
        tickers: list[str],
        x_binary: np.ndarray,
        expected_returns: np.ndarray,
        covariance_matrix: np.ndarray,
        budget: float,
        sector_tags: dict[str, str] | None = None,
        risk_free_rate: float = 0.02,
    ) -> tuple[list[Any], Any]:
        """Build equal-weight portfolio weights and metrics for selected assets.

        Constructs equal-weight allocations for the selected assets and
        computes portfolio performance metrics (return, volatility, Sharpe).

        Args:
            tickers: All asset ticker symbols, length n.
            x_binary: Binary selection vector, shape (n,). Exactly k ones.
            expected_returns: Annualised expected returns, shape (n,).
            covariance_matrix: Annualised covariance matrix, shape (n, n).
            budget: Total investment budget in USD.
            sector_tags: Optional mapping of ticker → GICS sector name.
            risk_free_rate: Annual risk-free rate for Sharpe computation.

        Returns:
            Tuple of:
            - ``weights_list``: List of :class:`QuantumAssetWeight` objects.
            - ``metrics``: :class:`QuantumPortfolioMetrics` object.
        """
        from app.engines.quantum.schemas import (  # noqa: PLC0415
            QuantumAssetWeight,
            QuantumPortfolioMetrics,
        )

        n = len(tickers)
        selected_indices = [i for i in range(n) if x_binary[i] > 0.5]

        # Equal-weight allocation
        weights_arr = np.zeros(n)
        if selected_indices:
            weight_per_asset = 1.0 / len(selected_indices)
            for i in selected_indices:
                weights_arr[i] = weight_per_asset

        # Portfolio metrics
        port_return = float(expected_returns @ weights_arr)
        port_variance = float(weights_arr @ covariance_matrix @ weights_arr)
        port_vol = float(np.sqrt(max(port_variance, 0.0)))
        sharpe = (
            (port_return - risk_free_rate) / port_vol
            if port_vol > 1e-10
            else 0.0
        )

        # Build weight objects
        tags = sector_tags or {}
        weights_list = [
            QuantumAssetWeight(
                ticker=tickers[i],
                weight=float(weights_arr[i]),
                allocation=float(weights_arr[i] * budget),
                sector=tags.get(tickers[i]),
            )
            for i in selected_indices
        ]

        metrics = QuantumPortfolioMetrics(
            expected_return=port_return,
            volatility=port_vol,
            sharpe_ratio=sharpe,
            num_assets=len(selected_indices),
        )

        return weights_list, metrics
