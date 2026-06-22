"""Portfolio metrics computation module.

Provides functions to compute standard portfolio performance metrics from
weight vectors, expected returns, and covariance matrices, as well as
historical return series.

All metrics are annualised unless otherwise noted.

Metrics computed:
    - Expected return (annualised)
    - Volatility / standard deviation (annualised)
    - Sharpe ratio
    - Sortino ratio
    - Maximum drawdown
    - Value at Risk (VaR) at 95% and 99% confidence
    - Conditional Value at Risk (CVaR / Expected Shortfall)
    - Calmar ratio
    - Beta (vs. equal-weight benchmark)
    - Diversification ratio

Usage::

    from app.data.metrics import compute_portfolio_metrics, compute_max_drawdown

    metrics = compute_portfolio_metrics(
        weights=np.array([0.4, 0.3, 0.3]),
        expected_returns=np.array([0.12, 0.10, 0.09]),
        covariance_matrix=cov,
        returns_data=returns_df,
        risk_free_rate=0.02,
    )
    print(metrics.sharpe_ratio)
"""
from __future__ import annotations


from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd


if TYPE_CHECKING:
    pass

# Trading days per year (approximate)
TRADING_DAYS_PER_YEAR = 252


@dataclass
class PortfolioMetricsResult:
    """Comprehensive portfolio performance metrics.

    All return/volatility figures are annualised.
    """

    # Core metrics
    expected_return: float
    """Annualised expected return (weighted sum of asset returns)."""

    volatility: float
    """Annualised portfolio volatility (standard deviation)."""

    sharpe_ratio: float
    """Sharpe ratio: (expected_return - risk_free_rate) / volatility."""

    # Risk-adjusted metrics
    sortino_ratio: float | None = None
    """Sortino ratio: (expected_return - risk_free_rate) / downside_deviation."""

    calmar_ratio: float | None = None
    """Calmar ratio: expected_return / abs(max_drawdown). None if no drawdown data."""

    # Drawdown
    max_drawdown: float | None = None
    """Maximum drawdown as a negative fraction (e.g. -0.25 = 25% drawdown)."""

    # Value at Risk
    var_95: float | None = None
    """Daily Value at Risk at 95% confidence (negative = loss)."""

    var_99: float | None = None
    """Daily Value at Risk at 99% confidence (negative = loss)."""

    cvar_95: float | None = None
    """Conditional VaR (Expected Shortfall) at 95% confidence."""

    cvar_99: float | None = None
    """Conditional VaR (Expected Shortfall) at 99% confidence."""

    # Diversification
    diversification_ratio: float | None = None
    """Diversification ratio: weighted avg vol / portfolio vol. >1 means diversified."""

    # Asset count
    num_assets: int = 0
    """Number of assets with non-negligible weight (> 1e-4)."""

    # Additional metadata
    annualised_downside_deviation: float | None = None
    """Annualised downside deviation (semi-deviation below risk-free rate)."""

    extra: dict = field(default_factory=dict)
    """Additional metrics or metadata."""


def compute_portfolio_metrics(
    weights: np.ndarray,
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    returns_data: pd.DataFrame | None = None,
    risk_free_rate: float = 0.02,
    weight_threshold: float = 1e-4,
) -> "PortfolioMetricsResult":
    """Compute comprehensive portfolio performance metrics.

    Args:
        weights: Portfolio weight vector, shape (n,). Must sum to 1.
        expected_returns: Annualised expected returns, shape (n,).
        covariance_matrix: Annualised covariance matrix, shape (n, n).
        returns_data: Optional DataFrame of daily log returns, shape (days, n).
            Required for drawdown, VaR, CVaR, and Sortino ratio.
        risk_free_rate: Annual risk-free rate for Sharpe/Sortino computation.
        weight_threshold: Minimum weight to count an asset as "included".

    Returns:
        PortfolioMetricsResult with all computed metrics.
    """
    weights = np.asarray(weights, dtype=float)

    # Clip tiny negatives from numerical noise and re-normalise
    weights = np.maximum(weights, 0.0)
    total = weights.sum()
    if total > 0:
        weights = weights / total

    # ── Core metrics ──────────────────────────────────────────────────────────
    port_return = float(expected_returns @ weights)
    port_variance = float(weights @ covariance_matrix @ weights)
    port_vol = float(np.sqrt(max(port_variance, 0.0)))

    sharpe = (
        (port_return - risk_free_rate) / port_vol
        if port_vol > 1e-10
        else 0.0
    )

    num_assets = int(np.sum(weights > weight_threshold))

    # ── Diversification ratio ─────────────────────────────────────────────────
    asset_vols = np.sqrt(np.maximum(np.diag(covariance_matrix), 0.0))
    weighted_avg_vol = float(weights @ asset_vols)
    diversification_ratio = (
        weighted_avg_vol / port_vol if port_vol > 1e-10 else None
    )

    # ── Historical metrics (require returns_data) ─────────────────────────────
    max_drawdown: float | None = None
    var_95: float | None = None
    var_99: float | None = None
    cvar_95: float | None = None
    cvar_99: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    annualised_downside_deviation: float | None = None

    if returns_data is not None and not returns_data.empty:
        # Align weights with columns
        n_cols = returns_data.shape[1]
        w_aligned = weights[:n_cols] if len(weights) >= n_cols else np.pad(
            weights, (0, n_cols - len(weights))
        )

        # Daily portfolio returns
        port_daily_returns = returns_data.values @ w_aligned

        # Max drawdown
        max_drawdown = compute_max_drawdown(port_daily_returns)

        # VaR and CVaR (historical simulation)
        var_95 = compute_var(port_daily_returns, confidence=0.95)
        var_99 = compute_var(port_daily_returns, confidence=0.99)
        cvar_95 = compute_cvar(port_daily_returns, confidence=0.95)
        cvar_99 = compute_cvar(port_daily_returns, confidence=0.99)

        # Sortino ratio (downside deviation)
        daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
        downside_returns = port_daily_returns[port_daily_returns < daily_rf]
        if len(downside_returns) > 1:
            downside_dev_daily = float(np.std(downside_returns, ddof=1))
            annualised_downside_deviation = downside_dev_daily * np.sqrt(
                TRADING_DAYS_PER_YEAR
            )
            sortino_ratio = (
                (port_return - risk_free_rate) / annualised_downside_deviation
                if annualised_downside_deviation > 1e-10
                else 0.0
            )

        # Calmar ratio
        if max_drawdown is not None and abs(max_drawdown) > 1e-10:
            calmar_ratio = port_return / abs(max_drawdown)

    return PortfolioMetricsResult(
        expected_return=port_return,
        volatility=port_vol,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino_ratio,
        calmar_ratio=calmar_ratio,
        max_drawdown=max_drawdown,
        var_95=var_95,
        var_99=var_99,
        cvar_95=cvar_95,
        cvar_99=cvar_99,
        diversification_ratio=diversification_ratio,
        num_assets=num_assets,
        annualised_downside_deviation=annualised_downside_deviation,
    )


def compute_max_drawdown(returns: np.ndarray) -> float:
    """Compute the maximum drawdown from a series of daily returns.

    Maximum drawdown is the largest peak-to-trough decline in the
    cumulative return series, expressed as a negative fraction.

    Args:
        returns: 1-D array of daily returns (log or simple).

    Returns:
        Maximum drawdown as a negative float (e.g. -0.25 for 25% drawdown).
        Returns 0.0 if the returns array is empty or has no drawdown.
    """
    if len(returns) == 0:
        return 0.0

    # Compute cumulative wealth index (starting at 1.0)
    # Using simple returns approximation from log returns
    cum_returns = np.exp(np.cumsum(returns))

    # Running maximum
    running_max = np.maximum.accumulate(cum_returns)

    # Drawdown at each point
    drawdowns = (cum_returns - running_max) / running_max

    return float(np.min(drawdowns))


def compute_var(
    returns: np.ndarray,
    confidence: float = 0.95,
) -> float:
    """Compute historical Value at Risk (VaR).

    VaR at confidence level c is the loss not exceeded with probability c.
    Returned as a negative number (loss convention).

    Args:
        returns: 1-D array of daily returns.
        confidence: Confidence level (e.g. 0.95 for 95% VaR).

    Returns:
        VaR as a negative float (e.g. -0.02 means 2% daily loss at threshold).
    """
    if len(returns) == 0:
        return 0.0

    return float(np.percentile(returns, (1 - confidence) * 100))


def compute_cvar(
    returns: np.ndarray,
    confidence: float = 0.95,
) -> float:
    """Compute historical Conditional Value at Risk (CVaR / Expected Shortfall).

    CVaR is the expected loss given that the loss exceeds the VaR threshold.
    Returned as a negative number (loss convention).

    Args:
        returns: 1-D array of daily returns.
        confidence: Confidence level (e.g. 0.95 for 95% CVaR).

    Returns:
        CVaR as a negative float.
    """
    if len(returns) == 0:
        return 0.0

    var = compute_var(returns, confidence=confidence)
    tail_returns = returns[returns <= var]

    if len(tail_returns) == 0:
        return var

    return float(np.mean(tail_returns))


def compute_sharpe_ratio(
    portfolio_return: float,
    portfolio_volatility: float,
    risk_free_rate: float = 0.02,
) -> float:
    """Compute the Sharpe ratio.

    Args:
        portfolio_return: Annualised portfolio return.
        portfolio_volatility: Annualised portfolio volatility.
        risk_free_rate: Annual risk-free rate.

    Returns:
        Sharpe ratio. Returns 0.0 if volatility is zero.
    """
    if portfolio_volatility <= 1e-10:
        return 0.0
    return (portfolio_return - risk_free_rate) / portfolio_volatility


def compute_portfolio_return(
    weights: np.ndarray,
    expected_returns: np.ndarray,
) -> float:
    """Compute the expected portfolio return.

    Args:
        weights: Portfolio weight vector, shape (n,).
        expected_returns: Annualised expected returns, shape (n,).

    Returns:
        Annualised expected portfolio return.
    """
    return float(np.asarray(weights) @ np.asarray(expected_returns))


def compute_portfolio_volatility(
    weights: np.ndarray,
    covariance_matrix: np.ndarray,
) -> float:
    """Compute the annualised portfolio volatility.

    Args:
        weights: Portfolio weight vector, shape (n,).
        covariance_matrix: Annualised covariance matrix, shape (n, n).

    Returns:
        Annualised portfolio volatility (standard deviation).
    """
    w = np.asarray(weights)
    cov = np.asarray(covariance_matrix)
    variance = float(w @ cov @ w)
    return float(np.sqrt(max(variance, 0.0)))


def compute_efficient_frontier_points(
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    num_points: int = 50,
    risk_free_rate: float = 0.02,
) -> list[dict]:
    """Compute points on the efficient frontier via parametric sweep.

    Uses a simple Monte Carlo approach (random weight sampling) to
    approximate the efficient frontier. For exact computation, use CVXPY.

    Args:
        expected_returns: Annualised expected returns, shape (n,).
        covariance_matrix: Annualised covariance matrix, shape (n, n).
        num_points: Number of random portfolios to generate.
        risk_free_rate: Annual risk-free rate for Sharpe computation.

    Returns:
        List of dicts with keys: ``return``, ``volatility``, ``sharpe``.
    """
    n = len(expected_returns)
    rng = np.random.default_rng(seed=42)
    points = []

    for _ in range(num_points):
        # Random weights (Dirichlet distribution for uniform simplex sampling)
        raw = rng.exponential(scale=1.0, size=n)
        w = raw / raw.sum()

        port_return = float(expected_returns @ w)
        port_vol = compute_portfolio_volatility(w, covariance_matrix)
        sharpe = compute_sharpe_ratio(port_return, port_vol, risk_free_rate)

        points.append(
            {
                "return": port_return,
                "volatility": port_vol,
                "sharpe": sharpe,
            }
        )

    # Sort by volatility for a cleaner frontier curve
    points.sort(key=lambda p: p["volatility"])
    return points


def annualise_returns(
    daily_returns: np.ndarray,
    trading_days: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualise a series of daily log returns.

    Args:
        daily_returns: 1-D array of daily log returns.
        trading_days: Number of trading days per year.

    Returns:
        Annualised return (geometric).
    """
    if len(daily_returns) == 0:
        return 0.0
    mean_daily = float(np.mean(daily_returns))
    return mean_daily * trading_days


def annualise_volatility(
    daily_returns: np.ndarray,
    trading_days: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualise the volatility of a series of daily log returns.

    Args:
        daily_returns: 1-D array of daily log returns.
        trading_days: Number of trading days per year.

    Returns:
        Annualised volatility.
    """
    if len(daily_returns) < 2:
        return 0.0
    daily_vol = float(np.std(daily_returns, ddof=1))
    return daily_vol * np.sqrt(trading_days)
