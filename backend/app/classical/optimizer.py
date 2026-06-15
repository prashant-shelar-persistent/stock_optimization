"""Markowitz Mean-Variance Optimization via CVXPY.

Solves the classic portfolio optimization problem:
    maximize  w^T μ - λ * w^T Σ w
    subject to:
        sum(w) = 1
        w >= 0
        (optional) w_i <= max_weight_per_asset
        (optional) w_i >= min_weight_per_asset  for selected assets
        (optional) sector weights <= sector limits
        (optional) portfolio return >= min_return
        (optional) portfolio volatility <= max_volatility
        (optional) per-objective hard thresholds (e.g. HHI ≤ 0.5)

Multi-objective extension (Phase 2)
-----------------------------------
When ``constraints["objectives"]`` is a non-empty list of validated
``BusinessObjective`` payloads, the optimiser builds a *scalarised*
weighted-sum objective from the enabled rows::

    maximise   Σ wᵢ · sign(directionᵢ) · normalisedᵢ(w)

where each measure is rescaled to a comparable order-of-magnitude
(see ``_measure_expression``).  Objectives that have a ``threshold``
become hard CVXPY constraints (``≥`` for maximise, ``≤`` for minimise).

Convex measures supported in the inner CVXPY problem
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    - ``return``                 — μᵀw                              (linear)
    - ``volatility``             — sqrt(wᵀΣw)                       (convex)
    - ``sharpe``                 — proxied by  μᵀw − λ·wᵀΣw          (convex)
    - ``diversification_hhi``    — Σ wᵢ²                             (convex, minimise)
    - ``sector_concentration``   — Σ_s (Σ_{i∈s} wᵢ)²                 (convex, minimise)

Non-convex / data-dependent measures
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    - ``max_drawdown`` and ``esg_score`` are accepted in the request
      payload (so they round-trip through the UI and LLM commentary)
      but are *not* applied inside the convex solve — they require
      out-of-sample simulation / external data and are scheduled for
      a future iteration.  A constraint-warning is recorded.

Back-compat
-----------
When ``constraints["objectives"]`` is empty or missing, the optimiser
behaves exactly as the original Markowitz MVO implementation:
``maximise  μᵀw − wᵀΣw`` subject to the scalar ``min_return`` /
``max_volatility`` constraints.

Usage::

    from app.classical.optimizer import run_markowitz_mvo

    result = run_markowitz_mvo(
        tickers=["AAPL", "MSFT", "GOOGL"],
        expected_returns=np.array([0.12, 0.10, 0.09]),
        covariance_matrix=cov,
        budget=100_000.0,
        constraints={},
    )
"""

from __future__ import annotations

import time
from typing import Any

import cvxpy as cp
import numpy as np

from app.core.config import get_settings
from app.core.exceptions import SolverInfeasibleError
from app.core.logging import get_logger
from app.schemas.responses import AssetWeight, ClassicalResult, PortfolioMetrics


logger = get_logger(__name__)

TRADING_DAYS_PER_YEAR = 252

# ── Measure registry ──────────────────────────────────────────────────────────
# Names that the convex inner loop knows how to handle.
_CONVEX_MEASURES: frozenset[str] = frozenset({
    "return",
    "volatility",
    "sharpe",
    "diversification_hhi",
    "sector_concentration",
})

# Names accepted in the schema but not applied inside the CVXPY solve
# (they are still surfaced in the LLM explanation / round-tripped to the UI).
_DEFERRED_MEASURES: frozenset[str] = frozenset({
    "max_drawdown",
    "esg_score",
})


def _normalise_weights(objectives: list[dict[str, Any]]) -> dict[str, float]:
    """Return a {name: weight} map for enabled rows, normalised to sum to 1.

    If the total of enabled weights is zero we degenerate to an equal
    split — this can only happen when all enabled rows have ``weight=0``
    (which Pydantic already rejects upstream), so the fallback exists
    purely for defensive arithmetic.
    """
    enabled = [o for o in objectives if o.get("enabled", True)]
    if not enabled:
        return {}
    total = sum(float(o.get("weight", 0.0)) for o in enabled)
    if total <= 0:
        n = len(enabled)
        return {str(o["name"]): 1.0 / n for o in enabled}
    return {
        str(o["name"]): float(o.get("weight", 0.0)) / total
        for o in enabled
    }


def _measure_expression(
    name: str,
    w: cp.Variable,
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    sector_indices_by_name: dict[str, list[int]],
) -> tuple[cp.Expression, float]:
    """Return (cvxpy_expression, typical_scale) for a measure name.

    The returned expression is in the "natural" direction of the measure
    (e.g. higher return = higher value, higher volatility = higher value).
    The optimiser then flips its sign based on the row's ``direction``.

    ``typical_scale`` is a positive float used to bring measures to a
    comparable order-of-magnitude in the weighted sum.  It is computed
    from the data so the same weights produce sensible trade-offs across
    different universes.
    """
    if name == "return":
        # Annualised return is typically O(0.1)
        scale = max(float(np.max(np.abs(expected_returns))), 1e-6)
        return expected_returns @ w, scale

    if name == "volatility":
        # Use the matrix square root so the expression is the true
        # portfolio standard deviation (convex in w).  Add a tiny
        # regularisation to keep the Cholesky factor PSD even when the
        # input has zero eigenvalues from floating-point noise.
        diag = np.diag(covariance_matrix)
        scale = float(np.sqrt(max(np.max(diag), 1e-12)))
        reg = covariance_matrix + 1e-10 * np.eye(covariance_matrix.shape[0])
        try:
            sqrt_cov = np.linalg.cholesky(reg)
        except np.linalg.LinAlgError:
            # Fall back to symmetric eigen sqrt if Cholesky fails
            eigvals, eigvecs = np.linalg.eigh(reg)
            eigvals = np.maximum(eigvals, 0.0)
            sqrt_cov = eigvecs @ np.diag(np.sqrt(eigvals)) @ eigvecs.T
        return cp.norm(sqrt_cov @ w, 2), scale

    if name == "sharpe":
        # Sharpe maximisation is non-convex; use the canonical convex
        # proxy: return − λ·variance with λ derived from the universe so
        # the two terms are O(1).
        scale = max(float(np.max(np.abs(expected_returns))), 1e-6)
        variance = cp.quad_form(w, cp.psd_wrap(covariance_matrix))
        # Choose λ so that the variance term has the same order as return
        lam = float(scale / max(np.trace(covariance_matrix) / len(expected_returns), 1e-9))
        return expected_returns @ w - lam * variance, scale

    if name == "diversification_hhi":
        # Herfindahl–Hirschman index: lower = more diversified.
        return cp.sum_squares(w), 1.0

    if name == "sector_concentration":
        if not sector_indices_by_name:
            return cp.sum_squares(w), 1.0  # behaves like HHI when no map
        return cp.sum(
            cp.hstack([
                cp.sum(w[idxs]) ** 2
                for idxs in sector_indices_by_name.values()
                if idxs
            ])
        ), 1.0

    raise ValueError(f"Unsupported convex measure '{name}'")


def _build_scalar_objective(
    objectives: list[dict[str, Any]],
    w: cp.Variable,
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    sector_indices_by_name: dict[str, list[int]],
) -> tuple[cp.Expression, list[cp.Constraint], list[str]]:
    """Return (objective_expression, threshold_constraints, deferred_warnings).

    The objective is always cast in "maximise" form — the caller wraps
    it with ``cp.Maximize``.  Each row of the matrix contributes::

        weight · sign(direction) · expression / scale

    Threshold rows are converted to hard CVXPY constraints.  Rows whose
    measure is in ``_DEFERRED_MEASURES`` are skipped (with a warning).
    """
    norm_weights = _normalise_weights(objectives)
    if not norm_weights:
        # No enabled rows — caller should fall back to the legacy objective.
        return cp.Constant(0.0), [], []

    objective_terms: list[cp.Expression] = []
    threshold_constraints: list[cp.Constraint] = []
    deferred_warnings: list[str] = []

    for row in objectives:
        if not row.get("enabled", True):
            continue
        name = str(row["name"])
        direction = str(row.get("direction", "maximize"))
        weight = norm_weights[name]
        threshold = row.get("threshold")

        if name in _DEFERRED_MEASURES:
            deferred_warnings.append(
                f"Objective '{name}' is accepted but not yet applied inside "
                "the convex solver. It is only surfaced in commentary."
            )
            continue

        if name not in _CONVEX_MEASURES:
            deferred_warnings.append(
                f"Unknown objective '{name}' — ignored by the optimiser."
            )
            continue

        expr, scale = _measure_expression(
            name,
            w,
            expected_returns,
            covariance_matrix,
            sector_indices_by_name,
        )

        # Normalise the expression to O(1) magnitude using the data scale
        signed = expr / scale if scale > 0 else expr
        if direction == "minimize":
            signed = -signed
        objective_terms.append(weight * signed)

        # Hard threshold → CVXPY constraint
        if threshold is not None:
            if direction == "maximize":
                # raw expression must be ≥ threshold
                threshold_constraints.append(expr >= float(threshold))
            else:
                threshold_constraints.append(expr <= float(threshold))

    if not objective_terms:
        return cp.Constant(0.0), threshold_constraints, deferred_warnings

    return cp.sum(cp.hstack(objective_terms)), threshold_constraints, deferred_warnings


def _build_sector_indices(
    tickers: list[str],
    sector_map: dict[str, str],
) -> dict[str, list[int]]:
    """Group ticker indices by sector name."""
    result: dict[str, list[int]] = {}
    for i, t in enumerate(tickers):
        sector = sector_map.get(t, "")
        if not sector:
            continue
        result.setdefault(sector, []).append(i)
    return result


def run_markowitz_mvo(
    tickers: list[str],
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    budget: float,
    constraints: dict[str, Any],
) -> ClassicalResult:
    """Run Markowitz Mean-Variance Optimization.

    Args:
        tickers: Asset ticker symbols.
        expected_returns: Annualised expected returns, shape (n,).
        covariance_matrix: Annualised covariance matrix, shape (n, n).
        budget: Total investment budget in USD.
        constraints: Validated constraint dict from constraint_validation_node.

    Returns:
        ClassicalResult with weights, metrics, and solver metadata.

    Raises:
        SolverInfeasibleError: If CVXPY cannot find a feasible solution.
    """
    n = len(tickers)
    settings = get_settings()
    risk_free_rate = settings.RISK_FREE_RATE

    start_time = time.perf_counter()

    sector_map: dict[str, str] = constraints.get("sector_map", {}) or {}
    sector_indices_by_name = _build_sector_indices(tickers, sector_map)

    # ── Decision variable ────────────────────────────────────────────────
    w = cp.Variable(n, nonneg=True)

    # ── Constraints ──────────────────────────────────────────────────────
    cvx_constraints: list[cp.Constraint] = [
        cp.sum(w) == 1.0,  # Fully invested
    ]

    # Max weight per asset
    max_weight = constraints.get("max_weight_per_asset")
    if max_weight is not None:
        cvx_constraints.append(w <= max_weight)

    # Legacy scalar Min return constraint
    min_return = constraints.get("min_return")
    portfolio_return = expected_returns @ w
    if min_return is not None:
        cvx_constraints.append(portfolio_return >= min_return)

    # Legacy scalar Max volatility constraint
    max_volatility = constraints.get("max_volatility")
    portfolio_variance = cp.quad_form(w, cp.psd_wrap(covariance_matrix))
    if max_volatility is not None:
        cvx_constraints.append(portfolio_variance <= max_volatility ** 2)

    # Sector constraints
    sector_constraints = constraints.get("sector_constraints", []) or []
    for sc in sector_constraints:
        sector_name = sc.get("sector", "")
        max_sector_weight = sc.get("max_weight", 1.0)
        sector_indices = sector_indices_by_name.get(sector_name, [])
        if sector_indices:
            cvx_constraints.append(
                cp.sum(w[sector_indices]) <= max_sector_weight
            )

    # ── Objective ────────────────────────────────────────────────────────
    objectives: list[dict[str, Any]] = constraints.get("objectives") or []
    deferred_warnings: list[str] = []

    if any(o.get("enabled", True) for o in objectives):
        # Multi-objective scalarised path
        scalar_expr, threshold_constraints, deferred_warnings = (
            _build_scalar_objective(
                objectives=objectives,
                w=w,
                expected_returns=expected_returns,
                covariance_matrix=covariance_matrix,
                sector_indices_by_name=sector_indices_by_name,
            )
        )
        cvx_constraints.extend(threshold_constraints)
        objective = cp.Maximize(scalar_expr)
        logger.info(
            "classical_objective_built",
            mode="multi_objective",
            num_objectives=sum(1 for o in objectives if o.get("enabled", True)),
            num_thresholds=len(threshold_constraints),
            num_deferred=len(deferred_warnings),
        )
    else:
        # Legacy Markowitz objective (unchanged behaviour)
        objective = cp.Maximize(portfolio_return - portfolio_variance)
        logger.info("classical_objective_built", mode="legacy_markowitz")

    # ── Solve ────────────────────────────────────────────────────────────
    problem = cp.Problem(objective, cvx_constraints)

    try:
        problem.solve(solver=cp.CLARABEL, verbose=False)
    except Exception as exc:
        logger.warning("cvxpy_primary_solver_failed", error=str(exc))
        try:
            problem.solve(solver=cp.SCS, verbose=False)
        except Exception as exc2:
            raise SolverInfeasibleError(
                message=f"All solvers failed: {exc2}",
                solver_status="error",
            ) from exc2

    solve_time_ms = (time.perf_counter() - start_time) * 1000

    if problem.status in (cp.INFEASIBLE, cp.INFEASIBLE_INACCURATE):
        raise SolverInfeasibleError(
            message=(
                "The optimization problem is infeasible with the given constraints. "
                "Try relaxing min_return, max_volatility, objective thresholds, "
                "or sector limits."
            ),
            solver_status=problem.status or "infeasible",
            relaxation_suggestions=[
                "Increase max_volatility",
                "Decrease min_return",
                "Increase max_weight_per_asset",
                "Relax sector constraints",
                "Relax objective thresholds",
            ],
        )

    if w.value is None:
        raise SolverInfeasibleError(
            message="Solver returned no solution.",
            solver_status=problem.status or "unknown",
        )

    weights_raw = np.maximum(w.value, 0.0)  # Clip tiny negatives from numerical noise
    weights_raw = weights_raw / weights_raw.sum()  # Re-normalise

    # ── Build result ─────────────────────────────────────────────────────
    asset_weights = [
        AssetWeight(
            ticker=tickers[i],
            weight=float(weights_raw[i]),
            allocation=float(weights_raw[i] * budget),
            sector=sector_map.get(tickers[i]),
        )
        for i in range(n)
        if weights_raw[i] > 1e-4  # Exclude near-zero weights
    ]

    # Recompute metrics from final weights
    w_arr = weights_raw
    port_return = float(expected_returns @ w_arr)
    port_variance = float(w_arr @ covariance_matrix @ w_arr)
    port_vol = float(np.sqrt(port_variance))
    sharpe = (port_return - risk_free_rate) / port_vol if port_vol > 0 else 0.0

    metrics = PortfolioMetrics(
        expected_return=port_return,
        volatility=port_vol,
        sharpe_ratio=sharpe,
        num_assets=len(asset_weights),
    )

    if deferred_warnings:
        logger.info(
            "classical_objective_deferred_measures",
            deferred=deferred_warnings,
        )

    logger.info(
        "classical_optimization_complete",
        sharpe=round(sharpe, 4),
        expected_return=round(port_return, 4),
        volatility=round(port_vol, 4),
        num_assets=len(asset_weights),
        solve_time_ms=round(solve_time_ms, 1),
    )

    return ClassicalResult(
        weights=asset_weights,
        metrics=metrics,
        solver_status=problem.status or "optimal",
        solve_time_ms=solve_time_ms,
    )
