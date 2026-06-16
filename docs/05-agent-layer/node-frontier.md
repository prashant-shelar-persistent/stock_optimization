# Node: Frontier Computation

`frontier_computation_node` is the **sixth node** in the optimization pipeline (conditional). It traces the Pareto-efficient frontier between two user-selected portfolio measures using the epsilon-constraint method. The node is **non-fatal** — frontier failure does not block the LLM explanation.

**Source files:**
- Node: `backend/app/agents/nodes.py` — `frontier_computation_node()`
- Frontier sweep: `backend/app/classical/frontier.py` — `compute_frontier()`

## When This Node Runs

The node is only invoked when:
1. `validated_constraints["frontier"]["enabled"] == True`
2. `classical_result` is present in state (the classical optimization succeeded)

The graph's `_route_after_comparison()` function enforces both conditions. If either is false, the graph routes directly to `llm_explanation`, skipping this node.

## Responsibility

```
frontier_computation_node
    └── compute_frontier(tickers, expected_returns, covariance_matrix, budget, constraints, frontier_cfg)
            ├── Validate x_measure and y_measure (must be in _FRONTIER_MEASURES)
            ├── Solve anchor portfolios (min-X and max-Y)
            ├── Build epsilon grid [x_lo, x_hi] with num_points levels
            ├── For each ε: maximise y_measure s.t. x_measure ≤ ε
            ├── Filter dominated points (_flag_dominance)
            ├── Detect knee point (maximum-curvature heuristic)
            ├── Tag max-Sharpe and min-risk reference indices
            └── Return FrontierReport
```

## Node Signature

```python
def frontier_computation_node(state: AgentState) -> AgentState:
    """Compute the Pareto frontier between two user-selected measures."""
```

**Reads from state:** `validated_constraints` (for `frontier_cfg`), `tickers`, `expected_returns`, `covariance_matrix`, `budget`

**Writes to state:** `frontier_report`, `constraint_warnings` (on failure), `node_timings_ms`, `completed_nodes`

**Fatal on failure:** **No** — frontier failure appends a warning to `constraint_warnings` and sets `frontier_report = None`. The run continues.

## `FrontierConfig` Parameters

The `frontier_cfg` dict is extracted from `validated_constraints["frontier"]`:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `enabled` | `bool` | `false` | Must be `true` for the node to run |
| `x_measure` | `str` | `"volatility"` | Measure plotted on the X axis |
| `y_measure` | `str` | `"return"` | Measure plotted on the Y axis |
| `num_points` | `int` | `25` | Number of epsilon-constraint levels to solve |

### Supported Measures

The following convex measures are supported for both axes:

| Measure | Direction | Description |
|---|---|---|
| `return` | maximize | Annualised expected portfolio return |
| `volatility` | minimize | Annualised portfolio volatility (std dev) |
| `sharpe` | maximize | Convex Sharpe proxy (return − λ·variance) |
| `diversification_hhi` | minimize | Herfindahl-Hirschman Index (sum of squared weights) |
| `sector_concentration` | minimize | Sum of squared sector weights |

Non-convex measures (`max_drawdown`, `esg_score`) raise `ValueError` — they cannot be expressed as CVXPY constraints.

## Epsilon-Constraint Algorithm

### Step 1: Anchor Solves

Two extreme portfolios bracket the feasible frontier range:

```python
# min-X portfolio: minimise x_measure (e.g. minimum volatility)
w_min_x, _ = _solve_extreme(x_dir, x_name, n, base_constraints, mu, cov, ...)

# max-Y portfolio: maximise y_measure (e.g. maximum return)
w_max_y, _ = _solve_extreme(y_dir, y_name, n, base_constraints, mu, cov, ...)
```

The X-values of these two portfolios define the sweep range `[x_lo, x_hi]`.

### Step 2: Parametric Sweep

A uniform grid of `num_points` epsilon levels is built across `[x_lo, x_hi]`. For each level ε, the optimizer solves:

```
maximise   y_measure(w)
subject to:
    x_measure(w) ≤ ε    (if x_direction == "minimize")
    x_measure(w) ≥ ε    (if x_direction == "maximize")
    sum(w) = 1
    w ≥ 0
    + base constraints (max_weight_per_asset, sector limits)
```

The solver preference is CLARABEL with SCS as fallback:

```python
problem.solve(solver=cp.CLARABEL, verbose=False)
# fallback:
problem.solve(solver=cp.SCS, verbose=False)
```

Infeasible or inaccurate solutions are skipped (not added to the points list).

### Step 3: Dominance Filtering

Each point is tagged as `is_dominant` or dominated using Pareto dominance:

```
Point p is dominated iff some other point q is:
  - at least as good on both axes, AND
  - strictly better on at least one axis
```

"Better" is direction-aware: lower is better for `minimize` measures, higher for `maximize`.

### Step 4: Knee Point Detection

The knee point is the portfolio with the maximum curvature on the frontier — the best trade-off between the two measures. It is found using the "distance from chord" heuristic:

```python
def _find_knee(points: list[FrontierPoint]) -> int | None:
    # Normalise both axes to [0, 1]
    # Find the point with maximum perpendicular distance from the chord
    # connecting the two extreme points
    distances = np.abs(
        (y1 - y0) * x_n - (x1 - x0) * y_n + x1 * y0 - y1 * x0
    ) / chord_len
    return int(np.argmax(distances))
```

The knee point index is stored in `FrontierReport.knee_point_index` and the corresponding `FrontierPoint.is_knee` flag is set to `True`.

## `FrontierPoint` Generation

Each solved portfolio becomes a `FrontierPoint`:

```python
class FrontierPoint(BaseModel):
    x: float              # X-axis measure value
    y: float              # Y-axis measure value
    sharpe: float         # Sharpe ratio (always computed for ranking)
    weights: list[AssetWeight]  # Full asset allocation
    is_dominant: bool     # True if Pareto-efficient
    is_knee: bool         # True for the knee point
    solver_status: str    # CVXPY solver status
```

The `weights` list contains only assets with weight > 0.0001, with `allocation = weight * budget`.

## `FrontierReport` Structure

```python
class FrontierReport(BaseModel):
    x_measure: FrontierMeasureName      # e.g. "volatility"
    y_measure: FrontierMeasureName      # e.g. "return"
    x_direction: Literal["maximize", "minimize"]
    y_direction: Literal["maximize", "minimize"]
    points: list[FrontierPoint]         # All sampled points
    knee_point_index: int | None        # Index of knee portfolio
    max_sharpe_index: int | None        # Index of max-Sharpe portfolio
    min_risk_index: int | None          # Index of min-risk portfolio
    num_dominant: int                   # Count of Pareto-dominant points
    num_dominated: int                  # Count of dominated points
    solve_time_ms: float                # Total sweep time in milliseconds
    commentary: str | None             # LLM-generated summary (future)
```

The `max_sharpe_index` points to the portfolio with the highest Sharpe ratio among all frontier points. The `min_risk_index` points to the portfolio with the lowest X-axis value (when X is a risk measure like volatility).

## Non-Fatal Error Handling

```python
try:
    report = compute_frontier(...)
except Exception as exc:
    existing_warnings = list(state.get("constraint_warnings") or [])
    existing_warnings.append(
        f"Efficient-frontier sweep failed: {type(exc).__name__}: {exc}"
    )
    updated["frontier_report"] = None
    updated["constraint_warnings"] = existing_warnings
    # NOTE: state["error"] is NOT set — frontier failure is non-fatal
    return updated
```

Common failure modes:
- Unsupported measure name → `ValueError`
- Both anchor solves infeasible → returns empty `FrontierReport` (no exception)
- CVXPY solver error on all grid points → empty points list

## Defensive No-Op

The node includes a defensive check in case the graph's routing logic is bypassed:

```python
if not frontier_cfg or not frontier_cfg.get("enabled"):
    updated["frontier_report"] = None
    _record_completed(updated, "frontier_computation")
    return updated
```

## Related Pages

- [Agent State](agent-state.md) — Full state field reference
- [Node: Comparison](node-comparison.md) — Runs before frontier computation
- [Node: LLM Explanation](node-llm-explanation.md) — Runs after frontier computation
- [Error Routing](error-routing.md) — `_route_after_comparison()` frontier routing logic
