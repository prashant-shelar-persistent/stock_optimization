"""Classical optimization metrics and efficient frontier computation.

This module provides:

1. **Re-exports** of the core portfolio metrics functions from
   :mod:`app.data.metrics` for convenience.

2. **Efficient frontier computation** — generates a set of portfolios
   along the Pareto-optimal risk/return frontier by solving a sequence
   of CVXPY problems with varying minimum-return targets.

3. **Maximum Sharpe ratio portfolio** — finds the portfolio that
   maximises the Sharpe ratio using ``scipy.optimize.minimize`` with
   the SLSQP method.

Usage::

    from app.engines.classical.metrics import (
        compute_efficient_frontier,
        compute_max_sharpe_weights,
    )
    import numpy as np

    mu = np.array([0.12, 0.10, 0.09, 0.08, 0.07])
    sigma = ...  # (5, 5) covariance matrix

    # Efficient frontier
    frontier = compute_efficient_frontier(mu, sigma, n_points=30)
    for point in frontier:
        print(point["return"], point["volatility"], point["sharpe_ratio"])

    # Max-Sharpe portfolio
    weights = compute_max_sharpe_weights(mu, sigma, risk_free_rate=0.02)
"""

import warnings
from typing import Any

import cvxpy as cp
import numpy as np
from scipy.optimize import minimize

from app.core.logging import get_logger

# Re-export core metrics functions so callers can import from one place
from app.data.metrics import (  # noqa: F401
    PortfolioMetricsResult,
    annualise_returns,
    annualise_volatility,
    compute_cvar,
    compute_max_drawdown,
    compute_portfolio_metrics,
    compute_sharpe_ratio,
    compute_var,
)


logger = get_logger(__name__)

# Trading days per year
TRADING_DAYS_PER_YEAR = 252

# Minimum weight threshold for counting an asset as "included"
_WEIGHT_THRESHOLD = 1e-4


# ── Efficient Frontier ────────────────────────────────────────────────────────


def compute_efficient_frontier(
    expected_returns: np.ndarray,
    cov_matrix: np.ndarray,
    n_points: int = 50,
    risk_free_rate: float = 0.02,
    max_weight_per_asset: float = 1.0,
) -> list[dict[str, Any]]:
    """Compute points on the efficient frontier via parametric CVXPY sweep.

    Solves a sequence of minimum-variance problems with increasing minimum-
    return targets, tracing the upper boundary of the feasible risk/return
    space. Each point on the frontier is Pareto-optimal: no other portfolio
    achieves the same return with lower volatility.

    Args:
        expected_returns: Annualised expected returns, shape (n,).
        cov_matrix: Annualised covariance matrix, shape (n, n).
        n_points: Number of frontier points to compute. More points give a
            smoother curve but take longer. Defaults to 50.
        risk_free_rate: Annual risk-free rate for Sharpe ratio computation.
            Defaults to 0.02.
        max_weight_per_asset: Maximum weight for any single asset. Defaults
            to 1.0 (unconstrained). Set to e.g. 0.4 to match the optimizer.

    Returns:
        List of dicts, each with keys:
            - ``"return"``: Annualised expected portfolio return (float).
            - ``"volatility"``: Annualised portfolio volatility (float).
            - ``"sharpe_ratio"``: Sharpe ratio (float).
            - ``"weights"``: Dict of ticker-index → weight (dict[int, float]).
              Note: keys are integer indices, not ticker symbols, because
              this function does not receive ticker names.
        Points are sorted by volatility (ascending).

    Notes:
        - Points where the CVXPY solver fails are silently skipped.
        - The minimum-variance portfolio (no return constraint) is always
          included as the first point.
        - The maximum-return portfolio (100% in the highest-return asset)
          is always included as the last point.
    """
    n = len(expected_returns)
    mu = np.asarray(expected_returns, dtype=float)
    sigma = np.asarray(cov_matrix, dtype=float)

    if n < 2:
        logger.warning("efficient_frontier_too_few_assets", n=n)
        return []

    # Determine the return range for the sweep
    # Min return: minimum-variance portfolio return
    # Max return: maximum achievable return (best single asset)
    min_return_achievable = float(np.min(mu))
    max_return_achievable = float(np.max(mu))

    if max_return_achievable <= min_return_achievable:
        logger.warning(
            "efficient_frontier_degenerate_returns",
            min_return=min_return_achievable,
            max_return=max_return_achievable,
        )
        return []

    # Generate target return levels (linear spacing from min to max)
    target_returns = np.linspace(min_return_achievable, max_return_achievable, n_points)

    points: list[dict[str, Any]] = []

    for target_return in target_returns:
        point = _solve_min_variance_for_return(
            mu=mu,
            sigma=sigma,
            target_return=float(target_return),
            max_weight_per_asset=max_weight_per_asset,
            risk_free_rate=risk_free_rate,
        )
        if point is not None:
            points.append(point)

    # Sort by volatility (ascending) for a clean frontier curve
    points.sort(key=lambda p: p["volatility"])

    logger.info(
        "efficient_frontier_computed",
        n_points_requested=n_points,
        n_points_computed=len(points),
    )

    return points


def _solve_min_variance_for_return(
    mu: np.ndarray,
    sigma: np.ndarray,
    target_return: float,
    max_weight_per_asset: float,
    risk_free_rate: float,
) -> dict[str, Any] | None:
    """Solve a single minimum-variance problem with a return constraint.

    Args:
        mu: Expected returns array, shape (n,).
        sigma: Covariance matrix, shape (n, n).
        target_return: Minimum portfolio return constraint.
        max_weight_per_asset: Maximum weight per asset.
        risk_free_rate: Risk-free rate for Sharpe computation.

    Returns:
        Dict with ``return``, ``volatility``, ``sharpe_ratio``, ``weights``
        keys, or ``None`` if the problem is infeasible or the solver fails.
    """
    n = len(mu)
    w = cp.Variable(n, nonneg=True)

    objective = cp.Minimize(cp.quad_form(w, sigma))
    constraints: list[cp.Constraint] = [
        cp.sum(w) == 1.0,
        w <= max_weight_per_asset,
        mu @ w >= target_return,
    ]

    problem = cp.Problem(objective, constraints)

    try:
        problem.solve(solver=cp.CLARABEL, verbose=False)
    except Exception:
        try:
            problem.solve(solver=cp.SCS, verbose=False)
        except Exception:
            return None

    if problem.status not in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
        return None

    if w.value is None:
        return None

    weights_raw = np.maximum(w.value, 0.0)
    weight_sum = weights_raw.sum()
    if weight_sum < 1e-10:
        return None
    weights_raw = weights_raw / weight_sum

    port_return = float(mu @ weights_raw)
    port_variance = float(weights_raw @ sigma @ weights_raw)
    port_vol = float(np.sqrt(max(port_variance, 0.0)))
    sharpe = (
        (port_return - risk_free_rate) / port_vol
        if port_vol > 1e-10
        else 0.0
    )

    weights_dict = {
        i: float(weights_raw[i])
        for i in range(n)
        if weights_raw[i] > _WEIGHT_THRESHOLD
    }

    return {
        "return": port_return,
        "volatility": port_vol,
        "sharpe_ratio": sharpe,
        "weights": weights_dict,
    }


# ── Maximum Sharpe Ratio Portfolio ────────────────────────────────────────────


def compute_max_sharpe_weights(
    expected_returns: np.ndarray,
    cov_matrix: np.ndarray,
    risk_free_rate: float = 0.02,
    max_weight_per_asset: float = 1.0,
) -> np.ndarray:
    """Find portfolio weights that maximise the Sharpe ratio.

    Uses ``scipy.optimize.minimize`` with the SLSQP method to solve:

        maximise  (w^T μ - r_f) / sqrt(w^T Σ w)
        subject to:
            sum(w) = 1
            w >= 0
            w_i <= max_weight_per_asset

    The Sharpe ratio is maximised by minimising its negative.

    Args:
        expected_returns: Annualised expected returns, shape (n,).
        cov_matrix: Annualised covariance matrix, shape (n, n).
        risk_free_rate: Annual risk-free rate. Defaults to 0.02.
        max_weight_per_asset: Maximum weight for any single asset.
            Defaults to 1.0 (unconstrained).

    Returns:
        Optimal weight vector, shape (n,). Weights sum to 1.0.
        Falls back to equal weights if the optimisation fails.

    Notes:
        - Multiple random starting points are tried to avoid local optima.
        - The result is the best solution found across all starting points.
    """
    mu = np.asarray(expected_returns, dtype=float)
    sigma = np.asarray(cov_matrix, dtype=float)
    n = len(mu)

    if n < 2:
        return np.ones(n) / n

    def neg_sharpe(w: np.ndarray) -> float:
        """Negative Sharpe ratio (to be minimised)."""
        port_return = float(mu @ w)
        port_variance = float(w @ sigma @ w)
        port_vol = float(np.sqrt(max(port_variance, 1e-12)))
        return -(port_return - risk_free_rate) / port_vol

    def neg_sharpe_grad(w: np.ndarray) -> np.ndarray:
        """Analytical gradient of the negative Sharpe ratio."""
        port_return = float(mu @ w)
        port_variance = float(w @ sigma @ w)
        port_vol = float(np.sqrt(max(port_variance, 1e-12)))
        excess_return = port_return - risk_free_rate

        # d/dw [ -(μ^T w - r_f) / sqrt(w^T Σ w) ]
        # = -[ μ * port_vol - excess_return * (Σ w / port_vol) ] / port_variance
        sigma_w = sigma @ w
        grad = -(mu * port_vol - excess_return * sigma_w / port_vol) / port_variance
        return grad

    # Constraints: sum(w) = 1
    eq_constraint = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}

    # Bounds: 0 <= w_i <= max_weight_per_asset
    bounds = [(0.0, max_weight_per_asset)] * n

    best_result = None
    best_sharpe = -np.inf

    # Try multiple starting points for robustness
    rng = np.random.default_rng(seed=42)
    starting_points = _generate_starting_points(n, max_weight_per_asset, rng, num=10)

    for w0 in starting_points:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                result = minimize(
                    neg_sharpe,
                    w0,
                    jac=neg_sharpe_grad,
                    method="SLSQP",
                    bounds=bounds,
                    constraints=[eq_constraint],
                    options={"ftol": 1e-9, "maxiter": 1000, "disp": False},
                )

            if result.success and result.fun < best_sharpe:
                # Verify the solution is feasible
                w_opt = np.maximum(result.x, 0.0)
                w_opt = w_opt / w_opt.sum()
                if np.all(w_opt <= max_weight_per_asset + 1e-6):
                    best_sharpe = result.fun
                    best_result = w_opt

        except Exception as exc:
            logger.debug("max_sharpe_starting_point_failed", error=str(exc))
            continue

    if best_result is None:
        logger.warning(
            "max_sharpe_optimization_failed",
            message="All starting points failed; returning equal weights.",
        )
        return np.ones(n) / n

    # Final normalisation
    best_result = np.maximum(best_result, 0.0)
    best_result = best_result / best_result.sum()

    logger.info(
        "max_sharpe_optimization_complete",
        sharpe=round(-best_sharpe, 4),
        num_assets=int(np.sum(best_result > _WEIGHT_THRESHOLD)),
    )

    return best_result


def _generate_starting_points(
    n: int,
    max_weight: float,
    rng: np.random.Generator,
    num: int = 10,
) -> list[np.ndarray]:
    """Generate diverse starting points for the Sharpe maximisation.

    Args:
        n: Number of assets.
        max_weight: Maximum weight per asset.
        rng: NumPy random generator.
        num: Number of starting points to generate.

    Returns:
        List of weight vectors, each summing to 1.0.
    """
    points: list[np.ndarray] = []

    # Equal weights
    points.append(np.ones(n) / n)

    # Random Dirichlet samples (uniform on the simplex)
    for _ in range(num - 1):
        raw = rng.exponential(scale=1.0, size=n)
        w = raw / raw.sum()
        # Clip to max_weight and re-normalise
        w = np.minimum(w, max_weight)
        w_sum = w.sum()
        if w_sum > 1e-10:
            w = w / w_sum
        else:
            w = np.ones(n) / n
        points.append(w)

    return points


# ── Convenience wrapper ───────────────────────────────────────────────────────


def compute_portfolio_volatility(
    weights: np.ndarray,
    cov_matrix: np.ndarray,
) -> float:
    """Compute annualised portfolio volatility from weights and covariance.

    Args:
        weights: Portfolio weight vector, shape (n,).
        cov_matrix: Annualised covariance matrix, shape (n, n).

    Returns:
        Annualised portfolio volatility (standard deviation).
    """
    w = np.asarray(weights, dtype=float)
    sigma = np.asarray(cov_matrix, dtype=float)
    variance = float(w @ sigma @ w)
    return float(np.sqrt(max(variance, 0.0)))
