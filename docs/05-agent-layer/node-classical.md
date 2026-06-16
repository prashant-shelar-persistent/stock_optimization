# Node: Classical Optimization

`classical_optimization_node` is the **third node** in the optimization pipeline. It runs the Markowitz Mean-Variance Optimization (MVO) via CVXPY and serialises the result into the agent state. The classical result serves as the baseline for quantum comparison and as the primary output when quantum optimization is disabled or unavailable.

**Source files:**
- Node: `backend/app/agents/nodes.py` — `classical_optimization_node()`
- Optimizer: `backend/app/classical/optimizer.py` — `run_markowitz_mvo()`

## Responsibility

```
classical_optimization_node
    └── run_markowitz_mvo(tickers, expected_returns, covariance_matrix, budget, constraints)
            ├── Build CVXPY objective (Markowitz or multi-objective scalarisation)
            ├── Apply weight constraints (max/min per asset, sector limits)
            ├── Apply return/volatility constraints
            ├── Solve with CLARABEL (fallback: SCS)
            ├── Compute portfolio metrics (return, volatility, Sharpe)
            └── Return ClassicalResult
```

## Node Signature

```python
def classical_optimization_node(state: AgentState) -> AgentState:
    """Run Markowitz Mean-Variance Optimization via CVXPY."""
```

**Reads from state:** `tickers`, `expected_returns`, `covariance_matrix`, `budget`, `validated_constraints`

**Writes to state:** `classical_result`, `node_timings_ms`, `completed_nodes`

**Fatal on failure:** Yes — sets `state["error"]` and `state["failed_node"]`, causing the graph to route to `END`. The comparison and explanation nodes cannot produce meaningful output without a classical baseline.

## Calling `run_markowitz_mvo()`

The node calls the optimizer with all required inputs:

```python
result = run_markowitz_mvo(
    tickers=tickers,
    expected_returns=expected_returns,
    covariance_matrix=covariance_matrix,
    budget=budget,
    constraints=constraints,
)
```

The `constraints` dict is the `validated_constraints` from the previous node, which includes:
- `max_weight_per_asset` / `min_weight_per_asset`
- `min_return` / `max_volatility`
- `sector_constraints` with `sector_map`
- `objectives` (multi-objective rows, may be empty)

### Standard Markowitz MVO

When `constraints["objectives"]` is empty or absent, the optimizer solves the classic mean-variance problem:

```
maximise  w^T μ - w^T Σ w
subject to:
    sum(w) = 1
    w >= 0
    (optional) w_i <= max_weight_per_asset
    (optional) w_i >= min_weight_per_asset
    (optional) sector weights <= sector limits
    (optional) portfolio return >= min_return
    (optional) portfolio volatility <= max_volatility
```

### Multi-Objective Extension

When `objectives` is non-empty, the optimizer builds a scalarised weighted-sum objective from the enabled rows. Supported convex measures include `return`, `volatility`, `sharpe`, `diversification_hhi`, and `sector_concentration`. Objectives with a `threshold` become hard CVXPY constraints.

## `ClassicalResult` Serialisation to State

The `ClassicalResult` Pydantic model is serialised to a plain dict via `.model_dump()` before being stored in state:

```python
updated["classical_result"] = result.model_dump()
```

The serialised structure matches the `ClassicalResult` schema:

```python
class ClassicalResult(BaseModel):
    weights: list[AssetWeight]    # [{ticker, weight, allocation, sector}, ...]
    metrics: PortfolioMetrics     # {expected_return, volatility, sharpe_ratio, num_assets}
    solver_status: str            # "optimal" | "optimal_inaccurate" | "infeasible"
    solve_time_ms: float          # Wall-clock solve time in milliseconds
```

The `AssetWeight` entries include only assets with non-zero weight (typically a sparse subset of the full universe). The `allocation` field is the dollar amount (`weight * budget`).

## Timing Recording

The node records its wall-clock execution time using `time.perf_counter()`:

```python
start_ms = time.perf_counter() * 1000

try:
    result = run_markowitz_mvo(...)
except Exception as exc:
    elapsed_ms = time.perf_counter() * 1000 - start_ms
    ...

elapsed_ms = time.perf_counter() * 1000 - start_ms
_record_timing(updated, "classical_optimization", elapsed_ms)
```

The timing is stored in `state["node_timings_ms"]["classical_optimization"]` and is visible in the API response and WebSocket progress events.

## Logged Metrics

On success, the node logs key portfolio metrics at `INFO` level:

```python
logger.info(
    "classical_optimization_completed",
    run_id=state.get("run_id"),
    sharpe=round(result.metrics.sharpe_ratio, 4),
    expected_return=round(result.metrics.expected_return, 4),
    volatility=round(result.metrics.volatility, 4),
    num_assets=result.metrics.num_assets,
    solver_status=result.solver_status,
    elapsed_ms=round(elapsed_ms, 1),
)
```

## Error Handling

```python
try:
    result = run_markowitz_mvo(...)
except Exception as exc:
    elapsed_ms = time.perf_counter() * 1000 - start_ms
    logger.error("classical_optimization_failed", ...)
    updated["error"] = str(exc)
    updated["failed_node"] = "classical_optimization"
    updated["error_details"] = {
        "node": "classical_optimization",
        "error_type": type(exc).__name__,
        "num_tickers": len(tickers),
    }
    _record_timing(updated, "classical_optimization", elapsed_ms)
    return updated
```

A `SolverInfeasibleError` is raised by `run_markowitz_mvo()` when CVXPY cannot find a feasible solution (e.g. conflicting constraints that passed the pre-validation check). This is treated as a fatal error.

## Routing After Classical Optimization

After this node, the graph calls `_route_after_classical()` which can return three outcomes:

| Outcome | Condition |
|---|---|
| `"end"` | `state["error"]` is set (classical optimization failed) |
| `"quantum"` | `run_quantum=True` AND `len(tickers) <= MAX_QUANTUM_ASSETS` |
| `"skip_quantum"` | `run_quantum=False` OR `len(tickers) > MAX_QUANTUM_ASSETS` |

See [Error Routing](error-routing.md) for the full routing logic.

## Related Pages

- [Agent State](agent-state.md) — Full state field reference
- [Node: Constraint Validation](node-constraint-validation.md) — Provides `validated_constraints`
- [Node: Quantum Dispatch](node-quantum-dispatch.md) — Runs after classical optimization (conditional)
- [Node: Comparison](node-comparison.md) — Consumes `classical_result`
- [Error Routing](error-routing.md) — `_route_after_classical()` logic

## Classical Optimization Cross-References

- [Markowitz MVO](../06-classical-optimization/markowitz-mvo.md) — Full CVXPY problem formulation and solver details
- [Multi-Objective](../06-classical-optimization/multi-objective.md) — Composite objective functions used by this node
- [Constraints](../06-classical-optimization/constraints.md) — How validated constraints are applied in the CVXPY problem
- [Efficient Frontier](../06-classical-optimization/efficient-frontier.md) — Frontier computation triggered after this node completes
