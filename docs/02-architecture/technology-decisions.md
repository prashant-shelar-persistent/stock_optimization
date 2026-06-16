# Technology Decisions

This page documents the rationale behind each major technology choice in the Portfolio Optimizer. Understanding *why* a technology was selected — and what alternatives were considered — helps contributors make consistent decisions when extending the system.

## FastAPI (Web Framework)

**Chosen:** FastAPI 0.111+ with Uvicorn (ASGI server)

**Rationale:**

FastAPI was selected as the web framework for three primary reasons:

### 1. Native Async Support

Portfolio optimization involves multiple I/O-bound operations: fetching price data from yfinance, reading/writing to PostgreSQL, publishing to Redis, and calling the OpenAI API. FastAPI's ASGI foundation means all of these can be awaited concurrently without blocking the event loop. A single Uvicorn worker can handle hundreds of concurrent WebSocket connections while Celery workers process optimization tasks in the background.

```python
# FastAPI's async handlers integrate naturally with SQLAlchemy async sessions
async def submit_optimization(request: OptimizationRequest, db: DbDep) -> OptimizationSubmitResponse:
    run = OptimizationRun(run_id=run_id, status="pending", ...)
    db.add(run)
    await db.flush()  # Non-blocking DB write
    ...
```

### 2. Pydantic v2 Integration

FastAPI uses Pydantic models for request/response validation. This provides:
- **Automatic JSON schema generation** — The OpenAPI spec is derived directly from the Pydantic models, keeping documentation in sync with the code.
- **Type-safe validation** — All incoming request data is validated and coerced before reaching handler code. Invalid requests return structured 422 errors automatically.
- **Serialization control** — `model_dump(mode="json")` produces JSON-safe dicts for storage in PostgreSQL JSON columns.

The `OptimizationRequest` schema (`backend/app/schemas/requests.py`) uses Pydantic validators to enforce business rules like minimum budget, valid ticker formats, and objective weight normalization.

### 3. Dependency Injection

FastAPI's `Depends()` system provides clean dependency injection for database sessions, Redis connections, and settings. This makes testing straightforward — dependencies can be overridden in tests without modifying handler code.

**Alternatives considered:**
- **Django REST Framework** — Too heavyweight; Django's ORM is synchronous and would require `django-channels` for WebSocket support, adding significant complexity.
- **Starlette (bare)** — FastAPI is built on Starlette; using Starlette directly would require reimplementing validation, OpenAPI generation, and dependency injection.
- **Flask** — Synchronous by default; async support via `flask[async]` is bolted on and lacks the ergonomics of FastAPI.

---

## LangGraph (Agent Orchestration)

**Chosen:** LangGraph 0.1+ with `StateGraph`

**Rationale:**

The optimization pipeline has a complex, branching control flow that is difficult to express cleanly as a linear sequence of function calls. LangGraph provides a graph-based abstraction that makes the control flow explicit and inspectable.

### Why a Graph, Not a Simple Pipeline?

The pipeline has three types of conditional logic:

1. **Fatal error routing** — If data fetch fails, skip all downstream nodes immediately.
2. **Feature flags** — Quantum optimization is optional; the graph routes around it when disabled.
3. **Conditional bonus steps** — Frontier computation only runs when explicitly requested.

Expressing this with `if/else` chains in a single function would produce deeply nested, hard-to-test code. LangGraph's `add_conditional_edges()` makes each routing decision explicit and independently testable.

### Stateful Shared Context

LangGraph's `StateGraph` passes a single `AgentState` TypedDict through all nodes. This eliminates the need to pass dozens of parameters between functions and makes it easy to add new fields (e.g., `frontier_report`) without changing existing node signatures.

### Observability

LangGraph's graph structure enables the `wrap_node` pattern — a single decorator that adds progress event publishing, timing, and error handling to every node without modifying the node functions. This separation of concerns keeps node functions pure and testable.

**Alternatives considered:**
- **Celery chains/chords** — Celery's workflow primitives (chains, groups, chords) can express sequential and parallel tasks, but they lack shared state and conditional routing. Each task would need to pass its full output to the next, creating large message payloads.
- **Prefect / Airflow** — Designed for data pipeline orchestration with scheduling, retries, and monitoring. Too heavyweight for a request-scoped pipeline that runs in milliseconds to seconds.
- **Plain Python functions** — A simple `run_pipeline()` function with `if/else` routing would work for the current complexity but would become unmaintainable as new nodes are added.

---

## CVXPY (Classical Optimization)

**Chosen:** CVXPY 1.5+ with the default CLARABEL/ECOS solver

**Rationale:**

Markowitz Mean-Variance Optimization is a **convex quadratic program** (QP). CVXPY is the standard Python library for expressing and solving convex optimization problems using a disciplined convex programming (DCP) framework.

### DCP Guarantees

CVXPY's DCP checker verifies at construction time that the problem is convex. This prevents subtle bugs where a non-convex objective or constraint is silently accepted and produces incorrect results. If a user-supplied objective (e.g., maximizing Sharpe ratio directly) is non-convex, CVXPY rejects it at problem construction — not at solve time.

### Multi-Objective Scalarization

The multi-objective extension (`backend/app/classical/optimizer.py`) builds a weighted-sum objective from user-defined business objectives. CVXPY's expression algebra makes it natural to compose these:

```python
# Each measure returns a CVXPY expression
expr, scale = _measure_expression(name, w, expected_returns, covariance_matrix, ...)
signed = expr / scale if scale > 0 else expr
if direction == "minimize":
    signed = -signed
objective_terms.append(weight * signed)

# Combine into a single maximization objective
problem = cp.Problem(cp.Maximize(cp.sum(cp.hstack(objective_terms))), constraints)
```

### Solver Flexibility

CVXPY supports multiple backend solvers (CLARABEL, ECOS, SCS, MOSEK, Gurobi). The default open-source solvers (CLARABEL for QPs, ECOS for SOCPs) are sufficient for portfolios up to ~500 assets. Commercial solvers can be plugged in for larger problems without changing the problem formulation.

**Alternatives considered:**
- **scipy.optimize** — Lower-level; requires manual gradient computation and constraint Jacobians. No DCP checking.
- **PyPortfolioOpt** — Higher-level wrapper around CVXPY, but less flexible for custom multi-objective formulations.
- **Gurobi / CPLEX** — Commercial solvers with Python APIs. More powerful for large-scale problems but require licenses.

---

## Qiskit + PennyLane (Quantum Simulation)

**Chosen:** Qiskit 1.1+ (QAOA) and PennyLane 0.36+ (VQE)

**Rationale:**

Running both QAOA and VQE provides a meaningful comparison between two distinct quantum optimization approaches, which is central to the application's educational purpose.

### Qiskit for QAOA

Qiskit's `qiskit-optimization` package provides a high-level `MinimumEigenOptimizer` that wraps QAOA with a `QuadraticProgram` interface. This makes it straightforward to convert the QUBO matrix to a quantum circuit without implementing the QAOA circuit manually:

```python
# From backend/app/engines/quantum/qaoa_qiskit.py
from qiskit_optimization.algorithms import MinimumEigenOptimizer
from qiskit_algorithms import QAOA

qaoa = QAOA(sampler=Sampler(), optimizer=COBYLA(), reps=p)
optimizer = MinimumEigenOptimizer(qaoa)
result = optimizer.solve(quadratic_program)
```

Qiskit Aer's statevector simulator provides exact quantum state simulation, which is appropriate for the small circuits used here (≤8 qubits).

### PennyLane for VQE

PennyLane's differentiable programming model makes it natural to implement VQE with gradient-based optimization. The QUBO-to-Ising transformation and hardware-efficient ansatz are implemented explicitly, giving full control over the circuit structure:

```python
# From backend/app/engines/quantum/vqe_pennylane.py
@qml.qnode(dev)
def circuit(params):
    # Hardware-efficient ansatz: Ry rotations + CNOT entanglement
    for layer in range(num_layers):
        for i in range(n_qubits):
            qml.RY(params[layer, i], wires=i)
        for i in range(n_qubits - 1):
            qml.CNOT(wires=[i, i + 1])
    return qml.expval(hamiltonian)
```

### Graceful Degradation

Both solvers implement a **greedy fallback** strategy: if Qiskit or PennyLane is not installed (e.g., in a lightweight CI environment), the solver falls back to selecting the top-k assets by expected return. This ensures the system degrades gracefully rather than crashing.

**Alternatives considered:**
- **D-Wave Ocean SDK** — Targets real quantum annealing hardware. Requires a D-Wave account and introduces network latency. Not suitable for a local simulation environment.
- **Cirq (Google)** — Lower-level circuit library without built-in QAOA/VQE implementations. Would require more boilerplate.
- **Using only one quantum framework** — Running both QAOA and VQE provides a richer comparison and demonstrates the system's extensibility.

---

## Redis (Cache + Pub/Sub + Broker)

**Chosen:** Redis 7 Alpine with three logical databases

**Rationale:**

Redis serves three distinct roles in the system, all on the same Redis instance but on separate logical databases:

### Role 1: Price Data Cache (DB 0)

yfinance API calls are expensive (network latency, rate limits). Price data for a given set of tickers and lookback period is cached in Redis with a configurable TTL (default: 3600 seconds). The cache key includes the ticker list and lookback period, so different requests with the same parameters share the cached data.

```python
# From backend/app/data/cache.py
cache.set(f"price_data:{sorted_tickers}:{lookback_days}", market_data, ttl=3600)
```

### Role 2: Progress Event Bus (DB 0, pub/sub)

Redis pub/sub bridges the Celery worker process and the FastAPI WebSocket handler. The worker publishes JSON progress events to `run:{run_id}:progress`; the WebSocket handler subscribes and forwards them to the browser. This is the only mechanism that enables real-time streaming without polling.

### Role 3: Celery Broker + Result Backend (DB 1, DB 2)

Celery uses Redis as both the message broker (task queue) and the result backend (task state storage). Using Redis for both avoids the operational complexity of running a separate RabbitMQ instance.

### Why Redis Over Alternatives?

| Requirement | Redis | RabbitMQ | Kafka |
|-------------|-------|----------|-------|
| Pub/sub for progress events | ✅ Native | ❌ Requires AMQP exchange | ✅ But heavyweight |
| Celery broker | ✅ Supported | ✅ Native | ✅ Supported |
| Key-value cache | ✅ Native | ❌ Not a cache | ❌ Not a cache |
| Operational simplicity | ✅ Single service | ❌ Separate service | ❌ Separate service |

Redis's ability to serve all three roles from a single service significantly reduces operational complexity.

**Redis configuration** (from `docker-compose.yml`):
```yaml
command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
```

The `allkeys-lru` eviction policy ensures Redis never runs out of memory — it evicts the least-recently-used keys when the memory limit is reached. This is appropriate for a cache workload where stale data is acceptable.

---

## Celery (Task Isolation)

**Chosen:** Celery 5.4+ with Redis broker

**Rationale:**

Quantum optimization jobs (QAOA/VQE) can run for 60+ seconds and are CPU-intensive. Running them in the FastAPI event loop would block all other requests. Celery provides:

### Process Isolation

Each Celery task runs in a separate worker process (prefork model). A quantum job that consumes 100% CPU for 60 seconds does not affect the FastAPI server's ability to accept new requests or serve WebSocket connections.

### Two-Queue Architecture

The system uses two separate queues with dedicated worker pools:

```yaml
# docker-compose.yml
worker:         # default queue — classical runs, concurrency=4
worker-quantum: # quantum queue — QAOA/VQE runs, concurrency=2
```

This prevents a backlog of slow quantum jobs from blocking fast classical-only runs. The `quantum` queue has lower concurrency because each QAOA/VQE simulation is CPU-bound and running multiple simultaneously would cause resource contention.

### Reliability Features

```python
# From backend/app/workers/celery_app.py
task_acks_late=True,           # Acknowledge only after task completes
task_reject_on_worker_lost=True,  # Re-queue if worker crashes
worker_prefetch_multiplier=1,  # Fetch one task at a time per worker
```

`acks_late=True` combined with `reject_on_worker_lost=True` ensures that if a worker process is killed mid-task (e.g., OOM kill), the task is re-queued rather than silently lost.

### Retry Policy

Transient failures (network errors, database timeouts) are retried up to 3 times with exponential backoff (30s, 60s, 120s). `SoftTimeLimitExceeded` (quantum timeout) is not retried because the timeout is deterministic — retrying would just time out again.

**Alternatives considered:**
- **FastAPI BackgroundTasks** — Runs in the same process as the API server. A CPU-intensive quantum job would block the event loop.
- **asyncio.create_task()** — Same problem as BackgroundTasks; no process isolation.
- **RQ (Redis Queue)** — Simpler than Celery but lacks soft time limits, retry policies, and the two-queue architecture needed for quantum/classical separation.

---

## PostgreSQL (Run History)

**Chosen:** PostgreSQL 16 with SQLAlchemy async + asyncpg driver

**Rationale:**

### Durable Run History

Every optimization run is persisted to PostgreSQL with its full input parameters, results, and status. This enables:
- **Run history browsing** — Users can view past runs via `GET /api/v1/runs`.
- **Audit trail** — The full `request_params` JSON column stores the exact request that produced each result.
- **Crash recovery** — If the Celery worker crashes, the run record remains in `pending` or `running` state and can be retried.

### JSON Columns for Rich Results

The `classical_result`, `quantum_result`, `comparison`, and `frontier_report` columns use PostgreSQL's native `JSON` type. This avoids over-normalization — the nested result structures (weights, metrics, circuit metadata) don't benefit from relational decomposition and are always read/written as a unit.

### Denormalized Sharpe Columns

The `classical_sharpe` and `quantum_sharpe` columns are denormalized from the JSON result blobs. This allows efficient list queries (`ORDER BY classical_sharpe DESC`) without deserializing the full JSON:

```python
# From backend/app/db/models.py
classical_sharpe: Mapped[float | None] = mapped_column(
    Float, nullable=True,
    comment="Denormalised classical Sharpe ratio for list query performance",
)
```

### Async Driver (asyncpg)

The `asyncpg` driver provides native async PostgreSQL support, allowing database operations to be awaited without blocking the FastAPI event loop. SQLAlchemy's async session (`AsyncSession`) wraps asyncpg with the familiar ORM interface.

### Alembic Migrations

Schema changes are managed via Alembic migrations (`backend/alembic/versions/`). The Docker Compose `backend` service runs `alembic upgrade head` on startup, ensuring the schema is always up to date.

**Alternatives considered:**
- **MongoDB** — Document store would be natural for the JSON result blobs, but PostgreSQL's JSON support is sufficient and avoids introducing a second database technology.
- **SQLite** — Not suitable for production; lacks concurrent write support and the `asyncpg` driver.
- **DynamoDB / Firestore** — Cloud-native options that would introduce vendor lock-in and require significant infrastructure changes.

---

## Summary Table

| Technology | Version | Role | Key Reason |
|-----------|---------|------|-----------|
| FastAPI | 0.111+ | Web framework | Async, Pydantic integration, WebSocket support |
| Uvicorn | 0.30+ | ASGI server | High-performance async HTTP/WebSocket |
| Pydantic v2 | 2.7+ | Data validation | Type-safe schemas, OpenAPI generation |
| LangGraph | 0.1+ | Agent orchestration | Stateful graph, conditional routing, observability |
| CVXPY | 1.5+ | Classical optimization | DCP framework, multi-objective scalarization |
| Qiskit | 1.1+ | QAOA solver | High-level QAOA API, Aer simulator |
| PennyLane | 0.36+ | VQE solver | Differentiable quantum circuits |
| Redis | 7 | Cache + pub/sub + broker | Single service for three roles |
| Celery | 5.4+ | Task queue | Process isolation, two-queue architecture |
| PostgreSQL | 16 | Run history | Durable storage, JSON columns, async driver |
| SQLAlchemy | 2.0+ | ORM | Async sessions, Alembic integration |
| yfinance | 0.2.40+ | Market data | Free, no API key required |
| structlog | 24.0+ | Structured logging | JSON log output, context binding |

## Related Pages

- [System Overview](system-overview.md) — How all these technologies fit together
- [Request Lifecycle](request-lifecycle.md) — FastAPI, Redis, and Celery in action
- [Agent Pipeline](agent-pipeline.md) — LangGraph in detail
