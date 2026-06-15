# E2E Tests — Portfolio Optimizer API

This directory contains two complementary test suites for end-to-end validation
of the Portfolio Optimizer API:

| File | Purpose | Runner |
|------|---------|--------|
| `smoke_test.py` | Pytest-based smoke tests — every public endpoint | `pytest` |
| `locustfile.py` | Locust load tests — realistic concurrent traffic | `locust` |

---

## Prerequisites

### Python environment

All tests require the backend Python environment to be active:

```bash
# From the repo root
cd backend
pip install -e ".[dev]"
```

### Locust (load tests only)

Locust is not included in the default dev dependencies.  Install it separately:

```bash
pip install locust>=2.28.0
```

---

## Smoke Tests (`smoke_test.py`)

### What is tested

| # | Scenario |
|---|----------|
| 1 | `GET /health` returns 200 with `status`, `version`, `services` |
| 2 | `GET /health` returns 503 with `status=unhealthy` when all services are down |
| 3 | `GET /health` returns 200 with `status=degraded` when some services are down |
| 4 | `GET /api/v1/assets/search?q=AAPL` returns Apple Inc. in Technology sector |
| 5 | Company name search (`?q=Apple`) returns AAPL in results |
| 6 | Empty query (`?q=`) returns 422 validation error |
| 7 | `limit` parameter is respected |
| 8 | `POST /api/v1/optimize` with minimal payload returns 202 with UUID `run_id` |
| 9 | Full request with all optional constraints returns 202 |
| 10 | Missing `budget` field returns 422 with field-level detail |
| 11 | Single ticker (< 2) returns 422 |
| 12 | Ticker exceeding 10 characters returns 422 |
| 13 | `GET /api/v1/runs/{id}/status` for pending run returns correct shape |
| 14 | Unknown `run_id` returns 404 with `error_code=RUN_NOT_FOUND` |
| 15 | `GET /api/v1/runs/{id}` for completed run returns full result shape |
| 16 | Unknown `run_id` on detail endpoint returns 404 |
| 17 | `GET /api/v1/runs` returns `items`, `total`, `page`, `page_size` |
| 18 | `page_size` parameter is respected |
| 19 | `status` filter returns only matching runs |
| 20 | Invalid `status` filter returns 422 with `error_code=INVALID_STATUS_FILTER` |
| 21 | Full flow: submit → run appears in list with correct `run_id` |
| 22 | `GET /metrics` returns Prometheus text format (skipped if not installed) |
| 23 | `GET /openapi.json` documents all key routes |
| 24 | CORS preflight returns `Access-Control-Allow-Origin` header |
| 25 | 10 concurrent submits all return unique `run_id` values |

### Running in CI (ASGI transport — no server required)

```bash
# From the repo root
cd backend
python -m pytest ../tests/e2e/smoke_test.py -v
```

Expected output:

```
35 passed, 1 skipped in ~0.6s
```

The 1 skipped test is the Prometheus `/metrics` test, which is skipped when
`prometheus-fastapi-instrumentator` is not installed.

### Running against a live server

Set `E2E_USE_REAL_SERVER=1` and `E2E_BASE_URL` to point at the running server:

```bash
# Start the server first
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000

# In another terminal
E2E_USE_REAL_SERVER=1 E2E_BASE_URL=http://localhost:8000 \
    python -m pytest tests/e2e/smoke_test.py -v
```

> **Note:** When running against a live server, the DB/Redis/Celery mocks are
> not applied.  The server must have real (or test) instances of PostgreSQL,
> Redis, and Celery available, or the optimization-related tests will fail.

### Running a single test

```bash
cd backend
python -m pytest ../tests/e2e/smoke_test.py::test_health_returns_200_when_all_services_up -v
```

---

## Load Tests (`locustfile.py`)

### User classes

| Class | Weight | Behaviour | Think time |
|-------|--------|-----------|------------|
| `HealthCheckUser` | 1 | Polls `/health` | 5–15 s |
| `AssetSearchUser` | 3 | Searches assets by ticker and name | 0.5–3 s |
| `OptimizationUser` | 2 | Submits runs and polls status | 2–10 s |
| `RunHistoryUser` | 2 | Browses paginated run history | 1–5 s |
| `MixedUser` | 5 | Combines all behaviours | 1–8 s |

### Prerequisites

1. The API server must be running:

   ```bash
   cd backend
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

2. PostgreSQL, Redis, and Celery must be available (or use Docker Compose):

   ```bash
   docker compose up -d postgres redis celery_worker
   ```

### Interactive mode (web UI)

```bash
locust -f tests/e2e/locustfile.py --host http://localhost:8000
```

Open http://localhost:8089 in your browser, set the number of users and spawn
rate, then click **Start swarming**.

### Headless mode (CI / scripted)

```bash
locust -f tests/e2e/locustfile.py \
    --host http://localhost:8000 \
    --headless \
    --users 50 \
    --spawn-rate 5 \
    --run-time 60s \
    --html tests/e2e/load_report.html \
    --csv tests/e2e/load_results
```

This runs for 60 seconds with up to 50 concurrent users, spawning 5 new users
per second.  Results are written to:

- `tests/e2e/load_report.html` — HTML report with charts
- `tests/e2e/load_results_stats.csv` — per-endpoint statistics
- `tests/e2e/load_results_failures.csv` — failure details

### Recommended load profiles

| Profile | Users | Spawn rate | Duration | Purpose |
|---------|-------|------------|----------|---------|
| Smoke | 5 | 1/s | 30 s | Verify load test setup works |
| Baseline | 20 | 2/s | 2 min | Establish performance baseline |
| Stress | 100 | 10/s | 5 min | Find breaking point |
| Soak | 30 | 3/s | 30 min | Detect memory leaks / degradation |

### Interpreting results

Key metrics to watch:

- **RPS (Requests per second)**: Should scale linearly with users up to the
  server's capacity.
- **p50 / p95 / p99 latency**: p95 < 500 ms for `/health` and `/assets/search`;
  p95 < 2 s for `POST /optimize` (which enqueues a Celery task).
- **Failure rate**: Should be 0% for all endpoints except the intentional
  error-path tasks (`[invalid]`, `[unknown]`), which are expected to return
  422/404 and are marked as successes by the locustfile.

### Running only specific user classes

```bash
# Run only the MixedUser class
locust -f tests/e2e/locustfile.py \
    --host http://localhost:8000 \
    --headless \
    --users 20 \
    --spawn-rate 2 \
    --run-time 30s \
    MixedUser
```

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `E2E_BASE_URL` | `http://localhost:8000` | Base URL for locust and real-server pytest mode |
| `E2E_USE_REAL_SERVER` | `0` | Set to `1` to make pytest use real HTTP instead of ASGI transport |

---

## CI integration

The smoke tests are designed to run in CI without any external services.
Add this step to your GitHub Actions workflow:

```yaml
- name: Run E2E smoke tests
  working-directory: backend
  run: python -m pytest ../tests/e2e/smoke_test.py -v --tb=short
```

For load tests in CI, use the headless mode with a short run time:

```yaml
- name: Run load tests (smoke profile)
  run: |
    pip install locust
    locust -f tests/e2e/locustfile.py \
      --host http://localhost:8000 \
      --headless \
      --users 5 \
      --spawn-rate 1 \
      --run-time 30s
```

> **Note:** Load tests in CI require the full stack (PostgreSQL + Redis + Celery)
> to be running.  Use `docker compose up -d` before this step.
