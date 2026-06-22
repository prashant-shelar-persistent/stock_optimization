"""Unit tests for app.engines.quantum.qaoa_qiskit — QAOA solver.

Tests cover:
- QAOASolver.name property
- QAOASolver.solve: happy path (greedy fallback always used in test env)
- Result structure: selected_assets, weights, metrics, circuit_depth
- Cardinality enforcement: exactly k assets selected
- Greedy fallback: selects top-k by return
- BaseQuantumSolver helpers: _enforce_cardinality, _greedy_selection,
  _build_equal_weight_portfolio
- run_qaoa convenience function
"""

import numpy as np
import pytest

from app.engines.quantum.qaoa_qiskit import QAOASolver, run_qaoa
from app.engines.quantum.schemas import QuantumAssetResult


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


@pytest.fixture
def qubo_4(mu_4: np.ndarray, sigma_4: np.ndarray) -> np.ndarray:
    from app.quantum.qubo import build_qubo_matrix
    return build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)


@pytest.fixture
def solver() -> QAOASolver:
    return QAOASolver()


# ── QAOASolver.name ───────────────────────────────────────────────────────────

class TestQAOASolverName:
    def test_name_is_qaoa(self, solver: QAOASolver) -> None:
        assert solver.name == "QAOA"


# ── QAOASolver.solve ──────────────────────────────────────────────────────────

class TestQAOASolverSolve:
    """Tests for QAOASolver.solve.

    In the test environment, Qiskit may or may not be available.
    The solver always falls back to greedy selection if Qiskit fails,
    so these tests work regardless of whether Qiskit is installed.
    """

    def test_returns_quantum_asset_result(
        self,
        solver: QAOASolver,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        qubo_4: np.ndarray,
    ) -> None:
        result = solver.solve(
            tickers=tickers_4,
            qubo_matrix=qubo_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
            num_assets_to_select=2,
        )
        assert isinstance(result, QuantumAssetResult)

    def test_algorithm_is_qaoa(
        self,
        solver: QAOASolver,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        qubo_4: np.ndarray,
    ) -> None:
        result = solver.solve(
            tickers=tickers_4,
            qubo_matrix=qubo_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
            num_assets_to_select=2,
        )
        assert result.algorithm == "QAOA"

    def test_exactly_k_assets_selected(
        self,
        solver: QAOASolver,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        qubo_4: np.ndarray,
    ) -> None:
        k = 2
        result = solver.solve(
            tickers=tickers_4,
            qubo_matrix=qubo_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
            num_assets_to_select=k,
        )
        assert len(result.selected_assets) == k

    def test_selected_assets_are_valid_tickers(
        self,
        solver: QAOASolver,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        qubo_4: np.ndarray,
    ) -> None:
        result = solver.solve(
            tickers=tickers_4,
            qubo_matrix=qubo_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
            num_assets_to_select=2,
        )
        for ticker in result.selected_assets:
            assert ticker in tickers_4

    def test_weights_sum_to_one(
        self,
        solver: QAOASolver,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        qubo_4: np.ndarray,
    ) -> None:
        result = solver.solve(
            tickers=tickers_4,
            qubo_matrix=qubo_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
            num_assets_to_select=2,
        )
        total_weight = sum(w.weight for w in result.weights)
        assert abs(total_weight - 1.0) < 1e-6

    def test_num_qubits_equals_n(
        self,
        solver: QAOASolver,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        qubo_4: np.ndarray,
    ) -> None:
        result = solver.solve(
            tickers=tickers_4,
            qubo_matrix=qubo_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
            num_assets_to_select=2,
        )
        assert result.num_qubits == 4

    def test_solve_time_ms_is_positive(
        self,
        solver: QAOASolver,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        qubo_4: np.ndarray,
    ) -> None:
        result = solver.solve(
            tickers=tickers_4,
            qubo_matrix=qubo_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
            num_assets_to_select=2,
        )
        assert result.solve_time_ms >= 0.0

    def test_circuit_depth_is_computed(
        self,
        solver: QAOASolver,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        qubo_4: np.ndarray,
    ) -> None:
        p = 2
        result = solver.solve(
            tickers=tickers_4,
            qubo_matrix=qubo_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
            num_assets_to_select=2,
            p=p,
        )
        # circuit_depth = 2 * p * n = 2 * 2 * 4 = 16
        assert result.circuit_depth == 2 * p * 4

    def test_metrics_expected_return_is_positive(
        self,
        solver: QAOASolver,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        qubo_4: np.ndarray,
    ) -> None:
        result = solver.solve(
            tickers=tickers_4,
            qubo_matrix=qubo_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
            num_assets_to_select=2,
        )
        assert result.metrics.expected_return > 0.0

    def test_metrics_volatility_is_positive(
        self,
        solver: QAOASolver,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        qubo_4: np.ndarray,
    ) -> None:
        result = solver.solve(
            tickers=tickers_4,
            qubo_matrix=qubo_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
            num_assets_to_select=2,
        )
        assert result.metrics.volatility > 0.0

    def test_dollar_allocations_sum_to_budget(
        self,
        solver: QAOASolver,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        qubo_4: np.ndarray,
    ) -> None:
        budget = 100_000.0
        result = solver.solve(
            tickers=tickers_4,
            qubo_matrix=qubo_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=budget,
            num_assets_to_select=2,
        )
        total_allocation = sum(w.allocation for w in result.weights)
        assert abs(total_allocation - budget) < 1.0  # Within $1

    def test_k_equals_1_selects_one_asset(
        self,
        solver: QAOASolver,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        from app.quantum.qubo import build_qubo_matrix
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=1)
        result = solver.solve(
            tickers=tickers_4,
            qubo_matrix=Q,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
            num_assets_to_select=1,
        )
        assert len(result.selected_assets) == 1

    def test_sector_tags_stored_in_weights(
        self,
        solver: QAOASolver,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        qubo_4: np.ndarray,
    ) -> None:
        sector_tags = {
            "AAPL": "Information Technology",
            "MSFT": "Information Technology",
            "GOOGL": "Communication Services",
            "AMZN": "Consumer Discretionary",
        }
        result = solver.solve(
            tickers=tickers_4,
            qubo_matrix=qubo_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
            num_assets_to_select=2,
            sector_tags=sector_tags,
        )
        for w in result.weights:
            assert w.sector is not None
            assert w.sector in sector_tags.values()


# ── BaseQuantumSolver helpers ─────────────────────────────────────────────────

class TestEnforceCardinality:
    """Tests for BaseQuantumSolver._enforce_cardinality."""

    def test_correct_count_unchanged(self) -> None:
        x = np.array([1.0, 0.0, 1.0, 0.0])
        mu = np.array([0.12, 0.10, 0.09, 0.15])
        result = QAOASolver._enforce_cardinality(x, k=2, expected_returns=mu)
        assert int(result.sum()) == 2

    def test_too_many_selected_reduced_to_k(self) -> None:
        x = np.array([1.0, 1.0, 1.0, 0.0])  # 3 selected
        mu = np.array([0.12, 0.10, 0.09, 0.15])
        result = QAOASolver._enforce_cardinality(x, k=2, expected_returns=mu)
        assert int(result.sum()) == 2

    def test_too_few_selected_increased_to_k(self) -> None:
        x = np.array([1.0, 0.0, 0.0, 0.0])  # 1 selected
        mu = np.array([0.12, 0.10, 0.09, 0.15])
        result = QAOASolver._enforce_cardinality(x, k=2, expected_returns=mu)
        assert int(result.sum()) == 2

    def test_removes_lowest_return_assets(self) -> None:
        """When reducing, should keep highest-return assets."""
        x = np.array([1.0, 1.0, 1.0, 0.0])  # 3 selected
        mu = np.array([0.12, 0.10, 0.09, 0.15])
        result = QAOASolver._enforce_cardinality(x, k=2, expected_returns=mu)
        # Should keep AAPL (0.12) and MSFT (0.10), remove GOOGL (0.09)
        assert result[0] == 1.0  # AAPL kept
        assert result[1] == 1.0  # MSFT kept
        assert result[2] == 0.0  # GOOGL removed (lowest return among selected)

    def test_adds_highest_return_assets(self) -> None:
        """When adding, should pick highest-return unselected assets."""
        x = np.array([0.0, 0.0, 0.0, 0.0])  # 0 selected
        mu = np.array([0.12, 0.10, 0.09, 0.15])
        result = QAOASolver._enforce_cardinality(x, k=2, expected_returns=mu)
        # Should select AMZN (0.15) and AAPL (0.12)
        assert result[3] == 1.0  # AMZN (highest return)
        assert result[0] == 1.0  # AAPL (second highest)

    def test_all_zeros_selects_k_best(self) -> None:
        x = np.zeros(4)
        mu = np.array([0.12, 0.10, 0.09, 0.15])
        result = QAOASolver._enforce_cardinality(x, k=3, expected_returns=mu)
        assert int(result.sum()) == 3


class TestGreedySelection:
    """Tests for BaseQuantumSolver._greedy_selection."""

    def test_selects_exactly_k_assets(self) -> None:
        mu = np.array([0.12, 0.10, 0.09, 0.15])
        result = QAOASolver._greedy_selection(mu, k=2)
        assert int(result.sum()) == 2

    def test_selects_highest_return_assets(self) -> None:
        mu = np.array([0.12, 0.10, 0.09, 0.15])
        result = QAOASolver._greedy_selection(mu, k=2)
        # Should select AMZN (0.15) and AAPL (0.12)
        assert result[3] == 1.0  # AMZN
        assert result[0] == 1.0  # AAPL

    def test_k_equals_n_selects_all(self) -> None:
        mu = np.array([0.12, 0.10, 0.09, 0.15])
        result = QAOASolver._greedy_selection(mu, k=4)
        assert int(result.sum()) == 4

    def test_k_equals_1_selects_best(self) -> None:
        mu = np.array([0.12, 0.10, 0.09, 0.15])
        result = QAOASolver._greedy_selection(mu, k=1)
        assert result[3] == 1.0  # AMZN has highest return
        assert int(result.sum()) == 1


# ── run_qaoa convenience function ─────────────────────────────────────────────

class TestRunQaoa:
    """Tests for the run_qaoa convenience function."""

    def test_returns_quantum_asset_result(
        self,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        qubo_4: np.ndarray,
    ) -> None:
        result = run_qaoa(
            tickers=tickers_4,
            qubo_matrix=qubo_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
            num_assets_to_select=2,
        )
        assert isinstance(result, QuantumAssetResult)

    def test_same_result_as_solver_instance(
        self,
        tickers_4: list[str],
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        qubo_4: np.ndarray,
    ) -> None:
        """run_qaoa should produce a valid result with the same structure."""
        result = run_qaoa(
            tickers=tickers_4,
            qubo_matrix=qubo_4,
            expected_returns=mu_4,
            covariance_matrix=sigma_4,
            budget=100_000.0,
            num_assets_to_select=2,
        )
        assert result.algorithm == "QAOA"
        assert len(result.selected_assets) == 2
