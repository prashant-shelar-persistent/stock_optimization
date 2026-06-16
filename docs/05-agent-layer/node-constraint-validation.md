# Node: Constraint Validation

`constraint_validation_node` is the **second node** in the optimization pipeline. It validates the user-supplied constraints for logical consistency against the actual asset universe, emits warnings for near-infeasible configurations, and produces a normalised `validated_constraints` dict that all downstream nodes consume.

**Source files:**
- Node: `backend/app/agents/nodes.py` — `constraint_validation_node()`
- Validation logic: `backend/app/classical/constraints.py` — `validate_constraints()`

## Responsibility

```
constraint_validation_node
    └── validate_constraints(request_params, tickers, expected_returns, covariance_matrix)
            ├── max_weight feasibility check (1/n lower bound)
            ├── min_return feasibility check (vs max achievable return)
            ├── max_volatility feasibility check (vs minimum variance portfolio)
            ├── sector constraint sum check
            ├── multi-objective weight normalisation check
            ├── objective threshold feasibility checks
            └── Build validated_constraints dict
```

## Node Signature

```python
def constraint_validation_node(state: AgentState) -> AgentState:
    """Validate and normalise optimization constraints."""
```

**Reads from state:** `request_params`, `tickers`, `expected_returns`, `covariance_matrix`, `sector_map`

**Writes to state:** `validated_constraints`, `constraint_warnings`, `node_timings_ms`, `completed_nodes`

**Fatal on failure:** Yes — a `ConstraintViolationError` (hard violation) sets `state["error"]` and routes to `END`.

## Weight Constraint Validation

### `max_weight_per_asset`

The maximum weight per asset must be at least `1/n` (where `n` is the number of assets), otherwise the budget constraint `sum(w) = 1` cannot be satisfied:

```python
if max_weight is not None:
    min_required_weight = 1.0 / n
    if max_weight < min_required_weight:
        violated.append(
            f"max_weight_per_asset ({max_weight:.3f}) is less than 1/n "
            f"({min_required_weight:.3f}) — budget constraint cannot be satisfied."
        )
```

This is a **hard violation** — it raises `ConstraintViolationError` and terminates the run.

## Sector Constraint Normalisation

If sector constraints are provided, the node checks whether their weight limits sum to less than 1.0. If all assets belong to constrained sectors and the limits sum below 1.0, full budget allocation may be impossible:

```python
if sector_constraints:
    total_sector_limit = sum(sc.get("max_weight", 1.0) for sc in sector_constraints)
    if total_sector_limit < 0.99:
        warnings.append(
            f"Sector weight limits sum to {total_sector_limit:.3f} < 1.0. "
            "If all assets belong to constrained sectors, full budget "
            "allocation may not be achievable."
        )
```

This is a **soft warning** — the run continues but the user is informed.

## Objective Weight Normalisation

When multi-objective optimization is requested (via `request_params["objectives"]`), the node checks that enabled objective weights sum to approximately 1.0:

```python
enabled_rows = [o for o in raw_objectives if o.get("enabled", True)]
if enabled_rows:
    total_w = sum(float(o.get("weight", 0.0)) for o in enabled_rows)
    if total_w <= 0:
        violated.append("All enabled objectives have weight 0 ...")
    elif abs(total_w - 1.0) > 0.01:
        warnings.append(
            f"Objective weights sum to {total_w:.3f}; they will be "
            "renormalised to 1.0 before optimisation."
        )
```

Weights that don't sum to 1.0 are flagged as a warning (not a hard violation) because the classical optimizer renormalises them automatically.

## `min_return` Feasibility Check

The requested minimum return is compared against the maximum achievable return in the asset universe (the highest individual asset expected return):

```python
if min_return is not None:
    max_achievable_return = float(np.max(expected_returns))
    if min_return > max_achievable_return:
        violated.append(...)  # Hard violation
    elif min_return > 0.9 * max_achievable_return:
        warnings.append(...)  # Soft warning: near-infeasible
```

## `max_volatility` Feasibility Check

The requested maximum volatility is compared against the minimum achievable portfolio volatility (the global minimum variance portfolio):

```python
if max_volatility is not None:
    inv_cov = np.linalg.inv(covariance_matrix)
    ones = np.ones(n)
    min_var = 1.0 / (ones @ inv_cov @ ones)
    min_vol = float(np.sqrt(max(min_var, 0.0)))

    if max_volatility < min_vol:
        violated.append(...)  # Hard violation
    elif max_volatility < 1.1 * min_vol:
        warnings.append(...)  # Soft warning: near-minimum-variance
```

## Constraint Warnings List

The `constraint_warnings` list accumulates all soft warnings during validation. These warnings are:
1. Stored in `state["constraint_warnings"]`
2. Logged at `WARNING` level
3. Passed to the LLM explanation node for inclusion in the portfolio narrative
4. Appended to by later nodes (`quantum_dispatch`, `frontier_computation`) if those nodes encounter non-fatal errors

Example warnings:
```
"min_return (0.185) is very close to the maximum achievable return (0.190). 
 The solver may struggle to find a feasible solution."

"Sector weight limits sum to 0.800 < 1.0. If all assets belong to 
 constrained sectors, full budget allocation may not be achievable."

"Objective weights sum to 1.200; they will be renormalised to 1.0 before optimisation."
```

## `validated_constraints` Output Structure

On success, `validate_constraints()` returns a dict with the following structure:

```python
validated: dict[str, Any] = {
    "max_weight_per_asset": float | None,
    "min_weight_per_asset": float | None,
    "min_return": float | None,
    "max_volatility": float | None,
    "sector_constraints": list[dict],   # [{sector, max_weight}, ...]
    "sector_map": dict[str, str],       # Injected from data_fetch state
    "objectives": list[dict],           # Multi-objective rows (may be empty)
    "frontier": dict | None,            # FrontierConfig (enabled, x_measure, y_measure, ...)
}
```

The `sector_map` is injected by the node itself (not by `validate_constraints()`) after the validation call returns:

```python
sector_map: dict[str, str] = state.get("sector_map") or {}
validated["sector_map"] = sector_map
```

This ensures the classical optimizer can apply sector-level weight limits without needing to read from state directly.

## Hard vs Soft Violations

| Condition | Type | Behaviour |
|---|---|---|
| `max_weight < 1/n` | Hard | Raises `ConstraintViolationError`, routes to END |
| `min_return > max_achievable` | Hard | Raises `ConstraintViolationError`, routes to END |
| `max_volatility < min_vol` | Hard | Raises `ConstraintViolationError`, routes to END |
| All objective weights = 0 | Hard | Raises `ConstraintViolationError`, routes to END |
| `min_return > 0.9 * max_achievable` | Soft | Warning added, run continues |
| `max_volatility < 1.1 * min_vol` | Soft | Warning added, run continues |
| Sector limits sum < 1.0 | Soft | Warning added, run continues |
| Objective weights ≠ 1.0 | Soft | Warning added, run continues |

## Error Handling

```python
try:
    validated, warnings = validate_constraints(
        request_params=request_params,
        tickers=tickers,
        expected_returns=expected_returns,
        covariance_matrix=covariance_matrix,
    )
except Exception as exc:
    updated["error"] = str(exc)
    updated["failed_node"] = "constraint_validation"
    updated["error_details"] = {"node": "constraint_validation", "error_type": type(exc).__name__}
    return updated
```

A `ConstraintViolationError` from `validate_constraints()` is caught here and converted to a state error. The graph then routes to `END` via `_route_after_fatal_node()`.

## Related Pages

- [Agent State](agent-state.md) — Full state field reference
- [Node: Data Fetch](node-data-fetch.md) — Provides `expected_returns`, `covariance_matrix`, `sector_map`
- [Node: Classical Optimization](node-classical.md) — Consumes `validated_constraints`
- [Error Routing](error-routing.md) — How constraint violations route to END
