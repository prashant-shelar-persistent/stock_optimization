# Configuration

The application configuration is centralised in `backend/app/core/config.py`. It uses **Pydantic Settings** (`pydantic-settings`) to load all environment-specific values from environment variables or a `.env` file, with sensible defaults for local development.

## Overview

```mermaid
graph LR
    A[".env file"] --> C["Settings.__init__()"]
    B["Environment Variables"] --> C
    C --> D["get_settings() — lru_cache"]
    D --> E["Application Code"]
    D --> F["FastAPI Dependencies"]
    D --> G["Celery Workers"]
```

All secrets and environment-specific values are loaded at startup. **Never hardcode secrets in source code** — always use environment variables or the `.env` file.

---

## `Settings` Class

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Central application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )
```

`Settings` extends `pydantic_settings.BaseSettings`. Each field is declared with a `Field()` descriptor that provides a default value, description, and optional validation constraints (`ge`, `le`).

### `SettingsConfigDict` Options

| Option | Value | Effect |
|--------|-------|--------|
| `env_file` | `".env"` | Load variables from a `.env` file in the working directory |
| `env_file_encoding` | `"utf-8"` | File encoding for the `.env` file |
| `case_sensitive` | `True` | Environment variable names must match exactly (e.g., `DATABASE_URL`, not `database_url`) |
| `extra` | `"ignore"` | Unknown environment variables are silently ignored rather than raising a validation error |

---

## Settings Fields Reference

### Database

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `DATABASE_URL` | `str` | `postgresql+asyncpg://postgres:postgres@localhost:5432/portfolio_optimizer` | Async PostgreSQL DSN using the `asyncpg` driver |

The `asyncpg` driver is required for non-blocking database I/O. The URL scheme must be `postgresql+asyncpg://` — the standard `postgresql://` scheme uses the synchronous `psycopg2` driver and will not work with SQLAlchemy's async engine.

### Redis

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `REDIS_URL` | `str` | `redis://localhost:6379/0` | Redis connection URL for the data cache |
| `CELERY_BROKER_URL` | `str` | `redis://localhost:6379/1` | Celery task broker (Redis database 1) |
| `CELERY_RESULT_BACKEND` | `str` | `redis://localhost:6379/2` | Celery result storage (Redis database 2) |

Three separate Redis logical databases (0, 1, 2) are used to keep cache data, task messages, and task results isolated from each other.

### OpenAI

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `OPENAI_API_KEY` | `str` | `""` (empty string) | API key for the GPT-4o LLM explanation node in the agent graph |

When `OPENAI_API_KEY` is empty, the agent's explainer node falls back to a template-based explanation instead of calling the OpenAI API. This allows the application to run fully offline without an API key.

### Application

| Field | Type | Default | Allowed Values | Description |
|-------|------|---------|----------------|-------------|
| `ENVIRONMENT` | `str` | `"development"` | `development`, `staging`, `production` | Controls log format, CORS policy, and OpenAPI docs visibility |
| `LOG_LEVEL` | `str` | `"INFO"` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | Minimum log level for the root logger |

The `ENVIRONMENT` value has several downstream effects:

- **`development`**: Human-readable coloured console logs, all CORS origins allowed, OpenAPI docs enabled at `/docs` and `/redoc`, SQL echo enabled in the database engine.
- **`staging` / `production`**: JSON-formatted logs, CORS restricted to the frontend domain, OpenAPI docs disabled.

### Quantum Engine

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `QUANTUM_TIMEOUT_SECONDS` | `int` | `60` | `ge=10`, `le=600` | Maximum wall-clock seconds for a single quantum optimization run |
| `MAX_QUANTUM_ASSETS` | `int` | `8` | `ge=2`, `le=20` | Maximum number of assets allowed in quantum optimization |

Quantum circuit complexity grows exponentially with the number of assets (qubits). The `MAX_QUANTUM_ASSETS` limit prevents requests that would take impractically long to simulate classically. Exceeding this limit raises `QuantumAssetLimitError` (HTTP 422).

### Data / Caching

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `CACHE_TTL_SECONDS` | `int` | `3600` | `ge=60` | Redis TTL for cached price data (1 hour default) |

### Portfolio Metrics

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `RISK_FREE_RATE` | `float` | `0.02` | `ge=0.0`, `le=0.2` | Annual risk-free rate used in Sharpe ratio calculation (2% default) |

---

## `get_settings()` — LRU Cache Singleton

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance.

    Using lru_cache ensures the .env file is read only once per process.
    In tests, call ``get_settings.cache_clear()`` before patching env vars.
    """
    return Settings()
```

`get_settings()` is decorated with `@lru_cache(maxsize=1)`, which means:

- The `.env` file is read and all environment variables are parsed **exactly once** per process.
- Every subsequent call returns the same `Settings` instance from the cache.
- There is no per-request overhead for configuration access.

### Usage Pattern

Import and call `get_settings()` wherever settings are needed:

```python
from app.core.config import get_settings

settings = get_settings()
print(settings.DATABASE_URL)
print(settings.ENVIRONMENT)
```

In FastAPI route handlers, prefer the `SettingsDep` annotated dependency from `app.core.dependencies` to benefit from FastAPI's dependency injection:

```python
from app.core.dependencies import SettingsDep

@router.get("/example")
async def example_endpoint(settings: SettingsDep):
    return {"environment": settings.ENVIRONMENT}
```

---

## `.env` File Loading

Pydantic Settings automatically loads a `.env` file from the current working directory when the `Settings` class is instantiated. A typical `.env` file for local development:

```dotenv
# .env — local development overrides
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/portfolio_optimizer
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

OPENAI_API_KEY=sk-...your-key-here...

ENVIRONMENT=development
LOG_LEVEL=DEBUG

QUANTUM_TIMEOUT_SECONDS=60
MAX_QUANTUM_ASSETS=8
CACHE_TTL_SECONDS=3600
RISK_FREE_RATE=0.02
```

> **Security:** Never commit `.env` files containing real secrets to version control. The repository's `.gitignore` should exclude `.env`. Use `.env.example` as a template with placeholder values.

### Variable Precedence

Pydantic Settings resolves values in this order (highest priority first):

1. **Actual environment variables** set in the shell or Docker environment
2. **`.env` file** values
3. **Field defaults** defined in the `Settings` class

This means a `DATABASE_URL` set in the Docker Compose environment will always override the `.env` file value, which in turn overrides the class default.

---

## Test Cache Clearing Pattern

Because `get_settings()` is cached with `lru_cache`, tests that need to override environment variables must clear the cache first:

```python
import pytest
from unittest.mock import patch
from app.core.config import get_settings

def test_custom_environment():
    # Clear the lru_cache so the next call re-reads environment variables
    get_settings.cache_clear()

    with patch.dict("os.environ", {"ENVIRONMENT": "production", "LOG_LEVEL": "ERROR"}):
        settings = get_settings()
        assert settings.ENVIRONMENT == "production"
        assert settings.LOG_LEVEL == "ERROR"

    # Always restore the cache after the test to avoid polluting other tests
    get_settings.cache_clear()
```

> **Important:** Always call `get_settings.cache_clear()` both **before** and **after** (or in a `finally` block) when patching environment variables in tests. Failing to restore the cache can cause subsequent tests to receive stale settings.

A pytest fixture pattern for clean cache management:

```python
@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Ensure settings cache is cleared before and after each test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
```

---

## Full Settings Example

```python
from app.core.config import get_settings

settings = get_settings()

# Database
settings.DATABASE_URL          # "postgresql+asyncpg://..."

# Redis
settings.REDIS_URL             # "redis://localhost:6379/0"
settings.CELERY_BROKER_URL     # "redis://localhost:6379/1"
settings.CELERY_RESULT_BACKEND # "redis://localhost:6379/2"

# OpenAI
settings.OPENAI_API_KEY        # "" or "sk-..."

# Application
settings.ENVIRONMENT           # "development" | "staging" | "production"
settings.LOG_LEVEL             # "DEBUG" | "INFO" | ...

# Quantum
settings.QUANTUM_TIMEOUT_SECONDS  # 60
settings.MAX_QUANTUM_ASSETS       # 8

# Cache
settings.CACHE_TTL_SECONDS     # 3600

# Metrics
settings.RISK_FREE_RATE        # 0.02
```

---

## Related Pages

- [Application Factory](application-factory.md) — How settings are consumed at startup
- [Logging](logging.md) — `LOG_LEVEL` and `ENVIRONMENT` effects on log output
- [Dependencies](dependencies.md) — `SettingsDep` FastAPI dependency
- [Exceptions](exceptions.md) — `QuantumAssetLimitError` triggered by `MAX_QUANTUM_ASSETS`
