"""Unit tests for app.data.metrics — portfolio metrics computation.

Tests cover:
- compute_portfolio_metrics (happy path + historical data path)
- compute_max_drawdown
- compute_var / compute_cvar
- compute_sharpe_ratio
- compute_portfolio_return / compute_portfolio_volatility
- annualise_returns / annualise_volatility
- compute_efficient_frontier_points
- Edge cases: zero volatility, empty arrays, single asset
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.data.metrics import (
    PortfolioMetricsResult,
    annualise_returns,
    annualise_volatility,
    compute_cvar,
    compute_efficient_frontier_points,
    compute_max_drawdown,
    compute_portfolio_metrics,
    compute_portfolio_return,
    compute_portfolio_volatility,
    compute_sharpe_ratio,
    compute_var,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def equal_weights_3() -> np.ndarray:
    return np.array([1 / 3, 1 / 3, 1 / 3])


@pytest.fixture
def mu_3() -> np.ndarray:
    return np.array([0.12, 0.10, 0.09])


@pytest.fixture
def sigma_3() -> np.ndarray:
    return np.array([
        [0.04, 0.01, 0.008],
        [0.01, 0.03, 0.007],
        [0.008, 0.007, 0.025],
    ])


@pytest.fixture
def returns_df(sigma_3: np.ndarray) -> pd.DataFrame:
    rng = np.random.default_rng(seed=7)
    daily_cov = sigma_3 / 252
    data = rng.multivariate_normal(
        mean=[0.12 / 252, 0.10 / 252, 0.09 / 252],
        cov=daily_cov,
        size=300,
    )
    return pd.DataFrame(data, columns=["A", "B", "C"])


# ── compute_portfolio_metrics ─────────────────────────────────────────────────

class TestComputePortfolioMetrics:
    """Tests for compute_portfolio_metrics."""

    def test_returns_portfolio_metrics_result(
        self,
        equal_weights_3: np.ndarray,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
    ) -> None:
        result = compute_portfolio_metrics(equal_weights_3, mu_3, sigma_3)
        assert isinstance(result, PortfolioMetricsResult)

    def test_expected_return_is_weighted_average(
        self,
        equal_weights_3: np.ndarray,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
    ) -> None:
        result = compute_portfolio_metrics(equal_weights_3, mu_3, sigma_3)
        expected = float(mu_3 @ equal_weights_3)
        assert abs(result.expected_return - expected) < 1e-10

    def test_volatility_is_positive(
        self,
        equal_weights_3: np.ndarray,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
    ) -> None:
        result = compute_portfolio_metrics(equal_weights_3, mu_3, sigma_3)
        assert result.volatility > 0.0

    def test_sharpe_ratio_formula(
        self,
        equal_weights_3: np.ndarray,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
    ) -> None:
        rfr = 0.02
        result = compute_portfolio_metrics(
            equal_weights_3, mu_3, sigma_3, risk_free_rate=rfr
        )
        expected_sharpe = (result.expected_return - rfr) / result.volatility
        assert abs(result.sharpe_ratio - expected_sharpe) < 1e-8

    def test_num_assets_counts_nonzero_weights(
        self,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
    ) -> None:
        # Only 2 of 3 assets have non-negligible weight
        weights = np.array([0.5, 0.5, 0.0])
        result = compute_portfolio_metrics(weights, mu_3, sigma_3)
        assert result.num_assets == 2

    def test_weights_are_renormalised(
        self,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
    ) -> None:
        # Weights sum to 2.0 — should be renormalised to 1.0
        weights = np.array([0.8, 0.6, 0.6])
        result = compute_portfolio_metrics(weights, mu_3, sigma_3)
        # Expected return should equal the normalised weighted sum
        w_norm = weights / weights.sum()
        expected = float(mu_3 @ w_norm)
        assert abs(result.expected_return - expected) < 1e-8

    def test_negative_weights_clipped_to_zero(
        self,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
    ) -> None:
        # Tiny negative from numerical noise should be clipped
        weights = np.array([0.5, 0.5, -1e-12])
        result = compute_portfolio_metrics(weights, mu_3, sigma_3)
        assert result.volatility >= 0.0
        assert result.expected_return > 0.0

    def test_diversification_ratio_greater_than_one(
        self,
        equal_weights_3: np.ndarray,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
    ) -> None:
        result = compute_portfolio_metrics(equal_weights_3, mu_3, sigma_3)
        # Diversified portfolio should have ratio > 1
        assert result.diversification_ratio is not None
        assert result.diversification_ratio >= 1.0

    def test_historical_metrics_computed_when_returns_provided(
        self,
        equal_weights_3: np.ndarray,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
        returns_df: pd.DataFrame,
    ) -> None:
        result = compute_portfolio_metrics(
            equal_weights_3, mu_3, sigma_3, returns_data=returns_df
        )
        assert result.max_drawdown is not None
        assert result.var_95 is not None
        assert result.var_99 is not None
        assert result.cvar_95 is not None
        assert result.cvar_99 is not None

    def test_max_drawdown_is_negative_or_zero(
        self,
        equal_weights_3: np.ndarray,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
        returns_df: pd.DataFrame,
    ) -> None:
        result = compute_portfolio_metrics(
            equal_weights_3, mu_3, sigma_3, returns_data=returns_df
        )
        assert result.max_drawdown is not None
        assert result.max_drawdown <= 0.0

    def test_var_95_less_than_var_99(
        self,
        equal_weights_3: np.ndarray,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
        returns_df: pd.DataFrame,
    ) -> None:
        """VaR at 99% should be a larger loss (more negative) than at 95%."""
        result = compute_portfolio_metrics(
            equal_weights_3, mu_3, sigma_3, returns_data=returns_df
        )
        assert result.var_99 is not None
        assert result.var_95 is not None
        assert result.var_99 <= result.var_95

    def test_cvar_worse_than_var(
        self,
        equal_weights_3: np.ndarray,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
        returns_df: pd.DataFrame,
    ) -> None:
        """CVaR (expected shortfall) should be <= VaR (more extreme loss)."""
        result = compute_portfolio_metrics(
            equal_weights_3, mu_3, sigma_3, returns_data=returns_df
        )
        assert result.cvar_95 is not None
        assert result.var_95 is not None
        assert result.cvar_95 <= result.var_95

    def test_sortino_ratio_computed_with_returns(
        self,
        equal_weights_3: np.ndarray,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
        returns_df: pd.DataFrame,
    ) -> None:
        result = compute_portfolio_metrics(
            equal_weights_3, mu_3, sigma_3, returns_data=returns_df
        )
        assert result.sortino_ratio is not None

    def test_calmar_ratio_computed_with_returns(
        self,
        equal_weights_3: np.ndarray,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
        returns_df: pd.DataFrame,
    ) -> None:
        result = compute_portfolio_metrics(
            equal_weights_3, mu_3, sigma_3, returns_data=returns_df
        )
        # Calmar may be None if drawdown is zero, but with random data it won't be
        assert result.calmar_ratio is not None

    def test_no_historical_metrics_without_returns(
        self,
        equal_weights_3: np.ndarray,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
    ) -> None:
        result = compute_portfolio_metrics(equal_weights_3, mu_3, sigma_3)
        assert result.max_drawdown is None
        assert result.var_95 is None
        assert result.sortino_ratio is None


# ── compute_max_drawdown ──────────────────────────────────────────────────────

class TestComputeMaxDrawdown:
    """Tests for compute_max_drawdown."""

    def test_empty_array_returns_zero(self) -> None:
        assert compute_max_drawdown(np.array([])) == 0.0

    def test_all_positive_returns_no_drawdown(self) -> None:
        returns = np.array([0.01, 0.02, 0.01, 0.03])
        dd = compute_max_drawdown(returns)
        assert dd <= 0.0  # May be 0 or very small negative

    def test_known_drawdown(self) -> None:
        # Simulate a 50% drawdown: go up then crash
        # log returns: +0.5 then -0.7 (cumulative wealth goes up then down)
        returns = np.array([0.5, -0.7, 0.1])
        dd = compute_max_drawdown(returns)
        assert dd < 0.0
        assert dd >= -1.0  # Can't lose more than 100%

    def test_monotonically_decreasing_returns(self) -> None:
        returns = np.array([-0.05, -0.05, -0.05, -0.05])
        dd = compute_max_drawdown(returns)
        assert dd < 0.0

    def test_single_element(self) -> None:
        dd = compute_max_drawdown(np.array([0.01]))
        assert dd == 0.0  # No peak-to-trough possible with 1 element


# ── compute_var ───────────────────────────────────────────────────────────────

class TestComputeVar:
    """Tests for compute_var."""

    def test_empty_returns_zero(self) -> None:
        assert compute_var(np.array([])) == 0.0

    def test_var_is_negative_for_mixed_returns(self) -> None:
        rng = np.random.default_rng(seed=1)
        returns = rng.normal(0.001, 0.02, size=500)
        var = compute_var(returns, confidence=0.95)
        assert var < 0.0

    def test_var_99_more_extreme_than_var_95(self) -> None:
        rng = np.random.default_rng(seed=2)
        returns = rng.normal(0.001, 0.02, size=500)
        var_95 = compute_var(returns, confidence=0.95)
        var_99 = compute_var(returns, confidence=0.99)
        assert var_99 <= var_95

    def test_var_at_50_percent_is_median(self) -> None:
        returns = np.array([-0.05, -0.02, 0.0, 0.02, 0.05])
        var_50 = compute_var(returns, confidence=0.50)
        # 50th percentile of losses = 50th percentile of returns
        assert abs(var_50 - np.percentile(returns, 50)) < 1e-10


# ── compute_cvar ──────────────────────────────────────────────────────────────

class TestComputeCvar:
    """Tests for compute_cvar."""

    def test_empty_returns_zero(self) -> None:
        assert compute_cvar(np.array([])) == 0.0

    def test_cvar_worse_than_var(self) -> None:
        rng = np.random.default_rng(seed=3)
        returns = rng.normal(0.001, 0.02, size=500)
        var = compute_var(returns, confidence=0.95)
        cvar = compute_cvar(returns, confidence=0.95)
        assert cvar <= var

    def test_cvar_is_mean_of_tail(self) -> None:
        returns = np.array([-0.10, -0.08, -0.06, -0.04, -0.02, 0.0, 0.02, 0.04])
        var = compute_var(returns, confidence=0.75)
        tail = returns[returns <= var]
        expected_cvar = float(np.mean(tail))
        cvar = compute_cvar(returns, confidence=0.75)
        assert abs(cvar - expected_cvar) < 1e-10


# ── compute_sharpe_ratio ──────────────────────────────────────────────────────

class TestComputeSharpeRatio:
    """Tests for compute_sharpe_ratio."""

    def test_basic_formula(self) -> None:
        sharpe = compute_sharpe_ratio(0.12, 0.15, risk_free_rate=0.02)
        expected = (0.12 - 0.02) / 0.15
        assert abs(sharpe - expected) < 1e-10

    def test_zero_volatility_returns_zero(self) -> None:
        sharpe = compute_sharpe_ratio(0.12, 0.0)
        assert sharpe == 0.0

    def test_negative_excess_return(self) -> None:
        sharpe = compute_sharpe_ratio(0.01, 0.15, risk_free_rate=0.05)
        assert sharpe < 0.0

    def test_default_risk_free_rate(self) -> None:
        sharpe = compute_sharpe_ratio(0.12, 0.15)
        expected = (0.12 - 0.02) / 0.15
        assert abs(sharpe - expected) < 1e-10


# ── compute_portfolio_return ──────────────────────────────────────────────────

class TestComputePortfolioReturn:
    """Tests for compute_portfolio_return."""

    def test_equal_weights(self) -> None:
        weights = np.array([0.5, 0.5])
        mu = np.array([0.10, 0.20])
        result = compute_portfolio_return(weights, mu)
        assert abs(result - 0.15) < 1e-10

    def test_concentrated_portfolio(self) -> None:
        weights = np.array([1.0, 0.0, 0.0])
        mu = np.array([0.12, 0.10, 0.09])
        result = compute_portfolio_return(weights, mu)
        assert abs(result - 0.12) < 1e-10


# ── compute_portfolio_volatility ──────────────────────────────────────────────

class TestComputePortfolioVolatility:
    """Tests for compute_portfolio_volatility."""

    def test_single_asset_vol(self) -> None:
        weights = np.array([1.0, 0.0])
        sigma = np.array([[0.04, 0.0], [0.0, 0.09]])
        vol = compute_portfolio_volatility(weights, sigma)
        assert abs(vol - 0.2) < 1e-8  # sqrt(0.04) = 0.2

    def test_diversification_reduces_vol(self) -> None:
        # Two uncorrelated assets with same vol
        sigma = np.array([[0.04, 0.0], [0.0, 0.04]])
        w_concentrated = np.array([1.0, 0.0])
        w_equal = np.array([0.5, 0.5])
        vol_conc = compute_portfolio_volatility(w_concentrated, sigma)
        vol_equal = compute_portfolio_volatility(w_equal, sigma)
        assert vol_equal < vol_conc


# ── annualise_returns ─────────────────────────────────────────────────────────

class TestAnnualiseReturns:
    """Tests for annualise_returns."""

    def test_empty_returns_zero(self) -> None:
        assert annualise_returns(np.array([])) == 0.0

    def test_constant_daily_return(self) -> None:
        daily = np.full(252, 0.001)
        annual = annualise_returns(daily)
        assert abs(annual - 0.252) < 1e-8

    def test_custom_trading_days(self) -> None:
        daily = np.full(100, 0.001)
        annual = annualise_returns(daily, trading_days=100)
        assert abs(annual - 0.1) < 1e-8


# ── annualise_volatility ──────────────────────────────────────────────────────

class TestAnnualiseVolatility:
    """Tests for annualise_volatility."""

    def test_empty_returns_zero(self) -> None:
        assert annualise_volatility(np.array([])) == 0.0

    def test_single_element_returns_zero(self) -> None:
        assert annualise_volatility(np.array([0.01])) == 0.0

    def test_scales_by_sqrt_trading_days(self) -> None:
        rng = np.random.default_rng(seed=5)
        daily = rng.normal(0.001, 0.01, size=252)
        daily_std = float(np.std(daily, ddof=1))
        annual = annualise_volatility(daily)
        expected = daily_std * np.sqrt(252)
        assert abs(annual - expected) < 1e-10


# ── compute_efficient_frontier_points ─────────────────────────────────────────

class TestComputeEfficientFrontierPoints:
    """Tests for compute_efficient_frontier_points."""

    def test_returns_list_of_dicts(
        self,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
    ) -> None:
        points = compute_efficient_frontier_points(mu_3, sigma_3, num_points=10)
        assert isinstance(points, list)
        assert len(points) == 10
        assert all(isinstance(p, dict) for p in points)

    def test_each_point_has_required_keys(
        self,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
    ) -> None:
        points = compute_efficient_frontier_points(mu_3, sigma_3, num_points=5)
        for p in points:
            assert "return" in p
            assert "volatility" in p
            assert "sharpe" in p

    def test_points_sorted_by_volatility(
        self,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
    ) -> None:
        points = compute_efficient_frontier_points(mu_3, sigma_3, num_points=20)
        vols = [p["volatility"] for p in points]
        assert vols == sorted(vols)

    def test_all_volatilities_positive(
        self,
        mu_3: np.ndarray,
        sigma_3: np.ndarray,
    ) -> None:
        points = compute_efficient_frontier_points(mu_3, sigma_3, num_points=10)
        assert all(p["volatility"] >= 0.0 for p in points)
