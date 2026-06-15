"""Constraint validation and normalisation for portfolio optimization.

Validates user-supplied constraints for logical consistency before
passing them to the CVXPY solver. Emits warnings for near-infeasible
configurations rather than hard-failing where possible.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.core.exceptions import ConstraintViolationError
from app.core.logging import get_logger


logger = get_logger(__name__)


def validate_constraints(
    request_params: dict[str, Any],
    tickers: list[str],
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
) -> tuple[dict[str, Any], list[str]]:
    """Validate and normalise optimization constraints.

    Args:
        request_params: Raw OptimizationRequest dict.
        tickers: Valid ticker symbols (after data fetch).
        expected_returns: Annualised expected returns, shape (n,).
        covariance_matrix: Annualised covariance matrix, shape (n, n).

    Returns:
        Tuple of (validated_constraints dict, list of warning strings).

    Raises:
        ConstraintViolationError: If constraints are logically impossible.
    """
    n = len(tickers)
    warnings: list[str] = []
    violated: list[str] = []

    max_weight = request_params.get("max_weight_per_asset")
    min_weight = request_params.get("min_weight_per_asset")
    min_return = request_params.get("min_return")
    max_volatility = request_params.get("max_volatility")
    sector_constraints = request_params.get("sector_constraints") or []

    # ── Check max_weight feasibility ──────────────────────────────────────────
    if max_weight is not None:
        min_required_weight = 1.0 / n
        if max_weight < min_required_weight:
            violated.append(
                f"max_weight_per_asset ({max_weight:.3f}) is less than 1/n "
                f"({min_required_weight:.3f}) — budget constraint cannot be satisfied."
            )

    # ── Check min_return feasibility ──────────────────────────────────────────
    if min_return is not None:
        max_achievable_return = float(np.max(expected_returns))
        if min_return > max_achievable_return:
            violated.append(
                f"min_return ({min_return:.3f}) exceeds the maximum achievable "
                f"return ({max_achievable_return:.3f}) in the asset universe."
            )
        elif min_return > 0.9 * max_achievable_return:
            warnings.append(
                f"min_return ({min_return:.3f}) is very close to the maximum "
                f"achievable return ({max_achievable_return:.3f}). "
                "The solver may struggle to find a feasible solution."
            )

    # ── Check max_volatility feasibility ─────────────────────────────────────
    if max_volatility is not None:
        # Minimum variance portfolio volatility (lower bound)
        try:
            inv_cov = np.linalg.inv(covariance_matrix)
            ones = np.ones(n)
            min_var = 1.0 / (ones @ inv_cov @ ones)
            min_vol = float(np.sqrt(max(min_var, 0.0)))
        except np.linalg.LinAlgError:
            min_vol = 0.0

        if max_volatility < min_vol:
            violated.append(
                f"max_volatility ({max_volatility:.3f}) is below the minimum "
                f"achievable portfolio volatility ({min_vol:.3f})."
            )
        elif max_volatility < 1.1 * min_vol:
            warnings.append(
                f"max_volatility ({max_volatility:.3f}) is very close to the "
                f"minimum achievable volatility ({min_vol:.3f}). "
                "The solver may produce a near-minimum-variance portfolio."
            )

    # ── Check sector constraint feasibility ───────────────────────────────────
    if sector_constraints:
        total_sector_limit = sum(sc.get("max_weight", 1.0) for sc in sector_constraints)
        # If all assets are covered by sector constraints and limits sum < 1
        # the budget constraint cannot be satisfied
        if total_sector_limit < 0.99:
            warnings.append(
                f"Sector weight limits sum to {total_sector_limit:.3f} < 1.0. "
                "If all assets belong to constrained sectors, full budget "
                "allocation may not be achievable."
            )

    # ── Raise if hard violations found ────────────────────────────────────────
    # ── Soft validation for the multi-objective matrix ──────────────────────────
    # Pydantic already enforces per-row types / ranges. Here we only flag
    # logical issues that can't be expressed in a schema (cross-row checks,
    # threshold vs. universe feasibility).
    raw_objectives = request_params.get("objectives") or []
    enabled_rows = [o for o in raw_objectives if o.get("enabled", True)]
    if enabled_rows:
        total_w = sum(float(o.get("weight", 0.0)) for o in enabled_rows)
        if total_w <= 0:
            violated.append(
                "All enabled objectives have weight 0 — at least one row "
                "must carry positive weight."
            )
        elif abs(total_w - 1.0) > 0.01:
            warnings.append(
                f"Objective weights sum to {total_w:.3f}; they will be "
                "renormalised to 1.0 before optimisation."
            )

        # Threshold sanity checks against the asset universe
        max_mu = float(np.max(expected_returns))
        for row in enabled_rows:
            name = row.get("name")
            thr = row.get("threshold")
            if thr is None:
                continue
            if name == "return" and row.get("direction") == "maximize" and thr > max_mu:
                violated.append(
                    f"Return threshold ({thr:.3f}) exceeds the maximum "
                    f"achievable return ({max_mu:.3f}) in the asset universe."
                )
            if name == "diversification_hhi":
                hhi_lo = 1.0 / n
                if row.get("direction") == "minimize" and thr < hhi_lo:
                    violated.append(
                        f"HHI threshold ({thr:.3f}) is below the theoretical "
                        f"minimum (1/n = {hhi_lo:.3f}) for {n} assets."
                    )

    if violated:
        raise ConstraintViolationError(
            message=(
                f"Found {len(violated)} constraint violation(s) that make the "
                "optimization problem infeasible."
            ),
            violated_constraints=violated,
        )

    # ── Build validated constraints dict ─────────────────────────────────────
    # ── Forward the multi-objective matrix ────────────────────────────────
    # The matrix is fully validated by Pydantic before reaching this layer
    # (see app.schemas.requests.OptimizationRequest). We re-emit it on the
    # validated dict so the classical optimizer can consume it directly
    # without re-parsing the raw request payload.
    objectives = request_params.get("objectives") or []
    frontier_cfg = request_params.get("frontier")

    validated: dict[str, Any] = {
        "max_weight_per_asset": max_weight,
        "min_weight_per_asset": min_weight,
        "min_return": min_return,
        "max_volatility": max_volatility,
        "sector_constraints": sector_constraints,
        "sector_map": {},  # Populated by data_fetch_node via state
        "objectives": objectives,
        "frontier": frontier_cfg,
    }

    logger.info(
        "constraints_validated",
        num_warnings=len(warnings),
        has_min_return=min_return is not None,
        has_max_volatility=max_volatility is not None,
        has_sector_constraints=bool(sector_constraints),
    )

    return validated, warnings
