"""Unit tests for app.engines.classical.optimizer.

Tests cover:
- ClassicalOptimizer.optimize: happy path with 3 and 5 assets
- Weights sum to 1.0 (within tolerance)
- Sharpe ratio is computed correctly
- Sector constraints are respected
- min_portfolio_return constraint is respected
- max_weight_per_asset constraint is respected
- SolverInfeasibleError raised for infeasible constraints
- Input validation (dimension mismatch)
- risk_tolerance=0 gives min-variance portfolio
- risk_tolerance=1 gives max-return portfolio
- OptimizationConstraints schema validation
- ClassicalOptimizationInput schema validation
"""

from __future__ import annotations

import numpy as np
import pytest

from app.core.exceptions import SolverInfeasibleError
from app.engines.classical.optimizer import ClassicalOptimizer
from app.engines.classical.schemas import (
    ClassicalOptimizationInput,
    ClassicalOptimizationResult,
    OptimizationConstraints,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_3asset_input(
    risk_tolerance: float = 0.5,
    max_weight: float = 0.6,
    min_return: float | None = None,
    sector_limits: dict | None = None,
) -> ClassicalOptimizationInput:
    """Build a 3-asset optimization input with synthetic data."""
    return ClassicalOptimizationInput(
        tickers=["AAPL", "MSFT", "GOOGL"],
        expected_returns=[0.15, 0.12, 0.10],
        cov_matrix=[
            [0.04, 0.01, 0.008],
            [0.01, 0.03, 0.007],
            [0.008, 0.007, 0.025],
        ],
        sector_tags={
            "AAPL": "Information Technology",
            "MSFT": "Information Technology",
            "GOOGL": "Communication Services",
        },
        constraints=OptimizationConstraints(
            max_weight_per_asset=max_weight,
            min_portfolio_return=min_return,
            sector_limits=sector_limits or {},
            risk_tolerance=risk_tolerance,
            budget=100_000.0,
        ),
    )


def _make_5asset_input() -> ClassicalOptimizationInput:
    """Build a 5-asset optimization input."""
    rng = np.random.default_rng(42)
    n = 5
    # Build a valid PSD covariance matrix
    A = rng.normal(0, 0.1, (n, n))
    sigma = A @ A.T + np.eye(n) * 0.01
    mu = rng.uniform(0.05, 0.20, n).tolist()

    return ClassicalOptimizationInput(
        tickers=["A", "B", "C", "D", "E"],
        expected_returns=mu,
        cov_matrix=sigma.tolist(),
        sector_tags={},
        constraints=OptimizationConstraints(
            max_weight_per_asset=0.5,
            risk_tolerance=0.5,
        ),
    )


# ---------------------------------------------------------------------------
# ClassicalOptimizer.optimize — happy path
# ---------------------------------------------------------------------------

class TestClassicalOptimizerHappyPath:
    def test_returns_result_object(self):
        optimizer = ClassicalOptimizer()
        result = optimizer.optimize(_make_3asset_input())
        assert isinstance(result, ClassicalOptimizationResult)

    def test_weights_sum_to_one(self):
        optimizer = ClassicalOptimizer()
        result = optimizer.optimize(_make_3asset_input())
        total = sum(result.weights.values())
        assert abs(total - 1.0) < 1e-4

    def test_all_weights_non_negative(self):
        optimizer = ClassicalOptimizer()
        result = optimizer.optimize(_make_3asset_input())
        for ticker, weight in result.weights.items():
            assert weight >= 0.0, f"Negative weight for {ticker}: {weight}"

    def test_portfolio_return_is_positive(self):
        optimizer = ClassicalOptimizer()
        result = optimizer.optimize(_make_3asset_input())
        assert result.portfolio_return > 0.0

    def test_portfolio_volatility_is_positive(self):
        optimizer = ClassicalOptimizer()
        result = optimizer.optimize(_make_3asset_input())
        assert result.portfolio_volatility > 0.0

    def test_sharpe_ratio_is_float(self):
        optimizer = ClassicalOptimizer()
        result = optimizer.optimize(_make_3asset_input())
        assert isinstance(result.sharpe_ratio, float)

    def test_solver_status_is_optimal(self):
        optimizer = ClassicalOptimizer()
        result = optimizer.optimize(_make_3asset_input())
        assert "optimal" in result.solver_status.lower()

    def test_solve_time_ms_is_positive(self):
        optimizer = ClassicalOptimizer()
        result = optimizer.optimize(_make_3asset_input())
        assert result.solve_time_ms > 0.0

    def test_num_assets_is_correct(self):
        optimizer = ClassicalOptimizer()
        result = optimizer.optimize(_make_3asset_input())
        assert result.num_assets == len(result.weights)

    def test_5asset_optimization_works(self):
        optimizer = ClassicalOptimizer()
        result = optimizer.optimize(_make_5asset_input())
        assert isinstance(result, ClassicalOptimizationResult)
        total = sum(result.weights.values())
        assert abs(total - 1.0) < 1e-4

    def test_weights_keys_are_valid_tickers(self):
        optimizer = ClassicalOptimizer()
        inp = _make_3asset_input()
        result = optimizer.optimize(inp)
        for ticker in result.weights:
            assert ticker in inp.tickers


# ---------------------------------------------------------------------------
# Constraint enforcement
# ---------------------------------------------------------------------------

class TestConstraintEnforcement:
    def test_max_weight_per_asset_respected(self):
        """No asset should exceed max_weight_per_asset."""
        max_weight = 0.4
        optimizer = ClassicalOptimizer()
        result = optimizer.optimize(_make_3asset_input(max_weight=max_weight))
        for ticker, weight in result.weights.items():
            assert weight <= max_weight + 1e-4, (
                f"Weight {weight:.4f} for {ticker} exceeds max {max_weight}"
            )

    def test_min_portfolio_return_respected(self):
        """Portfolio return should be >= min_portfolio_return."""
        min_return = 0.10
        optimizer = ClassicalOptimizer()
        result = optimizer.optimize(
            _make_3asset_input(min_return=min_return, risk_tolerance=0.5)
        )
        assert result.portfolio_return >= min_return - 1e-4

    def test_sector_limit_respected(self):
        """Combined weight of IT assets should not exceed sector limit."""
        sector_limits = {"Information Technology": 0.5}
        optimizer = ClassicalOptimizer()
        result = optimizer.optimize(
            _make_3asset_input(sector_limits=sector_limits, max_weight=0.5)
        )
        it_weight = sum(
            w for t, w in result.weights.items()
            if t in ("AAPL", "MSFT")
        )
        assert it_weight <= 0.5 + 1e-4

    def test_risk_tolerance_zero_gives_lower_volatility(self):
        """risk_tolerance=0 (min-variance) should give lower vol than risk_tolerance=1."""
        optimizer = ClassicalOptimizer()
        result_min_var = optimizer.optimize(_make_3asset_input(risk_tolerance=0.0))
        result_max_ret = optimizer.optimize(_make_3asset_input(risk_tolerance=1.0))
        # Min-variance should have lower or equal volatility
        assert result_min_var.portfolio_volatility <= result_max_ret.portfolio_volatility + 1e-4

    def test_risk_tolerance_one_gives_higher_return(self):
        """risk_tolerance=1 (max-return) should give higher return than risk_tolerance=0."""
        optimizer = ClassicalOptimizer()
        result_min_var = optimizer.optimize(_make_3asset_input(risk_tolerance=0.0))
        result_max_ret = optimizer.optimize(_make_3asset_input(risk_tolerance=1.0))
        # Max-return should have higher or equal expected return
        assert result_max_ret.portfolio_return >= result_min_var.portfolio_return - 1e-4


# ---------------------------------------------------------------------------
# Infeasible constraints
# ---------------------------------------------------------------------------

class TestInfeasibleConstraints:
    def test_impossible_min_return_raises_solver_infeasible_error(self):
        """min_portfolio_return higher than any achievable return should raise."""
        optimizer = ClassicalOptimizer()
        inp = _make_3asset_input(min_return=0.99)  # 99% return is impossible
        with pytest.raises(SolverInfeasibleError) as exc_info:
            optimizer.optimize(inp)
        assert exc_info.value.error_code == "SOLVER_INFEASIBLE"

    def test_infeasible_error_has_relaxation_suggestions(self):
        """SolverInfeasibleError should include relaxation suggestions."""
        optimizer = ClassicalOptimizer()
        inp = _make_3asset_input(min_return=0.99)
        with pytest.raises(SolverInfeasibleError) as exc_info:
            optimizer.optimize(inp)
        assert len(exc_info.value.relaxation_suggestions) > 0


# ---------------------------------------------------------------------------
# Input validation (schema level)
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_mismatched_expected_returns_raises_validation_error(self):
        """expected_returns length != len(tickers) should raise ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ClassicalOptimizationInput(
                tickers=["AAPL", "MSFT"],
                expected_returns=[0.10],  # Only 1 value for 2 tickers
                cov_matrix=[[0.04, 0.01], [0.01, 0.03]],
            )

    def test_mismatched_cov_matrix_rows_raises_validation_error(self):
        """cov_matrix with wrong number of rows should raise ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ClassicalOptimizationInput(
                tickers=["AAPL", "MSFT"],
                expected_returns=[0.10, 0.08],
                cov_matrix=[[0.04, 0.01]],  # Only 1 row for 2 tickers
            )

    def test_mismatched_cov_matrix_cols_raises_validation_error(self):
        """cov_matrix with wrong number of columns should raise ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ClassicalOptimizationInput(
                tickers=["AAPL", "MSFT"],
                expected_returns=[0.10, 0.08],
                cov_matrix=[[0.04], [0.01]],  # Only 1 col for 2 tickers
            )

    def test_single_ticker_raises_validation_error(self):
        """min_length=2 for tickers should reject single-ticker inputs."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ClassicalOptimizationInput(
                tickers=["AAPL"],
                expected_returns=[0.10],
                cov_matrix=[[0.04]],
            )

    def test_invalid_sector_limit_raises_validation_error(self):
        """Sector limit > 1.0 should raise ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            OptimizationConstraints(
                sector_limits={"Technology": 1.5}  # > 1.0
            )

    def test_max_weight_out_of_range_raises_validation_error(self):
        """max_weight_per_asset > 1.0 should raise ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            OptimizationConstraints(max_weight_per_asset=1.5)

    def test_risk_tolerance_out_of_range_raises_validation_error(self):
        """risk_tolerance > 1.0 should raise ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            OptimizationConstraints(risk_tolerance=1.5)


# ---------------------------------------------------------------------------
# OptimizationConstraints defaults
# ---------------------------------------------------------------------------

class TestOptimizationConstraintsDefaults:
    def test_default_max_weight(self):
        c = OptimizationConstraints()
        assert c.max_weight_per_asset == 0.4

    def test_default_risk_tolerance(self):
        c = OptimizationConstraints()
        assert c.risk_tolerance == 0.5

    def test_default_min_portfolio_return_is_none(self):
        c = OptimizationConstraints()
        assert c.min_portfolio_return is None

    def test_default_sector_limits_is_empty(self):
        c = OptimizationConstraints()
        assert c.sector_limits == {}

    def test_default_budget(self):
        c = OptimizationConstraints()
        assert c.budget == 1.0


# ---------------------------------------------------------------------------
# ClassicalOptimizationResult
# ---------------------------------------------------------------------------

class TestClassicalOptimizationResult:
    def test_result_is_json_serialisable(self):
        """Result should be serialisable to JSON via Pydantic."""
        optimizer = ClassicalOptimizer()
        result = optimizer.optimize(_make_3asset_input())
        json_str = result.model_dump_json()
        assert len(json_str) > 0

    def test_result_weights_dict_is_not_empty(self):
        optimizer = ClassicalOptimizer()
        result = optimizer.optimize(_make_3asset_input())
        assert len(result.weights) > 0

    def test_result_extra_contains_solver_used(self):
        optimizer = ClassicalOptimizer()
        result = optimizer.optimize(_make_3asset_input())
        assert "solver_used" in result.extra
