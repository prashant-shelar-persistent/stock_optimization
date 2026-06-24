"""Efficient-frontier sweep via the epsilon-constraint method.

Given two user-selected measures (e.g. volatility on X, return on Y),
this module traces the Pareto frontier by parametrically sweeping one
measure across a grid of levels and optimising the other at each level.

Algorithm (epsilon-constraint)
------------------------------
1. Solve two anchor portfolios:
     - min-X portfolio:  minimise x_measure(w)  (subject to base constraints)
     - max-Y portfolio:  maximise y_measure(w)  (subject to base constraints)
   Their X-values bracket the feasible frontier range [x_min, x_max].
2. Build a grid of ``num_points`` levels ε ∈ [x_min, x_max].
3. For each ε, solve::
        maximise   y_measure(w)
        s.t.       x_measure(w) ≤ ε     (if x is "minimize" direction)
                   sum(w) = 1,  w ≥ 0,  + base constraints (max_weight, sector …)
4. Filter out dominated / infeasible points.
5. Locate the knee point via the maximum-curvature heuristic on the
   normalised frontier.
6. Tag the max-Sharpe and min-risk reference indices.

The function returns a ``FrontierReport`` ready to serialise to JSON
and persist on the optimization run.

Supported measures in this iteration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The same five convex measures the main optimiser supports:
``return``, ``volatility``, ``sharpe``, ``diversification_hhi``,
``sector_concentration``.  Non-convex measures (``max_drawdown``,
``esg_score``) raise ``ValueError`` — the caller should validate
this before invoking the sweep.
"""

import time
from typing import Any, Callable

import cvxpy as cp
import numpy as np

from app.core.logging import get_logger
from app.schemas.responses import (
    AssetWeight,
    FrontierPoint,
    FrontierReport,
)


logger = get_logger(__name__)


# Convex measures supported by the sweep.  Mirrors optimizer._CONVEX_MEASURES
# but keeps a local copy so the two modules stay decoupled.
_FRONTIER_MEASURES: frozenset[str] = frozenset({
    "return",
    "volatility",
    "sharpe",
    "diversification_hhi",
    "sector_concentration",
})

# Natural optimisation direction of each measure (the UI may override
# per-row, but the sweep itself uses these as defaults).
_NATURAL_DIRECTION: dict[str, str] = {
    "return": "maximize",
    "volatility": "minimize",
    "sharpe": "maximize",
    "diversification_hhi": "minimize",
    "sector_concentration": "minimize",
}


# ── Measure expression builders ───────────────────────────────────────────────


def _measure_expr(
    name: str,
    w: cp.Variable,
    mu: np.ndarray,
    cov: np.ndarray,
    sector_indices_by_name: dict[str, list[int]],
    risk_free_rate: float = 0.0,
) -> cp.Expression:
    """Build a CVXPY expression for a measure.

    All expressions are returned in their natural "raw" form (no sign flip).
    The sweep loop applies sign flips based on direction.
    """
    if name == "return":
        return mu @ w
    if name == "volatility":
        reg = cov + 1e-10 * np.eye(cov.shape[0])
        try:
            sqrt_cov = np.linalg.cholesky(reg)
        except np.linalg.LinAlgError:
            eigvals, eigvecs = np.linalg.eigh(reg)
            eigvals = np.maximum(eigvals, 0.0)
            sqrt_cov = eigvecs @ np.diag(np.sqrt(eigvals)) @ eigvecs.T
        return cp.norm(sqrt_cov @ w, 2)
    if name == "sharpe":
        # Use the convex proxy (return − λ·variance) — not the true Sharpe.
        # The sweep treats this as "expected reward at given risk budget".
        scale = max(float(np.max(np.abs(mu))), 1e-6)
        lam = float(scale / max(np.trace(cov) / len(mu), 1e-9))
        return mu @ w - lam * cp.quad_form(w, cp.psd_wrap(cov))
    if name == "diversification_hhi":
        return cp.sum_squares(w)
    if name == "sector_concentration":
        if not sector_indices_by_name:
            return cp.sum_squares(w)
        return cp.sum(
            cp.hstack([
                cp.sum(w[idxs]) ** 2
                for idxs in sector_indices_by_name.values()
                if idxs
            ])
        )
    raise ValueError(f"Unsupported frontier measure '{name}'")


def _evaluate_raw(
    name: str,
    w_val: np.ndarray,
    mu: np.ndarray,
    cov: np.ndarray,
    sector_indices_by_name: dict[str, list[int]],
) -> float:
    """Evaluate a measure on a concrete weight vector (numpy, not CVXPY)."""
    if name == "return":
        return float(mu @ w_val)
    if name == "volatility":
        return float(np.sqrt(max(w_val @ cov @ w_val, 0.0)))
    if name == "sharpe":
        ret = float(mu @ w_val)
        vol = float(np.sqrt(max(w_val @ cov @ w_val, 0.0)))
        return ret / vol if vol > 1e-12 else 0.0
    if name == "diversification_hhi":
        return float(np.sum(w_val ** 2))
    if name == "sector_concentration":
        if not sector_indices_by_name:
            return float(np.sum(w_val ** 2))
        return float(sum(
            (w_val[idxs].sum()) ** 2
            for idxs in sector_indices_by_name.values() if idxs
        ))
    raise ValueError(f"Unsupported frontier measure '{name}'")


# ── Anchor solves ─────────────────────────────────────────────────────────────


def _solve_extreme(
    direction: str,
    measure_name: str,
    n: int,
    base_constraints_fn: Callable[[cp.Variable], list[cp.Constraint]],
    mu: np.ndarray,
    cov: np.ndarray,
    sector_indices_by_name: dict[str, list[int]],
) -> tuple[np.ndarray | None, str]:
    """Solve a single-objective extreme: min or max of one measure."""
    w = cp.Variable(n, nonneg=True)
    expr = _measure_expr(measure_name, w, mu, cov, sector_indices_by_name)
    objective = cp.Minimize(expr) if direction == "minimize" else cp.Maximize(expr)
    problem = cp.Problem(objective, base_constraints_fn(w))
    try:
        problem.solve(solver=cp.CLARABEL, verbose=False)
    except Exception:
        try:
            problem.solve(solver=cp.SCS, verbose=False)
        except Exception as exc:
            logger.warning("frontier_anchor_failed", measure=measure_name, error=str(exc))
            return None, "error"

    if problem.status in (cp.INFEASIBLE, cp.INFEASIBLE_INACCURATE) or w.value is None:
        return None, problem.status or "infeasible"
    w_val = np.maximum(w.value, 0.0)
    s = w_val.sum()
    if s > 0:
        w_val = w_val / s
    return w_val, problem.status or "optimal"


# ── Knee point detection ──────────────────────────────────────────────────────


def _find_knee(points: list[FrontierPoint]) -> int | None:
    """Return the index of the maximum-curvature point on the frontier.

    Uses the standard "distance from chord" heuristic: project each point
    onto the line joining the two extremes, and pick the point with the
    greatest perpendicular distance.  Works regardless of the directions
    of the two axes because we operate on normalised coordinates.
    """
    if len(points) < 3:
        return None

    xs = np.array([p.x for p in points], dtype=float)
    ys = np.array([p.y for p in points], dtype=float)

    # Normalise to [0, 1] so curvature is direction-independent
    def _norm(arr: np.ndarray) -> np.ndarray:
        lo, hi = float(arr.min()), float(arr.max())
        rng = hi - lo
        return (arr - lo) / rng if rng > 1e-12 else np.zeros_like(arr)

    x_n = _norm(xs)
    y_n = _norm(ys)

    # Chord from first to last (assumes sorted along x — caller ensures this)
    x0, y0 = x_n[0], y_n[0]
    x1, y1 = x_n[-1], y_n[-1]
    chord_len = np.hypot(x1 - x0, y1 - y0)
    if chord_len < 1e-12:
        return None

    # Perpendicular distance from each point to the chord
    distances = np.abs(
        (y1 - y0) * x_n - (x1 - x0) * y_n + x1 * y0 - y1 * x0
    ) / chord_len

    # Exclude the endpoints — the chord passes through them so distance ≈ 0
    distances[0] = 0.0
    distances[-1] = 0.0
    idx = int(np.argmax(distances))
    return idx if distances[idx] > 1e-6 else None


# ── Pareto filtering ──────────────────────────────────────────────────────────


def _flag_dominance(
    points: list[FrontierPoint],
    x_direction: str,
    y_direction: str,
) -> "None":
    """Mark each point's ``is_dominant`` flag in place.

    A point p is dominated iff some other point q is at least as good
    on both axes and strictly better on one.  Direction-aware: "better"
    means lower for ``minimize`` axes and higher for ``maximize`` axes.

    For the standard minimize-X / maximize-Y case (e.g. volatility vs return),
    an O(N) single-pass algorithm is used: after sorting ascending by X, a
    point is non-dominated iff its Y strictly exceeds all Y values to its left.
    This replaces the original O(N^2) nested loop and matters when num_points
    is large (>50).

    For non-standard axis direction combinations the O(N^2) fallback is used.
    """
    if len(points) <= 1:
        if points:
            points[0].is_dominant = True
        return

    if x_direction == "minimize" and y_direction == "maximize":
        # O(N) pass: points are pre-sorted ascending by X (caller ensures this).
        # A point is dominant iff no point to its left has a >= Y value.
        best_y = float("-inf")
        for p in points:
            if p.y > best_y + 1e-9:
                p.is_dominant = True
                best_y = p.y
            else:
                p.is_dominant = False
        return

    if x_direction == "maximize" and y_direction == "minimize":
        # Mirror case: descending X, ascending Y.
        # Points are sorted ascending by X, so scan right-to-left.
        best_y = float("inf")
        for p in reversed(points):
            if p.y < best_y - 1e-9:
                p.is_dominant = True
                best_y = p.y
            else:
                p.is_dominant = False
        return

    # General O(N^2) fallback for non-standard axis direction combinations.
    def better_or_equal(a: float, b: float, direction: str) -> bool:
        return a <= b + 1e-9 if direction == "minimize" else a >= b - 1e-9

    def strictly_better(a: float, b: float, direction: str) -> bool:
        return a < b - 1e-9 if direction == "minimize" else a > b + 1e-9

    for i, p in enumerate(points):
        dominated = False
        for j, q in enumerate(points):
            if i == j:
                continue
            if (
                better_or_equal(q.x, p.x, x_direction)
                and better_or_equal(q.y, p.y, y_direction)
                and (
                    strictly_better(q.x, p.x, x_direction)
                    or strictly_better(q.y, p.y, y_direction)
                )
            ):
                dominated = True
                break
        p.is_dominant = not dominated


# ── Main sweep entry point ────────────────────────────────────────────────────


def compute_frontier(
    tickers: list[str],
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    budget: float,
    constraints: dict[str, Any],
    frontier_cfg: dict[str, Any],
) -> "FrontierReport":
    """Compute the efficient frontier between two measures.

    Args:
        tickers: Asset symbols.
        expected_returns: Annualised expected returns, shape (n,).
        covariance_matrix: Annualised covariance, shape (n, n).
        budget: Total budget — used only to fill ``AssetWeight.allocation``.
        constraints: Validated constraints dict (same shape used by the
            main optimiser; ``max_weight_per_asset``, ``sector_*`` etc.).
        frontier_cfg: Dict with ``x_measure``, ``y_measure``, ``num_points``.

    Returns:
        FrontierReport with the sampled points, knee/reference indices,
        and timing metadata.

    Raises:
        ValueError: If an unsupported measure is requested.
    """
    n = len(tickers)
    start_ts = time.perf_counter()

    x_name = str(frontier_cfg.get("x_measure", "volatility"))
    y_name = str(frontier_cfg.get("y_measure", "return"))
    num_points = int(frontier_cfg.get("num_points", 25))

    if x_name not in _FRONTIER_MEASURES or y_name not in _FRONTIER_MEASURES:
        raise ValueError(
            f"Frontier measures must be in {sorted(_FRONTIER_MEASURES)}; "
            f"got x={x_name!r}, y={y_name!r}"
        )
    if x_name == y_name:
        raise ValueError("Frontier x_measure and y_measure must differ")

    x_dir = _NATURAL_DIRECTION[x_name]
    y_dir = _NATURAL_DIRECTION[y_name]

    mu = np.asarray(expected_returns, dtype=float)
    cov = np.asarray(covariance_matrix, dtype=float)

    sector_map: dict[str, str] = constraints.get("sector_map") or {}
    sector_indices_by_name: dict[str, list[int]] = {}
    for i, t in enumerate(tickers):
        sec = sector_map.get(t)
        if sec:
            sector_indices_by_name.setdefault(sec, []).append(i)

    max_weight = constraints.get("max_weight_per_asset")
    sector_constraints = constraints.get("sector_constraints") or []

    def base_constraints(w: cp.Variable) -> list[cp.Constraint]:
        cons: list[cp.Constraint] = [cp.sum(w) == 1.0]
        if max_weight is not None:
            cons.append(w <= float(max_weight))
        for sc in sector_constraints:
            sec_name = sc.get("sector", "")
            idxs = sector_indices_by_name.get(sec_name, [])
            if idxs:
                cons.append(cp.sum(w[idxs]) <= float(sc.get("max_weight", 1.0)))
        return cons

    # ── Step 1: anchor solves ──────────────────────────────────────────────
    w_min_x, _ = _solve_extreme(
        x_dir, x_name, n, base_constraints, mu, cov, sector_indices_by_name,
    )
    w_max_y, _ = _solve_extreme(
        y_dir, y_name, n, base_constraints, mu, cov, sector_indices_by_name,
    )

    if w_min_x is None or w_max_y is None:
        logger.warning("frontier_anchor_infeasible", x=x_name, y=y_name)
        return FrontierReport(
            x_measure=x_name,
            y_measure=y_name,
            x_direction=x_dir,
            y_direction=y_dir,
            points=[],
            solve_time_ms=(time.perf_counter() - start_ts) * 1000,
        )

    # X bounds: the "good" extreme (min_x) and the "bad" extreme (x at max_y)
    x_lo = _evaluate_raw(x_name, w_min_x, mu, cov, sector_indices_by_name)
    x_hi = _evaluate_raw(x_name, w_max_y, mu, cov, sector_indices_by_name)
    if x_hi < x_lo:  # sanity: ensure x_lo ≤ x_hi for the grid
        x_lo, x_hi = x_hi, x_lo

    # If the range collapses, the frontier is a single point
    if x_hi - x_lo < 1e-9:
        only = _build_point(
            w_min_x, tickers, budget, x_name, y_name, mu, cov,
            sector_indices_by_name, sector_map, "optimal",
        )
        return FrontierReport(
            x_measure=x_name,
            y_measure=y_name,
            x_direction=x_dir,
            y_direction=y_dir,
            points=[only],
            num_dominant=1,
            num_dominated=0,
            solve_time_ms=(time.perf_counter() - start_ts) * 1000,
        )

    # ── Step 2: parametric sweep ──────────────────────────────────────────
    eps_grid = np.linspace(x_lo, x_hi, num_points)

    # Parallelise the sweep: each epsilon-constraint subproblem is independent.
    # ThreadPoolExecutor is used instead of ProcessPoolExecutor because:
    # (a) CLARABEL and SCS are C extensions that release the GIL during solving,
    #     so threads achieve real parallelism for the solver portion.
    # (b) Closures (like _solve_one below) are not picklable, which would prevent
    #     ProcessPoolExecutor from working without a module-level helper function.
    # For small num_points (<8) the thread-pool overhead exceeds the gain, so
    # we fall back to the sequential loop in that case.
    from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor  # noqa: PLC0415

    def _solve_one(eps: float) -> "FrontierPoint | None":
        """Solve one epsilon-constraint subproblem."""
        w = cp.Variable(n, nonneg=True)
        x_expr = _measure_expr(x_name, w, mu, cov, sector_indices_by_name)
        y_expr = _measure_expr(y_name, w, mu, cov, sector_indices_by_name)
        cons = base_constraints(w)
        if x_dir == "minimize":
            cons.append(x_expr <= float(eps))
        else:
            cons.append(x_expr >= float(eps))
        objective = cp.Maximize(y_expr) if y_dir == "maximize" else cp.Minimize(y_expr)
        problem = cp.Problem(objective, cons)
        try:
            problem.solve(solver=cp.CLARABEL, verbose=False)
        except Exception:
            try:
                problem.solve(solver=cp.SCS, verbose=False)
            except Exception:
                return None
        if problem.status in (cp.INFEASIBLE, cp.INFEASIBLE_INACCURATE):
            return None
        if w.value is None:
            return None
        w_val = np.maximum(w.value, 0.0)
        s = w_val.sum()
        if s <= 1e-9:
            return None
        w_val = w_val / s
        return _build_point(
            w_val, tickers, budget, x_name, y_name, mu, cov,
            sector_indices_by_name, sector_map, problem.status or "optimal",
        )

    if num_points >= 8:
        # Parallel path: distribute solves across available CPU cores.
        # Cap workers at num_points to avoid idle threads.
        _workers = min(num_points, os.cpu_count() or 4)
        with _ThreadPoolExecutor(max_workers=_workers) as _pool:
            _raw_results = list(_pool.map(_solve_one, eps_grid))
        points: list[FrontierPoint] = [p for p in _raw_results if p is not None]
    else:
        # Sequential fallback for small sweeps where thread overhead > gain.
        points = []
        for eps in eps_grid:
            pt = _solve_one(eps)
            if pt is not None:
                points.append(pt)

    if not points:
        return FrontierReport(
            x_measure=x_name,
            y_measure=y_name,
            x_direction=x_dir,
            y_direction=y_dir,
            points=[],
            solve_time_ms=(time.perf_counter() - start_ts) * 1000,
        )

    # ── Step 3: sort along X for plotting (ascending raw X) ───────────────
    points.sort(key=lambda p: p.x)

    # ── Step 4: flag dominance ────────────────────────────────────────────
    _flag_dominance(points, x_dir, y_dir)

    # ── Step 5: knee detection (over dominant subset, mapped back) ────────
    dominant_indices = [i for i, p in enumerate(points) if p.is_dominant]
    knee_index: int | None = None
    if len(dominant_indices) >= 3:
        dominant_points = [points[i] for i in dominant_indices]
        local_knee = _find_knee(dominant_points)
        if local_knee is not None:
            knee_index = dominant_indices[local_knee]
            points[knee_index].is_knee = True

    # ── Step 6: reference indices ─────────────────────────────────────────
    max_sharpe_idx = int(max(range(len(points)), key=lambda i: points[i].sharpe))
    # min-risk index = the point with the lowest volatility-like X axis when
    # X is a "minimize" measure; otherwise the lowest Y when Y is risk-like.
    if x_dir == "minimize":
        min_risk_idx = int(min(range(len(points)), key=lambda i: points[i].x))
    elif y_dir == "minimize":
        min_risk_idx = int(min(range(len(points)), key=lambda i: points[i].y))
    else:
        min_risk_idx = None  # type: ignore[assignment]

    num_dominant = sum(1 for p in points if p.is_dominant)

    solve_time_ms = (time.perf_counter() - start_ts) * 1000

    logger.info(
        "frontier_sweep_complete",
        x_measure=x_name,
        y_measure=y_name,
        num_points=len(points),
        num_dominant=num_dominant,
        knee_index=knee_index,
        solve_time_ms=round(solve_time_ms, 1),
    )

    return FrontierReport(
        x_measure=x_name,
        y_measure=y_name,
        x_direction=x_dir,
        y_direction=y_dir,
        points=points,
        knee_point_index=knee_index,
        max_sharpe_index=max_sharpe_idx,
        min_risk_index=min_risk_idx,
        num_dominant=num_dominant,
        num_dominated=len(points) - num_dominant,
        solve_time_ms=solve_time_ms,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_point(
    w_val: np.ndarray,
    tickers: list[str],
    budget: float,
    x_name: str,
    y_name: str,
    mu: np.ndarray,
    cov: np.ndarray,
    sector_indices_by_name: dict[str, list[int]],
    sector_map: dict[str, str],
    solver_status: str,
) -> "FrontierPoint":
    """Assemble a FrontierPoint from a solved weight vector."""
    x_val = _evaluate_raw(x_name, w_val, mu, cov, sector_indices_by_name)
    y_val = _evaluate_raw(y_name, w_val, mu, cov, sector_indices_by_name)

    # Always compute a Sharpe-like ranking metric (regardless of axes)
    port_ret = float(mu @ w_val)
    port_vol = float(np.sqrt(max(w_val @ cov @ w_val, 0.0)))
    sharpe = port_ret / port_vol if port_vol > 1e-12 else 0.0

    weights = [
        AssetWeight(
            ticker=tickers[i],
            weight=float(w_val[i]),
            allocation=float(w_val[i] * budget),
            sector=sector_map.get(tickers[i]),
        )
        for i in range(len(tickers))
        if w_val[i] > 1e-4
    ]

    return FrontierPoint(
        x=x_val,
        y=y_val,
        sharpe=sharpe,
        weights=weights,
        is_dominant=True,  # will be overwritten by _flag_dominance
        is_knee=False,
        solver_status=solver_status,
    )
