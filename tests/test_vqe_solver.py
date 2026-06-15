"""Unit tests for app.engines.quantum.vqe_pennylane — VQE solver.

Tests cover:
- VQESolver.name property
- VQESolver.solve: happy path (greedy fallback or PennyLane)
- Result structure: selected_assets, weights, metrics
- Cardinality enforcement: exactly k assets selected
- Weights sum to 1.0
- Dollar allocations sum to budget
- Sector tags stored in weights
"""

from __future__ import annotations

import numpy as np
import pytest

from app.engines.quantum.schemas import QuantumAssetResult
from app.engines.quantum.vqe_pennylane import VQESolver


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
def solver() -> VQESolver:
    return VQESolver()


# ── VQESolver.name ────────────────────────────────────────────────────────────

class TestVQESolverName:
    def test_name_is_vqe(self, solver: VQESolver) -> None:
        assert solver.name == "VQE"


# ── VQESolver.solve ───────────────────────────────────────────────────────────

class TestVQESolverSolve:
    """Tests for VQESolver.solve.

    In the test environment, PennyLane may or may not be available.
    The solver always falls back to greedy selection if PennyLane fails,
    so these tests work regardless of whether PennyLane is installed.
    """

    def test_returns_quantum_asset_result(
        self,
        solver: VQESolver,
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

    def test_algorithm_is_vqe(
        self,
        solver: VQESolver,
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
        assert result.algorithm == "VQE"

    def test_exactly_k_assets_selected(
        self,
        solver: VQESolver,
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
        solver: VQESolver,
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
        solver: VQESolver,
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
        solver: VQESolver,
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

    def test_solve_time_ms_is_non_negative(
        self,
        solver: VQESolver,
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

    def test_metrics_expected_return_is_positive(
        self,
        solver: VQESolver,
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
        solver: VQESolver,
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
        solver: VQESolver,
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
        assert abs(total_allocation - budget) < 1.0

    def test_k_equals_1_selects_one_asset(
        self,
        solver: VQESolver,
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
        solver: VQESolver,
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

    def test_num_assets_in_metrics_matches_k(
        self,
        solver: VQESolver,
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
        assert result.metrics.num_assets == 2

    def test_extra_contains_num_assets_to_select(
        self,
        solver: VQESolver,
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
        assert "num_assets_to_select" in result.extra
        assert result.extra["num_assets_to_select"] == 2
