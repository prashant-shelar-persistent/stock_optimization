"""Application configuration via Pydantic BaseSettings.

All secrets and environment-specific values are loaded from environment
variables or a .env file. Never hardcode secrets in source code.
"""

from __future__ import annotations

from functools import lru_cache

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

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/portfolio_optimizer",
        description="Async PostgreSQL DSN (asyncpg driver)",
    )

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )

    # ── Celery ────────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = Field(
        default="redis://localhost:6379/1",
        description="Celery broker URL (Redis)",
    )
    CELERY_RESULT_BACKEND: str = Field(
        default="redis://localhost:6379/2",
        description="Celery result backend URL (Redis)",
    )

    # ── OpenAI ────────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = Field(
        default="",
        description="OpenAI API key for GPT-4o LLM explanation node. "
        "If empty, template-based fallback is used.",
    )

    # ── Application ───────────────────────────────────────────────────────────
    ENVIRONMENT: str = Field(
        default="development",
        description="Runtime environment: development | staging | production",
    )
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level: DEBUG | INFO | WARNING | ERROR | CRITICAL",
    )

    # ── Quantum engine ────────────────────────────────────────────────────────
    QUANTUM_TIMEOUT_SECONDS: int = Field(
        default=60,
        ge=10,
        le=600,
        description="Maximum wall-clock seconds allowed for a single quantum optimization run",
    )
    MAX_QUANTUM_ASSETS: int = Field(
        default=8,
        ge=2,
        le=20,
        description="Maximum number of assets allowed in quantum optimization "
        "(QAOA/VQE complexity grows exponentially)",
    )

    # ── Data / caching ────────────────────────────────────────────────────────
    CACHE_TTL_SECONDS: int = Field(
        default=3600,
        ge=60,
        description="Redis TTL for cached price data (seconds)",
    )

    # ── Portfolio metrics ─────────────────────────────────────────────────────
    RISK_FREE_RATE: float = Field(
        default=0.02,
        ge=0.0,
        le=0.2,
        description="Annual risk-free rate used in Sharpe ratio calculation",
    )

    # ── Chat assistant ────────────────────────────────────────────────────────
    CHAT_SESSION_TTL_HOURS: int = Field(
        default=24,
        ge=1,
        le=168,  # max 1 week
        description=(
            "Time-to-live for chat sessions in hours.  Sessions that have not "
            "been confirmed within this window are considered expired and will "
            "no longer accept new messages.  Defaults to 24 hours."
        ),
    )
    CHAT_MAX_MESSAGES_PER_SESSION: int = Field(
        default=50,
        ge=4,
        le=200,
        description=(
            "Maximum number of messages (user + assistant combined) allowed in "
            "a single chat session.  Prevents unbounded conversation growth and "
            "protects against runaway LLM token costs.  When the limit is "
            "reached, the service raises ChatTooManyMessagesError (HTTP 422) "
            "and the client must start a new session.  Defaults to 50."
        ),
    )
    CHAT_MAX_SLOT_OVERRIDE_KEYS: int = Field(
        default=20,
        ge=1,
        le=50,
        description=(
            "Maximum number of keys allowed in the ``slot_overrides`` dict "
            "supplied to the confirm endpoint.  Prevents excessively large "
            "override payloads from being accepted.  Defaults to 20."
        ),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance.

    Using lru_cache ensures the .env file is read only once per process.
    In tests, call ``get_settings.cache_clear()`` before patching env vars.
    """
    return Settings()
