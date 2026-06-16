# Markowitz Mean-Variance Optimization

The classical optimization engine implements Harry Markowitz's Mean-Variance Optimization (MVO) using [CVXPY](https://www.cvxpy.org/), a Python-embedded domain-specific language for convex optimization. This page covers the mathematical formulation, CVXPY variable setup, the `run_markowitz_mvo()` function, solver status handling, and the `ClassicalResult` output schema.

Source file: `backend/app/classical/optimizer.py`

---

## Mathematical Formulation

### Standard Markowitz Objective

The core optimization problem maximizes the risk-adjusted return of a portfolio:

```
maximize   w^T μ - λ · w^T Σ w

subject to:
    sum(w) = 1          (fully invested)
    w >= 0              (long-only)
    w_i <= max_weight   (optional per-asset cap)
    μ^T w >= r_min      (optional minimum return)
    w^T Σ w <= σ²_max   (optional maximum variance)
```

Where:
- **w** ∈ ℝⁿ — portfolio weight vector (decision variable)
- **μ** ∈ ℝⁿ — annualised expected returns vector
- **Σ** ∈ ℝⁿˣⁿ — annualised covariance matrix (positive semi-definite)
- **λ** — risk-aversion parameter (implicit in the legacy path; the multi-objective path uses explicit per-measure weights)

### Legacy vs. Multi-Objective Paths

The optimizer supports two operating modes:

| Mode | Trigger | Objective |
|------|---------|-----------|
| **Legacy Markowitz** | `objectives` list is empty or absent | `maximize μᵀw − wᵀΣw` |
| **Multi-objective scalarized** | At least one enabled `BusinessObjective` row | `maximize Σᵢ wᵢ · sign(directionᵢ) · normalizedᵢ(w)` |

In the legacy path, the risk-aversion coefficient λ is implicitly set to 1 (the variance term is subtracted directly from the return term). In the multi-objective path, each measure is independently scaled to O(1) magnitude before being combined.

### Annualised Metrics

The optimizer uses `TRADING_DAYS_PER_YEAR = 252` as the standard annualisation constant. The risk-free rate defaults to `0.02` (2% per annum) and is read from `settings.RISK_FREE_RATE`.

---

## CVXPY Variable and Parameter Setup

The optimizer constructs the CVXPY problem programmatically inside `run_markowitz_mvo()`. Here is the core setup:

```python
import cvxpy as cp
import numpy as np

# Decision variable: n-dimensional weight vector, non-negative
w = cp.Variable(n, nonneg=True)

# Core constraints
cvx_constraints: list[cp.Constraint] = [
    cp.sum(w) == 1.0,   # Fully invested (budget constraint)
]

# Optional: per-asset weight cap
if max_weight is not None:
    cvx_constraints.append(w <= max_weight)

# Optional: minimum portfolio return (linear constraint)
portfolio_return = expected_returns @ w
if min_return is not None:
    cvx_constraints.append(portfolio_return >= min_return)

# Optional: maximum portfolio volatility (quadratic constraint)
portfolio_variance = cp.quad_form(w, cp.psd_wrap(covariance_matrix))
if max_volatility is not None:
    cvx_constraints.append(portfolio_variance <= max_volatility ** 2)
```

### Key CVXPY Constructs

| Construct | Purpose |
|-----------|---------|
| `cp.Variable(n, nonneg=True)` | Creates an n-dimensional non-negative variable (implicitly adds `w >= 0`) |
| `cp.sum(w) == 1.0` | Budget equality constraint |
| `cp.quad_form(w, cp.psd_wrap(Σ))` | Quadratic form `wᵀΣw`; `psd_wrap` tells CVXPY the matrix is PSD |
| `cp.norm(sqrt_cov @ w, 2)` | Portfolio standard deviation via Cholesky decomposition |
| `cp.sum_squares(w)` | Herfindahl-Hirschman Index (HHI) for diversification |
| `cp.Maximize(expr)` | Wraps the objective expression |

### Covariance Matrix Regularization

To handle near-singular covariance matrices from floating-point noise, the optimizer adds a small diagonal regularization before computing the Cholesky factor:

```python
reg = covariance_matrix + 1e-10 * np.eye(covariance_matrix.shape[0])
try:
    sqrt_cov = np.linalg.cholesky(reg)
except np.linalg.LinAlgError:
    # Fall back to symmetric eigen sqrt if Cholesky fails
    eigvals, eigvecs = np.linalg.eigh(reg)
    eigvals = np.maximum(eigvals, 0.0)
    sqrt_cov = eigvecs @ np.diag(np.sqrt(eigvals)) @ eigvecs.T
```

---

## `run_markowitz_mvo()` Function Signature

```python
def run_markowitz_mvo(
    tickers: list[str],
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    budget: float,
    constraints: dict[str, Any],
) -> ClassicalResult:
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `tickers` | `list[str]` | Asset ticker symbols (length n) |
| `expected_returns` | `np.ndarray` | Annualised expected returns, shape `(n,)` |
| `covariance_matrix` | `np.ndarray` | Annualised covariance matrix, shape `(n, n)` |
| `budget` | `float` | Total investment budget in USD (used for dollar allocation) |
| `constraints` | `dict[str, Any]` | Validated constraint dict from `constraint_validation_node` |

### Constraints Dict Keys

The `constraints` dict is produced by `validate_constraints()` in `backend/app/classical/constraints.py` and contains:

| Key | Type | Description |
|-----|------|-------------|
| `max_weight_per_asset` | `float \| None` | Per-asset weight ceiling |
| `min_weight_per_asset` | `float \| None` | Per-asset weight floor |
| `min_return` | `float \| None` | Minimum portfolio return threshold |
| `max_volatility` | `float \| None` | Maximum portfolio volatility threshold |
| `sector_constraints` | `list[dict]` | Sector-level allocation limits |
| `sector_map` | `dict[str, str]` | Ticker → sector name mapping |
| `objectives` | `list[dict]` | Multi-objective matrix rows |
| `frontier` | `dict \| None` | Frontier sweep configuration |

### Returns

`ClassicalResult` — see [ClassicalResult Output](#classicalresult-output) below.

### Raises

`SolverInfeasibleError` — when CVXPY cannot find a feasible solution. See [Solver Status Handling](#solver-status-handling).

---

## Solve Time Measurement

The optimizer measures wall-clock time using `time.perf_counter()` for high-resolution timing:

```python
start_time = time.perf_counter()

# ... build problem, solve ...

solve_time_ms = (time.perf_counter() - start_time) * 1000
```

The `solve_time_ms` value is included in the `ClassicalResult` and logged at INFO level. Typical solve times for a 10–50 asset portfolio are **5–200 ms** depending on the number of constraints and the solver used.

---

## Solver Status Handling

The optimizer uses a two-solver fallback strategy:

```python
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
```

### Solver Priority

| Priority | Solver | Notes |
|----------|--------|-------|
| Primary | **CLARABEL** | Interior-point solver; fast and accurate for QP/SOCP |
| Fallback | **SCS** | First-order ADMM solver; more robust on ill-conditioned problems |

### Status Codes

After solving, the optimizer checks the problem status:

```python
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
```

| CVXPY Status | Meaning | Action |
|-------------|---------|--------|
| `optimal` | Solution found | Return `ClassicalResult` |
| `optimal_inaccurate` | Solution found but may be imprecise | Return `ClassicalResult` (status preserved) |
| `infeasible` | No feasible solution exists | Raise `SolverInfeasibleError` |
| `infeasible_inaccurate` | Likely infeasible | Raise `SolverInfeasibleError` |
| `unbounded` | Objective is unbounded | Raise `SolverInfeasibleError` |

### Post-Solve Weight Cleanup

After a successful solve, tiny negative weights from numerical noise are clipped and the weights are re-normalized:

```python
weights_raw = np.maximum(w.value, 0.0)   # Clip tiny negatives
weights_raw = weights_raw / weights_raw.sum()  # Re-normalise to sum=1
```

Assets with weight below `1e-4` (0.01%) are excluded from the output to keep the result clean.

---

## `ClassicalResult` Output

The function returns a `ClassicalResult` Pydantic model defined in `backend/app/schemas/responses.py`:

```python
class ClassicalResult(BaseModel):
    """Result from the Markowitz MVO classical optimizer."""

    weights: list[AssetWeight]
    metrics: PortfolioMetrics
    solver_status: str
    solve_time_ms: float
```

### `AssetWeight` Sub-model

```python
class AssetWeight(BaseModel):
    ticker: str
    weight: float = Field(ge=0.0, le=1.0)
    allocation: float = Field(ge=0.0, description="Dollar amount allocated")
    sector: str | None = None
```

### `PortfolioMetrics` Sub-model

```python
class PortfolioMetrics(BaseModel):
    expected_return: float   # Annualised expected return
    volatility: float        # Annualised volatility (std dev)
    sharpe_ratio: float      # Sharpe ratio
    max_drawdown: float | None = None
    num_assets: int          # Number of assets with non-zero weight
```

### Metrics Computation

After the solve, portfolio metrics are recomputed from the final (cleaned) weight vector:

```python
w_arr = weights_raw
port_return = float(expected_returns @ w_arr)
port_variance = float(w_arr @ covariance_matrix @ w_arr)
port_vol = float(np.sqrt(port_variance))
sharpe = (port_return - risk_free_rate) / port_vol if port_vol > 0 else 0.0
```

### Example Output

```json
{
  "weights": [
    {"ticker": "AAPL", "weight": 0.35, "allocation": 35000.0, "sector": "Technology"},
    {"ticker": "MSFT", "weight": 0.40, "allocation": 40000.0, "sector": "Technology"},
    {"ticker": "GOOGL", "weight": 0.25, "allocation": 25000.0, "sector": "Communication Services"}
  ],
  "metrics": {
    "expected_return": 0.118,
    "volatility": 0.162,
    "sharpe_ratio": 0.607,
    "max_drawdown": null,
    "num_assets": 3
  },
  "solver_status": "optimal",
  "solve_time_ms": 12.4
}
```

---

## Complete Usage Example

```python
import numpy as np
from app.classical.optimizer import run_markowitz_mvo

tickers = ["AAPL", "MSFT", "GOOGL"]
expected_returns = np.array([0.15, 0.12, 0.10])
covariance_matrix = np.array([
    [0.04, 0.01, 0.008],
    [0.01, 0.03, 0.007],
    [0.008, 0.007, 0.025],
])

result = run_markowitz_mvo(
    tickers=tickers,
    expected_returns=expected_returns,
    covariance_matrix=covariance_matrix,
    budget=100_000.0,
    constraints={
        "max_weight_per_asset": 0.5,
        "min_return": 0.10,
        "max_volatility": 0.20,
        "sector_constraints": [],
        "sector_map": {},
        "objectives": [],
    },
)

print(f"Sharpe: {result.metrics.sharpe_ratio:.3f}")
print(f"Return: {result.metrics.expected_return:.1%}")
print(f"Volatility: {result.metrics.volatility:.1%}")
print(f"Solve time: {result.solve_time_ms:.1f} ms")
```

---

## Logging

The optimizer emits structured log events at key stages:

| Event | Level | Fields |
|-------|-------|--------|
| `classical_objective_built` | INFO | `mode`, `num_objectives`, `num_thresholds`, `num_deferred` |
| `classical_objective_deferred_measures` | INFO | `deferred` (list of warning strings) |
| `classical_optimization_complete` | INFO | `sharpe`, `expected_return`, `volatility`, `num_assets`, `solve_time_ms` |
| `cvxpy_primary_solver_failed` | WARNING | `error` |

---

## See Also

- [Multi-Objective Optimization](multi-objective.md) — how the `objectives` matrix is built and scalarized
- [Constraints](constraints.md) — all supported constraint types and infeasibility handling
- [Efficient Frontier](efficient-frontier.md) — epsilon-constraint sweep over the Pareto frontier
