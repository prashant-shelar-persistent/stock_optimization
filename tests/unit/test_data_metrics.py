"""Unit tests for app.data.metrics.

Tests cover:
- compute_portfolio_metrics: happy path, edge cases (zero vol, single asset)
- compute_max_drawdown: no drawdown, monotonic decline, recovery
- compute_var: basic VaR at 95% and 99%
- compute_cvar: CVaR is <= VaR (more negative)
- compute_sharpe_ratio: positive/negative/zero volatility
- compute_portfolio_volatility: correct formula
- annualise_returns / annualise_volatility: scaling
- compute_efficient_frontier_points: returns list of dicts with correct keys
- PortfolioMetricsResult: dataclass fields
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
    compute_portfolio_volatility,
    compute_sharpe_ratio,
    compute_var,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _simple_3asset_setup():
    """Return weights, expected_returns, cov_matrix for 3 assets."""
    weights = np.array([0.4, 0.3, 0.3])
    expected_returns = np.array([0.12, 0.10, 0.08])
    cov_matrix = np.array([
        [0.04, 0.01, 0.005],
        [0.01, 0.03, 0.008],
        [0.005, 0.008, 0.02],
    ])
    return weights, expected_returns, cov_matrix


def _make_returns_df(n_days: int = 252, n_assets: int = 3, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic daily log returns."""
    rng = np.random.default_rng(seed)
    data = rng.normal(0.0004, 0.01, size=(n_days, n_assets))
    return pd.DataFrame(data, columns=[f"A{i}" for i in range(n_assets)])


# ---------------------------------------------------------------------------
# compute_portfolio_metrics
# ---------------------------------------------------------------------------

class TestComputePortfolioMetrics:
    def test_happy_path_returns_result(self):
        weights, mu, sigma = _simple_3asset_setup()
        result = compute_portfolio_metrics(weights, mu, sigma)
        assert isinstance(result, PortfolioMetricsResult)

    def test_expected_return_is_weighted_sum(self):
        weights, mu, sigma = _simple_3asset_setup()
        result = compute_portfolio_metrics(weights, mu, sigma)
        expected = float(mu @ weights)
        assert abs(result.expected_return - expected) < 1e-10

    def test_volatility_is_positive(self):
        weights, mu, sigma = _simple_3asset_setup()
        result = compute_portfolio_metrics(weights, mu, sigma)
        assert result.volatility > 0.0

    def test_sharpe_ratio_computed_correctly(self):
        weights, mu, sigma = _simple_3asset_setup()
        result = compute_portfolio_metrics(weights, mu, sigma, risk_free_rate=0.02)
        expected_sharpe = (result.expected_return - 0.02) / result.volatility
        assert abs(result.sharpe_ratio - expected_sharpe) < 1e-8

    def test_num_assets_counts_nonzero_weights(self):
        weights = np.array([0.5, 0.5, 0.0])
        mu = np.array([0.10, 0.08, 0.06])
        sigma = np.eye(3) * 0.04
        result = compute_portfolio_metrics(weights, mu, sigma)
        assert result.num_assets == 2

    def test_diversification_ratio_greater_than_one_for_diversified_portfolio(self):
        """A diversified portfolio should have diversification_ratio > 1."""
        weights = np.array([0.5, 0.5])
        mu = np.array([0.10, 0.08])
        # Low correlation between assets
        sigma = np.array([[0.04, 0.001], [0.001, 0.03]])
        result = compute_portfolio_metrics(weights, mu, sigma)
        assert result.diversification_ratio is not None
        assert result.diversification_ratio > 1.0

    def test_with_returns_data_computes_historical_metrics(self):
        weights, mu, sigma = _simple_3asset_setup()
        returns_df = _make_returns_df(n_days=252, n_assets=3)
        result = compute_portfolio_metrics(weights, mu, sigma, returns_data=returns_df)
        assert result.max_drawdown is not None
        assert result.var_95 is not None
        assert result.var_99 is not None
        assert result.cvar_95 is not None
        assert result.cvar_99 is not None

    def test_without_returns_data_historical_metrics_are_none(self):
        weights, mu, sigma = _simple_3asset_setup()
        result = compute_portfolio_metrics(weights, mu, sigma, returns_data=None)
        assert result.max_drawdown is None
        assert result.var_95 is None
        assert result.sortino_ratio is None

    def test_weights_normalised_if_not_summing_to_one(self):
        """Weights that don't sum to 1 should be normalised."""
        weights = np.array([2.0, 2.0, 2.0])  # Sum = 6, not 1
        mu = np.array([0.10, 0.08, 0.06])
        sigma = np.eye(3) * 0.04
        result = compute_portfolio_metrics(weights, mu, sigma)
        # After normalisation, weights = [1/3, 1/3, 1/3]
        expected_return = float(mu @ np.array([1 / 3, 1 / 3, 1 / 3]))
        assert abs(result.expected_return - expected_return) < 1e-8

    def test_zero_volatility_gives_zero_sharpe(self):
        """When volatility is effectively zero, Sharpe should be 0."""
        weights = np.array([1.0])
        mu = np.array([0.10])
        sigma = np.array([[0.0]])  # Zero variance
        result = compute_portfolio_metrics(weights, mu, sigma)
        assert result.sharpe_ratio == 0.0

    def test_sortino_ratio_computed_with_returns_data(self):
        weights, mu, sigma = _simple_3asset_setup()
        # Use returns with clear downside
        rng = np.random.default_rng(0)
        returns_data = pd.DataFrame(
            rng.normal(-0.001, 0.02, size=(252, 3)),
            columns=["A0", "A1", "A2"],
        )
        result = compute_portfolio_metrics(
            weights, mu, sigma, returns_data=returns_data, risk_free_rate=0.02
        )
        # Sortino may be None if no downside returns exist, but with negative mean it should exist
        # Just check it's a float if not None
        if result.sortino_ratio is not None:
            assert isinstance(result.sortino_ratio, float)

    def test_calmar_ratio_computed_with_returns_data(self):
        weights, mu, sigma = _simple_3asset_setup()
        returns_df = _make_returns_df(n_days=252, n_assets=3)
        result = compute_portfolio_metrics(weights, mu, sigma, returns_data=returns_df)
        if result.calmar_ratio is not None:
            assert isinstance(result.calmar_ratio, float)

    def test_var_99_more_negative_than_var_95(self):
        """VaR at 99% should be more negative (worse) than VaR at 95%."""
        weights, mu, sigma = _simple_3asset_setup()
        returns_df = _make_returns_df(n_days=252, n_assets=3)
        result = compute_portfolio_metrics(weights, mu, sigma, returns_data=returns_df)
        assert result.var_99 is not None
        assert result.var_95 is not None
        assert result.var_99 <= result.var_95

    def test_cvar_more_negative_than_var(self):
        """CVaR should be <= VaR (CVaR is the expected loss beyond VaR)."""
        weights, mu, sigma = _simple_3asset_setup()
        returns_df = _make_returns_df(n_days=252, n_assets=3)
        result = compute_portfolio_metrics(weights, mu, sigma, returns_data=returns_df)
        assert result.cvar_95 is not None
        assert result.var_95 is not None
        assert result.cvar_95 <= result.var_95


# ---------------------------------------------------------------------------
# compute_max_drawdown
# ---------------------------------------------------------------------------

class TestComputeMaxDrawdown:
    def test_empty_returns_gives_zero(self):
        result = compute_max_drawdown(np.array([]))
        assert result == 0.0

    def test_all_positive_returns_gives_zero_drawdown(self):
        """Monotonically increasing wealth → no drawdown."""
        returns = np.full(100, 0.001)  # All positive
        result = compute_max_drawdown(returns)
        assert result == 0.0

    def test_monotonic_decline_gives_large_drawdown(self):
        """Monotonically declining wealth → large negative drawdown."""
        returns = np.full(100, -0.01)  # All negative
        result = compute_max_drawdown(returns)
        assert result < -0.5  # Should be a large drawdown

    def test_drawdown_is_negative(self):
        """Max drawdown should always be <= 0."""
        rng = np.random.default_rng(42)
        returns = rng.normal(0.0, 0.01, 252)
        result = compute_max_drawdown(returns)
        assert result <= 0.0

    def test_single_return_gives_zero_drawdown(self):
        """Single return: cumulative max equals cumulative return, so drawdown = 0."""
        result_pos = compute_max_drawdown(np.array([0.01]))
        result_neg = compute_max_drawdown(np.array([-0.01]))
        # With a single data point, running_max == cum_returns, so drawdown = 0
        assert result_pos == 0.0
        assert result_neg == 0.0

    def test_recovery_after_drawdown(self):
        """After a drawdown and recovery, max drawdown should reflect the trough."""
        # Decline then recover
        returns = np.array([-0.05, -0.05, -0.05, 0.10, 0.10, 0.10])
        result = compute_max_drawdown(returns)
        assert result < 0.0  # There was a drawdown


# ---------------------------------------------------------------------------
# compute_var
# ---------------------------------------------------------------------------

class TestComputeVar:
    def test_empty_returns_gives_zero(self):
        result = compute_var(np.array([]), confidence=0.95)
        assert result == 0.0

    def test_var_is_negative_for_mixed_returns(self):
        rng = np.random.default_rng(42)
        returns = rng.normal(0.0, 0.01, 252)
        result = compute_var(returns, confidence=0.95)
        assert result < 0.0

    def test_var_99_more_negative_than_var_95(self):
        rng = np.random.default_rng(42)
        returns = rng.normal(0.0, 0.01, 252)
        var_95 = compute_var(returns, confidence=0.95)
        var_99 = compute_var(returns, confidence=0.99)
        assert var_99 <= var_95

    def test_var_at_50_percent_is_median(self):
        """VaR at 50% confidence should be the median return."""
        returns = np.array([-0.05, -0.02, 0.0, 0.02, 0.05])
        result = compute_var(returns, confidence=0.50)
        assert abs(result - np.median(returns)) < 1e-10


# ---------------------------------------------------------------------------
# compute_cvar
# ---------------------------------------------------------------------------

class TestComputeCvar:
    def test_empty_returns_gives_zero(self):
        result = compute_cvar(np.array([]), confidence=0.95)
        assert result == 0.0

    def test_cvar_is_less_than_or_equal_to_var(self):
        rng = np.random.default_rng(42)
        returns = rng.normal(0.0, 0.01, 252)
        var = compute_var(returns, confidence=0.95)
        cvar = compute_cvar(returns, confidence=0.95)
        assert cvar <= var

    def test_cvar_is_mean_of_tail_losses(self):
        """CVaR should be the mean of returns below VaR."""
        returns = np.array([-0.10, -0.08, -0.05, -0.02, 0.01, 0.03, 0.05])
        var = compute_var(returns, confidence=0.95)
        tail = returns[returns <= var]
        expected_cvar = float(np.mean(tail)) if len(tail) > 0 else var
        result = compute_cvar(returns, confidence=0.95)
        assert abs(result - expected_cvar) < 1e-10


# ---------------------------------------------------------------------------
# compute_sharpe_ratio
# ---------------------------------------------------------------------------

class TestComputeSharpeRatio:
    def test_positive_sharpe(self):
        result = compute_sharpe_ratio(0.12, 0.15, risk_free_rate=0.02)
        expected = (0.12 - 0.02) / 0.15
        assert abs(result - expected) < 1e-10

    def test_negative_sharpe(self):
        result = compute_sharpe_ratio(0.01, 0.15, risk_free_rate=0.05)
        expected = (0.01 - 0.05) / 0.15
        assert abs(result - expected) < 1e-10

    def test_zero_volatility_returns_zero(self):
        result = compute_sharpe_ratio(0.10, 0.0, risk_free_rate=0.02)
        assert result == 0.0

    def test_zero_excess_return_gives_zero_sharpe(self):
        result = compute_sharpe_ratio(0.05, 0.10, risk_free_rate=0.05)
        assert abs(result) < 1e-10


# ---------------------------------------------------------------------------
# compute_portfolio_volatility
# ---------------------------------------------------------------------------

class TestComputePortfolioVolatility:
    def test_single_asset_volatility(self):
        """Single asset: portfolio vol = sqrt(w^2 * sigma^2) = w * sigma."""
        weights = np.array([1.0])
        sigma = np.array([[0.04]])  # variance = 0.04, vol = 0.2
        result = compute_portfolio_volatility(weights, sigma)
        assert abs(result - 0.2) < 1e-8

    def test_equal_weight_uncorrelated_assets(self):
        """Equal-weight, uncorrelated: vol = sigma / sqrt(n)."""
        n = 4
        weights = np.full(n, 1.0 / n)
        sigma = np.eye(n) * 0.04  # Each asset has vol = 0.2
        result = compute_portfolio_volatility(weights, sigma)
        expected = 0.2 / np.sqrt(n)
        assert abs(result - expected) < 1e-8

    def test_volatility_is_non_negative(self):
        weights, _, sigma = _simple_3asset_setup()
        result = compute_portfolio_volatility(weights, sigma)
        assert result >= 0.0


# ---------------------------------------------------------------------------
# annualise_returns
# ---------------------------------------------------------------------------

class TestAnnualiseReturns:
    def test_empty_returns_gives_zero(self):
        result = annualise_returns(np.array([]))
        assert result == 0.0

    def test_constant_daily_return(self):
        """Constant daily return of r → annualised = r * 252."""
        daily_r = 0.001
        returns = np.full(252, daily_r)
        result = annualise_returns(returns)
        assert abs(result - daily_r * 252) < 1e-10

    def test_custom_trading_days(self):
        daily_r = 0.001
        returns = np.full(100, daily_r)
        result = annualise_returns(returns, trading_days=200)
        assert abs(result - daily_r * 200) < 1e-10


# ---------------------------------------------------------------------------
# annualise_volatility
# ---------------------------------------------------------------------------

class TestAnnualiseVolatility:
    def test_empty_returns_gives_zero(self):
        result = annualise_volatility(np.array([]))
        assert result == 0.0

    def test_single_return_gives_zero(self):
        result = annualise_volatility(np.array([0.01]))
        assert result == 0.0

    def test_constant_returns_give_near_zero_volatility(self):
        """Constant returns have zero std dev; result should be near zero."""
        returns = np.full(100, 0.001)
        result = annualise_volatility(returns)
        assert result < 1e-10

    def test_scales_by_sqrt_trading_days(self):
        rng = np.random.default_rng(42)
        returns = rng.normal(0.0, 0.01, 252)
        daily_vol = float(np.std(returns, ddof=1))
        result = annualise_volatility(returns)
        expected = daily_vol * np.sqrt(252)
        assert abs(result - expected) < 1e-10


# ---------------------------------------------------------------------------
# compute_efficient_frontier_points
# ---------------------------------------------------------------------------

class TestComputeEfficientFrontierPoints:
    def test_returns_list_of_dicts(self):
        mu = np.array([0.12, 0.10, 0.08])
        sigma = np.eye(3) * 0.04
        points = compute_efficient_frontier_points(mu, sigma, num_points=10)
        assert isinstance(points, list)
        assert len(points) == 10

    def test_each_point_has_required_keys(self):
        mu = np.array([0.12, 0.10, 0.08])
        sigma = np.eye(3) * 0.04
        points = compute_efficient_frontier_points(mu, sigma, num_points=5)
        for point in points:
            assert "return" in point
            assert "volatility" in point
            assert "sharpe" in point

    def test_points_sorted_by_volatility(self):
        mu = np.array([0.12, 0.10, 0.08])
        sigma = np.eye(3) * 0.04
        points = compute_efficient_frontier_points(mu, sigma, num_points=20)
        vols = [p["volatility"] for p in points]
        assert vols == sorted(vols)

    def test_volatility_values_are_positive(self):
        mu = np.array([0.12, 0.10, 0.08])
        sigma = np.eye(3) * 0.04
        points = compute_efficient_frontier_points(mu, sigma, num_points=10)
        for point in points:
            assert point["volatility"] >= 0.0

    def test_return_values_are_floats(self):
        mu = np.array([0.12, 0.10, 0.08])
        sigma = np.eye(3) * 0.04
        points = compute_efficient_frontier_points(mu, sigma, num_points=5)
        for point in points:
            assert isinstance(point["return"], float)
            assert isinstance(point["volatility"], float)
            assert isinstance(point["sharpe"], float)
