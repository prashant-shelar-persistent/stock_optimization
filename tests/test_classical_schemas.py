"""Unit tests for app.engines.classical.schemas — Pydantic v2 schemas.

Tests cover:
- OptimizationConstraints: defaults, validation, sector_limits validation
- ClassicalOptimizationInput: dimension validation, sector_tags defaults
- ClassicalOptimizationResult: construction and field types
"""

import pytest
from pydantic import ValidationError

from app.engines.classical.schemas import (
    ClassicalOptimizationInput,
    ClassicalOptimizationResult,
    OptimizationConstraints,
)


# ── OptimizationConstraints ───────────────────────────────────────────────────

class TestOptimizationConstraints:
    """Tests for OptimizationConstraints."""

    def test_default_values(self) -> None:
        c = OptimizationConstraints()
        assert c.max_weight_per_asset == 0.4
        assert c.min_portfolio_return is None
        assert c.sector_limits == {}
        assert c.risk_tolerance == 0.5
        assert c.budget == 1.0

    def test_custom_values(self) -> None:
        c = OptimizationConstraints(
            max_weight_per_asset=0.3,
            min_portfolio_return=0.08,
            sector_limits={"Technology": 0.5},
            risk_tolerance=0.7,
            budget=100_000.0,
        )
        assert c.max_weight_per_asset == 0.3
        assert c.min_portfolio_return == 0.08
        assert c.sector_limits == {"Technology": 0.5}
        assert c.risk_tolerance == 0.7
        assert c.budget == 100_000.0

    def test_max_weight_must_be_in_0_to_1(self) -> None:
        with pytest.raises(ValidationError):
            OptimizationConstraints(max_weight_per_asset=1.5)

    def test_max_weight_zero_is_invalid(self) -> None:
        # ge=0.0 means 0.0 is allowed by field, but let's check boundary
        c = OptimizationConstraints(max_weight_per_asset=0.0)
        assert c.max_weight_per_asset == 0.0

    def test_risk_tolerance_must_be_in_0_to_1(self) -> None:
        with pytest.raises(ValidationError):
            OptimizationConstraints(risk_tolerance=1.5)

    def test_risk_tolerance_negative_is_invalid(self) -> None:
        with pytest.raises(ValidationError):
            OptimizationConstraints(risk_tolerance=-0.1)

    def test_budget_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            OptimizationConstraints(budget=0.0)

    def test_budget_negative_is_invalid(self) -> None:
        with pytest.raises(ValidationError):
            OptimizationConstraints(budget=-1000.0)

    def test_sector_limits_invalid_value_raises(self) -> None:
        with pytest.raises(ValidationError):
            OptimizationConstraints(sector_limits={"Technology": 1.5})

    def test_sector_limits_negative_value_raises(self) -> None:
        with pytest.raises(ValidationError):
            OptimizationConstraints(sector_limits={"Technology": -0.1})

    def test_sector_limits_zero_is_valid(self) -> None:
        c = OptimizationConstraints(sector_limits={"Technology": 0.0})
        assert c.sector_limits["Technology"] == 0.0

    def test_sector_limits_one_is_valid(self) -> None:
        c = OptimizationConstraints(sector_limits={"Technology": 1.0})
        assert c.sector_limits["Technology"] == 1.0

    def test_min_portfolio_return_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            OptimizationConstraints(min_portfolio_return=-0.01)

    def test_min_portfolio_return_none_is_valid(self) -> None:
        c = OptimizationConstraints(min_portfolio_return=None)
        assert c.min_portfolio_return is None


# ── ClassicalOptimizationInput ────────────────────────────────────────────────

class TestClassicalOptimizationInput:
    """Tests for ClassicalOptimizationInput."""

    def _make_valid_input(
        self,
        tickers: list[str] | None = None,
        expected_returns: list[float] | None = None,
        cov_matrix: list[list[float]] | None = None,
    ) -> ClassicalOptimizationInput:
        tickers = tickers or ["AAPL", "MSFT", "GOOGL"]
        n = len(tickers)
        expected_returns = expected_returns or [0.12, 0.10, 0.09][:n]
        cov_matrix = cov_matrix or [
            [0.04, 0.01, 0.008],
            [0.01, 0.03, 0.007],
            [0.008, 0.007, 0.025],
        ][:n]
        return ClassicalOptimizationInput(
            tickers=tickers,
            expected_returns=expected_returns,
            cov_matrix=cov_matrix,
        )

    def test_valid_input_constructs_successfully(self) -> None:
        inp = self._make_valid_input()
        assert inp.tickers == ["AAPL", "MSFT", "GOOGL"]
        assert len(inp.expected_returns) == 3
        assert len(inp.cov_matrix) == 3

    def test_default_constraints_are_applied(self) -> None:
        inp = self._make_valid_input()
        assert isinstance(inp.constraints, OptimizationConstraints)
        assert inp.constraints.max_weight_per_asset == 0.4

    def test_default_sector_tags_is_empty_dict(self) -> None:
        inp = self._make_valid_input()
        assert inp.sector_tags == {}

    def test_requires_at_least_2_tickers(self) -> None:
        with pytest.raises(ValidationError):
            ClassicalOptimizationInput(
                tickers=["AAPL"],
                expected_returns=[0.12],
                cov_matrix=[[0.04]],
            )

    def test_mismatched_expected_returns_length_raises(self) -> None:
        with pytest.raises(ValidationError):
            ClassicalOptimizationInput(
                tickers=["AAPL", "MSFT"],
                expected_returns=[0.12],  # Only 1 instead of 2
                cov_matrix=[[0.04, 0.01], [0.01, 0.03]],
            )

    def test_mismatched_cov_matrix_rows_raises(self) -> None:
        with pytest.raises(ValidationError):
            ClassicalOptimizationInput(
                tickers=["AAPL", "MSFT"],
                expected_returns=[0.12, 0.10],
                cov_matrix=[[0.04, 0.01]],  # Only 1 row instead of 2
            )

    def test_non_square_cov_matrix_raises(self) -> None:
        with pytest.raises(ValidationError):
            ClassicalOptimizationInput(
                tickers=["AAPL", "MSFT"],
                expected_returns=[0.12, 0.10],
                cov_matrix=[[0.04], [0.01, 0.03]],  # Row 0 has 1 col, row 1 has 2
            )

    def test_sector_tags_accepted(self) -> None:
        inp = ClassicalOptimizationInput(
            tickers=["AAPL", "MSFT"],
            expected_returns=[0.12, 0.10],
            cov_matrix=[[0.04, 0.01], [0.01, 0.03]],
            sector_tags={"AAPL": "Information Technology", "MSFT": "Information Technology"},
        )
        assert inp.sector_tags["AAPL"] == "Information Technology"

    def test_custom_constraints_accepted(self) -> None:
        constraints = OptimizationConstraints(
            max_weight_per_asset=0.3,
            risk_tolerance=0.8,
        )
        inp = ClassicalOptimizationInput(
            tickers=["AAPL", "MSFT"],
            expected_returns=[0.12, 0.10],
            cov_matrix=[[0.04, 0.01], [0.01, 0.03]],
            constraints=constraints,
        )
        assert inp.constraints.max_weight_per_asset == 0.3
        assert inp.constraints.risk_tolerance == 0.8


# ── ClassicalOptimizationResult ───────────────────────────────────────────────

class TestClassicalOptimizationResult:
    """Tests for ClassicalOptimizationResult."""

    def _make_result(self, **kwargs) -> ClassicalOptimizationResult:
        defaults = dict(
            weights={"AAPL": 0.5, "MSFT": 0.5},
            portfolio_return=0.11,
            portfolio_volatility=0.15,
            sharpe_ratio=0.6,
            solver_status="optimal",
            solve_time_ms=42.5,
            num_assets=2,
        )
        defaults.update(kwargs)
        return ClassicalOptimizationResult(**defaults)

    def test_basic_construction(self) -> None:
        result = self._make_result()
        assert result.weights == {"AAPL": 0.5, "MSFT": 0.5}
        assert result.portfolio_return == 0.11
        assert result.portfolio_volatility == 0.15
        assert result.sharpe_ratio == 0.6
        assert result.solver_status == "optimal"
        assert result.solve_time_ms == 42.5
        assert result.num_assets == 2

    def test_optional_fields_default_to_none(self) -> None:
        result = self._make_result()
        assert result.max_drawdown is None
        assert result.sortino_ratio is None
        assert result.var_95 is None

    def test_extra_field_defaults_to_empty_dict(self) -> None:
        result = self._make_result()
        assert result.extra == {}

    def test_extra_field_accepts_dict(self) -> None:
        result = self._make_result(extra={"solver_used": "CLARABEL"})
        assert result.extra["solver_used"] == "CLARABEL"

    def test_solve_time_ms_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            self._make_result(solve_time_ms=-1.0)

    def test_optional_fields_can_be_set(self) -> None:
        result = self._make_result(
            max_drawdown=-0.15,
            sortino_ratio=0.8,
            var_95=-0.02,
        )
        assert result.max_drawdown == -0.15
        assert result.sortino_ratio == 0.8
        assert result.var_95 == -0.02

    def test_json_serialisable(self) -> None:
        result = self._make_result()
        json_str = result.model_dump_json()
        assert "AAPL" in json_str
        assert "optimal" in json_str
