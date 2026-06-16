# Configuration

Complete reference for all environment variables, Pydantic settings, and runtime configuration options that control the Portfolio Optimizer's behavior across development, staging, and production environments.

## Section Contents

| Page | Description |
|------|-------------|
| [Request Schemas](../12-schemas/request-schemas.md) | `OptimizationRequest` Pydantic model and all input fields |
| [Response Schemas](../12-schemas/response-schemas.md) | `OptimizationResult` and nested response models |
| [Validation Rules](../12-schemas/validation-rules.md) | Field validators, business rules, and constraint bounds |

> **Note:** This section covers Pydantic schemas and validation. For environment variable configuration, see [Environment Variables](../01-getting-started/environment-variables.md) and [Backend Configuration](../03-backend/configuration.md). For the full operations configuration reference, see [Configuration Reference](../17-operations/configuration-reference.md).

## Configuration Overview

The Portfolio Optimizer uses **Pydantic Settings** (`pydantic-settings`) for all configuration, loading values from environment variables and `.env` files. This provides:

- **Type safety**: All settings are typed and validated at startup
- **Documentation**: Settings classes serve as self-documenting configuration references
- **Environment isolation**: Different `.env` files for dev/staging/prod

## Key Configuration Categories

| Category | Source | Documentation |
|----------|--------|---------------|
| Database | `DATABASE_URL` env var | [Backend Configuration](../03-backend/configuration.md) |
| Redis | `REDIS_URL` env var | [Celery Configuration](../10-task-queue/celery-configuration.md) |
| OpenAI | `OPENAI_API_KEY` env var | [Environment Variables](../01-getting-started/environment-variables.md) |
| Quantum limits | `MAX_QUANTUM_ASSETS`, `QAOA_LAYERS` | [Quantum Dispatcher](../07-quantum-optimization/quantum-dispatcher.md) |
| API security | `API_KEY`, `CORS_ORIGINS` | [Backend Configuration](../03-backend/configuration.md) |
| Celery | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | [Celery Configuration](../10-task-queue/celery-configuration.md) |

## Cross-References

- **Environment variable reference** → [Environment Variables](../01-getting-started/environment-variables.md)
- **Pydantic Settings class** → [Backend Configuration](../03-backend/configuration.md)
- **Production configuration** → [Configuration Reference](../17-operations/configuration-reference.md)
- **Infrastructure environments** → [Environments](../14-infrastructure/environments.md)
