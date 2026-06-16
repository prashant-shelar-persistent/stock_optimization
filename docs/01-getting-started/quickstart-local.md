# Quickstart: Local Development

This guide walks through running the Portfolio Optimizer without Docker — useful when you want faster iteration cycles, direct debugger access, or when Docker is not available.

You will run PostgreSQL and Redis as external services (via Docker, Homebrew, or a system package manager) while running the Python backend and Node.js frontend directly on your host machine.

---

## Prerequisites

| Requirement | Minimum Version | Install |
|-------------|----------------|---------|
| Python | 3.11+ | [python.org](https://www.python.org/downloads/) or `pyenv` |
| Node.js | 20+ | [nodejs.org](https://nodejs.org/) or `nvm` |
| PostgreSQL | 14+ | Docker, Homebrew (`brew install postgresql@16`), or system package |
| Redis | 7+ | Docker, Homebrew (`brew install redis`), or system package |
| Git | Any | Pre-installed on most systems |

> **Tip:** The easiest way to run PostgreSQL and Redis locally without Docker is via Homebrew on macOS or `apt`/`dnf` on Linux. Alternatively, start only the infrastructure services with Docker Compose: `docker compose up postgres redis -d`

---

## Step 1 — Start Infrastructure Services

### Option A: Docker Compose (infrastructure only)

```bash
# Start only PostgreSQL and Redis, leave the app running locally
docker compose up postgres redis -d
```

This exposes PostgreSQL on `localhost:5432` and Redis on `localhost:6379`.

### Option B: Homebrew (macOS)

```bash
brew install postgresql@16 redis

# Start services
brew services start postgresql@16
brew services start redis

# Create the database
createdb portfolio_optimizer
```

### Option C: System packages (Ubuntu/Debian)

```bash
sudo apt-get install -y postgresql redis-server

# Start services
sudo systemctl start postgresql redis-server

# Create the database
sudo -u postgres createdb portfolio_optimizer
```

---

## Step 2 — Configure Environment Variables

```bash
# From the repository root
cp .env.example .env
```

Edit `.env` to point to your local services. The defaults work if you used Option A (Docker Compose infrastructure):

```bash
# .env — local development settings

DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/portfolio_optimizer
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

ENVIRONMENT=development
LOG_LEVEL=INFO

QUANTUM_TIMEOUT_SECONDS=60
MAX_QUANTUM_ASSETS=8
CACHE_TTL_SECONDS=3600
RISK_FREE_RATE=0.02

# Optional — leave empty to use template-based fallback explanations
OPENAI_API_KEY=
```

If you created the database with a different user or password, update `DATABASE_URL` accordingly.

---

## Step 3 — Set Up the Python Backend

### Create a virtual environment

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

### Install dependencies

```bash
# Install the package in editable mode with all dev dependencies
pip install -e ".[dev]"
```

This installs all production and development dependencies defined in `backend/pyproject.toml`, including:
- FastAPI, Uvicorn, Pydantic v2
- CVXPY, SciPy, NumPy, Pandas (classical optimization)
- Qiskit 1.1.x + qiskit-algorithms, PennyLane 0.36.x (quantum optimization)
- LangGraph, LangChain, langchain-openai (agent layer)
- SQLAlchemy 2.0 (async), asyncpg, Alembic (database)
- Celery 5.4.x, redis[asyncio] (task queue and caching)
- pytest, ruff, mypy (development tools)

> **Note:** Installing Qiskit and PennyLane takes several minutes on first install due to their scientific computing dependencies. Subsequent installs use pip's cache.

### Run database migrations

```bash
# From the backend/ directory with .venv activated
alembic upgrade head
```

This applies all Alembic migrations in `backend/alembic/versions/` to create the database schema. You should see output like:

```
INFO  [alembic.runtime.migration] Context impl PostgreSQLImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 001, initial_schema
INFO  [alembic.runtime.migration] Running upgrade 001 -> 002, add_frontier_report
```

### Start the FastAPI server

```bash
uvicorn app.main:app --reload --port 8000
```

The `--reload` flag enables hot-reload: the server automatically restarts when you save a Python file. The API is now available at http://localhost:8000.

Verify it's running:

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
    "celery": "down"
  }
}
```

> **Note:** `celery` will show `"down"` until you start the Celery worker in the next step. The API still works for synchronous requests; only async task dispatch requires the worker.

---

## Step 4 — Start the Celery Worker

Open a **new terminal**, activate the virtual environment, and start the worker:

```bash
cd backend
source .venv/bin/activate

# Start the default queue worker (classical optimization)
celery -A app.workers.celery_app worker \
  --loglevel=info \
  --concurrency=4 \
  --queues=default \
  -n default-worker@%h
```

For quantum optimization, start a second worker in another terminal:

```bash
celery -A app.workers.celery_app worker \
  --loglevel=info \
  --concurrency=2 \
  --queues=quantum \
  -n quantum-worker@%h
```

> **Tip:** For local development you can run a single worker that handles both queues: `celery -A app.workers.celery_app worker --loglevel=info --queues=default,quantum`

---

## Step 5 — Set Up the Frontend

Open a **new terminal**:

```bash
cd frontend

# Install Node.js dependencies
npm install

# Start the Vite development server
npm run dev
```

The frontend is now available at http://localhost:5173 (Vite's default port). It proxies API requests to `http://localhost:8000`.

> **Note:** In Docker Compose, the frontend is mapped to port 3000 (`0.0.0.0:3000->5173/tcp`). When running locally, Vite uses its native port 5173 directly.

---

## Step 6 — Verify the Full Stack

With all services running, verify end-to-end connectivity:

```bash
# 1. Check the health endpoint
curl http://localhost:8000/health
# Expected: {"status":"healthy","services":{"database":"up","redis":"up","celery":"up"}}

# 2. Submit a test optimization run
curl -X POST http://localhost:8000/api/v1/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "tickers": ["AAPL", "MSFT", "GOOGL"],
    "budget": 50000.0,
    "run_quantum": false,
    "lookback_days": 90
  }'
# Expected: {"run_id": "..."}

# 3. Open the frontend
open http://localhost:5173
```

---

## Running Tests

The test suite lives in `tests/` and is configured in `backend/pyproject.toml`:

```bash
cd backend
source .venv/bin/activate

# Run all tests with coverage
pytest

# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run a specific test file
pytest tests/test_classical_optimizer.py

# Run with verbose output, no coverage
pytest --no-cov -v

# Run tests matching a keyword
pytest -k "test_classical"
```

> **Note:** Integration tests require a running PostgreSQL and Redis instance. Unit tests are fully isolated and can run without any external services.

---

## Development Workflow

### Backend hot-reload

Uvicorn's `--reload` flag watches for file changes in the `backend/` directory. Any change to a `.py` file triggers an automatic server restart. No manual restart is needed during development.

### Frontend hot-reload

Vite's dev server provides instant hot module replacement (HMR). Changes to `.tsx`, `.ts`, and `.css` files are reflected in the browser without a full page reload.

### Code quality tools

```bash
cd backend
source .venv/bin/activate

# Lint with ruff
ruff check app/

# Auto-fix lint issues
ruff check --fix app/

# Type-check with mypy
mypy app/

# Format code
ruff format app/
```

```bash
cd frontend

# Lint TypeScript/React
npm run lint

# Auto-fix lint issues
npm run lint:fix

# Format with Prettier
npm run format

# Type-check
npm run type-check
```

### Creating a new migration

After modifying SQLAlchemy models in `backend/app/db/models.py`:

```bash
cd backend
source .venv/bin/activate

# Auto-generate a migration from model changes
alembic revision --autogenerate -m "describe_your_change"

# Review the generated file in backend/alembic/versions/
# Then apply it:
alembic upgrade head
```

---

## Environment Summary

When all services are running locally, the stack looks like this:

```mermaid
graph TD
    Browser["Browser<br/>localhost:5173"] --> Vite["Vite Dev Server<br/>npm run dev"]
    Vite --> Uvicorn["FastAPI / Uvicorn<br/>localhost:8000 --reload"]
    Uvicorn --> PG["PostgreSQL<br/>localhost:5432"]
    Uvicorn --> Redis["Redis<br/>localhost:6379"]
    Uvicorn --> Celery["Celery Worker<br/>(default + quantum queues)"]
    Celery --> Redis
    Celery --> PG
```

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'app'`

Make sure you installed the package in editable mode (`pip install -e ".[dev]"`) and that your virtual environment is activated. The `PYTHONPATH` must include the `backend/` directory:

```bash
cd backend
export PYTHONPATH=$(pwd)
uvicorn app.main:app --reload
```

### `asyncpg.exceptions.InvalidCatalogNameError: database "portfolio_optimizer" does not exist`

Create the database manually:

```bash
# Using psql
psql -U postgres -c "CREATE DATABASE portfolio_optimizer;"

# Or using createdb
createdb -U postgres portfolio_optimizer
```

### `redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379`

Redis is not running. Start it:

```bash
# macOS (Homebrew)
brew services start redis

# Linux
sudo systemctl start redis-server

# Docker
docker run -d -p 6379:6379 redis:7-alpine
```

### Alembic `Target database is not up to date`

Run `alembic upgrade head` from the `backend/` directory with your virtual environment activated.

---

## Next Steps

- [Environment Variables](environment-variables.md) — Full configuration reference
- [Quickstart: Docker](quickstart-docker.md) — Run the full stack with Docker Compose
- [Podman Notes](podman-notes.md) — Rootless Podman setup
