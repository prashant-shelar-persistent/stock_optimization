# Environment Variables

All application configuration is loaded from environment variables or a `.env` file. The settings are defined in `backend/app/core/config.py` using Pydantic's `BaseSettings`, which validates types and ranges at startup.

> **Security:** Never commit `.env` to version control. The repository's `.gitignore` already excludes it. Copy `.env.example` to `.env` and fill in your values.

---

## Quick Setup

```bash
cp .env.example .env
# Edit .env with your values
```

The only variable that requires a real value for full functionality is `OPENAI_API_KEY`. All other variables have sensible defaults for local development.

---

## Complete Variable Reference

### Database

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/portfolio_optimizer` | `str` | Async PostgreSQL DSN using the `asyncpg` driver. Must use the `postgresql+asyncpg://` scheme — the synchronous `postgresql://` scheme is not supported. |

**Notes:**
- The `asyncpg` driver is required because the application uses SQLAlchemy's async engine (`create_async_engine`).
- In Docker Compose, the hostname is `postgres` (the service name), not `localhost`.
- For production, use a connection string with SSL: `postgresql+asyncpg://user:pass@host:5432/db?ssl=require`

**Example values:**

```bash
# Local development
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/portfolio_optimizer

# Docker Compose (service-to-service)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/portfolio_optimizer

# Production (with SSL)
DATABASE_URL=postgresql+asyncpg://appuser:secret@db.example.com:5432/portfolio_optimizer?ssl=require
```

---

### Redis

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | `str` | Redis connection URL for the application cache (price data, session state). Uses database index `0`. |

**Notes:**
- The application uses `redis[asyncio]` for async cache operations.
- Redis database `0` is reserved for the application cache. Celery uses databases `1` and `2` (see below).
- For Redis with authentication: `redis://:password@localhost:6379/0`
- For Redis with TLS: `rediss://localhost:6380/0`

---

### Celery

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | `str` | Celery message broker URL. Uses Redis database index `1` to avoid conflicts with the application cache. |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/2` | `str` | Celery result backend URL. Uses Redis database index `2` to store task results separately from the broker. |

**Notes:**
- Celery uses three separate Redis databases (`0`, `1`, `2`) to prevent key collisions between the application cache, task queue, and task results.
- The broker and result backend can point to different Redis instances in production for better isolation.
- The `quantum` queue worker and `default` queue worker both use the same broker and result backend.

**Example (separate Redis instances for production):**

```bash
CELERY_BROKER_URL=redis://broker.internal:6379/0
CELERY_RESULT_BACKEND=redis://results.internal:6379/0
```

---

### OpenAI

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `OPENAI_API_KEY` | `""` (empty string) | `str` | OpenAI API key for the GPT-4o LLM explanation node. If empty, a template-based fallback explanation is generated instead. |

**Notes:**
- This is the only variable that requires an external account to obtain.
- The application **does not fail** if this key is missing — it gracefully falls back to a template-based explanation.
- The key is used only in the `llm_explanation` node of the LangGraph pipeline (`backend/app/agents/explainer.py`).
- Get your key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys).

> **Security:** Treat `OPENAI_API_KEY` as a secret. Do not log it, include it in error messages, or expose it in API responses. The `Settings` model uses `extra="ignore"` so it will not be accidentally serialized.

---

### Application

| Variable | Default | Valid Values | Description |
|----------|---------|-------------|-------------|
| `ENVIRONMENT` | `development` | `development`, `staging`, `production` | Runtime environment. Controls CORS policy, Swagger UI availability, and log format. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | Logging verbosity. Uses `structlog` for structured JSON logging in `staging`/`production`. |

**Behavior by environment:**

| Feature | `development` | `staging` | `production` |
|---------|--------------|-----------|-------------|
| Swagger UI (`/docs`) | ✅ Enabled | ✅ Enabled | ❌ Disabled |
| ReDoc (`/redoc`) | ✅ Enabled | ✅ Enabled | ❌ Disabled |
| OpenAPI JSON (`/openapi.json`) | ✅ Enabled | ✅ Enabled | ❌ Disabled |
| CORS | Allow all origins (`*`) | Restricted | Restricted |
| Log format | Human-readable | JSON | JSON |

---

### Quantum Engine

| Variable | Default | Range | Type | Description |
|----------|---------|-------|------|-------------|
| `QUANTUM_TIMEOUT_SECONDS` | `60` | `10`–`600` | `int` | Maximum wall-clock seconds allowed for a single quantum optimization run (QAOA or VQE). If exceeded, the task is terminated with a `QUANTUM_TIMEOUT` error and the run falls back to the classical result. |
| `MAX_QUANTUM_ASSETS` | `8` | `2`–`20` | `int` | Maximum number of assets allowed in a quantum optimization run. QAOA/VQE circuit depth grows exponentially with asset count, so this limit prevents impractically long runtimes. Requests with more assets automatically skip quantum optimization. |

**Notes on quantum limits:**
- QAOA with 8 assets requires a circuit with ~8 qubits and O(2^8) = 256 basis states. At 20 assets, this becomes 1,048,576 states — impractical on a classical simulator.
- The `QUANTUM_TIMEOUT_SECONDS` limit is enforced via Celery's `SoftTimeLimitExceeded` exception, which allows the task to clean up gracefully before being killed.
- Increasing `MAX_QUANTUM_ASSETS` beyond 12 is not recommended without access to real quantum hardware or a high-performance simulator.

**Recommended values by use case:**

| Use Case | `QUANTUM_TIMEOUT_SECONDS` | `MAX_QUANTUM_ASSETS` |
|----------|--------------------------|---------------------|
| Local development | `60` | `6` |
| CI/CD testing | `30` | `4` |
| Production (simulator) | `120` | `8` |
| Production (real hardware) | `600` | `20` |

---

### Data / Caching

| Variable | Default | Range | Type | Description |
|----------|---------|-------|------|-------------|
| `CACHE_TTL_SECONDS` | `3600` | `60`–∞ | `int` | Redis TTL (time-to-live) for cached market price data. After this period, the next request for the same ticker data will re-fetch from yfinance. |

**Notes:**
- Price data is cached in Redis under keys like `prices:{ticker}:{lookback_days}`.
- A TTL of `3600` (1 hour) is appropriate for development. In production, consider `86400` (24 hours) for daily data or `300` (5 minutes) for intraday data.
- Setting `CACHE_TTL_SECONDS` too low increases yfinance API calls and latency. Setting it too high means stale data.

---

### Portfolio Metrics

| Variable | Default | Range | Type | Description |
|----------|---------|-------|------|-------------|
| `RISK_FREE_RATE` | `0.02` | `0.0`–`0.2` | `float` | Annual risk-free rate used in the Sharpe ratio calculation: `Sharpe = (portfolio_return - risk_free_rate) / portfolio_volatility`. |

**Notes:**
- The default `0.02` (2%) approximates the US 10-year Treasury yield as of mid-2024.
- Update this value to reflect current market conditions. Common values:
  - `0.00` — Zero rate (conservative, ignores opportunity cost)
  - `0.02` — 2% (typical developed market rate)
  - `0.05` — 5% (elevated rate environment)
- This value affects Sharpe ratio calculations in both the classical optimizer and the comparison node.

---

### Additional Variables (`.env.example`)

| Variable | Description |
|----------|-------------|
| `GITHUB_PERSONAL_ACCESS_TOKEN` | Used by CI/CD pipelines for GitHub Actions authentication. Not required for local development. |

---

## How Settings Are Loaded

Settings are loaded by `backend/app/core/config.py` using Pydantic's `BaseSettings`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/portfolio_optimizer",
    )
    # ... other fields
```

Key behaviors:
- **Priority order:** Environment variables > `.env` file > field defaults
- **Case-sensitive:** `DATABASE_URL` must be uppercase (not `database_url`)
- **Extra variables ignored:** Unknown variables in `.env` are silently ignored (`extra="ignore"`)
- **Singleton:** Settings are cached via `@lru_cache(maxsize=1)` — the `.env` file is read only once per process. In tests, call `get_settings.cache_clear()` before patching environment variables.

---

## Validation Rules

Pydantic validates all settings at startup. Invalid values cause an immediate `ValidationError` with a clear message:

| Variable | Validation |
|----------|-----------|
| `QUANTUM_TIMEOUT_SECONDS` | Must be between 10 and 600 (`ge=10, le=600`) |
| `MAX_QUANTUM_ASSETS` | Must be between 2 and 20 (`ge=2, le=20`) |
| `CACHE_TTL_SECONDS` | Must be at least 60 (`ge=60`) |
| `RISK_FREE_RATE` | Must be between 0.0 and 0.2 (`ge=0.0, le=0.2`) |

Example validation error:

```
pydantic_settings.env_settings.SettingsError: 1 validation error for Settings
QUANTUM_TIMEOUT_SECONDS
  Input should be greater than or equal to 10 [type=greater_than_equal, input_value=5, input_url=...]
```

---

## Docker Compose Environment

In `docker-compose.yml`, environment variables are set via the `x-backend-env` YAML anchor and shared across all backend services:

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

Note that `OPENAI_API_KEY` is passed through from the host environment using `${OPENAI_API_KEY:-}` (empty string default). Set it in your `.env` file and Docker Compose will pick it up automatically.

---

## Related Pages

- [Quickstart: Docker](quickstart-docker.md) — Using Docker Compose
- [Quickstart: Local](quickstart-local.md) — Local Python/Node.js setup
- [Podman Notes](podman-notes.md) — Podman-specific configuration
