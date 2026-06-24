# Performance & Parallelization Optimization Report

**Project:** Stock Portfolio Optimizer  
**Scope:** Backend pipeline (agents, classical solver, quantum dispatcher, data fetcher)  
**Date:** 2026-06-23

---

## Executive Summary

The pipeline has five high-impact performance issues, ordered by expected wall-clock savings:

| # | Issue | Location | Severity | Expected Gain |
|---|-------|----------|----------|---------------|
| 1 | QAOA and VQE run sequentially | `quantum/dispatcher.py` | **Critical** | ~50% of quantum time |
| 2 | Frontier sweep is a sequential loop of N CVXPY solves | `classical/frontier.py` | **High** | ~70–80% of frontier time |
| 3 | Sync nodes block the async event loop | `agents/graph.py` | **Already fixed** | `run_in_executor` already used |
| 4 | `_fetch_ticker_metadata` is sequential per-ticker | `data/fetcher.py` | **Medium** | ~(N-1)×metadata_latency |
| 5 | `_flag_dominance` is O(N²) | `classical/frontier.py` | **Low** | Negligible at N≤50, matters at N>100 |

---

## Issue 1 — QAOA and VQE Run Sequentially (Critical)

### Location
`backend/app/quantum/dispatcher.py`, function `run_quantum_optimization`, lines ~130–185.

### Problem
QAOA (`run_qaoa`) and VQE (`run_vqe`) are called one after the other with a plain `try/except` block each. Both solvers receive the **same** QUBO matrix and are completely independent of each other. With `qaoa_p=2` and `vqe_max_iter=100`, each solver takes 10–60 seconds on a simulated backend. Running them sequentially doubles the quantum stage latency.

```python
# CURRENT — sequential
qaoa_result = run_qaoa(...)   # blocks for ~30s
vqe_result  = run_vqe(...)    # blocks for another ~30s
# total: ~60s
```

### Fix
Run both solvers concurrently using `asyncio.gather` (since the graph runner is already inside an async context via `asyncio.run` in the Celery worker) or `concurrent.futures.ThreadPoolExecutor` (since the solvers are CPU-bound Python, not I/O-bound).

Because QAOA/VQE use Qiskit/PennyLane simulators that release the GIL during their C-extension work, `ThreadPoolExecutor` with 2 workers is the correct choice — it avoids the overhead of spawning a new process while still achieving true parallelism for the C-level computation.

**Patch — `backend/app/quantum/dispatcher.py`:**

```python
# Replace the sequential QAOA/VQE calls with concurrent execution.
# Add to imports at top of file:
from concurrent.futures import ThreadPoolExecutor, as_completed

# Replace the two sequential try/except blocks with:
qaoa_result = None
vqe_result  = None

def _run_qaoa() -> Any:
    return run_qaoa(
        tickers=tickers,
        qubo_matrix=qubo_matrix,
        expected_returns=expected_returns,
        covariance_matrix=covariance_matrix,
        budget=budget,
        num_assets_to_select=num_assets_to_select,
        p=qaoa_p,
    )

def _run_vqe() -> Any:
    return run_vqe(
        tickers=tickers,
        qubo_matrix=qubo_matrix,
        expected_returns=expected_returns,
        covariance_matrix=covariance_matrix,
        budget=budget,
        num_assets_to_select=num_assets_to_select,
        num_layers=vqe_layers,
        max_iterations=vqe_max_iter,
    )

with ThreadPoolExecutor(max_workers=2) as pool:
    future_qaoa = pool.submit(_run_qaoa)
    future_vqe  = pool.submit(_run_vqe)

    try:
        qaoa_result = future_qaoa.result()
        logger.info("qaoa_succeeded", sharpe=round(qaoa_result.metrics.sharpe_ratio, 4),
                    selected=qaoa_result.selected_assets,
                    solve_time_ms=round(qaoa_result.solve_time_ms, 1))
    except Exception as exc:
        logger.error("qaoa_failed", error=str(exc), error_type=type(exc).__name__, exc_info=True)

    try:
        vqe_result = future_vqe.result()
        logger.info("vqe_succeeded", sharpe=round(vqe_result.metrics.sharpe_ratio, 4),
                    selected=vqe_result.selected_assets,
                    solve_time_ms=round(vqe_result.solve_time_ms, 1))
    except Exception as exc:
        logger.error("vqe_failed", error=str(exc), error_type=type(exc).__name__, exc_info=True)
```

**Expected gain:** ~50% reduction in quantum stage wall-clock time (e.g. 60s → 30s).

---

## Issue 2 — Frontier Sweep is a Sequential Loop of N CVXPY Solves (High)

### Location
`backend/app/classical/frontier.py`, function `compute_frontier`, lines ~388–430.

### Problem
The epsilon-constraint sweep iterates over `num_points` (default 25) grid levels. Each iteration creates a fresh `cp.Variable`, builds a `cp.Problem`, and calls `problem.solve()`. These solves are **completely independent** — each one only depends on `eps` (a scalar from `np.linspace`) and the shared read-only data (`mu`, `cov`, `base_constraints`). There is no data dependency between iterations.

```python
# CURRENT — sequential, 25 independent CVXPY solves
for eps in eps_grid:          # 25 iterations
    w = cp.Variable(n, nonneg=True)
    ...
    problem.solve(solver=cp.CLARABEL, verbose=False)
    ...
```

With 25 points and ~0.5s per CVXPY solve (10 assets), the sweep takes ~12.5s. With parallelism across 4 cores it drops to ~3s.

### Fix
Use `ThreadPoolExecutor` to run all epsilon-constraint subproblems concurrently. `ThreadPoolExecutor` is preferred over `ProcessPoolExecutor` here for two reasons:

1. **CLARABEL and SCS are C extensions** — they release the GIL during their solver work, so threads achieve real parallelism for the computationally expensive portion.
2. **Closure pickling** — `_solve_one` is defined as a closure inside `compute_frontier` to capture local variables (`n`, `x_name`, `mu`, `cov`, etc.). Python closures are not picklable, which would cause `ProcessPoolExecutor` to fail with a `PicklingError`. Using `ThreadPoolExecutor` avoids this entirely.

**Patch — `backend/app/classical/frontier.py`:**

```python
# Add to imports (top of file):
import os

# Inside compute_frontier, replace the sequential for-loop with:
from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor

def _solve_one(eps: float) -> FrontierPoint | None:
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
    if problem.status in (cp.INFEASIBLE, cp.INFEASIBLE_INACCURATE) or w.value is None:
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
    _workers = min(num_points, os.cpu_count() or 4)
    with _ThreadPoolExecutor(max_workers=_workers) as _pool:
        _raw_results = list(_pool.map(_solve_one, eps_grid))
    points = [p for p in _raw_results if p is not None]
else:
    # Sequential fallback for small sweeps where thread overhead > gain.
    points = []
    for eps in eps_grid:
        pt = _solve_one(eps)
        if pt is not None:
            points.append(pt)
```

**Expected gain:** ~70–80% reduction in frontier sweep time (e.g. 12.5s → 3s on 4 cores).

---

## Issue 3 — Synchronous Nodes Block the Async Event Loop (Already Mitigated)

### Location
`backend/app/agents/graph.py`, `run_agent_graph` function.

### Status: ALREADY CORRECTLY HANDLED

`run_agent_graph` already offloads the entire synchronous LangGraph execution to a thread pool executor:

```python
loop = asyncio.get_running_loop()
final_state: AgentState = await loop.run_in_executor(
    None,
    lambda: compiled_graph.invoke(initial_state),
)
```

This means the entire graph (all nodes, including yfinance downloads, CVXPY solves, and LLM calls) runs in a thread pool worker, never blocking the FastAPI event loop. This is the correct and idiomatic pattern.

**No change required.** The existing implementation is correct.

---

## Issue 4 — `_fetch_ticker_metadata` is Sequential Per-Ticker (Medium)

### Location
`backend/app/data/fetcher.py`, function `_fetch_ticker_metadata`, lines ~430–470.

### Problem
Ticker metadata (sector, name, exchange) is fetched by calling `yf.Ticker(ticker).info` in a sequential `for ticker in tickers` loop. Each `.info` call is a separate HTTP request to Yahoo Finance (~200–500ms each). For 10 tickers this adds ~2–5s of purely sequential I/O.

```python
# CURRENT — sequential, one HTTP call per ticker
for ticker in tickers:
    info = yf.Ticker(ticker).info   # ~300ms per call
    ...
```

### Fix
Use `ThreadPoolExecutor` to fetch metadata concurrently. Since `.info` is I/O-bound (HTTP), threads are appropriate and the GIL is not a bottleneck.

```python
from concurrent.futures import ThreadPoolExecutor

def _fetch_one_ticker_metadata(ticker: str) -> tuple[str, dict]:
    """Fetch metadata for a single ticker. Returns (ticker, metadata_dict)."""
    try:
        info = yf.Ticker(ticker).info
        sector = info.get("sector") or "Unknown"
        return ticker, {
            "sector": sector,
            "name": info.get("longName") or info.get("shortName") or ticker,
            "industry": info.get("industry") or "Unknown",
            "exchange": info.get("exchange") or "Unknown",
            "currency": info.get("currency") or "USD",
            "market_cap": info.get("marketCap"),
        }
    except Exception as exc:
        logger.warning("ticker_metadata_fetch_failed", ticker=ticker, error=str(exc))
        return ticker, {
            "name": ticker, "sector": "Unknown", "industry": "Unknown",
            "exchange": "Unknown", "currency": "USD", "market_cap": None,
        }

def _fetch_ticker_metadata(tickers: list[str]) -> tuple[dict, dict]:
    max_workers = min(len(tickers), 8)  # cap at 8 to avoid Yahoo rate-limiting
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(_fetch_one_ticker_metadata, tickers))

    sector_map = {t: meta["sector"] for t, meta in results}
    metadata   = {t: meta for t, meta in results}
    return sector_map, metadata
```

**Expected gain:** ~(N-1)/N × metadata_latency. For 10 tickers: ~2.7s → ~0.5s (limited by the slowest single call).

---

## Issue 5 — `_flag_dominance` is O(N²) (Low)

### Location
`backend/app/classical/frontier.py`, function `_flag_dominance`, lines ~240–275.

### Problem
The dominance check uses a nested double loop over all pairs of points. For N=25 (default) this is 625 comparisons — negligible. But if `num_points` is increased to 100+, it becomes 10,000+ comparisons.

```python
# CURRENT — O(N²)
for i, p in enumerate(points):
    for j, q in enumerate(points):
        ...
```

### Fix
Since the points are already sorted along X after `points.sort(key=lambda p: p.x)`, a single-pass O(N log N) algorithm suffices: scan from left to right tracking the running maximum Y. A point is non-dominated iff its Y is strictly greater than all Y values of points to its left (for a minimize-X / maximize-Y frontier).

```python
def _flag_dominance(points, x_direction, y_direction):
    if len(points) <= 1:
        if points:
            points[0].is_dominant = True
        return

    # Points are pre-sorted ascending by X.
    # For minimize-X / maximize-Y: a point is dominant iff no point to its
    # left has a higher-or-equal Y (i.e. it improves Y as X increases).
    # General case: track running best Y from the left.
    if x_direction == "minimize" and y_direction == "maximize":
        best_y = float("-inf")
        for p in points:
            if p.y > best_y + 1e-9:
                p.is_dominant = True
                best_y = p.y
            else:
                p.is_dominant = False
    else:
        # Fall back to O(N²) for non-standard axis directions
        # (rare in practice — the default frontier is vol vs return)
        _flag_dominance_quadratic(points, x_direction, y_direction)
```

**Expected gain:** Negligible at N=25, but future-proofs the code for large sweeps.

---

## Additional Observations (No Code Change Required)

### A. Redis cache already exists for market data
`fetcher.py` already implements Redis caching with `_get_from_cache` / `_set_in_cache`. This is well-designed. No change needed.

### B. CVXPY problem is rebuilt on every call (optimizer.py)
`run_markowitz_mvo` reconstructs the full CVXPY problem on each invocation. CVXPY does not support warm-starting across separate `Problem` instances. The current approach is correct — warm-starting in CVXPY requires keeping the same `Problem` object alive between calls, which is not safe in a multi-worker Celery environment. No change recommended.

### C. yfinance `threads=False` is intentional
`_download_with_retry` passes `threads=False` to `yf.download`. This is a deliberate workaround for Yahoo Finance 429 rate-limiting (documented in the code). Do not change this.

### D. Celery task uses `asyncio.run()` correctly
`run_optimization_task` calls `asyncio.run(_execute_optimization(...))` to bridge the synchronous Celery worker to the async graph. This is the correct pattern. No change needed.

---

## Implementation Priority

Apply in this order to maximise impact with minimal risk:

1. **Issue 4** (metadata parallelism) — smallest change, zero risk, immediate gain
2. **Issue 1** (QAOA/VQE parallelism) — high impact, self-contained change in one function
3. **Issue 2** (frontier parallelism) — high impact, requires extracting a top-level helper
4. **Issue 3** (async node wrapping) — already correctly handled via `run_in_executor`; no change needed
5. **Issue 5** (O(N²) dominance) — low priority, only matters at large N

---

## File Change Summary

| File | Change | Lines Affected |
|------|--------|----------------|
| `backend/app/quantum/dispatcher.py` | Replace sequential QAOA/VQE with `ThreadPoolExecutor(2)` | ~130–185 |
| `backend/app/classical/frontier.py` | Add `_solve_one` closure + `ThreadPoolExecutor` sweep (CLARABEL/SCS release GIL) | ~385–430 |
| `backend/app/data/fetcher.py` | Replace sequential metadata loop with `ThreadPoolExecutor` | ~430–470 |
| `backend/app/agents/graph.py` | No change needed — `run_in_executor` already correctly used | — |
| `backend/app/classical/frontier.py` | O(N) dominance check for standard axis directions | ~240–275 |
