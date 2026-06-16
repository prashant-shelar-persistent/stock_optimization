# Quickstart: Docker Compose

The fastest way to run the full Portfolio Optimizer stack — backend, frontend, workers, PostgreSQL, and Redis — is with Docker Compose. All services are defined in `docker-compose.yml` and start with a single command.

---

## Prerequisites

Before you begin, ensure the following tools are installed:

| Tool | Minimum Version | Notes |
|------|----------------|-------|
| Docker Engine | 24.x | Or Docker Desktop 4.x |
| Docker Compose | 2.27+ | Bundled with Docker Desktop; standalone install on Linux |
| Git | Any | To clone the repository |

> **Podman users:** See [Podman Notes](podman-notes.md) for the `userns_mode: keep-id` fix required for rootless Podman on macOS and Fedora/RHEL.

---

## Step 1 — Clone and Configure

```bash
# Clone the repository
git clone <repository-url>
cd stock_optimization

# Copy the environment template
cp .env.example .env
```

Open `.env` in your editor. The defaults work for local development, but you should review:

```bash
# .env — key settings to review

# Optional: set your OpenAI API key for GPT-4o explanations.
# If left empty, a template-based fallback explanation is used.
OPENAI_API_KEY=sk-...your-key-here...

# These defaults work as-is for Docker Compose (services communicate
# by container name, not localhost):
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/portfolio_optimizer
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

> **Security note:** Never commit `.env` to version control. The `.gitignore` already excludes it. The `OPENAI_API_KEY` is the only secret that needs to be set for full functionality.

---

## Step 2 — Build and Start All Services

```bash
docker compose up --build
```

This command:
1. Builds the `backend` image (Python 3.11-slim, installs all dependencies including Qiskit and PennyLane)
2. Builds the `frontend` image (Node.js 20, installs npm dependencies)
3. Starts PostgreSQL 16 and Redis 7
4. Waits for database and Redis health checks to pass
5. Runs Alembic migrations (`alembic upgrade head`) inside the backend container
6. Starts the FastAPI server with hot-reload
7. Starts two Celery workers (`default` queue and `quantum` queue)
8. Starts the Celery Beat scheduler
9. Starts the Vite dev server

> **First build time:** The initial build takes 3–8 minutes because it installs Qiskit, PennyLane, and other scientific Python packages. Subsequent builds use Docker layer cache and are much faster.

To run in the background (detached mode):

```bash
docker compose up --build -d
```

---

## Step 3 — Verify Services Are Running

Once all containers are healthy, the following URLs are available:

| Service | URL | Description |
|---------|-----|-------------|
| **Frontend** | http://localhost:3000 | React + Vite dev server |
| **Backend API** | http://localhost:8000 | FastAPI application |
| **API Docs** | http://localhost:8000/docs | Swagger UI (development only) |
| **ReDoc** | http://localhost:8000/redoc | ReDoc API reference |
| **Health Check** | http://localhost:8000/health | Service health status |
| **Metrics** | http://localhost:8000/metrics | Prometheus metrics endpoint |
| **PostgreSQL** | localhost:5432 | Direct DB access (user: `postgres`, pass: `postgres`) |
| **Redis** | localhost:6379 | Direct Redis access |

Check that all services are healthy:

```bash
docker compose ps
```

Expected output (all services should show `healthy` or `running`):

```
NAME                    STATUS              PORTS
stock_optimization-backend-1        healthy             0.0.0.0:8000->8000/tcp
stock_optimization-celery-beat-1    running
stock_optimization-frontend-1       running             0.0.0.0:3000->5173/tcp
stock_optimization-postgres-1       healthy             0.0.0.0:5432->5432/tcp
stock_optimization-redis-1          healthy             0.0.0.0:6379->6379/tcp
stock_optimization-worker-1         running
stock_optimization-worker-quantum-1 running
```

Verify the health endpoint:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "services": {
    "database": "up",
    "redis": "up",
    "celery": "up"
  }
}
```

---

## Step 4 — Run Your First Optimization

### Using the Frontend

Open http://localhost:3000 in your browser. The React application provides a form to:
1. Enter ticker symbols (e.g., `AAPL`, `MSFT`, `GOOGL`, `AMZN`, `NVDA`)
2. Set a budget (e.g., `$100,000`)
3. Configure objectives and constraints
4. Toggle quantum optimization on/off
5. Submit and watch real-time progress via WebSocket

### Using the API Directly

Submit an optimization run via `curl`:

```bash
curl -X POST http://localhost:8000/api/v1/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"],
    "budget": 100000.0,
    "objectives": [
      {
        "name": "return",
        "direction": "maximize",
        "weight": 0.5,
        "target": 0.12,
        "threshold": 0.08,
        "enabled": true
      },
      {
        "name": "volatility",
        "direction": "minimize",
        "weight": 0.5,
        "target": 0.18,
        "threshold": 0.25,
        "enabled": true
      }
    ],
    "run_quantum": false,
    "lookback_days": 365
  }'
```

The API responds immediately with a `run_id`:

```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Poll for the result:

```bash
curl http://localhost:8000/api/v1/runs/550e8400-e29b-41d4-a716-446655440000
```

Or stream real-time progress via WebSocket:

```bash
# Using websocat (install: brew install websocat)
websocat ws://localhost:8000/ws/runs/550e8400-e29b-41d4-a716-446655440000/progress
```

Progress events look like:

```json
{"type": "progress", "run_id": "...", "node": "data_fetch", "status": "started", "message": "Fetching market data for 5 assets..."}
{"type": "progress", "run_id": "...", "node": "data_fetch", "status": "completed", "message": "Market data fetched successfully"}
{"type": "progress", "run_id": "...", "node": "classical_optimization", "status": "started", "message": "Running classical MVO..."}
{"type": "result", "run_id": "...", "result": {...}}
```

---

## Service Architecture

```mermaid
graph LR
    Browser["Browser<br/>:3000"] --> Frontend["Frontend<br/>(Vite :5173)"]
    Frontend --> Backend["Backend<br/>(FastAPI :8000)"]
    Backend --> Postgres["PostgreSQL<br/>:5432"]
    Backend --> Redis["Redis<br/>:6379"]
    Backend --> Worker["Celery Worker<br/>(default queue)"]
    Backend --> WorkerQ["Celery Worker<br/>(quantum queue)"]
    Worker --> Redis
    WorkerQ --> Redis
    Worker --> Postgres
    WorkerQ --> Postgres
    Beat["Celery Beat"] --> Redis
```

---

## Useful Commands

### View logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f worker-quantum
```

### Restart a single service

```bash
docker compose restart backend
```

### Run database migrations manually

```bash
docker compose exec backend alembic upgrade head
```

### Open a PostgreSQL shell

```bash
docker compose exec postgres psql -U postgres -d portfolio_optimizer
```

### Open a Redis CLI

```bash
docker compose exec redis redis-cli
```

### Run the test suite

```bash
docker compose exec backend pytest --no-cov -x
```

### Stop all services

```bash
docker compose down

# Also remove volumes (wipes database and Redis data)
docker compose down -v
```

---

## Adjusting Worker Concurrency

The number of parallel Celery workers can be tuned without rebuilding images using environment variables:

```bash
# Start with 8 classical workers and 4 quantum workers
CELERY_DEFAULT_CONCURRENCY=8 CELERY_QUANTUM_CONCURRENCY=4 docker compose up
```

The defaults are `4` for the classical worker and `2` for the quantum worker (set in `docker-compose.yml`).

---

## Troubleshooting

### Backend fails to start — "could not connect to server"

The backend waits for PostgreSQL to pass its health check before starting. If it still fails, check PostgreSQL logs:

```bash
docker compose logs postgres
```

### Frontend shows "EPERM: operation not permitted"

You are likely running under rootless Podman. See [Podman Notes](podman-notes.md) for the fix.

### Docker Desktop rejects `keep-id` in `userns_mode`

The `docker-compose.override.yml` file sets `userns_mode: "keep-id"` for Podman compatibility. Docker Desktop does not support this value. Run with the base file only:

```bash
docker compose -f docker-compose.yml up --build
```

### Quantum worker is slow

Quantum optimization (QAOA/VQE) is CPU-intensive and can take 30–60 seconds per run. This is expected behavior. The `QUANTUM_TIMEOUT_SECONDS` environment variable (default: `60`) controls the maximum allowed time.

---

## Next Steps

- [Quickstart: Local Development](quickstart-local.md) — Run without Docker
- [Environment Variables](environment-variables.md) — Full configuration reference
- [Podman Notes](podman-notes.md) — Rootless Podman setup
