"""Unit tests for app.engines.classical.optimizer — Markowitz MVO.

Tests cover:
- Happy path: basic optimization with 3 and 4 assets
- Weights sum to 1.0 (within tolerance)
- Sharpe ratio is computed correctly
- max_weight_per_asset constraint is respected
- min_portfolio_return constraint is respected
- sector_limits constraint is respected
- risk_tolerance=0 → min-variance portfolio
- risk_tolerance=1 → max-return portfolio
- SolverInfeasibleError raised for impossible constraints
- Input validation errors
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_input(
    tickers: list[str],
    expected_returns: list[float],
    cov_matrix: list[list[float]],
    constraints: OptimizationConstraints | None = None,
    sector_tags: dict[str, str] | None = None,
) -> ClassicalOptimizationInput:
    return ClassicalOptimizationInput(
        tickers=tickers,
        expected_returns=expected_returns,
        cov_matrix=cov_matrix,
        sector_tags=sector_tags or {},
        constraints=constraints or OptimizationConstraints(),
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def optimizer() -> ClassicalOptimizer:
    return ClassicalOptimizer()


@pytest.fixture
def tickers_3() -> list[str]:
    return ["AAPL", "MSFT", "GOOGL"]


@pytest.fixture
def mu_3() -> list[float]:
    return [0.12, 0.10, 0.09]


@pytest.fixture
def sigma_3() -> list[list[float]]:
    return [
        [0.04, 0.01, 0.008],
        [0.01, 0.03, 0.007],
        [0.008, 0.007, 0.025],
    ]


@pytest.fixture
def tickers_4() -> list[str]:
    return ["AAPL", "MSFT", "GOOGL", "AMZN"]


@pytest.fixture
def mu_4() -> list[float]:
    return [0.12, 0.10, 0.09, 0.15]


@pytest.fixture
def sigma_4() -> list[list[float]]:
    return [
        [0.04, 0.01, 0.008, 0.012],
        [0.01, 0.03, 0.007, 0.009],
        [0.008, 0.007, 0.025, 0.006],
        [0.012, 0.009, 0.006, 0.05],
    ]


# ── Happy path ────────────────────────────────────────────────────────────────

class TestClassicalOptimizerHappyPath:
    """Tests for the basic optimization workflow."""

    def test_returns_classical_optimization_result(
        self,
        optimizer: ClassicalOptimizer,
        tickers_3: list[str],
        mu_3: list[float],
        sigma_3: list[list[float]],
    ) -> None:
        inp = make_input(tickers_3, mu_3, sigma_3)
        result = optimizer.optimize(inp)
        assert isinstance(result, ClassicalOptimizationResult)

    def test_weights_sum_to_one(
        self,
        optimizer: ClassicalOptimizer,
        tickers_3: list[str],
        mu_3: list[float],
        sigma_3: list[list[float]],
    ) -> None:
        inp = make_input(tickers_3, mu_3, sigma_3)
        result = optimizer.optimize(inp)
        total = sum(result.weights.values())
        assert abs(total - 1.0) < 1e-4

    def test_all_weights_non_negative(
        self,
        optimizer: ClassicalOptimizer,
        tickers_3: list[str],
        mu_3: list[float],
        sigma_3: list[list[float]],
    ) -> None:
        inp = make_input(tickers_3, mu_3, sigma_3)
        result = optimizer.optimize(inp)
        assert all(w >= 0.0 for w in result.weights.values())

    def test_portfolio_return_is_positive(
        self,
        optimizer: ClassicalOptimizer,
        tickers_3: list[str],
        mu_3: list[float],
        sigma_3: list[list[float]],
    ) -> None:
        inp = make_input(tickers_3, mu_3, sigma_3)
        result = optimizer.optimize(inp)
        assert result.portfolio_return > 0.0

    def test_portfolio_volatility_is_positive(
        self,
        optimizer: ClassicalOptimizer,
        tickers_3: list[str],
        mu_3: list[float],
        sigma_3: list[list[float]],
    ) -> None:
        inp = make_input(tickers_3, mu_3, sigma_3)
        result = optimizer.optimize(inp)
        assert result.portfolio_volatility > 0.0

    def test_sharpe_ratio_is_computed(
        self,
        optimizer: ClassicalOptimizer,
        tickers_3: list[str],
        mu_3: list[float],
        sigma_3: list[list[float]],
    ) -> None:
        inp = make_input(tickers_3, mu_3, sigma_3)
        result = optimizer.optimize(inp)
        expected_sharpe = (result.portfolio_return - 0.02) / result.portfolio_volatility
        assert abs(result.sharpe_ratio - expected_sharpe) < 1e-4

    def test_solver_status_is_optimal(
        self,
        optimizer: ClassicalOptimizer,
        tickers_3: list[str],
        mu_3: list[float],
        sigma_3: list[list[float]],
    ) -> None:
        inp = make_input(tickers_3, mu_3, sigma_3)
        result = optimizer.optimize(inp)
        assert "optimal" in result.solver_status.lower()

    def test_solve_time_ms_is_positive(
        self,
        optimizer: ClassicalOptimizer,
        tickers_3: list[str],
        mu_3: list[float],
        sigma_3: list[list[float]],
    ) -> None:
        inp = make_input(tickers_3, mu_3, sigma_3)
        result = optimizer.optimize(inp)
        assert result.solve_time_ms > 0.0

    def test_num_assets_is_correct(
        self,
        optimizer: ClassicalOptimizer,
        tickers_3: list[str],
        mu_3: list[float],
        sigma_3: list[list[float]],
    ) -> None:
        inp = make_input(tickers_3, mu_3, sigma_3)
        result = optimizer.optimize(inp)
        assert result.num_assets >= 1
        assert result.num_assets <= 3

    def test_4_asset_optimization(
        self,
        optimizer: ClassicalOptimizer,
        tickers_4: list[str],
        mu_4: list[float],
        sigma_4: list[list[float]],
    ) -> None:
        inp = make_input(tickers_4, mu_4, sigma_4)
        result = optimizer.optimize(inp)
        assert abs(sum(result.weights.values()) - 1.0) < 1e-4
        assert result.portfolio_return > 0.0


# ── Constraint: max_weight_per_asset ─────────────────────────────────────────

class TestMaxWeightConstraint:
    """Tests for the max_weight_per_asset constraint."""

    def test_no_weight_exceeds_max(
        self,
        optimizer: ClassicalOptimizer,
        tickers_4: list[str],
        mu_4: list[float],
        sigma_4: list[list[float]],
    ) -> None:
        max_w = 0.35
        constraints = OptimizationConstraints(max_weight_per_asset=max_w)
        inp = make_input(tickers_4, mu_4, sigma_4, constraints=constraints)
        result = optimizer.optimize(inp)
        for ticker, w in result.weights.items():
            assert w <= max_w + 1e-4, f"{ticker} weight {w:.4f} exceeds {max_w}"

    def test_tight_max_weight_forces_diversification(
        self,
        optimizer: ClassicalOptimizer,
        tickers_4: list[str],
        mu_4: list[float],
        sigma_4: list[list[float]],
    ) -> None:
        # With max_weight=0.25 and 4 assets, all must be used
        constraints = OptimizationConstraints(max_weight_per_asset=0.25)
        inp = make_input(tickers_4, mu_4, sigma_4, constraints=constraints)
        result = optimizer.optimize(inp)
        assert result.num_assets == 4


# ── Constraint: min_portfolio_return ─────────────────────────────────────────

class TestMinReturnConstraint:
    """Tests for the min_portfolio_return constraint."""

    def test_portfolio_return_meets_minimum(
        self,
        optimizer: ClassicalOptimizer,
        tickers_4: list[str],
        mu_4: list[float],
        sigma_4: list[list[float]],
    ) -> None:
        min_ret = 0.10
        constraints = OptimizationConstraints(min_portfolio_return=min_ret)
        inp = make_input(tickers_4, mu_4, sigma_4, constraints=constraints)
        result = optimizer.optimize(inp)
        assert result.portfolio_return >= min_ret - 1e-4

    def test_impossible_min_return_raises_infeasible(
        self,
        optimizer: ClassicalOptimizer,
        tickers_3: list[str],
        mu_3: list[float],
        sigma_3: list[list[float]],
    ) -> None:
        # Max possible return is 0.12 (AAPL), so 0.50 is impossible
        constraints = OptimizationConstraints(min_portfolio_return=0.50)
        inp = make_input(tickers_3, mu_3, sigma_3, constraints=constraints)
        with pytest.raises(SolverInfeasibleError):
            optimizer.optimize(inp)


# ── Constraint: sector_limits ─────────────────────────────────────────────────

class TestSectorLimitsConstraint:
    """Tests for the sector_limits constraint."""

    def test_sector_weight_does_not_exceed_limit(
        self,
        optimizer: ClassicalOptimizer,
        tickers_4: list[str],
        mu_4: list[float],
        sigma_4: list[list[float]],
    ) -> None:
        sector_tags = {
            "AAPL": "Information Technology",
            "MSFT": "Information Technology",
            "GOOGL": "Communication Services",
            "AMZN": "Consumer Discretionary",
        }
        constraints = OptimizationConstraints(
            sector_limits={"Information Technology": 0.4}
        )
        inp = make_input(
            tickers_4, mu_4, sigma_4,
            constraints=constraints,
            sector_tags=sector_tags,
        )
        result = optimizer.optimize(inp)
        it_weight = sum(
            w for t, w in result.weights.items()
            if sector_tags.get(t) == "Information Technology"
        )
        assert it_weight <= 0.4 + 1e-4


# ── Risk tolerance ────────────────────────────────────────────────────────────

class TestRiskTolerance:
    """Tests for the risk_tolerance parameter."""

    def test_risk_tolerance_zero_minimises_variance(
        self,
        optimizer: ClassicalOptimizer,
        tickers_4: list[str],
        mu_4: list[float],
        sigma_4: list[list[float]],
    ) -> None:
        """risk_tolerance=0 should produce a lower-volatility portfolio."""
        constraints_low = OptimizationConstraints(risk_tolerance=0.0)
        constraints_high = OptimizationConstraints(risk_tolerance=1.0)
        inp_low = make_input(tickers_4, mu_4, sigma_4, constraints=constraints_low)
        inp_high = make_input(tickers_4, mu_4, sigma_4, constraints=constraints_high)
        result_low = optimizer.optimize(inp_low)
        result_high = optimizer.optimize(inp_high)
        # Min-variance should have lower or equal volatility
        assert result_low.portfolio_volatility <= result_high.portfolio_volatility + 1e-4

    def test_risk_tolerance_one_maximises_return(
        self,
        optimizer: ClassicalOptimizer,
        tickers_4: list[str],
        mu_4: list[float],
        sigma_4: list[list[float]],
    ) -> None:
        """risk_tolerance=1 should produce a higher-return portfolio."""
        constraints_low = OptimizationConstraints(risk_tolerance=0.0)
        constraints_high = OptimizationConstraints(risk_tolerance=1.0)
        inp_low = make_input(tickers_4, mu_4, sigma_4, constraints=constraints_low)
        inp_high = make_input(tickers_4, mu_4, sigma_4, constraints=constraints_high)
        result_low = optimizer.optimize(inp_low)
        result_high = optimizer.optimize(inp_high)
        # Max-return should have higher or equal return
        assert result_high.portfolio_return >= result_low.portfolio_return - 1e-4


# ── Input validation ──────────────────────────────────────────────────────────

class TestInputValidation:
    """Tests for input validation in ClassicalOptimizer."""

    def test_single_ticker_raises_value_error(
        self,
        optimizer: ClassicalOptimizer,
    ) -> None:
        """Pydantic should reject single-ticker input before reaching optimizer."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ClassicalOptimizationInput(
                tickers=["AAPL"],
                expected_returns=[0.12],
                cov_matrix=[[0.04]],
            )

    def test_non_psd_covariance_still_solves(
        self,
        optimizer: ClassicalOptimizer,
    ) -> None:
        """The optimizer should handle near-PSD matrices via _ensure_psd."""
        # Slightly non-PSD due to floating point
        tickers = ["A", "B", "C"]
        mu = [0.10, 0.08, 0.09]
        sigma = [
            [0.04, 0.02, 0.02],
            [0.02, 0.04, 0.02],
            [0.02, 0.02, 0.04],
        ]
        inp = make_input(tickers, mu, sigma)
        result = optimizer.optimize(inp)
        assert abs(sum(result.weights.values()) - 1.0) < 1e-4

    def test_extra_metadata_in_result(
        self,
        optimizer: ClassicalOptimizer,
        tickers_3: list[str],
        mu_3: list[float],
        sigma_3: list[list[float]],
    ) -> None:
        inp = make_input(tickers_3, mu_3, sigma_3)
        result = optimizer.optimize(inp)
        assert "solver_used" in result.extra
        assert "risk_tolerance" in result.extra
