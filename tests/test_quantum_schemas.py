"""Unit tests for app.engines.quantum.schemas — Pydantic v2 schemas.

Tests cover:
- QuantumOptimizationConstraints: defaults, validation
- QuantumOptimizationInput: dimension validation, num_assets_to_select validation
- QuantumAssetWeight: field validation
- QuantumPortfolioMetrics: construction and field types
- QuantumAssetResult: construction with all fields
- QuantumOptimizationResult: construction with optional fields
"""

import pytest
from pydantic import ValidationError

from app.engines.quantum.schemas import (
    QuantumAssetResult,
    QuantumAssetWeight,
    QuantumOptimizationConstraints,
    QuantumOptimizationInput,
    QuantumOptimizationResult,
    QuantumPortfolioMetrics,
)


# ── QuantumOptimizationConstraints ────────────────────────────────────────────

class TestQuantumOptimizationConstraints:
    """Tests for QuantumOptimizationConstraints."""

    def test_default_values(self) -> None:
        c = QuantumOptimizationConstraints()
        assert c.num_assets_to_select is None
        assert c.lambda_return == 1.0
        assert c.lambda_risk == 1.0
        assert c.lambda_cardinality == 5.0
        assert c.qaoa_p == 2
        assert c.vqe_layers == 2
        assert c.vqe_max_iterations == 100
        assert c.run_qaoa is True
        assert c.run_vqe is True

    def test_custom_values(self) -> None:
        c = QuantumOptimizationConstraints(
            num_assets_to_select=3,
            qaoa_p=4,
            vqe_layers=3,
            run_qaoa=True,
            run_vqe=False,
        )
        assert c.num_assets_to_select == 3
        assert c.qaoa_p == 4
        assert c.vqe_layers == 3
        assert c.run_vqe is False

    def test_lambda_return_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            QuantumOptimizationConstraints(lambda_return=0.0)

    def test_lambda_risk_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            QuantumOptimizationConstraints(lambda_risk=-1.0)

    def test_lambda_cardinality_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            QuantumOptimizationConstraints(lambda_cardinality=0.0)

    def test_qaoa_p_must_be_at_least_1(self) -> None:
        with pytest.raises(ValidationError):
            QuantumOptimizationConstraints(qaoa_p=0)

    def test_qaoa_p_max_is_10(self) -> None:
        with pytest.raises(ValidationError):
            QuantumOptimizationConstraints(qaoa_p=11)

    def test_vqe_layers_must_be_at_least_1(self) -> None:
        with pytest.raises(ValidationError):
            QuantumOptimizationConstraints(vqe_layers=0)

    def test_vqe_max_iterations_min_is_10(self) -> None:
        with pytest.raises(ValidationError):
            QuantumOptimizationConstraints(vqe_max_iterations=5)

    def test_vqe_max_iterations_max_is_1000(self) -> None:
        with pytest.raises(ValidationError):
            QuantumOptimizationConstraints(vqe_max_iterations=1001)

    def test_num_assets_to_select_must_be_at_least_1(self) -> None:
        with pytest.raises(ValidationError):
            QuantumOptimizationConstraints(num_assets_to_select=0)


# ── QuantumOptimizationInput ──────────────────────────────────────────────────

class TestQuantumOptimizationInput:
    """Tests for QuantumOptimizationInput."""

    def _make_valid_input(
        self,
        tickers: list[str] | None = None,
        num_assets_to_select: int | None = None,
    ) -> QuantumOptimizationInput:
        tickers = tickers or ["AAPL", "MSFT", "GOOGL", "AMZN"]
        n = len(tickers)
        constraints = QuantumOptimizationConstraints(
            num_assets_to_select=num_assets_to_select
        )
        return QuantumOptimizationInput(
            tickers=tickers,
            expected_returns=[0.12, 0.10, 0.09, 0.15][:n],
            cov_matrix=[
                [0.04, 0.01, 0.008, 0.012],
                [0.01, 0.03, 0.007, 0.009],
                [0.008, 0.007, 0.025, 0.006],
                [0.012, 0.009, 0.006, 0.05],
            ][:n],
            constraints=constraints,
        )

    def test_valid_input_constructs_successfully(self) -> None:
        inp = self._make_valid_input()
        assert len(inp.tickers) == 4
        assert len(inp.expected_returns) == 4

    def test_requires_at_least_2_tickers(self) -> None:
        with pytest.raises(ValidationError):
            QuantumOptimizationInput(
                tickers=["AAPL"],
                expected_returns=[0.12],
                cov_matrix=[[0.04]],
            )

    def test_mismatched_expected_returns_raises(self) -> None:
        with pytest.raises(ValidationError):
            QuantumOptimizationInput(
                tickers=["AAPL", "MSFT"],
                expected_returns=[0.12],  # Only 1 instead of 2
                cov_matrix=[[0.04, 0.01], [0.01, 0.03]],
            )

    def test_mismatched_cov_matrix_rows_raises(self) -> None:
        with pytest.raises(ValidationError):
            QuantumOptimizationInput(
                tickers=["AAPL", "MSFT"],
                expected_returns=[0.12, 0.10],
                cov_matrix=[[0.04, 0.01]],  # Only 1 row
            )

    def test_num_assets_to_select_exceeding_n_raises(self) -> None:
        with pytest.raises(ValidationError):
            QuantumOptimizationInput(
                tickers=["AAPL", "MSFT"],
                expected_returns=[0.12, 0.10],
                cov_matrix=[[0.04, 0.01], [0.01, 0.03]],
                constraints=QuantumOptimizationConstraints(num_assets_to_select=5),
            )

    def test_num_assets_to_select_equal_to_n_is_valid(self) -> None:
        inp = self._make_valid_input(num_assets_to_select=4)
        assert inp.constraints.num_assets_to_select == 4

    def test_default_budget_is_one(self) -> None:
        inp = self._make_valid_input()
        assert inp.budget == 1.0

    def test_custom_budget_accepted(self) -> None:
        inp = QuantumOptimizationInput(
            tickers=["AAPL", "MSFT"],
            expected_returns=[0.12, 0.10],
            cov_matrix=[[0.04, 0.01], [0.01, 0.03]],
            budget=100_000.0,
        )
        assert inp.budget == 100_000.0

    def test_sector_tags_default_empty(self) -> None:
        inp = self._make_valid_input()
        assert inp.sector_tags == {}


# ── QuantumAssetWeight ────────────────────────────────────────────────────────

class TestQuantumAssetWeight:
    """Tests for QuantumAssetWeight."""

    def test_basic_construction(self) -> None:
        w = QuantumAssetWeight(
            ticker="AAPL",
            weight=0.5,
            allocation=50_000.0,
            sector="Information Technology",
        )
        assert w.ticker == "AAPL"
        assert w.weight == 0.5
        assert w.allocation == 50_000.0
        assert w.sector == "Information Technology"

    def test_sector_defaults_to_none(self) -> None:
        w = QuantumAssetWeight(ticker="AAPL", weight=0.5, allocation=50_000.0)
        assert w.sector is None

    def test_weight_must_be_in_0_to_1(self) -> None:
        with pytest.raises(ValidationError):
            QuantumAssetWeight(ticker="AAPL", weight=1.5, allocation=50_000.0)

    def test_weight_negative_raises(self) -> None:
        with pytest.raises(ValidationError):
            QuantumAssetWeight(ticker="AAPL", weight=-0.1, allocation=50_000.0)

    def test_allocation_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            QuantumAssetWeight(ticker="AAPL", weight=0.5, allocation=-100.0)


# ── QuantumPortfolioMetrics ───────────────────────────────────────────────────

class TestQuantumPortfolioMetrics:
    """Tests for QuantumPortfolioMetrics."""

    def test_basic_construction(self) -> None:
        m = QuantumPortfolioMetrics(
            expected_return=0.12,
            volatility=0.15,
            sharpe_ratio=0.67,
            num_assets=2,
        )
        assert m.expected_return == 0.12
        assert m.volatility == 0.15
        assert m.sharpe_ratio == 0.67
        assert m.num_assets == 2

    def test_optional_fields_default_to_none(self) -> None:
        m = QuantumPortfolioMetrics(
            expected_return=0.12,
            volatility=0.15,
            sharpe_ratio=0.67,
            num_assets=2,
        )
        assert m.max_drawdown is None
        assert m.qubo_energy is None

    def test_optional_fields_can_be_set(self) -> None:
        m = QuantumPortfolioMetrics(
            expected_return=0.12,
            volatility=0.15,
            sharpe_ratio=0.67,
            num_assets=2,
            max_drawdown=-0.15,
            qubo_energy=-3.5,
        )
        assert m.max_drawdown == -0.15
        assert m.qubo_energy == -3.5


# ── QuantumAssetResult ────────────────────────────────────────────────────────

class TestQuantumAssetResult:
    """Tests for QuantumAssetResult."""

    def _make_metrics(self) -> QuantumPortfolioMetrics:
        return QuantumPortfolioMetrics(
            expected_return=0.12,
            volatility=0.15,
            sharpe_ratio=0.67,
            num_assets=2,
        )

    def _make_weights(self) -> list[QuantumAssetWeight]:
        return [
            QuantumAssetWeight(ticker="AAPL", weight=0.5, allocation=50_000.0),
            QuantumAssetWeight(ticker="MSFT", weight=0.5, allocation=50_000.0),
        ]

    def test_basic_construction(self) -> None:
        result = QuantumAssetResult(
            algorithm="QAOA",
            selected_assets=["AAPL", "MSFT"],
            weights=self._make_weights(),
            metrics=self._make_metrics(),
            solve_time_ms=150.0,
            num_qubits=4,
        )
        assert result.algorithm == "QAOA"
        assert result.selected_assets == ["AAPL", "MSFT"]
        assert result.solve_time_ms == 150.0
        assert result.num_qubits == 4

    def test_optional_fields_defaults(self) -> None:
        result = QuantumAssetResult(
            algorithm="VQE",
            selected_assets=["AAPL"],
            weights=self._make_weights()[:1],
            metrics=self._make_metrics(),
            solve_time_ms=100.0,
            num_qubits=4,
        )
        assert result.circuit_depth is None
        assert result.solver_used == "unknown"
        assert result.fallback_used is False
        assert result.extra == {}

    def test_solve_time_ms_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            QuantumAssetResult(
                algorithm="QAOA",
                selected_assets=["AAPL"],
                weights=self._make_weights()[:1],
                metrics=self._make_metrics(),
                solve_time_ms=-1.0,
                num_qubits=4,
            )

    def test_json_serialisable(self) -> None:
        result = QuantumAssetResult(
            algorithm="QAOA",
            selected_assets=["AAPL", "MSFT"],
            weights=self._make_weights(),
            metrics=self._make_metrics(),
            solve_time_ms=150.0,
            num_qubits=4,
        )
        json_str = result.model_dump_json()
        assert "QAOA" in json_str
        assert "AAPL" in json_str


# ── QuantumOptimizationResult ─────────────────────────────────────────────────

class TestQuantumOptimizationResult:
    """Tests for QuantumOptimizationResult."""

    def test_basic_construction_with_no_results(self) -> None:
        result = QuantumOptimizationResult(
            num_assets_universe=4,
            num_assets_selected=2,
            qubo_shape=[4, 4],
            total_solve_time_ms=500.0,
        )
        assert result.qaoa is None
        assert result.vqe is None
        assert result.best_algorithm is None
        assert result.best_sharpe is None

    def test_total_solve_time_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            QuantumOptimizationResult(
                num_assets_universe=4,
                num_assets_selected=2,
                qubo_shape=[4, 4],
                total_solve_time_ms=-1.0,
            )

    def test_extra_field_defaults_to_empty_dict(self) -> None:
        result = QuantumOptimizationResult(
            num_assets_universe=4,
            num_assets_selected=2,
            qubo_shape=[4, 4],
            total_solve_time_ms=500.0,
        )
        assert result.extra == {}

    def test_json_serialisable(self) -> None:
        result = QuantumOptimizationResult(
            num_assets_universe=4,
            num_assets_selected=2,
            qubo_shape=[4, 4],
            total_solve_time_ms=500.0,
            best_algorithm="QAOA",
            best_sharpe=0.75,
        )
        json_str = result.model_dump_json()
        assert "QAOA" in json_str
        assert "4" in json_str
