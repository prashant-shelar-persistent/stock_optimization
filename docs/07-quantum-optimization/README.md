# Quantum Optimization

Documentation for the quantum optimization engines — QUBO formulation, QAOA (Qiskit), VQE (PennyLane), the quantum dispatcher, and performance metrics comparing quantum vs. classical results.

## Section Contents

| Page | Description |
|------|-------------|
| [QUBO Formulation](qubo-formulation.md) | Encoding portfolio selection as a Quadratic Unconstrained Binary Optimization problem |
| [QAOA Solver](qaoa-solver.md) | Quantum Approximate Optimization Algorithm via Qiskit |
| [VQE Solver](vqe-solver.md) | Variational Quantum Eigensolver via PennyLane |
| [Quantum Dispatcher](quantum-dispatcher.md) | Solver selection, asset limit enforcement, and result aggregation |
| [Quantum vs Classical](quantum-vs-classical.md) | Side-by-side performance comparison and trade-off analysis |

## Quantum Optimization Pipeline

```mermaid
graph TD
    A["Portfolio Selection Problem"] --> B["QUBO Formulation<br/>(binary asset selection)"]
    B --> C["QAOA Circuit<br/>(Qiskit Aer)"]
    B --> D["VQE Circuit<br/>(PennyLane)"]
    C --> E["Quantum Dispatcher"]
    D --> E
    E --> F["Best Quantum Portfolio"]
```

## Practical Limits

| Constraint | Value | Reason |
|------------|-------|--------|
| Maximum assets | 8 (`MAX_QUANTUM_ASSETS`) | Exponential circuit depth growth |
| Execution queue | `quantum` Celery queue | Isolates slow quantum jobs |
| Simulator backend | Qiskit Aer / PennyLane default | No real quantum hardware required |
| QAOA layers (p) | 1–3 | Configurable via `QAOA_LAYERS` |

> **Note:** When `run_quantum=False` or the portfolio exceeds `MAX_QUANTUM_ASSETS`, the quantum dispatch node is skipped and the pipeline continues with classical results only.

## Cross-References

- **Agent node** → [Node: Quantum Dispatch](../05-agent-layer/node-quantum-dispatch.md)
- **Classical alternative** → [Markowitz MVO](../06-classical-optimization/markowitz-mvo.md)
- **Comparison logic** → [Node: Comparison](../05-agent-layer/node-comparison.md)
- **Queue routing** → [Queue Routing](../10-task-queue/queue-routing.md)
