"""Integration tests for the full optimization pipeline.

Tests cover:
1. Classical optimizer end-to-end: input → CVXPY → result with valid metrics
2. Quantum dispatcher end-to-end: input → QUBO → QAOA + VQE → combined result
3. Classical vs. quantum comparison: both engines on same universe
4. QuantumDispatcher: asset limit enforcement
5. Full pipeline: classical + quantum on 4-asset universe with sector constraints

These tests exercise real code paths (no mocking) and verify that the
output shapes, types, and values are correct.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.core.exceptions import QuantumAssetLimitError
from app.engines.classical.optimizer import ClassicalOptimizer
from app.engines.classical.schemas import (
    ClassicalOptimizationInput,
    OptimizationConstraints,
)
from app.engines.quantum.dispatcher import QuantumDispatcher
from app.engines.quantum.metrics import compute_classical_vs_quantum_comparison
from app.engines.quantum.schemas import (
    QuantumOptimizationConstraints,
    QuantumOptimizationInput,
    QuantumOptimizationResult,
)


# ── Shared test data ──────────────────────────────────────────────────────────

TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN"]
MU = [0.12, 0.10, 0.09, 0.15]
SIGMA = [
    [0.04, 0.01, 0.008, 0.012],
    [0.01, 0.03, 0.007, 0.009],
    [0.008, 0.007, 0.025, 0.006],
    [0.012, 0.009, 0.006, 0.05],
]
SECTOR_TAGS = {
    "AAPL": "Information Technology",
    "MSFT": "Information Technology",
    "GOOGL": "Communication Services",
    "AMZN": "Consumer Discretionary",
}
BUDGET = 100_000.0


# ── Classical optimizer integration ──────────────────────────────────────────

class TestClassicalOptimizerIntegration:
    """End-to-end tests for the classical Markowitz optimizer."""

    def test_full_pipeline_produces_valid_portfolio(self) -> None:
        """Full pipeline: input → CVXPY → result with valid metrics."""
        optimizer = ClassicalOptimizer()
        inp = ClassicalOptimizationInput(
            tickers=TICKERS,
            expected_returns=MU,
            cov_matrix=SIGMA,
            sector_tags=SECTOR_TAGS,
            constraints=OptimizationConstraints(
                max_weight_per_asset=0.4,
                risk_tolerance=0.5,
                budget=BUDGET,
            ),
        )
        result = optimizer.optimize(inp)

        # Weights are valid
        assert abs(sum(result.weights.values()) - 1.0) < 1e-4
        assert all(w >= 0.0 for w in result.weights.values())
        assert all(w <= 0.4 + 1e-4 for w in result.weights.values())

        # Metrics are valid
        assert result.portfolio_return > 0.0
        assert result.portfolio_volatility > 0.0
        assert result.sharpe_ratio > 0.0  # All returns > risk-free rate

        # Solver metadata
        assert "optimal" in result.solver_status.lower()
        assert result.solve_time_ms > 0.0
        assert result.num_assets >= 1

    def test_sector_constraint_respected(self) -> None:
        """IT sector capped at 40% — AAPL + MSFT combined weight ≤ 0.40."""
        optimizer = ClassicalOptimizer()
        inp = ClassicalOptimizationInput(
            tickers=TICKERS,
            expected_returns=MU,
            cov_matrix=SIGMA,
            sector_tags=SECTOR_TAGS,
            constraints=OptimizationConstraints(
                sector_limits={"Information Technology": 0.40},
                max_weight_per_asset=0.4,
            ),
        )
        result = optimizer.optimize(inp)
        it_weight = sum(
            w for t, w in result.weights.items()
            if SECTOR_TAGS.get(t) == "Information Technology"
        )
        assert it_weight <= 0.40 + 1e-4

    def test_min_return_constraint_met(self) -> None:
        """Portfolio return must meet the minimum return floor."""
        optimizer = ClassicalOptimizer()
        min_ret = 0.10
        inp = ClassicalOptimizationInput(
            tickers=TICKERS,
            expected_returns=MU,
            cov_matrix=SIGMA,
            constraints=OptimizationConstraints(
                min_portfolio_return=min_ret,
                max_weight_per_asset=0.5,
            ),
        )
        result = optimizer.optimize(inp)
        assert result.portfolio_return >= min_ret - 1e-4

    def test_result_is_json_serialisable(self) -> None:
        """Result should be JSON-serialisable for API responses."""
        optimizer = ClassicalOptimizer()
        inp = ClassicalOptimizationInput(
            tickers=TICKERS,
            expected_returns=MU,
            cov_matrix=SIGMA,
        )
        result = optimizer.optimize(inp)
        json_str = result.model_dump_json()
        assert "weights" in json_str
        assert "sharpe_ratio" in json_str


# ── Quantum dispatcher integration ────────────────────────────────────────────

class TestQuantumDispatcherIntegration:
    """End-to-end tests for the quantum optimization dispatcher."""

    def test_full_pipeline_produces_valid_result(self) -> None:
        """Full pipeline: input → QUBO → QAOA + VQE → combined result."""
        dispatcher = QuantumDispatcher()
        inp = QuantumOptimizationInput(
            tickers=TICKERS,
            expected_returns=MU,
            cov_matrix=SIGMA,
            sector_tags=SECTOR_TAGS,
            constraints=QuantumOptimizationConstraints(
                num_assets_to_select=2,
                run_qaoa=True,
                run_vqe=True,
            ),
            budget=BUDGET,
        )
        result = dispatcher.optimize(inp)

        assert isinstance(result, QuantumOptimizationResult)
        assert result.num_assets_universe == 4
        assert result.num_assets_selected == 2
        assert result.qubo_shape == [4, 4]
        assert result.total_solve_time_ms >= 0.0

    def test_qaoa_result_is_present(self) -> None:
        """QAOA result should be present when run_qaoa=True."""
        dispatcher = QuantumDispatcher()
        inp = QuantumOptimizationInput(
            tickers=TICKERS,
            expected_returns=MU,
            cov_matrix=SIGMA,
            constraints=QuantumOptimizationConstraints(
                num_assets_to_select=2,
                run_qaoa=True,
                run_vqe=False,
            ),
            budget=BUDGET,
        )
        result = dispatcher.optimize(inp)
        assert result.qaoa is not None
        assert result.vqe is None

    def test_vqe_result_is_present(self) -> None:
        """VQE result should be present when run_vqe=True."""
        dispatcher = QuantumDispatcher()
        inp = QuantumOptimizationInput(
            tickers=TICKERS,
            expected_returns=MU,
            cov_matrix=SIGMA,
            constraints=QuantumOptimizationConstraints(
                num_assets_to_select=2,
                run_qaoa=False,
                run_vqe=True,
            ),
            budget=BUDGET,
        )
        result = dispatcher.optimize(inp)
        assert result.vqe is not None
        assert result.qaoa is None

    def test_best_algorithm_is_set_when_both_run(self) -> None:
        """best_algorithm should be set when both QAOA and VQE run."""
        dispatcher = QuantumDispatcher()
        inp = QuantumOptimizationInput(
            tickers=TICKERS,
            expected_returns=MU,
            cov_matrix=SIGMA,
            constraints=QuantumOptimizationConstraints(
                num_assets_to_select=2,
                run_qaoa=True,
                run_vqe=True,
            ),
            budget=BUDGET,
        )
        result = dispatcher.optimize(inp)
        assert result.best_algorithm in ("QAOA", "VQE")
        assert result.best_sharpe is not None

    def test_asset_limit_exceeded_raises(self) -> None:
        """Too many assets should raise QuantumAssetLimitError."""
        dispatcher = QuantumDispatcher()
        # MAX_QUANTUM_ASSETS defaults to 8; use 10 tickers
        many_tickers = [f"T{i}" for i in range(10)]
        n = len(many_tickers)
        mu = [0.10] * n
        sigma = (np.eye(n) * 0.04).tolist()
        inp = QuantumOptimizationInput(
            tickers=many_tickers,
            expected_returns=mu,
            cov_matrix=sigma,
        )
        with pytest.raises(QuantumAssetLimitError):
            dispatcher.optimize(inp)

    def test_qaoa_result_has_valid_weights(self) -> None:
        """QAOA weights should sum to 1.0 and be non-negative."""
        dispatcher = QuantumDispatcher()
        inp = QuantumOptimizationInput(
            tickers=TICKERS,
            expected_returns=MU,
            cov_matrix=SIGMA,
            constraints=QuantumOptimizationConstraints(
                num_assets_to_select=2,
                run_qaoa=True,
                run_vqe=False,
            ),
            budget=BUDGET,
        )
        result = dispatcher.optimize(inp)
        assert result.qaoa is not None
        total_weight = sum(w.weight for w in result.qaoa.weights)
        assert abs(total_weight - 1.0) < 1e-6
        assert all(w.weight >= 0.0 for w in result.qaoa.weights)

    def test_result_is_json_serialisable(self) -> None:
        """Result should be JSON-serialisable for API responses."""
        dispatcher = QuantumDispatcher()
        inp = QuantumOptimizationInput(
            tickers=TICKERS,
            expected_returns=MU,
            cov_matrix=SIGMA,
            constraints=QuantumOptimizationConstraints(
                num_assets_to_select=2,
                run_qaoa=True,
                run_vqe=False,
            ),
            budget=BUDGET,
        )
        result = dispatcher.optimize(inp)
        json_str = result.model_dump_json()
        assert "qaoa" in json_str
        assert "num_assets_universe" in json_str


# ── Classical vs. quantum comparison ─────────────────────────────────────────

class TestClassicalVsQuantumComparison:
    """Integration tests for classical vs. quantum comparison."""

    def test_comparison_on_same_universe(self) -> None:
        """Run both engines on the same universe and compare results."""
        # Classical
        classical_optimizer = ClassicalOptimizer()
        classical_inp = ClassicalOptimizationInput(
            tickers=TICKERS,
            expected_returns=MU,
            cov_matrix=SIGMA,
            constraints=OptimizationConstraints(max_weight_per_asset=0.5),
        )
        classical_result = classical_optimizer.optimize(classical_inp)

        # Quantum (QAOA only for speed)
        quantum_dispatcher = QuantumDispatcher()
        quantum_inp = QuantumOptimizationInput(
            tickers=TICKERS,
            expected_returns=MU,
            cov_matrix=SIGMA,
            constraints=QuantumOptimizationConstraints(
                num_assets_to_select=2,
                run_qaoa=True,
                run_vqe=False,
            ),
            budget=BUDGET,
        )
        quantum_result = quantum_dispatcher.optimize(quantum_inp)

        assert quantum_result.qaoa is not None

        # Compare
        comparison = compute_classical_vs_quantum_comparison(
            classical_return=classical_result.portfolio_return,
            classical_volatility=classical_result.portfolio_volatility,
            classical_sharpe=classical_result.sharpe_ratio,
            quantum_return=quantum_result.qaoa.metrics.expected_return,
            quantum_volatility=quantum_result.qaoa.metrics.volatility,
            quantum_sharpe=quantum_result.qaoa.metrics.sharpe_ratio,
            algorithm_name="QAOA",
        )

        # Comparison result has all required fields
        assert "algorithm" in comparison
        assert "sharpe_improvement" in comparison
        assert "quantum_better" in comparison
        assert "recommendation" in comparison
        assert isinstance(comparison["quantum_better"], bool)
        assert isinstance(comparison["recommendation"], str)
        assert len(comparison["recommendation"]) > 0

    def test_both_engines_produce_positive_sharpe(self) -> None:
        """Both engines should produce positive Sharpe ratios for this universe."""
        # Classical
        classical_optimizer = ClassicalOptimizer()
        classical_inp = ClassicalOptimizationInput(
            tickers=TICKERS,
            expected_returns=MU,
            cov_matrix=SIGMA,
        )
        classical_result = classical_optimizer.optimize(classical_inp)

        # Quantum
        quantum_dispatcher = QuantumDispatcher()
        quantum_inp = QuantumOptimizationInput(
            tickers=TICKERS,
            expected_returns=MU,
            cov_matrix=SIGMA,
            constraints=QuantumOptimizationConstraints(
                num_assets_to_select=2,
                run_qaoa=True,
                run_vqe=False,
            ),
            budget=BUDGET,
        )
        quantum_result = quantum_dispatcher.optimize(quantum_inp)

        assert classical_result.sharpe_ratio > 0.0
        assert quantum_result.qaoa is not None
        assert quantum_result.qaoa.metrics.sharpe_ratio > 0.0
