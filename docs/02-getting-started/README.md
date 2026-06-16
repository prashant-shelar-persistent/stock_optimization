# Getting Started

Step-by-step instructions for setting up and running the Portfolio Optimizer locally using Docker Compose, Podman, or a bare-metal Python/Node.js environment.

## Section Contents

| Page | Description |
|------|-------------|
| [Project Overview](../01-getting-started/overview.md) | Introduction to the system, capabilities, and technology stack |
| [Docker Quickstart](../01-getting-started/quickstart-docker.md) | Run the full stack with Docker Compose in minutes (recommended) |
| [Local Quickstart](../01-getting-started/quickstart-local.md) | Run with bare-metal Python + Node.js without Docker |
| [Environment Variables](../01-getting-started/environment-variables.md) | Complete reference for all `.env` configuration options |
| [Podman Notes](../01-getting-started/podman-notes.md) | Podman-specific setup, caveats, and workarounds |

## Prerequisites

Before you begin, ensure you have the following installed:

| Tool | Minimum Version | Purpose |
|------|----------------|---------|
| Docker | 24.x | Container runtime |
| Docker Compose | 2.x | Multi-service orchestration |
| Python | 3.11+ | Backend runtime (local setup only) |
| Node.js | 18+ | Frontend runtime (local setup only) |
| Git | 2.x | Source control |

## Quickstart (Docker — Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/your-org/stock_optimization.git
cd stock_optimization

# 2. Copy and configure environment variables
cp .env.example .env
# Edit .env — at minimum set OPENAI_API_KEY (optional) and POSTGRES_PASSWORD

# 3. Start all services
docker compose up --build

# 4. Open the application
open http://localhost:5173
```

The API will be available at `http://localhost:8000` and the frontend at `http://localhost:5173`.

## Choosing Your Setup Method

| Method | Best For | Pros | Cons |
|--------|----------|------|------|
| **Docker Compose** | Most users | One command, isolated, reproducible | Requires Docker |
| **Local (bare-metal)** | Active development | Fast iteration, direct debugging | Manual dependency management |
| **Podman** | Rootless environments | No daemon, rootless security | Some compose compatibility quirks |

## Next Steps

After getting the system running:

1. **Explore the API** → [Optimize Endpoint](../04-api-reference/optimize-endpoint.md)
2. **Understand the architecture** → [System Overview](../02-architecture/system-overview.md)
3. **Configure for production** → [Environment Variables](../01-getting-started/environment-variables.md)
4. **Run the test suite** → [Backend Tests](../13-testing/backend-tests.md)
