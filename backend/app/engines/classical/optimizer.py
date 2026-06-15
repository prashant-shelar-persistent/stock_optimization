"""Markowitz Mean-Variance Optimization engine using CVXPY.

Implements the ``ClassicalOptimizer`` class which solves the portfolio
optimization problem:

    minimize   w^T Σ w  -  risk_tolerance * μ^T w
    subject to:
        sum(w) = 1                          (fully invested)
        w >= 0                              (long-only)
        w_i <= max_weight_per_asset         (exposure cap)
        μ^T w >= min_portfolio_return       (optional return floor)
        sum(w_j for j in sector) <= limit   (optional sector caps)

The objective blends variance minimisation with return maximisation via
the ``risk_tolerance`` parameter (0 = pure min-variance, 1 = pure max-return).

Solver cascade: CLARABEL → SCS → ECOS. If all solvers fail or return an
infeasible status, :class:`~app.core.exceptions.SolverInfeasibleError` is
raised with structured relaxation suggestions.

Usage::

    from app.engines.classical.optimizer import ClassicalOptimizer
    from app.engines.classical.schemas import (
        ClassicalOptimizationInput,
        OptimizationConstraints,
    )
    from app.core.config import get_settings

    optimizer = ClassicalOptimizer(settings=get_settings())
    result = optimizer.optimize(input_data)
    print(result.weights)
    print(result.sharpe_ratio)
"""

from __future__ import annotations

import time
from typing import Any

import cvxpy as cp
import numpy as np

from app.core.config import Settings, get_settings
from app.core.exceptions import SolverInfeasibleError
from app.core.logging import get_logger
from app.engines.classical.schemas import (
    ClassicalOptimizationInput,
    ClassicalOptimizationResult,
)


logger = get_logger(__name__)

# Minimum weight threshold — weights below this are treated as zero
_WEIGHT_THRESHOLD = 1e-4

# Ordered list of CVXPY solvers to try
_SOLVER_CASCADE = [cp.CLARABEL, cp.SCS, cp.ECOS]


class ClassicalOptimizer:
    """Markowitz Mean-Variance Optimizer backed by CVXPY.

    Attributes:
        settings: Application settings (used for ``RISK_FREE_RATE``).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialise the optimizer.

        Args:
            settings: Application settings. If ``None``, the global
                singleton from :func:`~app.core.config.get_settings` is used.
        """
        self.settings: Settings = settings or get_settings()

    # ── Public API ────────────────────────────────────────────────────────────

    def optimize(
        self,
        input_data: ClassicalOptimizationInput,
    ) -> ClassicalOptimizationResult:
        """Run Markowitz MVO and return the optimal portfolio.

        Args:
            input_data: Validated :class:`ClassicalOptimizationInput` containing
                tickers, expected returns, covariance matrix, sector tags, and
                optimization constraints.

        Returns:
            :class:`ClassicalOptimizationResult` with optimal weights, portfolio
            metrics, solver status, and solve time.

        Raises:
            SolverInfeasibleError: If no feasible solution can be found with
                the given constraints.
            ValueError: If input dimensions are inconsistent (caught by Pydantic
                validation before reaching this method).
        """
        tickers = input_data.tickers
        n = len(tickers)
        constraints = input_data.constraints

        # Convert to numpy arrays
        mu = np.asarray(input_data.expected_returns, dtype=float)
        sigma = np.asarray(input_data.cov_matrix, dtype=float)

        # Validate inputs before building the CVXPY problem
        self._validate_inputs(input_data, mu, sigma)

        start_time = time.perf_counter()

        # ── Decision variable ─────────────────────────────────────────────────
        w = cp.Variable(n, nonneg=True)

        # ── Objective ─────────────────────────────────────────────────────────
        # Blend variance minimisation with return maximisation.
        # risk_tolerance=0 → pure min-variance
        # risk_tolerance=1 → pure max-return (linear objective, may be unbounded
        #                     without a max_weight constraint — handled by solver)
        portfolio_variance = cp.quad_form(w, sigma)
        portfolio_return_expr = mu @ w

        # Scale: variance is O(σ²) ≈ 0.01–0.10; return is O(μ) ≈ 0.05–0.20.
        # We normalise by the trace of Σ so the two terms are comparable.
        sigma_scale = max(float(np.trace(sigma)), 1e-8)
        mu_scale = max(float(np.max(np.abs(mu))), 1e-8)

        objective = cp.Minimize(
            (1.0 - constraints.risk_tolerance) * portfolio_variance / sigma_scale
            - constraints.risk_tolerance * portfolio_return_expr / mu_scale
        )

        # ── Constraints ───────────────────────────────────────────────────────
        cvx_constraints: list[cp.Constraint] = [
            cp.sum(w) == 1.0,  # Fully invested
            w <= constraints.max_weight_per_asset,  # Exposure cap
        ]

        # Minimum portfolio return floor
        if constraints.min_portfolio_return is not None:
            cvx_constraints.append(
                portfolio_return_expr >= constraints.min_portfolio_return
            )

        # Sector allocation caps
        for sector_name, sector_limit in constraints.sector_limits.items():
            sector_indices = [
                i
                for i, ticker in enumerate(tickers)
                if input_data.sector_tags.get(ticker, "") == sector_name
            ]
            if sector_indices:
                cvx_constraints.append(
                    cp.sum(w[sector_indices]) <= sector_limit
                )
            else:
                logger.debug(
                    "sector_constraint_no_matching_tickers",
                    sector=sector_name,
                    tickers=tickers,
                )

        # ── Solve ─────────────────────────────────────────────────────────────
        problem = cp.Problem(objective, cvx_constraints)
        solver_used, solver_status = self._solve_with_cascade(problem)

        solve_time_ms = (time.perf_counter() - start_time) * 1000.0

        # ── Check feasibility ─────────────────────────────────────────────────
        if solver_status in (cp.INFEASIBLE, cp.INFEASIBLE_INACCURATE):
            raise SolverInfeasibleError(
                message=(
                    "The optimization problem is infeasible with the given constraints. "
                    "Try relaxing min_portfolio_return, max_weight_per_asset, or "
                    "sector limits."
                ),
                solver_status=solver_status,
                relaxation_suggestions=self._build_relaxation_suggestions(constraints),
            )

        if w.value is None:
            raise SolverInfeasibleError(
                message=(
                    f"Solver '{solver_used}' returned status '{solver_status}' "
                    "but no solution vector. The problem may be numerically ill-conditioned."
                ),
                solver_status=solver_status or "unknown",
                relaxation_suggestions=self._build_relaxation_suggestions(constraints),
            )

        # ── Post-process weights ───────────────────────────────────────────────
        weights_raw = np.maximum(w.value, 0.0)  # Clip tiny negatives
        weight_sum = weights_raw.sum()
        if weight_sum < 1e-10:
            raise SolverInfeasibleError(
                message="Solver returned an all-zero weight vector.",
                solver_status=solver_status or "unknown",
            )
        weights_raw = weights_raw / weight_sum  # Re-normalise to sum=1

        # Build weights dict (exclude near-zero weights)
        weights_dict: dict[str, float] = {
            tickers[i]: float(weights_raw[i])
            for i in range(n)
            if weights_raw[i] > _WEIGHT_THRESHOLD
        }

        # ── Compute portfolio metrics ──────────────────────────────────────────
        w_arr = weights_raw
        port_return = float(mu @ w_arr)
        port_variance_val = float(w_arr @ sigma @ w_arr)
        port_vol = float(np.sqrt(max(port_variance_val, 0.0)))
        risk_free_rate = self.settings.RISK_FREE_RATE
        sharpe = (
            (port_return - risk_free_rate) / port_vol
            if port_vol > 1e-10
            else 0.0
        )
        num_assets = sum(1 for v in weights_dict.values() if v > _WEIGHT_THRESHOLD)

        logger.info(
            "classical_optimization_complete",
            solver=solver_used,
            solver_status=solver_status,
            sharpe=round(sharpe, 4),
            expected_return=round(port_return, 4),
            volatility=round(port_vol, 4),
            num_assets=num_assets,
            solve_time_ms=round(solve_time_ms, 1),
        )

        return ClassicalOptimizationResult(
            weights=weights_dict,
            portfolio_return=port_return,
            portfolio_volatility=port_vol,
            sharpe_ratio=sharpe,
            solver_status=solver_status or "optimal",
            solve_time_ms=solve_time_ms,
            num_assets=num_assets,
            extra={
                "solver_used": solver_used,
                "objective_value": float(problem.value) if problem.value is not None else None,
                "risk_tolerance": constraints.risk_tolerance,
            },
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _validate_inputs(
        self,
        input_data: ClassicalOptimizationInput,
        mu: np.ndarray,
        sigma: np.ndarray,
    ) -> None:
        """Validate inputs before building the CVXPY problem.

        Args:
            input_data: The full input bundle.
            mu: Expected returns array, shape (n,).
            sigma: Covariance matrix, shape (n, n).

        Raises:
            ValueError: If n < 2, sigma is not square, or the max_weight
                constraint makes the budget constraint infeasible.
        """
        n = len(input_data.tickers)

        if n < 2:
            raise ValueError(
                f"At least 2 assets are required for optimization, got {n}."
            )

        if sigma.shape != (n, n):
            raise ValueError(
                f"Covariance matrix must be ({n}, {n}), got {sigma.shape}."
            )

        # Check that max_weight_per_asset allows the budget constraint to be met
        max_w = input_data.constraints.max_weight_per_asset
        min_required = 1.0 / n
        if max_w < min_required - 1e-8:
            raise ValueError(
                f"max_weight_per_asset ({max_w:.4f}) is less than 1/n "
                f"({min_required:.4f}). The budget constraint (sum(w)=1) "
                "cannot be satisfied."
            )

        # Check that the covariance matrix is positive semi-definite
        # (eigenvalues should all be >= 0)
        try:
            eigenvalues = np.linalg.eigvalsh(sigma)
            min_eigenvalue = float(np.min(eigenvalues))
            if min_eigenvalue < -1e-6:
                logger.warning(
                    "covariance_matrix_not_psd",
                    min_eigenvalue=min_eigenvalue,
                    message="Covariance matrix has negative eigenvalues; "
                    "numerical issues may occur.",
                )
        except np.linalg.LinAlgError:
            logger.warning("covariance_matrix_eigenvalue_check_failed")

    def _solve_with_cascade(
        self,
        problem: cp.Problem,
    ) -> tuple[str, str]:
        """Attempt to solve the problem using the solver cascade.

        Tries CLARABEL → SCS → ECOS in order. Returns on the first
        solver that does not raise an exception.

        Args:
            problem: The CVXPY problem to solve.

        Returns:
            Tuple of (solver_name, solver_status).

        Raises:
            SolverInfeasibleError: If all solvers fail with exceptions.
        """
        last_exc: Exception | None = None

        for solver in _SOLVER_CASCADE:
            try:
                problem.solve(solver=solver, verbose=False)
                solver_name = str(solver)
                solver_status = problem.status or "unknown"

                logger.debug(
                    "solver_attempt",
                    solver=solver_name,
                    status=solver_status,
                )

                # If the solver returned a definitive infeasible/unbounded status,
                # don't try the next solver — the problem itself is infeasible.
                if solver_status in (cp.INFEASIBLE, cp.INFEASIBLE_INACCURATE):
                    return solver_name, solver_status

                # If we got a solution (optimal or optimal_inaccurate), return it
                if solver_status in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
                    return solver_name, solver_status

                # For other statuses (e.g. "unbounded"), try the next solver
                logger.warning(
                    "solver_non_optimal_status",
                    solver=solver_name,
                    status=solver_status,
                )

            except Exception as exc:
                logger.warning(
                    "solver_exception",
                    solver=str(solver),
                    error=str(exc),
                )
                last_exc = exc
                continue

        # All solvers failed with exceptions
        raise SolverInfeasibleError(
            message=(
                f"All solvers ({', '.join(str(s) for s in _SOLVER_CASCADE)}) "
                f"failed. Last error: {last_exc}"
            ),
            solver_status="error",
            relaxation_suggestions=[
                "Check that the covariance matrix is positive semi-definite",
                "Reduce the number of constraints",
                "Increase max_weight_per_asset",
            ],
        )

    @staticmethod
    def _build_relaxation_suggestions(
        constraints: Any,
    ) -> list[str]:
        """Build human-readable relaxation suggestions for infeasible problems.

        Args:
            constraints: :class:`OptimizationConstraints` instance.

        Returns:
            List of suggestion strings.
        """
        suggestions: list[str] = []

        if constraints.min_portfolio_return is not None:
            suggestions.append(
                f"Decrease min_portfolio_return (currently {constraints.min_portfolio_return:.3f})"
            )

        if constraints.max_weight_per_asset < 0.5:
            suggestions.append(
                f"Increase max_weight_per_asset (currently {constraints.max_weight_per_asset:.3f})"
            )

        if constraints.sector_limits:
            suggestions.append(
                "Relax or remove sector_limits constraints"
            )

        if not suggestions:
            suggestions.append(
                "The problem may be numerically ill-conditioned — "
                "check that the covariance matrix is positive semi-definite"
            )

        return suggestions
