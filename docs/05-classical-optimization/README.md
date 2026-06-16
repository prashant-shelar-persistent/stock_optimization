# Classical Optimization

Documentation for the Markowitz Mean-Variance Optimization (MVO) engine built with CVXPY — covering the optimizer, constraints, efficient frontier computation, and portfolio metrics.

## Section Contents

| Page | Description |
|------|-------------|
| [Markowitz MVO](../06-classical-optimization/markowitz-mvo.md) | Mean-variance optimization problem formulation and CVXPY implementation |
| [Multi-Objective](../06-classical-optimization/multi-objective.md) | Composite objective functions combining return, risk, and Sharpe ratio |
| [Constraints](../06-classical-optimization/constraints.md) | Budget equality, weight bounds, sector concentration, and risk constraints |
| [Efficient Frontier](../06-classical-optimization/efficient-frontier.md) | Epsilon-constraint sweep to trace the Pareto-optimal frontier |

## What Is Classical Optimization?

The classical optimization engine implements **Markowitz Mean-Variance Optimization (MVO)** — the foundational framework of modern portfolio theory. Given a set of assets with historical return and covariance data, MVO finds the portfolio weights that maximize the Sharpe ratio (or a user-defined composite objective) subject to a set of constraints.

```mermaid
graph LR
    A["Historical Prices<br/>(yfinance + Redis)"] --> B["Compute Returns<br/>& Covariance Matrix"]
    B --> C["CVXPY Problem<br/>Formulation"]
    C --> D["SCS / ECOS Solver"]
    D --> E["Optimal Weights<br/>+ Portfolio Metrics"]
    E --> F["Efficient Frontier<br/>(epsilon-constraint sweep)"]
```

## The Optimization Problem

The standard MVO problem solved by the engine:

**Maximize:** `(w^T μ - r_f) / sqrt(w^T Σ w)` (Sharpe ratio)

**Subject to:**
- `sum(w) = 1` (budget constraint)
- `w_min ≤ w_i ≤ w_max` (per-asset weight bounds)
- `sum(w_i for i in sector_k) ≤ sector_max_k` (sector concentration limits)
- `w^T μ ≥ min_return` (minimum return floor, optional)
- `sqrt(w^T Σ w) ≤ max_volatility` (maximum volatility ceiling, optional)

## Cross-References

- **Agent node that invokes this engine** → [Node: Classical Optimization](../05-agent-layer/node-classical.md)
- **Quantum alternative** → [Quantum Optimization](../07-quantum-optimization/qubo-formulation.md)
- **Performance comparison** → [Quantum vs Classical](../07-quantum-optimization/quantum-vs-classical.md)
- **Portfolio metrics computation** → [Portfolio Metrics](../08-data-layer/portfolio-metrics.md)
