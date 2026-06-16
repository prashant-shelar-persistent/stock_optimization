# Backend Tests

The backend test suite is a comprehensive collection of unit, integration, and end-to-end tests
written with **pytest** and **pytest-asyncio**. Tests live in the `tests/` directory at the
workspace root and are run from the `backend/` directory where `pyproject.toml` is located.

## pytest Configuration

All pytest settings are declared in `backend/pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["../tests"]
addopts = "--cov=app --cov-report=term-missing -v"
```

| Option | Value | Purpose |
|--------|-------|---------|
| `asyncio_mode` | `"auto"` | All `async def` test functions are automatically treated as asyncio coroutines — no `@pytest.mark.asyncio` decorator required (though it is still used for clarity) |
| `testpaths` | `["../tests"]` | Points pytest at the `tests/` directory one level above `backend/` |
| `addopts` | `--cov=app --cov-report=term-missing -v` | Enables coverage collection on the `app` package, prints missing lines, and uses verbose output |

### Running the Suite

```bash
# From the backend/ directory
cd backend
python -m pytest -v

# Run a single test file
python -m pytest ../tests/test_api_health.py -v

# Run a specific test function
python -m pytest ../tests/test_api_health.py::test_health_all_up_returns_200_healthy -v

# Run with coverage report
python -m pytest --cov=app --cov-report=html
```

---

## `conftest.py` Fixtures

### Root `tests/conftest.py`

The root conftest provides **shared numpy/pandas fixtures** used across unit tests for
classical and quantum optimization. All fixtures use a deterministic random seed (`seed=42`)
for reproducibility.

```python
RNG = np.random.default_rng(seed=42)
```

#### 3-Asset Universe Fixtures

| Fixture | Type | Description |
|---------|------|-------------|
| `tickers_3` | `list[str]` | `["AAPL", "MSFT", "GOOGL"]` |
| `expected_returns_3` | `np.ndarray` | Annualised returns `[0.12, 0.10, 0.09]` |
| `cov_matrix_3` | `np.ndarray` | 3×3 positive-definite covariance matrix |
| `returns_df_3` | `pd.DataFrame` | 250 days of simulated daily log returns |

#### 4-Asset Universe Fixtures

| Fixture | Type | Description |
|---------|------|-------------|
| `tickers_4` | `list[str]` | `["AAPL", "MSFT", "GOOGL", "AMZN"]` |
| `expected_returns_4` | `np.ndarray` | Annualised returns `[0.12, 0.10, 0.09, 0.15]` |
| `cov_matrix_4` | `np.ndarray` | 4×4 positive-definite covariance matrix |
| `sector_tags_4` | `dict[str, str]` | GICS sector mapping for 4 assets |

**Example usage:**

```python
def test_optimizer_3_assets(
    tickers_3: list[str],
    expected_returns_3: np.ndarray,
    cov_matrix_3: np.ndarray,
) -> None:
    optimizer = ClassicalOptimizer()
    result = optimizer.optimize(make_input(tickers_3, expected_returns_3, cov_matrix_3))
    assert abs(sum(w.weight for w in result.weights) - 1.0) < 1e-6
```

### Integration `tests/integration/conftest.py`

The integration conftest provides **HTTP client and database mock fixtures** for API endpoint tests.

#### `client` Fixture

```python
@pytest_asyncio.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac
```

Uses `httpx.ASGITransport` to wire the FastAPI app directly — no real network socket is opened.
Each test gets a fresh client to prevent state leakage.

#### Mock DB Session Helpers

Three factory functions build `AsyncMock` sessions for different query patterns:

| Helper | Use Case |
|--------|----------|
| `make_mock_session()` | Write endpoints (POST /optimize) — no-ops on `add`, `flush`, `commit` |
| `make_mock_session_for_list(runs, total)` | List queries — handles two `execute` calls: COUNT then rows |
| `make_mock_session_for_single(run)` | Single-row lookups — `scalar_one_or_none()` returns the run or `None` |

#### `OptimizationRun` Factory

```python
def make_run(
    run_id: str | None = None,
    status: str = "completed",
    tickers: list[str] | None = None,
    budget: float = 100_000.0,
    classical_sharpe: float | None = 1.25,
    ...
) -> OptimizationRun:
```

Builds an in-memory `OptimizationRun` ORM object without touching the database.

#### Standard Request Payloads

```python
MINIMAL_REQUEST = {"tickers": ["AAPL", "MSFT"], "budget": 50_000.0, "run_quantum": False}
STANDARD_REQUEST = {"tickers": ["AAPL", "MSFT", "GOOGL"], "budget": 100_000.0, "run_quantum": False}
QUANTUM_REQUEST  = {"tickers": ["AAPL", "MSFT", "GOOGL"], "budget": 100_000.0, "run_quantum": True}
FULL_REQUEST     = {... all optional fields including sector_constraints ...}
```

#### DB Override Helper

```python
def override_db_with(session: AsyncMock):
    async def _override():
        yield session
    return _override
```

Used with `app.dependency_overrides[get_db] = override_db_with(mock_session)` to inject mock
sessions into FastAPI's dependency injection system.

---

## Test File Inventory

### API Endpoint Tests

#### `test_api_health.py`
Tests for `GET /health`. Patches `_check_database`, `_check_redis`, and `_check_celery` to
control service status without real connections.

| Test | Scenario |
|------|----------|
| `test_health_all_up_returns_200_healthy` | All services up → HTTP 200, `status=healthy` |
| `test_health_response_shape` | Body has `status`, `version`, `services` fields |
| `test_health_services_shape` | `services` has `database`, `redis`, `celery` keys |
| `test_health_all_down_returns_503_unhealthy` | All down → HTTP 503, `status=unhealthy` |
| `test_health_db_down_returns_degraded` | DB down only → HTTP 200, `status=degraded` |
| `test_health_redis_down_returns_degraded` | Redis down only → degraded |
| `test_health_celery_down_returns_degraded` | Celery down only → degraded |
| `test_health_version_is_semver_like` | Version string matches `\d+\.\d+\.\d+` |

#### `test_api_assets.py`
Tests for `GET /api/v1/assets/search`. Uses real in-memory asset registry; patches
`_lookup_yfinance` for fallback tests.

| Test | Scenario |
|------|----------|
| `test_search_exact_ticker_returns_result` | `q=AAPL` returns Apple Inc. |
| `test_search_aapl_returns_technology_sector` | AAPL has `sector=Technology`, `exchange=NASDAQ` |
| `test_search_by_company_name` | `q=Microsoft` returns MSFT |
| `test_search_case_insensitive_ticker` | `q=nvda` == `q=NVDA` |
| `test_search_limit_zero_returns_422` | `limit=0` → 422 validation error |
| `test_search_limit_over_50_returns_422` | `limit=51` → 422 validation error |
| `test_search_unknown_ticker_yfinance_fallback` | Unknown ticker triggers yfinance lookup |
| `test_search_unknown_ticker_yfinance_returns_none` | yfinance returns None → empty list |

#### `test_api_optimize.py`
Tests for `POST /api/v1/optimize`. Mocks the DB session and Celery task dispatch.

| Test | Scenario |
|------|----------|
| `test_optimize_valid_request_returns_202` | Valid request → HTTP 202 |
| `test_optimize_returns_valid_uuid_run_id` | `run_id` is a valid UUID string |
| `test_optimize_missing_tickers_returns_422` | Missing `tickers` → 422 |
| `test_optimize_negative_budget_returns_422` | `budget=-1` → 422 |
| `test_optimize_celery_task_dispatched` | `apply_async` called with correct args |
| `test_optimize_quantum_routes_to_quantum_queue` | `run_quantum=True` → `queue="quantum"` |

#### `test_api_runs.py`
Tests for `GET /api/v1/runs` and `GET /api/v1/runs/{run_id}`. Uses mock DB sessions.

| Test | Scenario |
|------|----------|
| `test_runs_empty_list_returns_200` | Empty DB → `{"items": [], "total": 0}` |
| `test_runs_returns_paginated_list` | Returns correct `items`, `total`, `page` |
| `test_runs_status_filter` | `?status=completed` returns only completed runs |
| `test_runs_invalid_status_returns_422` | `?status=invalid` → 422 |
| `test_run_detail_returns_full_shape` | Detail endpoint returns all fields |
| `test_run_detail_unknown_id_returns_404` | Unknown `run_id` → 404 with `error_code` |
| `test_run_status_completed_has_completed_at` | Completed run has `completed_at` timestamp |

#### `test_api_websocket.py`
Tests for `WS /ws/runs/{run_id}/progress`. Tests the `_safe_send_json` helper and
Redis pub/sub message forwarding.

| Test | Scenario |
|------|----------|
| `test_safe_send_json_sends_data` | Calls `websocket.send_json` with data |
| `test_safe_send_json_swallows_exception` | RuntimeError on send → no raise |
| `test_safe_send_json_swallows_disconnect_error` | `WebSocketDisconnect` → no raise |
| `test_websocket_accepts_connection` | WebSocket connection is accepted |
| `test_progress_message_forwarded` | Redis progress message → WebSocket client |
| `test_result_message_terminates_stream` | `type=result` message closes stream |
| `test_error_message_terminates_stream` | `type=error` message closes stream |
| `test_invalid_json_silently_skipped` | Malformed Redis message → skipped |

### Task Queue Tests

#### `test_celery_tasks.py`
Tests for `OptimizationTask` and Celery app configuration. Uses a mocked Redis client.

```python
def _make_task_instance() -> OptimizationTask:
    task = OptimizationTask()
    task._redis_client = MagicMock()
    task._redis_client.publish = MagicMock(return_value=1)
    return task
```

| Test Group | Coverage |
|------------|----------|
| `publish_progress` | Channel name, JSON fields (`type`, `run_id`, `node`, `status`, `message`, `timestamp`), Redis exception swallowing |
| `publish_result` | Channel name, JSON fields (`type`, `run_id`, `result`), exception swallowing |
| `publish_error` | Channel name, JSON fields (`type`, `run_id`, `error_code`, `message`, `timestamp`), exception swallowing |
| Celery app config | `default` and `quantum` queues, JSON serializer, UTC timezone, `prefetch_multiplier=1`, `acks_late=True`, `reject_on_worker_lost=True` |
| Task registration | `run_optimization_task` in `celery_app.tasks`, `max_retries=3`, `acks_late=True` |
| Redis lazy init | `redis_client` property creates client on first access, reuses on subsequent calls |

### Optimization Engine Tests

#### `test_classical_optimizer.py`
Unit tests for `ClassicalOptimizer` (Markowitz MVO via CVXPY).

| Test | Scenario |
|------|----------|
| `test_optimize_3_assets_weights_sum_to_1` | Weights sum to 1.0 within tolerance |
| `test_optimize_sharpe_ratio_computed` | Sharpe ratio is positive |
| `test_max_weight_constraint_respected` | No weight exceeds `max_weight_per_asset` |
| `test_min_return_constraint_respected` | Portfolio return ≥ `min_portfolio_return` |
| `test_sector_limits_respected` | Sector allocation ≤ sector limit |
| `test_risk_tolerance_0_min_variance` | `risk_tolerance=0` → minimum variance portfolio |
| `test_infeasible_constraints_raise_error` | Impossible constraints → `SolverInfeasibleError` |

#### `test_classical_schemas.py`
Pydantic v2 schema validation for `OptimizationConstraints`, `ClassicalOptimizationInput`,
and `ClassicalOptimizationResult`.

#### `test_quantum_qubo.py`
Unit tests for `app.quantum.qubo` — QUBO matrix construction and evaluation.

| Test | Scenario |
|------|----------|
| `test_output_shape_is_n_by_n` | `build_qubo_matrix` returns (n, n) array |
| `test_matrix_is_symmetric` | Q is symmetric |
| `test_qubo_energy_correct` | Energy matches manual quadratic form |
| `test_decode_bitstring_valid` | Bitstring → asset index list |
| `test_validate_qubo_solution_cardinality` | Validates k-asset selection |
| `test_qubo_to_dict_nonzero_entries` | Only non-zero entries in dict |

#### `test_engines_quantum_qubo.py`
Tests for the engines-layer QUBO wrapper (`app.engines.quantum.qubo`), including
`QUBOMetadata`, `enumerate_all_solutions`, and `compute_approximation_ratio`.

#### `test_engines_quantum_metrics.py`
Tests for `compute_quantum_portfolio_metrics`, `compute_quantum_solution_quality`,
`compute_classical_vs_quantum_comparison`, and `select_best_quantum_result`.

#### `test_qaoa_solver.py`
Unit tests for `QAOASolver` (Qiskit QAOA). Tests the greedy fallback path used in
test environments where full quantum simulation is too slow.

| Test | Scenario |
|------|----------|
| `test_name_is_qaoa` | `solver.name == "QAOA"` |
| `test_solve_returns_result` | Returns `QuantumAssetResult` |
| `test_cardinality_enforced` | Exactly k assets selected |
| `test_greedy_fallback_selects_top_k` | Greedy selects highest-return assets |

#### `test_vqe_solver.py`
Unit tests for `VQESolver` (PennyLane VQE). Similar structure to QAOA tests.

### Data Layer Tests

#### `test_data_metrics.py`
Unit tests for `app.data.metrics` — portfolio metrics computation.

| Function Tested | Scenarios |
|-----------------|-----------|
| `compute_portfolio_metrics` | Happy path, historical data path |
| `compute_max_drawdown` | Drawdown calculation |
| `compute_var` / `compute_cvar` | Value-at-Risk at 95% confidence |
| `compute_sharpe_ratio` | Positive and zero-volatility cases |
| `compute_efficient_frontier_points` | Returns list of (return, volatility) pairs |
| `annualise_returns` / `annualise_volatility` | Scaling by √252 |

#### `test_data_sector_tags.py`
Unit tests for `app.data.sector_tags` — GICS sector classification.

| Function Tested | Scenarios |
|-----------------|-----------|
| `get_sector` | Known tickers (AAPL, MSFT, GOOGL), unknown tickers, case-insensitivity |
| `enrich_sector_map` | Priority: yfinance > static > fallback |
| `get_tickers_by_sector` | Known and unknown sectors |
| `is_valid_gics_sector` | Valid and invalid sector names |
| `normalise_sector_name` | Common aliases (e.g., "Tech" → "Information Technology") |

### Schema Tests

#### `test_classical_schemas.py`
Pydantic v2 validation for classical optimization schemas.

#### `test_quantum_schemas.py`
Pydantic v2 validation for quantum optimization schemas including
`QuantumOptimizationConstraints`, `QuantumOptimizationInput`, `QuantumAssetResult`,
and `QuantumOptimizationResult`.

#### `test_schemas_multi_objective.py`
Tests for multi-objective and efficient frontier schema additions:

| Schema | Tests |
|--------|-------|
| `BusinessObjective` | Field bounds, defaults |
| `FrontierConfig` | Distinct-axis validator, `num_points` bounds |
| `OptimizationRequest` | Duplicate objective names rejected, all-disabled rejected, zero-sum weights rejected, back-compat with legacy payloads |
| `FrontierPoint` | Defaults and required fields |
| `FrontierReport` | Required fields, optional indices |

### Agent Graph Tests

#### `test_agent_graph.py`
Integration tests for the LangGraph agent graph routing functions and the full
`run_agent_graph` pipeline.

```python
def _make_state(**kwargs: Any) -> AgentState:
    base: AgentState = {
        "run_id": str(uuid.uuid4()),
        "tickers": ["AAPL", "MSFT", "GOOGL"],
        "budget": 100_000.0,
        "request_params": {"run_quantum": True},
    }
    base.update(kwargs)
    return base
```

| Test Group | Coverage |
|------------|----------|
| `_route_after_fatal_node` | Returns `"end"` when both `error` and `failed_node` are set; `"continue"` otherwise |
| `_route_after_classical` | Returns `"end"` on any failure, `"quantum"` when enabled, `"skip_quantum"` when disabled or too many assets |
| `_should_run_quantum` | Returns `"quantum"` for small portfolios, `"skip_quantum"` when disabled or exceeds `MAX_QUANTUM_ASSETS` |
| `AgentState` TypedDict | Required fields, optional error fields default to `None` |
| `run_agent_graph` | Full pipeline with mocked nodes, failed data_fetch, non-fatal quantum failure |
| `_state_to_run_detail` | Extracts QAOA/VQE sharpe, handles invalid quantum_result, includes failed_node in error_message |

### Integration Tests

#### `test_integration_optimization.py`
End-to-end tests exercising real code paths (no mocking) for the optimization pipeline.

```python
TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN"]
MU = [0.12, 0.10, 0.09, 0.15]
SIGMA = [[0.04, 0.01, 0.008, 0.012], ...]
```

| Test | Scenario |
|------|----------|
| `test_full_pipeline_produces_valid_portfolio` | Classical optimizer → valid metrics |
| `test_quantum_dispatcher_end_to_end` | QUBO → QAOA + VQE → combined result |
| `test_classical_vs_quantum_comparison` | Both engines on same universe |
| `test_quantum_dispatcher_asset_limit` | `QuantumAssetLimitError` for too many assets |

#### `test_objectives_frontier_wiring.py`
Tests for multi-objective optimizer and efficient frontier node wiring.

| Test | Scenario |
|------|----------|
| `test_run_markowitz_mvo_with_objectives` | Objectives matrix applied correctly |
| `test_compute_frontier_happy_path` | Returns list of (volatility, return) pairs |
| `test_compute_frontier_unsupported_measure` | `ValueError` for unknown measure |
| `test_frontier_node_skips_when_disabled` | `frontier.enabled=False` → state unchanged |
| `test_frontier_node_runs_when_enabled` | `frontier.enabled=True` → `frontier_report` populated |
| `test_frontier_node_nonfatal_on_error` | Solver error → non-fatal, state continues |

---

## Test Directory Structure

```
tests/
├── __init__.py
├── conftest.py                    # Shared numpy/pandas fixtures
├── test_agent_graph.py            # Agent graph routing + run_agent_graph
├── test_api_assets.py             # GET /api/v1/assets/search
├── test_api_health.py             # GET /health
├── test_api_optimize.py           # POST /api/v1/optimize
├── test_api_runs.py               # GET /api/v1/runs + /runs/{id}
├── test_api_websocket.py          # WS /ws/runs/{id}/progress
├── test_celery_tasks.py           # OptimizationTask + Celery config
├── test_classical_optimizer.py    # ClassicalOptimizer (CVXPY)
├── test_classical_schemas.py      # Classical Pydantic schemas
├── test_data_metrics.py           # Portfolio metrics computation
├── test_data_sector_tags.py       # GICS sector classification
├── test_engines_quantum_metrics.py # Quantum metrics + comparison
├── test_engines_quantum_qubo.py   # Engines-layer QUBO wrapper
├── test_integration_optimization.py # Full pipeline integration
├── test_objectives_frontier_wiring.py # Multi-objective + frontier
├── test_qaoa_solver.py            # QAOA solver (Qiskit)
├── test_quantum_qubo.py           # Core QUBO formulation
├── test_quantum_schemas.py        # Quantum Pydantic schemas
├── test_schemas_multi_objective.py # Multi-objective API schemas
├── test_vqe_solver.py             # VQE solver (PennyLane)
├── test_e2e_smoke.py              # Full pipeline smoke tests
├── test_load.py                   # Concurrent load tests
├── integration/
│   ├── conftest.py                # HTTP client + DB mock fixtures
│   ├── test_agent_graph.py
│   ├── test_assets_endpoint.py
│   ├── test_celery_tasks.py
│   ├── test_health_endpoint.py
│   ├── test_optimize_endpoint.py
│   └── test_runs_endpoint.py
├── e2e/
│   ├── smoke_test.py              # ASGI + live-server smoke tests
│   └── locustfile.py              # Locust load test scenarios
└── unit/
    ├── test_classical_optimizer.py
    ├── test_data_cache.py
    ├── test_data_fetcher.py
    ├── test_data_metrics.py
    ├── test_db_models.py
    ├── test_qaoa_optimizer.py
    ├── test_qubo_formulator.py
    ├── test_sector_tags.py
    └── test_vqe_optimizer.py
```

---

## Coverage Configuration

Coverage is configured in `backend/pyproject.toml`:

```toml
[tool.coverage.run]
source = ["app"]
omit = ["*/tests/*", "*/__init__.py"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
    "@abstractmethod",
]
```

See [Test Coverage](test-coverage.md) for coverage targets and CI gate configuration.

> **Note:** The `asyncio_mode = "auto"` setting in `pyproject.toml` means all `async def`
> test functions are automatically run as asyncio coroutines. The `@pytest.mark.asyncio`
> decorator is still used in many test files for explicit documentation, but it is not
> strictly required.
