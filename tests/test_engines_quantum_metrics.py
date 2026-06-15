"""Unit tests for app.engines.quantum.metrics — quantum portfolio metrics.

Tests cover:
- compute_quantum_portfolio_metrics: happy path, equal weights, QUBO energy
- compute_quantum_solution_quality: cardinality check, brute-force comparison
- compute_classical_vs_quantum_comparison: improvement metrics, recommendation
- select_best_quantum_result: both present, one None, both None
- Re-exported functions from app.data.metrics are accessible
"""

from __future__ import annotations

import numpy as np
import pytest

from app.engines.quantum.metrics import (
    PortfolioMetricsResult,
    annualise_returns,
    compute_classical_vs_quantum_comparison,
    compute_max_drawdown,
    compute_portfolio_metrics,
    compute_quantum_portfolio_metrics,
    compute_quantum_solution_quality,
    compute_sharpe_ratio,
    select_best_quantum_result,
)
from app.engines.quantum.schemas import QuantumPortfolioMetrics


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tickers_4() -> list[str]:
    return ["AAPL", "MSFT", "GOOGL", "AMZN"]


@pytest.fixture
def mu_4() -> np.ndarray:
    return np.array([0.12, 0.10, 0.09, 0.15])


@pytest.fixture
def sigma_4() -> np.ndarray:
    return np.array([
        [0.04, 0.01, 0.008, 0.012],
        [0.01, 0.03, 0.007, 0.009],
        [0.008, 0.007, 0.025, 0.006],
        [0.012, 0.009, 0.006, 0.05],
    ])


# ── compute_quantum_portfolio_metrics ─────────────────────────────────────────

class TestComputeQuantumPortfolioMetrics:
    """Tests for compute_quantum_portfolio_metrics."""

    def test_returns_quantum_portfolio_metrics(
        self,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        result = compute_quantum_portfolio_metrics(
            selected_indices=[0, 3],
            tickers=tickers_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
        )
        assert isinstance(result, QuantumPortfolioMetrics)

    def test_equal_weight_allocation(
        self,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        """Two selected assets should each get 50% weight."""
        result = compute_quantum_portfolio_metrics(
            selected_indices=[0, 3],
            tickers=tickers_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
        )
        # Expected return = 0.5 * 0.12 + 0.5 * 0.15 = 0.135
        expected_return = 0.5 * mu_4[0] + 0.5 * mu_4[3]
        assert abs(result.expected_return - expected_return) < 1e-8

    def test_num_assets_matches_selected(
        self,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        result = compute_quantum_portfolio_metrics(
            selected_indices=[0, 1, 3],
            tickers=tickers_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
        )
        assert result.num_assets == 3

    def test_volatility_is_positive(
        self,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        result = compute_quantum_portfolio_metrics(
            selected_indices=[0, 2],
            tickers=tickers_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
        )
        assert result.volatility > 0.0

    def test_sharpe_ratio_formula(
        self,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        rfr = 0.02
        result = compute_quantum_portfolio_metrics(
            selected_indices=[0, 3],
            tickers=tickers_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
            risk_free_rate=rfr,
        )
        expected_sharpe = (result.expected_return - rfr) / result.volatility
        assert abs(result.sharpe_ratio - expected_sharpe) < 1e-8

    def test_qubo_energy_computed_when_provided(
        self,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        from app.quantum.qubo import build_qubo_matrix
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)
        x = np.array([1.0, 0.0, 0.0, 1.0])
        result = compute_quantum_portfolio_metrics(
            selected_indices=[0, 3],
            tickers=tickers_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
            qubo_matrix=Q,
            x_binary=x,
        )
        expected_energy = float(x @ Q @ x)
        assert result.qubo_energy is not None
        assert abs(result.qubo_energy - expected_energy) < 1e-10

    def test_qubo_energy_none_when_not_provided(
        self,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        result = compute_quantum_portfolio_metrics(
            selected_indices=[0, 3],
            tickers=tickers_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
        )
        assert result.qubo_energy is None

    def test_empty_selected_indices_raises(
        self,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        with pytest.raises(ValueError, match="selected_indices"):
            compute_quantum_portfolio_metrics(
                selected_indices=[],
                tickers=tickers_4,
                expected_returns=mu_4,
                covariance_matrix=sigma_4,
                budget=100_000.0,
            )

    def test_single_asset_selection(
        self,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        result = compute_quantum_portfolio_metrics(
            selected_indices=[0],
            tickers=tickers_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
        )
        assert result.num_assets == 1
        assert abs(result.expected_return - mu_4[0]) < 1e-8


# ── compute_quantum_solution_quality ─────────────────────────────────────────

class TestComputeQuantumSolutionQuality:
    """Tests for compute_quantum_solution_quality."""

    def test_returns_dict_with_required_keys(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        from app.quantum.qubo import build_qubo_matrix
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)
        x = np.array([1.0, 0.0, 0.0, 1.0])
        quality = compute_quantum_solution_quality(Q, x, num_assets_to_select=2)
        assert "qubo_energy" in quality
        assert "cardinality_satisfied" in quality
        assert "num_selected" in quality
        assert "optimal_energy" in quality
        assert "approximation_ratio" in quality
        assert "energy_gap" in quality

    def test_cardinality_satisfied_for_valid_solution(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        from app.quantum.qubo import build_qubo_matrix
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)
        x = np.array([1.0, 0.0, 0.0, 1.0])  # Exactly 2 selected
        quality = compute_quantum_solution_quality(Q, x, num_assets_to_select=2)
        assert quality["cardinality_satisfied"] is True
        assert quality["num_selected"] == 2

    def test_cardinality_not_satisfied_for_wrong_count(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        from app.quantum.qubo import build_qubo_matrix
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)
        x = np.array([1.0, 1.0, 1.0, 0.0])  # 3 selected, expected 2
        quality = compute_quantum_solution_quality(Q, x, num_assets_to_select=2)
        assert quality["cardinality_satisfied"] is False

    def test_optimal_energy_computed_for_small_n(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        from app.quantum.qubo import build_qubo_matrix
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)
        x = np.array([1.0, 0.0, 0.0, 1.0])
        quality = compute_quantum_solution_quality(
            Q, x, num_assets_to_select=2, brute_force_limit=12
        )
        # n=4 <= 12, so optimal should be computed
        assert quality["optimal_energy"] is not None

    def test_optimal_energy_none_for_large_n(self) -> None:
        """For n > brute_force_limit, optimal_energy should be None."""
        n = 15
        Q = np.eye(n)
        x = np.zeros(n)
        x[0] = 1.0
        x[1] = 1.0
        quality = compute_quantum_solution_quality(
            Q, x, num_assets_to_select=2, brute_force_limit=10
        )
        assert quality["optimal_energy"] is None

    def test_qubo_energy_is_float(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        from app.quantum.qubo import build_qubo_matrix
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)
        x = np.array([1.0, 0.0, 0.0, 1.0])
        quality = compute_quantum_solution_quality(Q, x, num_assets_to_select=2)
        assert isinstance(quality["qubo_energy"], float)


# ── compute_classical_vs_quantum_comparison ───────────────────────────────────

class TestComputeClassicalVsQuantumComparison:
    """Tests for compute_classical_vs_quantum_comparison."""

    def test_returns_dict_with_required_keys(self) -> None:
        result = compute_classical_vs_quantum_comparison(
            classical_return=0.12,
            classical_volatility=0.15,
            classical_sharpe=0.67,
            quantum_return=0.10,
            quantum_volatility=0.12,
            quantum_sharpe=0.67,
        )
        required_keys = [
            "algorithm", "sharpe_improvement", "sharpe_improvement_pct",
            "return_diff", "volatility_diff", "quantum_better", "recommendation",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_quantum_better_true_when_higher_sharpe(self) -> None:
        result = compute_classical_vs_quantum_comparison(
            classical_return=0.10,
            classical_volatility=0.15,
            classical_sharpe=0.53,
            quantum_return=0.12,
            quantum_volatility=0.14,
            quantum_sharpe=0.71,
        )
        assert result["quantum_better"] is True

    def test_quantum_better_false_when_lower_sharpe(self) -> None:
        result = compute_classical_vs_quantum_comparison(
            classical_return=0.12,
            classical_volatility=0.14,
            classical_sharpe=0.71,
            quantum_return=0.10,
            quantum_volatility=0.15,
            quantum_sharpe=0.53,
        )
        assert result["quantum_better"] is False

    def test_sharpe_improvement_is_difference(self) -> None:
        result = compute_classical_vs_quantum_comparison(
            classical_return=0.10,
            classical_volatility=0.15,
            classical_sharpe=0.53,
            quantum_return=0.12,
            quantum_volatility=0.14,
            quantum_sharpe=0.71,
        )
        expected = round(0.71 - 0.53, 6)
        assert abs(result["sharpe_improvement"] - expected) < 1e-4

    def test_return_diff_is_quantum_minus_classical(self) -> None:
        result = compute_classical_vs_quantum_comparison(
            classical_return=0.10,
            classical_volatility=0.15,
            classical_sharpe=0.53,
            quantum_return=0.12,
            quantum_volatility=0.14,
            quantum_sharpe=0.71,
        )
        expected = round(0.12 - 0.10, 6)
        assert abs(result["return_diff"] - expected) < 1e-4

    def test_recommendation_is_string(self) -> None:
        result = compute_classical_vs_quantum_comparison(
            classical_return=0.10,
            classical_volatility=0.15,
            classical_sharpe=0.53,
            quantum_return=0.12,
            quantum_volatility=0.14,
            quantum_sharpe=0.71,
        )
        assert isinstance(result["recommendation"], str)
        assert len(result["recommendation"]) > 0

    def test_algorithm_name_in_result(self) -> None:
        result = compute_classical_vs_quantum_comparison(
            classical_return=0.10,
            classical_volatility=0.15,
            classical_sharpe=0.53,
            quantum_return=0.12,
            quantum_volatility=0.14,
            quantum_sharpe=0.71,
            algorithm_name="QAOA",
        )
        assert result["algorithm"] == "QAOA"

    def test_zero_classical_sharpe_does_not_crash(self) -> None:
        result = compute_classical_vs_quantum_comparison(
            classical_return=0.02,
            classical_volatility=0.15,
            classical_sharpe=0.0,
            quantum_return=0.10,
            quantum_volatility=0.14,
            quantum_sharpe=0.57,
        )
        assert isinstance(result["sharpe_improvement_pct"], float)


# ── select_best_quantum_result ────────────────────────────────────────────────

class TestSelectBestQuantumResult:
    """Tests for select_best_quantum_result."""

    def test_returns_qaoa_when_higher_sharpe(self) -> None:
        result = select_best_quantum_result(qaoa_sharpe=0.8, vqe_sharpe=0.6)
        assert result is not None
        assert result[0] == "QAOA"
        assert result[1] == 0.8

    def test_returns_vqe_when_higher_sharpe(self) -> None:
        result = select_best_quantum_result(qaoa_sharpe=0.6, vqe_sharpe=0.9)
        assert result is not None
        assert result[0] == "VQE"
        assert result[1] == 0.9

    def test_returns_qaoa_when_vqe_is_none(self) -> None:
        result = select_best_quantum_result(qaoa_sharpe=0.7, vqe_sharpe=None)
        assert result is not None
        assert result[0] == "QAOA"

    def test_returns_vqe_when_qaoa_is_none(self) -> None:
        result = select_best_quantum_result(qaoa_sharpe=None, vqe_sharpe=0.7)
        assert result is not None
        assert result[0] == "VQE"

    def test_returns_none_when_both_none(self) -> None:
        result = select_best_quantum_result(qaoa_sharpe=None, vqe_sharpe=None)
        assert result is None

    def test_returns_tuple_of_str_and_float(self) -> None:
        result = select_best_quantum_result(qaoa_sharpe=0.8, vqe_sharpe=0.6)
        assert isinstance(result, tuple)
        assert isinstance(result[0], str)
        assert isinstance(result[1], float)


# ── Re-exported functions ─────────────────────────────────────────────────────

class TestReExportedFunctions:
    """Tests that re-exported functions from app.data.metrics are accessible."""

    def test_compute_sharpe_ratio_accessible(self) -> None:
        sharpe = compute_sharpe_ratio(0.12, 0.15, risk_free_rate=0.02)
        assert abs(sharpe - (0.12 - 0.02) / 0.15) < 1e-10

    def test_compute_max_drawdown_accessible(self) -> None:
        returns = np.array([0.01, -0.05, 0.02])
        dd = compute_max_drawdown(returns)
        assert isinstance(dd, float)

    def test_annualise_returns_accessible(self) -> None:
        daily = np.full(252, 0.001)
        annual = annualise_returns(daily)
        assert abs(annual - 0.252) < 1e-8

    def test_portfolio_metrics_result_accessible(self) -> None:
        assert PortfolioMetricsResult is not None

    def test_compute_portfolio_metrics_accessible(self) -> None:
        weights = np.array([0.5, 0.5])
        mu = np.array([0.10, 0.12])
        sigma = np.array([[0.04, 0.01], [0.01, 0.03]])
        result = compute_portfolio_metrics(weights, mu, sigma)
        assert isinstance(result, PortfolioMetricsResult)
