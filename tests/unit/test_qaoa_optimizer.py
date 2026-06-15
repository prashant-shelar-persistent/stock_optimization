"""Unit tests for app.quantum.qaoa_solver.

Tests cover:
- run_qaoa: happy path (greedy fallback when Qiskit unavailable)
- run_qaoa: returns QAOAResult with correct structure
- run_qaoa: selected_assets has exactly k assets
- run_qaoa: weights sum to 1.0
- run_qaoa: portfolio metrics are computed
- _greedy_selection: selects top-k by expected return
- _enforce_cardinality: adjusts selection to exactly k
- QuantumTimeoutError raised when timeout exceeded
- Fallback to greedy when Qiskit raises an exception
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.core.exceptions import QuantumTimeoutError
from app.quantum.qaoa_solver import (
    _enforce_cardinality,
    _greedy_selection,
    run_qaoa,
)
from app.schemas.responses import QAOAResult


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_qaoa_inputs(n: int = 4, k: int = 2):
    """Build synthetic inputs for run_qaoa."""
    rng = np.random.default_rng(42)
    tickers = [f"T{i}" for i in range(n)]
    mu = rng.uniform(0.05, 0.20, n)
    A = rng.normal(0, 0.1, (n, n))
    sigma = A @ A.T + np.eye(n) * 0.01

    from app.quantum.qubo import build_qubo_matrix
    Q = build_qubo_matrix(mu, sigma, num_assets_to_select=k)

    return tickers, Q, mu, sigma, k


# ---------------------------------------------------------------------------
# _greedy_selection
# ---------------------------------------------------------------------------

class TestGreedySelection:
    def test_selects_exactly_k_assets(self):
        mu = np.array([0.10, 0.15, 0.08, 0.20, 0.12])
        x = _greedy_selection(mu, k=2)
        assert int(x.sum()) == 2

    def test_selects_top_k_by_return(self):
        """Should select the assets with the highest expected returns."""
        mu = np.array([0.10, 0.15, 0.08, 0.20, 0.12])
        x = _greedy_selection(mu, k=2)
        # Top 2 by return: index 3 (0.20) and index 1 (0.15)
        assert x[3] == 1.0
        assert x[1] == 1.0
        assert x[0] == 0.0
        assert x[2] == 0.0
        assert x[4] == 0.0

    def test_output_is_binary(self):
        mu = np.array([0.10, 0.15, 0.08, 0.20])
        x = _greedy_selection(mu, k=2)
        for val in x:
            assert val in (0.0, 1.0)

    def test_k_larger_than_n_clamped(self):
        """k > n should be clamped to n."""
        mu = np.array([0.10, 0.15, 0.08])
        x = _greedy_selection(mu, k=10)  # k > n
        assert int(x.sum()) == 3  # All selected

    def test_k_equals_n_selects_all(self):
        mu = np.array([0.10, 0.15, 0.08])
        x = _greedy_selection(mu, k=3)
        assert int(x.sum()) == 3

    def test_k_equals_one_selects_best(self):
        mu = np.array([0.10, 0.15, 0.08, 0.20])
        x = _greedy_selection(mu, k=1)
        assert x[3] == 1.0  # Highest return
        assert int(x.sum()) == 1


# ---------------------------------------------------------------------------
# _enforce_cardinality
# ---------------------------------------------------------------------------

class TestEnforceCardinality:
    def test_correct_cardinality_unchanged(self):
        x = np.array([1.0, 0.0, 1.0, 0.0])
        mu = np.array([0.10, 0.15, 0.08, 0.20])
        result = _enforce_cardinality(x, k=2, expected_returns=mu)
        assert int(result.sum()) == 2

    def test_too_many_selected_reduced_to_k(self):
        x = np.array([1.0, 1.0, 1.0, 0.0])  # 3 selected
        mu = np.array([0.10, 0.15, 0.08, 0.20])
        result = _enforce_cardinality(x, k=2, expected_returns=mu)
        assert int(result.sum()) == 2

    def test_too_few_selected_increased_to_k(self):
        x = np.array([1.0, 0.0, 0.0, 0.0])  # 1 selected
        mu = np.array([0.10, 0.15, 0.08, 0.20])
        result = _enforce_cardinality(x, k=2, expected_returns=mu)
        assert int(result.sum()) == 2

    def test_removes_lowest_return_assets_when_too_many(self):
        """When reducing, should remove lowest-return selected assets."""
        x = np.array([1.0, 1.0, 1.0, 0.0])  # 3 selected
        mu = np.array([0.10, 0.15, 0.08, 0.20])
        result = _enforce_cardinality(x, k=2, expected_returns=mu)
        # Should keep indices 0 (0.10) and 1 (0.15), remove index 2 (0.08)
        assert result[2] == 0.0  # Lowest return removed
        assert result[1] == 1.0  # Kept

    def test_adds_highest_return_assets_when_too_few(self):
        """When adding, should add highest-return unselected assets."""
        x = np.array([1.0, 0.0, 0.0, 0.0])  # 1 selected (index 0)
        mu = np.array([0.10, 0.15, 0.08, 0.20])
        result = _enforce_cardinality(x, k=2, expected_returns=mu)
        # Should add index 3 (0.20) as it has highest return among unselected
        assert result[3] == 1.0

    def test_output_is_binary(self):
        x = np.array([0.7, 0.3, 0.8, 0.1])  # Continuous values
        mu = np.array([0.10, 0.15, 0.08, 0.20])
        result = _enforce_cardinality(x, k=2, expected_returns=mu)
        for val in result:
            assert val in (0.0, 1.0)

    def test_all_zeros_adds_top_k(self):
        x = np.zeros(4)
        mu = np.array([0.10, 0.15, 0.08, 0.20])
        result = _enforce_cardinality(x, k=2, expected_returns=mu)
        assert int(result.sum()) == 2


# ---------------------------------------------------------------------------
# run_qaoa — happy path (greedy fallback)
# ---------------------------------------------------------------------------

class TestRunQaoa:
    def test_returns_qaoa_result(self):
        """run_qaoa should return a QAOAResult (using greedy fallback)."""
        tickers, Q, mu, sigma, k = _make_qaoa_inputs(n=4, k=2)

        # Force greedy fallback by making Qiskit import fail
        with patch.dict("sys.modules", {"qiskit_optimization": None}):
            result = run_qaoa(
                tickers=tickers,
                qubo_matrix=Q,
                expected_returns=mu,
                covariance_matrix=sigma,
                budget=100_000.0,
                num_assets_to_select=k,
                p=1,
            )

        assert isinstance(result, QAOAResult)

    def test_selected_assets_has_exactly_k_assets(self):
        tickers, Q, mu, sigma, k = _make_qaoa_inputs(n=4, k=2)

        with patch.dict("sys.modules", {"qiskit_optimization": None}):
            result = run_qaoa(
                tickers=tickers,
                qubo_matrix=Q,
                expected_returns=mu,
                covariance_matrix=sigma,
                budget=100_000.0,
                num_assets_to_select=k,
            )

        assert len(result.selected_assets) == k

    def test_weights_sum_to_one(self):
        tickers, Q, mu, sigma, k = _make_qaoa_inputs(n=4, k=2)

        with patch.dict("sys.modules", {"qiskit_optimization": None}):
            result = run_qaoa(
                tickers=tickers,
                qubo_matrix=Q,
                expected_returns=mu,
                covariance_matrix=sigma,
                budget=100_000.0,
                num_assets_to_select=k,
            )

        total_weight = sum(w.weight for w in result.weights)
        assert abs(total_weight - 1.0) < 1e-6

    def test_weights_are_equal(self):
        """Equal-weight allocation: each selected asset gets 1/k weight."""
        tickers, Q, mu, sigma, k = _make_qaoa_inputs(n=4, k=2)

        with patch.dict("sys.modules", {"qiskit_optimization": None}):
            result = run_qaoa(
                tickers=tickers,
                qubo_matrix=Q,
                expected_returns=mu,
                covariance_matrix=sigma,
                budget=100_000.0,
                num_assets_to_select=k,
            )

        expected_weight = 1.0 / k
        for asset_weight in result.weights:
            assert abs(asset_weight.weight - expected_weight) < 1e-6

    def test_metrics_are_populated(self):
        tickers, Q, mu, sigma, k = _make_qaoa_inputs(n=4, k=2)

        with patch.dict("sys.modules", {"qiskit_optimization": None}):
            result = run_qaoa(
                tickers=tickers,
                qubo_matrix=Q,
                expected_returns=mu,
                covariance_matrix=sigma,
                budget=100_000.0,
                num_assets_to_select=k,
            )

        assert result.metrics.expected_return is not None
        assert result.metrics.volatility >= 0.0
        assert result.metrics.sharpe_ratio is not None

    def test_num_qubits_equals_n(self):
        tickers, Q, mu, sigma, k = _make_qaoa_inputs(n=4, k=2)

        with patch.dict("sys.modules", {"qiskit_optimization": None}):
            result = run_qaoa(
                tickers=tickers,
                qubo_matrix=Q,
                expected_returns=mu,
                covariance_matrix=sigma,
                budget=100_000.0,
                num_assets_to_select=k,
            )

        assert result.num_qubits == len(tickers)

    def test_circuit_depth_is_positive(self):
        tickers, Q, mu, sigma, k = _make_qaoa_inputs(n=4, k=2)

        with patch.dict("sys.modules", {"qiskit_optimization": None}):
            result = run_qaoa(
                tickers=tickers,
                qubo_matrix=Q,
                expected_returns=mu,
                covariance_matrix=sigma,
                budget=100_000.0,
                num_assets_to_select=k,
                p=2,
            )

        assert result.circuit_depth > 0

    def test_solve_time_ms_is_positive(self):
        tickers, Q, mu, sigma, k = _make_qaoa_inputs(n=4, k=2)

        with patch.dict("sys.modules", {"qiskit_optimization": None}):
            result = run_qaoa(
                tickers=tickers,
                qubo_matrix=Q,
                expected_returns=mu,
                covariance_matrix=sigma,
                budget=100_000.0,
                num_assets_to_select=k,
            )

        assert result.solve_time_ms >= 0.0

    def test_selected_assets_are_valid_tickers(self):
        tickers, Q, mu, sigma, k = _make_qaoa_inputs(n=4, k=2)

        with patch.dict("sys.modules", {"qiskit_optimization": None}):
            result = run_qaoa(
                tickers=tickers,
                qubo_matrix=Q,
                expected_returns=mu,
                covariance_matrix=sigma,
                budget=100_000.0,
                num_assets_to_select=k,
            )

        for ticker in result.selected_assets:
            assert ticker in tickers

    def test_allocation_equals_weight_times_budget(self):
        tickers, Q, mu, sigma, k = _make_qaoa_inputs(n=4, k=2)
        budget = 50_000.0

        with patch.dict("sys.modules", {"qiskit_optimization": None}):
            result = run_qaoa(
                tickers=tickers,
                qubo_matrix=Q,
                expected_returns=mu,
                covariance_matrix=sigma,
                budget=budget,
                num_assets_to_select=k,
            )

        for asset_weight in result.weights:
            expected_alloc = asset_weight.weight * budget
            assert abs(asset_weight.allocation - expected_alloc) < 1e-4


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------

class TestQaoaTimeout:
    def test_timeout_raises_quantum_timeout_error(self):
        """When elapsed time exceeds timeout, QuantumTimeoutError should be raised."""
        tickers, Q, mu, sigma, k = _make_qaoa_inputs(n=4, k=2)

        # Patch time.perf_counter to simulate timeout
        import time
        call_count = [0]
        original_perf_counter = time.perf_counter

        def mock_perf_counter():
            call_count[0] += 1
            # First call returns 0, subsequent calls return large value
            if call_count[0] == 1:
                return 0.0
            return 1000.0  # Way past any timeout

        with (
            patch("app.quantum.qaoa_solver.time.perf_counter", side_effect=mock_perf_counter),
            patch.dict("sys.modules", {"qiskit_optimization": None}),
        ):
            with pytest.raises(QuantumTimeoutError) as exc_info:
                run_qaoa(
                    tickers=tickers,
                    qubo_matrix=Q,
                    expected_returns=mu,
                    covariance_matrix=sigma,
                    budget=100_000.0,
                    num_assets_to_select=k,
                )

        assert exc_info.value.error_code == "QUANTUM_TIMEOUT"


# ---------------------------------------------------------------------------
# Greedy fallback on Qiskit exception
# ---------------------------------------------------------------------------

class TestQaoaGreedyFallback:
    def test_greedy_fallback_on_import_error(self):
        """When Qiskit is not available, should fall back to greedy selection."""
        tickers, Q, mu, sigma, k = _make_qaoa_inputs(n=4, k=2)

        with patch.dict("sys.modules", {"qiskit_optimization": None}):
            result = run_qaoa(
                tickers=tickers,
                qubo_matrix=Q,
                expected_returns=mu,
                covariance_matrix=sigma,
                budget=100_000.0,
                num_assets_to_select=k,
            )

        # Should still return a valid result
        assert isinstance(result, QAOAResult)
        assert len(result.selected_assets) == k

    def test_greedy_fallback_selects_top_k_by_return(self):
        """Greedy fallback should select the top-k assets by expected return."""
        n = 4
        k = 2
        tickers = ["LOW", "HIGH", "MED", "HIGHEST"]
        mu = np.array([0.05, 0.15, 0.10, 0.20])  # HIGHEST > HIGH > MED > LOW
        rng = np.random.default_rng(42)
        A = rng.normal(0, 0.1, (n, n))
        sigma = A @ A.T + np.eye(n) * 0.01

        from app.quantum.qubo import build_qubo_matrix
        Q = build_qubo_matrix(mu, sigma, num_assets_to_select=k)

        with patch.dict("sys.modules", {"qiskit_optimization": None}):
            result = run_qaoa(
                tickers=tickers,
                qubo_matrix=Q,
                expected_returns=mu,
                covariance_matrix=sigma,
                budget=100_000.0,
                num_assets_to_select=k,
            )

        # Should select HIGHEST and HIGH
        assert "HIGHEST" in result.selected_assets
        assert "HIGH" in result.selected_assets
