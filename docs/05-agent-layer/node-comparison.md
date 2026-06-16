# Node: Comparison

`comparison_node` is the **fifth node** in the optimization pipeline. It computes side-by-side performance metrics between the classical Markowitz result and the quantum (QAOA/VQE) results, then generates a human-readable recommendation string. The node is **non-fatal** — comparison failure does not block the LLM explanation.

**Source files:**
- Node: `backend/app/agents/nodes.py` — `comparison_node()`
- Comparison logic: `backend/app/agents/comparison.py` — `compute_comparison()`

## Responsibility

```
comparison_node
    └── compute_comparison(classical_result, quantum_result)
            ├── Extract classical metrics (Sharpe, return, volatility)
            ├── Compute QAOA vs classical differences
            ├── Compute VQE vs classical differences
            ├── Determine best quantum algorithm
            └── Generate recommendation string
```

## Node Signature

```python
def comparison_node(state: AgentState) -> AgentState:
    """Compare classical and quantum optimization results."""
```

**Reads from state:** `classical_result`, `quantum_result`

**Writes to state:** `comparison_summary`, `node_timings_ms`, `completed_nodes`

**Fatal on failure:** **No** — comparison failure is logged but does not set `state["error"]`. The LLM explanation node will generate a partial explanation without the comparison summary.

## Sharpe Improvement Calculation

The core metric is the Sharpe ratio improvement of each quantum algorithm over the classical baseline:

```python
classical_sharpe = float(classical_metrics.get("sharpe_ratio", 0.0))

# QAOA improvement
qaoa_sharpe = float(qaoa_metrics.get("sharpe_ratio", 0.0))
sharpe_improvement_qaoa = qaoa_sharpe - classical_sharpe

# VQE improvement
vqe_sharpe = float(vqe_metrics.get("sharpe_ratio", 0.0))
sharpe_improvement_vqe = vqe_sharpe - classical_sharpe
```

A positive value means the quantum algorithm outperforms classical; negative means classical is better.

## Return and Volatility Differences

In addition to Sharpe, the node computes absolute differences in expected return and volatility:

```python
return_diff_qaoa = qaoa_return - classical_return
volatility_diff_qaoa = qaoa_vol - classical_vol

return_diff_vqe = vqe_return - classical_return
volatility_diff_vqe = vqe_vol - classical_vol
```

These differences are stored in `ComparisonSummary` and used by the LLM explanation node to describe risk/return trade-offs.

## Recommendation Generation

The `_generate_recommendation()` function produces a human-readable recommendation string based on the best Sharpe improvement across QAOA and VQE. Two thresholds control the recommendation tier:

```python
_SIGNIFICANT_SHARPE_DELTA = 0.05   # > 0.05 → quantum recommended
_MARGINAL_SHARPE_DELTA = 0.0       # 0.0–0.05 → marginal improvement
```

### Recommendation Tiers

| Condition | Recommendation |
|---|---|
| No quantum result | Classical-only summary with Sharpe/return/volatility |
| Quantum attempted but both failed | Classical recommended; quantum unavailable |
| Best improvement > 0.05 | Quantum recommended; includes return note |
| Best improvement 0.0–0.05 | Marginal improvement; both approaches viable |
| Best improvement < -0.05 | Classical outperforms quantum; classical recommended |
| Best improvement ≈ 0 | Comparable results; classical recommended for production |

### Example Recommendations

**Quantum significantly better:**
```
Quantum optimization (QAOA) outperforms classical by +0.087 Sharpe ratio points
(classical: 1.234, QAOA: 1.321). The quantum portfolio also offers a higher
expected return (+2.3% vs classical). The quantum portfolio is recommended
for this asset universe.
```

**Classical better:**
```
Classical optimization outperforms quantum by 0.062 Sharpe ratio points
(classical: 1.234, best quantum: 1.172). The classical Markowitz portfolio
is recommended.
```

**No quantum run:**
```
The classical Markowitz MVO portfolio achieves a Sharpe ratio of 1.234
(expected return: 12.3%, volatility: 9.8%). Quantum optimization was not
run for this configuration.
```

## `ComparisonSummary` Structure

The `ComparisonSummary` Pydantic model is serialised to a plain dict via `.model_dump()`:

```python
class ComparisonSummary(BaseModel):
    sharpe_improvement_qaoa: float | None = None   # QAOA Sharpe - classical Sharpe
    sharpe_improvement_vqe: float | None = None    # VQE Sharpe - classical Sharpe
    return_diff_qaoa: float | None = None          # QAOA return - classical return
    return_diff_vqe: float | None = None           # VQE return - classical return
    volatility_diff_qaoa: float | None = None      # QAOA vol - classical vol
    volatility_diff_vqe: float | None = None       # VQE vol - classical vol
    recommendation: str                            # Human-readable recommendation
```

All difference fields are `None` when the corresponding quantum algorithm did not produce a result (either because quantum was skipped or the solver failed).

## Handling Missing Classical Result

If `classical_result` is `None` (which should not happen in normal flow since classical failure routes to END), the comparison returns a minimal summary:

```python
if classical_result is None:
    return ComparisonSummary(
        recommendation=(
            "Classical optimization did not produce a result. "
            "Please review your constraints and try again."
        )
    )
```

## Non-Fatal Error Handling

```python
try:
    comparison = compute_comparison(
        classical_result=classical_result,
        quantum_result=quantum_result,
    )
except Exception as exc:
    elapsed_ms = time.perf_counter() * 1000 - start_ms
    logger.error("comparison_failed", ...)
    # NOTE: state["error"] is NOT set — comparison failure is non-fatal
    _record_timing(updated, "comparison", elapsed_ms)
    _record_completed(updated, "comparison")
    return updated  # comparison_summary is absent from state
```

If comparison fails, `state["comparison_summary"]` is not set. The LLM explanation node handles this gracefully by generating a partial explanation based only on the classical and quantum results.

## Routing After Comparison

After this node, the graph calls `_route_after_comparison()` which decides whether to run the frontier sweep:

| Outcome | Condition |
|---|---|
| `"frontier"` | `validated_constraints["frontier"]["enabled"] == True` AND `classical_result` is present |
| `"skip_frontier"` | Frontier not enabled, or classical result missing |

See [Error Routing](error-routing.md) for the full routing logic.

## Related Pages

- [Agent State](agent-state.md) — Full state field reference
- [Node: Quantum Dispatch](node-quantum-dispatch.md) — Provides `quantum_result`
- [Node: Frontier Computation](node-frontier.md) — Runs after comparison (conditional)
- [Node: LLM Explanation](node-llm-explanation.md) — Consumes `comparison_summary`
- [Error Routing](error-routing.md) — `_route_after_comparison()` logic
