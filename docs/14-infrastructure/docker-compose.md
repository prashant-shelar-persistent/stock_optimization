# Docker Compose — Development Stack

The `docker-compose.yml` file at the repository root defines the complete local development environment for Portfolio Optimizer. It orchestrates seven services that mirror the production AWS topology, enabling full end-to-end development without any cloud dependencies.

> **File location:** `docker-compose.yml` (root), `docker-compose.override.yml` (Podman fixes), `docker-compose.prod.yml` (production reference)

## Service Overview

```mermaid
graph TD
    FE["frontend<br/>React + Vite :3000"]
    BE["backend<br/>FastAPI :8000"]
    W["worker<br/>Celery default queue"]
    WQ["worker-quantum<br/>Celery quantum queue"]
    CB["celery-beat<br/>Periodic scheduler"]
    PG["postgres<br/>PostgreSQL 16 :5432"]
    RD["redis<br/>Redis 7 :6379"]

    FE -->|"HTTP API calls"| BE
    BE -->|"asyncpg"| PG
    BE -->|"cache / broker"| RD
    W -->|"asyncpg"| PG
    W -->|"broker / result"| RD
    WQ -->|"asyncpg"| PG
    WQ -->|"broker / result"| RD
    CB -->|"schedule"| RD

    style PG fill:#336791,color:#fff
    style RD fill:#DC382D,color:#fff
    style BE fill:#009688,color:#fff
    style FE fill:#61DAFB,color:#000
    style W fill:#37B24D,color:#fff
    style WQ fill:#7950F2,color:#fff
    style CB fill:#F59F00,color:#fff
```

## The `x-backend-env` YAML Anchor

All backend-derived services (backend, worker, worker-quantum, celery-beat) share an identical set of environment variables. Rather than duplicating them four times, the compose file uses a YAML anchor:

```yaml
x-backend-env: &backend-env
  DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/portfolio_optimizer
  REDIS_URL: redis://redis:6379/0
  CELERY_BROKER_URL: redis://redis:6379/1
  CELERY_RESULT_BACKEND: redis://redis:6379/2
  ENVIRONMENT: development
  LOG_LEVEL: INFO
  QUANTUM_TIMEOUT_SECONDS: "60"
  MAX_QUANTUM_ASSETS: "8"
  CACHE_TTL_SECONDS: "3600"
  RISK_FREE_RATE: "0.02"
  OPENAI_API_KEY: "${OPENAI_API_KEY:-}"
```

Each service that needs these variables merges the anchor with `<<: *backend-env`:

```yaml
services:
  backend:
    environment:
      <<: *backend-env
```

### Redis Database Allocation

| Redis DB | Purpose |
|----------|---------|
| `redis://redis:6379/0` | Application cache (market data, sector classifications) |
| `redis://redis:6379/1` | Celery broker (task queue) |
| `redis://redis:6379/2` | Celery result backend (task results) |

## Service Definitions

### `postgres` — PostgreSQL 16

```yaml
postgres:
  image: postgres:16-alpine
  restart: unless-stopped
  environment:
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: postgres
    POSTGRES_DB: portfolio_optimizer
  volumes:
    - postgres_data:/var/lib/postgresql/data
  ports:
    - "5432:5432"
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U postgres -d portfolio_optimizer"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 10s
```

**Key details:**
- Uses the lightweight `16-alpine` image for minimal footprint
- Data is persisted in the named volume `postgres_data` so it survives container restarts
- The `pg_isready` health check ensures dependent services only start once PostgreSQL is accepting connections
- Port `5432` is exposed to the host for direct access with tools like `psql` or DBeaver

### `redis` — Redis 7

```yaml
redis:
  image: redis:7-alpine
  restart: unless-stopped
  command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
  volumes:
    - redis_data:/data
  ports:
    - "6379:6379"
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 5s
```

**Key details:**
- `--appendonly yes` enables AOF persistence so the Celery broker queue survives restarts
- `--maxmemory 256mb` caps memory usage to prevent the container from consuming unbounded host RAM
- `--maxmemory-policy allkeys-lru` evicts the least-recently-used keys when the limit is reached — appropriate for a cache where all keys are expendable
- The `redis-cli ping` health check is lightweight and reliable

### `backend` — FastAPI Application

```yaml
backend:
  build:
    context: ./backend
    dockerfile: Dockerfile
    target: development
  restart: unless-stopped
  environment:
    <<: *backend-env
  volumes:
    - ./backend:/app
  ports:
    - "8000:8000"
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
  command: >
    sh -c "alembic upgrade head &&
           uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 30s
```

**Key details:**
- Uses the `development` build target which installs dev dependencies and keeps source code writable
- The `./backend:/app` bind mount enables **hot-reload** — Uvicorn's `--reload` flag watches for file changes and restarts automatically without rebuilding the image
- The startup command runs **Alembic migrations first** (`alembic upgrade head`) before starting the server, ensuring the database schema is always up to date
- `depends_on` with `condition: service_healthy` prevents the backend from starting before PostgreSQL and Redis pass their health checks
- The backend health check polls `/api/v1/health` — the same endpoint used by the ALB in production

### `worker` — Celery Default Queue

```yaml
worker:
  build:
    context: ./backend
    dockerfile: Dockerfile
    target: development
  restart: unless-stopped
  environment:
    <<: *backend-env
  volumes:
    - ./backend:/app
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
  command: >
    sh -c "celery -A app.workers.celery_app worker
           --loglevel=info
           --concurrency=${CELERY_DEFAULT_CONCURRENCY:-4}
           --queues=default
           -n default-worker@%h"
```

**Key details:**
- Handles **classical optimization** runs from the `default` queue
- Concurrency defaults to `4` but is tunable via `CELERY_DEFAULT_CONCURRENCY` without rebuilding
- Named `default-worker@%h` (where `%h` expands to the hostname) for easy identification in Celery monitoring tools
- Higher concurrency is appropriate here because classical optimization tasks are CPU-bound but relatively short-lived

### `worker-quantum` — Celery Quantum Queue

```yaml
worker-quantum:
  build:
    context: ./backend
    dockerfile: Dockerfile
    target: development
  restart: unless-stopped
  environment:
    <<: *backend-env
  volumes:
    - ./backend:/app
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
  command: >
    sh -c "celery -A app.workers.celery_app worker
           --loglevel=info
           --concurrency=${CELERY_QUANTUM_CONCURRENCY:-2}
           --queues=quantum
           -n quantum-worker@%h"
```

**Key details:**
- Dedicated to the `quantum` queue — QAOA and VQE simulations never block classical runs
- Concurrency defaults to `2` via `CELERY_QUANTUM_CONCURRENCY` because each quantum simulation is CPU-intensive
- The queue isolation is critical: a long-running VQE job on 8 assets can take 60+ seconds; without isolation it would starve classical requests
- See [Queue Routing](../10-task-queue/queue-routing.md) for how tasks are routed to the correct queue

### `celery-beat` — Periodic Task Scheduler

```yaml
celery-beat:
  build:
    context: ./backend
    dockerfile: Dockerfile
    target: development
  restart: unless-stopped
  environment:
    <<: *backend-env
  volumes:
    - ./backend:/app
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
  command: >
    celery -A app.workers.celery_app beat
    --loglevel=info
    --scheduler celery.beat:PersistentScheduler
```

**Key details:**
- Uses `PersistentScheduler` which stores the schedule state on disk (inside the container) so periodic tasks resume correctly after restarts
- Only one instance of celery-beat should ever run — running multiple instances causes duplicate task submissions
- Depends on both postgres and redis being healthy before starting

### `frontend` — React + Vite Dev Server

```yaml
frontend:
  build:
    context: ./frontend
    dockerfile: Dockerfile
    target: development
  restart: unless-stopped
  environment:
    VITE_API_BASE_URL: http://localhost:8000
    VITE_WS_BASE_URL: ws://localhost:8000
  volumes:
    - ./frontend:/app
    - /app/node_modules
  ports:
    - "3000:5173"
  depends_on:
    - backend
  command: npm run dev -- --host 0.0.0.0
```

**Key details:**
- Vite's dev server runs on port `5173` inside the container, mapped to `3000` on the host
- `./frontend:/app` bind mount enables hot-module replacement (HMR) — React components update in the browser without a full page reload
- The anonymous volume `/app/node_modules` prevents the host's `node_modules` (or lack thereof) from overriding the container's installed packages — a common Docker gotcha
- `VITE_API_BASE_URL` and `VITE_WS_BASE_URL` point to the backend on `localhost:8000` (the host-side port mapping)

## Volume Mounts Summary

| Volume | Type | Purpose |
|--------|------|---------|
| `postgres_data` | Named volume | PostgreSQL data directory — persists across restarts |
| `redis_data` | Named volume | Redis AOF persistence file |
| `./backend:/app` | Bind mount | Backend source code for hot-reload |
| `./frontend:/app` | Bind mount | Frontend source code for HMR |
| `/app/node_modules` | Anonymous volume | Isolates container's node_modules from host |

## Health Check Dependency Chain

Services start in dependency order, with each waiting for its dependencies to pass health checks:

```mermaid
graph LR
    PG["postgres<br/>(pg_isready)"] -->|healthy| BE["backend<br/>(curl /health)"]
    RD["redis<br/>(redis-cli ping)"] -->|healthy| BE
    PG -->|healthy| W["worker"]
    RD -->|healthy| W
    PG -->|healthy| WQ["worker-quantum"]
    RD -->|healthy| WQ
    PG -->|healthy| CB["celery-beat"]
    RD -->|healthy| CB
    BE -->|started| FE["frontend"]
```

The `condition: service_healthy` directive (used for postgres and redis) is stricter than the default `condition: service_started` — it waits for the health check to pass, not just for the container process to start.

## Parallelism and Concurrency

The compose file includes detailed comments explaining the concurrency model:

> Multiple optimization runs are processed in parallel by setting `--concurrency=N` (one `prefork` child process per slot). Combined with `worker_prefetch_multiplier=1` (in `celery_app.py`) this gives N truly-parallel tasks per worker without one slow task starving others.

| Variable | Default | Controls |
|----------|---------|---------|
| `CELERY_DEFAULT_CONCURRENCY` | `4` | Number of parallel classical optimization tasks |
| `CELERY_QUANTUM_CONCURRENCY` | `2` | Number of parallel quantum simulation tasks |

Adjust these in your `.env` file or shell environment without rebuilding images.

## Podman Override (`docker-compose.override.yml`)

When running under **rootless Podman** (common on macOS and RHEL 9+), a permissions issue arises with bind-mounted source code. The override file fixes this:

```yaml
services:
  backend:
    userns_mode: "keep-id"
  worker:
    userns_mode: "keep-id"
  worker-quantum:
    userns_mode: "keep-id"
  celery-beat:
    userns_mode: "keep-id"
  frontend:
    userns_mode: "keep-id"
```

`userns_mode: "keep-id"` maps the host user 1:1 into the container namespace, so bind-mounted files have correct ownership. This file is auto-loaded by `podman-compose` but should be excluded when using Docker Desktop (pass `-f docker-compose.yml` explicitly).

See [Podman Notes](../01-getting-started/podman-notes.md) for full details.

## Quick Start

```bash
# Start all services
docker compose up --build

# Start in background
docker compose up -d --build

# View logs for a specific service
docker compose logs -f backend

# Scale the default worker
CELERY_DEFAULT_CONCURRENCY=8 docker compose up -d worker

# Stop everything
docker compose down

# Stop and remove volumes (wipes database)
docker compose down -v
```

## Related Documentation

- [Quickstart with Docker](../01-getting-started/quickstart-docker.md) — step-by-step setup guide
- [Environment Variables](../01-getting-started/environment-variables.md) — all configurable variables
- [Celery Configuration](../10-task-queue/celery-configuration.md) — worker and queue settings
- [Queue Routing](../10-task-queue/queue-routing.md) — how tasks are routed to default vs quantum queues

## CI/CD Integration

- [CI Workflow](../15-cicd/ci-workflow.md) — Docker build validation runs in CI on every PR
- [CD Workflow](../15-cicd/cd-workflow.md) — Production Docker images are built and pushed to ECR on merge
- [Terraform Overview](terraform-overview.md) — Terraform provisions the AWS equivalents of these services
- [Deployment Guide](../17-operations/deployment-guide.md) — Step-by-step production deployment procedures
