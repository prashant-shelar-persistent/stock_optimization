# Portfolio Optimizer — Classical + Quantum + Agent-First

A production-grade portfolio optimization simulator that combines classical
Markowitz Mean-Variance Optimization (CVXPY), quantum optimization (QAOA via
Qiskit, VQE-style via PennyLane), and an LLM-powered agent layer (LangGraph +
GPT-4o) to recommend optimized portfolios under real-world constraints.

---

## Architecture

```
Frontend (React + Vite + shadcn/ui)
    │
    ▼
API Layer (FastAPI + WebSocket)
    │
    ▼
Agent Layer (LangGraph)
    ├── Data Fetch Node (yfinance + Redis cache)
    ├── Constraint Validation Node
    ├── Classical Optimization Node (CVXPY / Markowitz MVO)
    ├── Quantum Dispatch Node (QAOA / VQE)
    ├── Comparison Node
    └── LLM Explanation Node (GPT-4o)
    │
    ▼
Storage (PostgreSQL run history + Redis cache)
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose 2.27+

### Development (Docker Compose)

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env — set OPENAI_API_KEY if you want LLM explanations

# 2. Start all services
docker compose up --build

# 3. Open the app
open http://localhost:5173
```

### Running under Podman (rootless)

Rootless Podman (default on macOS and modern Fedora/RHEL) maps the host
user into a separate UID namespace. Bind-mounted source code is therefore
*unreadable* to the unprivileged users that the official `node` and
`python` images run as — Vite/uvicorn crash with:

```
EPERM: operation not permitted, open '/app/index.html'
```

The repo ships a [`docker-compose.override.yml`](docker-compose.override.yml)
that adds `userns_mode: "keep-id"` to every dev service that bind-mounts
source. `podman-compose` (and `docker compose` with Podman's compatible
socket) auto-loads it, so you can just run:

```bash
podman-compose up --build
# or, if you've enabled the Docker-compatible socket:
docker compose up --build
```

Under Docker Desktop the override is harmless (the unknown `userns_mode`
value is ignored with a warning). If you'd rather drop it, delete the file.

### Local Development (without Docker)

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

---

## Project Structure

```
.
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── main.py             # FastAPI app factory + lifespan
│   │   ├── core/               # Config, logging, exceptions, dependencies
│   │   ├── api/                # REST routers + WebSocket gateway
│   │   ├── agents/             # LangGraph agent graph + nodes
│   │   ├── classical/          # Markowitz MVO (CVXPY)
│   │   ├── quantum/            # QAOA (Qiskit) + VQE (PennyLane)
│   │   ├── data/               # yfinance fetcher + Redis cache
│   │   ├── db/                 # SQLAlchemy models + session
│   │   ├── schemas/            # Pydantic v2 request/response models
│   │   └── workers/            # Celery task definitions
│   ├── alembic/                # Database migrations
│   └── pyproject.toml
├── frontend/                   # React + Vite application
│   ├── src/
│   │   ├── components/         # UI components (shadcn/ui)
│   │   ├── pages/              # Route-level page components
│   │   ├── hooks/              # Custom React hooks
│   │   ├── lib/                # API client + utilities
│   │   └── types/              # TypeScript type definitions
│   ├── package.json
│   └── vite.config.ts
├── tests/                      # pytest test suite
├── infra/                      # Terraform IaC (AWS ECS Fargate)
├── docker-compose.yml
├── docker-compose.prod.yml
└── .env.example
```

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI 0.111.x, Uvicorn 0.30.x |
| Frontend | TypeScript 5.4, React 18.3.x, Vite 5.x, shadcn/ui |
| Classical Opt | CVXPY 1.5.x, SciPy 1.13.x, NumPy 1.26.x, Pandas 2.2.x |
| Quantum Opt | Qiskit 1.1.x + qiskit-algorithms 0.3.x, PennyLane 0.36.x |
| Agent Layer | LangGraph 0.1.x, LangChain 0.2.x, GPT-4o |
| Market Data | yfinance 0.2.x |
| Caching | Redis 7.x |
| Task Queue | Celery 5.4.x |
| Database | PostgreSQL 16.x, SQLAlchemy 2.0.x, asyncpg 0.29.x |
| Migrations | Alembic 1.13.x |
| Infra | Docker, AWS ECS Fargate, Terraform 1.8.x |

---

## Environment Variables

See [`.env.example`](.env.example) for all available configuration options.

Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL async DSN |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `OPENAI_API_KEY` | _(empty)_ | GPT-4o API key (optional) |
| `ENVIRONMENT` | `development` | `development` / `staging` / `production` |
| `QUANTUM_TIMEOUT_SECONDS` | `60` | Max seconds for quantum jobs |
| `MAX_QUANTUM_ASSETS` | `8` | Max assets for quantum optimization |
| `RISK_FREE_RATE` | `0.02` | Annual risk-free rate for Sharpe ratio |

---

## Running Tests

```bash
cd backend
pytest                          # Run all tests with coverage
pytest -k "test_classical"      # Run specific tests
pytest --no-cov                 # Skip coverage
```

---

## License

MIT
