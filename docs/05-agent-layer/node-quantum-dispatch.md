# Node: Quantum Dispatch

`quantum_dispatch_node` is the **fourth node** in the optimization pipeline (conditional). It converts the portfolio selection problem into a QUBO (Quadratic Unconstrained Binary Optimization) formulation and dispatches it to both the QAOA (Qiskit) and VQE (PennyLane) quantum solvers in sequence. The node is **non-fatal** — quantum failure does not block the comparison or explanation nodes.

**Source files:**
- Node: `backend/app/agents/nodes.py` — `quantum_dispatch_node()`
- Dispatcher: `backend/app/quantum/dispatcher.py` — `run_quantum_optimization()`
- QUBO builder: `backend/app/quantum/qubo.py` — `build_qubo_matrix()`
- QAOA solver: `backend/app/quantum/qaoa_solver.py` — `run_qaoa()`
- VQE solver: `backend/app/quantum/vqe_solver.py` — `run_vqe()`

## Responsibility

```
quantum_dispatch_node
    └── run_quantum_optimization(tickers, expected_returns, covariance_matrix, budget, constraints)
            ├── Asset count check (n <= MAX_QUANTUM_ASSETS)
            ├── Determine num_assets_to_select (k)
            ├── build_qubo_matrix(expected_returns, covariance_matrix, k, λ_return, λ_risk, λ_cardinality)
            ├── run_qaoa(tickers, qubo_matrix, ..., p=qaoa_p)
            ├── run_vqe(tickers, qubo_matrix, ..., num_layers=vqe_layers)
            └── Return QuantumResult(qaoa=..., vqe=...)
```

## Node Signature

```python
def quantum_dispatch_node(state: AgentState) -> AgentState:
    """Run QAOA (Qiskit) and VQE-style (PennyLane) quantum optimization."""
```

**Reads from state:** `tickers`, `expected_returns`, `covariance_matrix`, `budget`, `validated_constraints`

**Writes to state:** `quantum_result`, `constraint_warnings` (on failure), `node_timings_ms`, `completed_nodes`

**Fatal on failure:** **No** — quantum failure appends a warning to `constraint_warnings` but does NOT set `state["error"]`. The run continues with only the classical result.

## Asset Limit Check (`MAX_QUANTUM_ASSETS`)

The graph's routing function (`_should_run_quantum()`) checks the asset count **before** this node is called. If `len(tickers) > MAX_QUANTUM_ASSETS` (default: 8), the graph routes directly to `comparison`, skipping this node entirely:

```python
settings = get_settings()
if len(tickers) > settings.MAX_QUANTUM_ASSETS:
    logger.warning("quantum_skipped_too_many_assets", ...)
    return "skip_quantum"
```

Inside the dispatcher, a second check raises `QuantumAssetLimitError` as a safety net:

```python
if n > settings.MAX_QUANTUM_ASSETS:
    raise QuantumAssetLimitError(
        num_assets=n,
        max_assets=settings.MAX_QUANTUM_ASSETS,
    )
```

The `MAX_QUANTUM_ASSETS` limit exists because QAOA/VQE complexity grows exponentially with the number of qubits (one qubit per asset). The default limit of 8 assets corresponds to 8-qubit circuits, which are tractable on simulators.

## QUBO Construction

The QUBO matrix encodes the portfolio selection problem as a binary optimization:

```
minimise  x^T Q x
subject to:  x ∈ {0, 1}^n,  sum(x) = k
```

where `x_i = 1` means asset `i` is selected. The QUBO matrix `Q` is built from:

```python
qubo_matrix = build_qubo_matrix(
    expected_returns=expected_returns,
    covariance_matrix=covariance_matrix,
    num_assets_to_select=num_assets_to_select,
    lambda_return=lambda_return,      # default: 1.0
    lambda_risk=lambda_risk,          # default: 1.0
    lambda_cardinality=lambda_cardinality,  # default: 5.0
)
```

The QUBO formulation combines three terms:
- **Return term** (`λ_return`): Reward for selecting high-return assets
- **Risk term** (`λ_risk`): Penalty for correlated asset pairs
- **Cardinality penalty** (`λ_cardinality`): Enforces exactly `k` assets selected

The same QUBO matrix is shared between QAOA and VQE to ensure they solve the same problem.

### QUBO Parameters from Constraints

The dispatcher reads tuning parameters from `validated_constraints`:

| Parameter | Key in constraints | Default |
|---|---|---|
| Number of assets to select | `num_assets_to_select` | `max(2, int(n * 0.5))` |
| Return weight | `lambda_return` | `1.0` |
| Risk weight | `lambda_risk` | `1.0` |
| Cardinality penalty | `lambda_cardinality` | `5.0` |
| QAOA circuit depth | `qaoa_p` | `2` |
| VQE ansatz layers | `vqe_layers` | `2` |
| VQE max iterations | `vqe_max_iter` | `100` |

## QAOA Execution (Qiskit)

QAOA is run first using the Qiskit-based solver:

```python
qaoa_result = run_qaoa(
    tickers=tickers,
    qubo_matrix=qubo_matrix,
    expected_returns=expected_returns,
    covariance_matrix=covariance_matrix,
    budget=budget,
    num_assets_to_select=num_assets_to_select,
    p=qaoa_p,
)
```

The QAOA solver:
1. Encodes the QUBO as a Qiskit `SparsePauliOp` cost Hamiltonian
2. Builds a QAOA circuit with `p` layers (default: 2)
3. Optimises circuit parameters using COBYLA
4. Samples the circuit to find the best binary string
5. Converts the selected assets to equal-weight portfolio metrics

The result is a `QAOAResult` with `selected_assets`, `weights`, `metrics`, `circuit_depth`, `num_qubits`, and `solve_time_ms`.

## VQE Execution (PennyLane)

VQE is run after QAOA using the PennyLane-based solver:

```python
vqe_result = run_vqe(
    tickers=tickers,
    qubo_matrix=qubo_matrix,
    expected_returns=expected_returns,
    covariance_matrix=covariance_matrix,
    budget=budget,
    num_assets_to_select=num_assets_to_select,
    num_layers=vqe_layers,
    max_iterations=vqe_max_iter,
)
```

The VQE solver:
1. Builds a PennyLane variational ansatz with `num_layers` layers
2. Minimises the QUBO energy expectation value using gradient descent
3. Samples the optimised circuit to find the best binary string
4. Converts the selected assets to equal-weight portfolio metrics

The result is a `VQEResult` with `selected_assets`, `weights`, `metrics`, `num_qubits`, and `solve_time_ms`.

## Parallel vs Sequential Execution

Both QAOA and VQE are run **sequentially** in the current implementation. Each solver is wrapped in its own `try/except` block so that a failure in one does not prevent the other from running:

```python
qaoa_result = None
try:
    qaoa_result = run_qaoa(...)
except Exception as exc:
    logger.error("qaoa_failed", ...)

vqe_result = None
try:
    vqe_result = run_vqe(...)
except Exception as exc:
    logger.error("vqe_failed", ...)

return QuantumResult(qaoa=qaoa_result, vqe=vqe_result)
```

Either `qaoa` or `vqe` (or both) may be `None` in the returned `QuantumResult`.

## `QuantumResult` Serialisation

The `QuantumResult` Pydantic model is serialised to a plain dict via `.model_dump()`:

```python
updated["quantum_result"] = result.model_dump()
```

The serialised structure:

```python
class QuantumResult(BaseModel):
    qaoa: QAOAResult | None = None
    vqe: VQEResult | None = None
```

## Non-Fatal Error Handling

If the entire quantum dispatch fails (e.g. `QuantumAssetLimitError`, import error, or unexpected exception), the node appends a warning to `constraint_warnings` but does **not** set `state["error"]`:

```python
except Exception as exc:
    existing_warnings = list(state.get("constraint_warnings") or [])
    existing_warnings.append(
        f"Quantum optimization failed: {type(exc).__name__}: {exc}"
    )
    updated["constraint_warnings"] = existing_warnings
    # NOTE: state["error"] is NOT set — quantum failure is non-fatal
    _record_timing(updated, "quantum_dispatch", elapsed_ms)
    _record_completed(updated, "quantum_dispatch")
    return updated
```

The warning is later surfaced in the LLM explanation so the user understands why quantum results are absent.

## Related Pages

- [Agent State](agent-state.md) — Full state field reference
- [Node: Classical Optimization](node-classical.md) — Runs before quantum dispatch
- [Node: Comparison](node-comparison.md) — Consumes `quantum_result`
- [Error Routing](error-routing.md) — `_should_run_quantum()` and quantum skip logic

## Quantum Optimization Cross-References

- [QUBO Formulation](../07-quantum-optimization/qubo-formulation.md) — How the portfolio problem is encoded as a QUBO
- [QAOA Solver](../07-quantum-optimization/qaoa-solver.md) — Qiskit QAOA circuit and optimization details
- [VQE Solver](../07-quantum-optimization/vqe-solver.md) — PennyLane VQE implementation details
- [Quantum Dispatcher](../07-quantum-optimization/quantum-dispatcher.md) — The dispatcher function called by this node
- [Quantum vs Classical](../07-quantum-optimization/quantum-vs-classical.md) — Performance comparison and when quantum helps
- [Queue Routing](../10-task-queue/queue-routing.md) — How quantum tasks are routed to the dedicated queue
