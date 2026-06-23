"""Application configuration via Pydantic BaseSettings.

All secrets and environment-specific values are loaded from environment
variables or a .env file. Never hardcode secrets in source code.

Security hardening (Phase 1)
-----------------------------
- ``SECRET_KEY``      — Required in production; used to sign WebSocket HMAC
                        tokens and any other stateless signed payloads.
- ``REDIS_PASSWORD``  — Optional Redis AUTH password.  When set, the validator
                        ``_inject_redis_auth`` rewrites all three Redis URLs
                        (``REDIS_URL``, ``CELERY_BROKER_URL``,
                        ``CELERY_RESULT_BACKEND``) to embed the password in
                        the URL authority so every Redis client in the process
                        automatically authenticates.
- ``ALLOWED_ORIGINS`` — Comma-separated list of allowed CORS origins.
                        Defaults to ``http://localhost:3000`` in development.
                        In production the validator enforces that this is
                        explicitly set to a non-wildcard value.

Production validators (``@model_validator(mode="after")``)
-----------------------------------------------------------
1. ``_validate_production_secrets`` — raises ``ValueError`` at startup if
   ``ENVIRONMENT == "production"`` and ``SECRET_KEY`` is empty or still set
   to the insecure development placeholder.
2. ``_inject_redis_auth`` — rewrites Redis URLs to include the password in
   the ``redis://:password@host:port/db`` authority form so that all Redis
   clients (async pool, Celery broker, Celery result backend) authenticate
   automatically without each caller needing to pass credentials separately.
"""

import secrets
from functools import lru_cache
from urllib.parse import urlparse, urlunparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Placeholder value that signals "not yet configured".  The production
# validator rejects this value so operators cannot accidentally deploy with
# the default.
_INSECURE_DEFAULT_SECRET = "CHANGE_ME_IN_PRODUCTION"


class Settings(BaseSettings):
    """Central application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Database ────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/portfolio_optimizer",
        description="Async PostgreSQL DSN (asyncpg driver)",
    )

    # ── Redis ────────────────────────────────────────────────────────────────
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL (password injected automatically if REDIS_PASSWORD is set)",
    )

    # ── Celery ───────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = Field(
        default="redis://localhost:6379/1",
        description="Celery broker URL (Redis)",
    )
    CELERY_RESULT_BACKEND: str = Field(
        default="redis://localhost:6379/2",
        description="Celery result backend URL (Redis)",
    )

    # ── OpenAI ───────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = Field(
        default="",
        description="OpenAI API key for GPT-4o LLM explanation node. "
        "If empty, template-based fallback is used.",
    )

    # ── Security ─────────────────────────────────────────────────────────────
    SECRET_KEY: str = Field(
        default=_INSECURE_DEFAULT_SECRET,
        description=(
            "Secret key used to sign WebSocket HMAC tokens and other "
            "stateless signed payloads.  MUST be set to a strong random "
            "value in production (e.g. `openssl rand -hex 32`).  "
            "The application will refuse to start in production if this "
            "is left at the default placeholder value."
        ),
    )

    REDIS_PASSWORD: str = Field(
        default="",
        description=(
            "Redis AUTH password.  When non-empty, all Redis URLs are "
            "automatically rewritten to embed the password in the URL "
            "authority (``redis://:password@host:port/db``).  "
            "Must match the ``requirepass`` value in redis.conf / "
            "the Docker Compose ``command`` flag."
        ),
    )

    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000",
        description=(
            "Comma-separated list of allowed CORS origins.  "
            "Example: ``https://app.example.com,https://www.example.com``.  "
            "Wildcard (``*``) is rejected in production.  "
            "Defaults to ``http://localhost:3000`` for local development."
        ),
    )

    # ── Application ──────────────────────────────────────────────────────────
    ENVIRONMENT: str = Field(
        default="development",
        description="Runtime environment: development | staging | production",
    )
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level: DEBUG | INFO | WARNING | ERROR | CRITICAL",
    )

    # ── Quantum engine ───────────────────────────────────────────────────────
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

    # ── Data / caching ───────────────────────────────────────────────────────
    CACHE_TTL_SECONDS: int = Field(
        default=3600,
        ge=60,
        description="Redis TTL for cached price data (seconds)",
    )

    # ── Portfolio metrics ────────────────────────────────────────────────────
    RISK_FREE_RATE: float = Field(
        default=0.02,
        ge=0.0,
        le=0.2,
        description="Annual risk-free rate used in Sharpe ratio calculation",
    )

    # ── Chat assistant ───────────────────────────────────────────────────────
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

    # ── Computed / derived properties ────────────────────────────────────────

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse ``ALLOWED_ORIGINS`` into a list of origin strings.

        Splits on commas, strips whitespace, and filters empty strings so
        that ``"https://a.com, https://b.com"`` and
        ``"https://a.com,https://b.com"`` both work correctly.
        """
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    # ── Validators ───────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        """Enforce strong secrets in production environments.

        Raises ``ValueError`` at startup (before any request is served) if:
        - ``ENVIRONMENT`` is ``"production"`` or ``"staging"`` AND
        - ``SECRET_KEY`` is empty or still set to the insecure placeholder.

        This causes the application to fail fast rather than silently
        operating without proper secret management.
        """
        is_prod_like = self.ENVIRONMENT in ("production", "staging")
        if is_prod_like:
            if not self.SECRET_KEY or self.SECRET_KEY == _INSECURE_DEFAULT_SECRET:
                raise ValueError(
                    "SECRET_KEY must be set to a strong random value in "
                    f"ENVIRONMENT={self.ENVIRONMENT!r}.  "
                    "Generate one with: openssl rand -hex 32"
                )
            # Validate ALLOWED_ORIGINS does not contain wildcard in production
            origins = self.allowed_origins_list
            if "*" in origins:
                raise ValueError(
                    "ALLOWED_ORIGINS must not contain '*' in "
                    f"ENVIRONMENT={self.ENVIRONMENT!r}.  "
                    "Set it to your actual frontend domain(s)."
                )
            if not origins:
                raise ValueError(
                    "ALLOWED_ORIGINS must be set to at least one origin in "
                    f"ENVIRONMENT={self.ENVIRONMENT!r}."
                )
        return self

    @model_validator(mode="after")
    def _inject_redis_auth(self) -> "Settings":
        """Rewrite Redis URLs to embed the password in the URL authority.

        When ``REDIS_PASSWORD`` is non-empty, transforms:
            ``redis://host:port/db``
        into:
            ``redis://:password@host:port/db``

        This ensures every Redis client in the process (async pool, Celery
        broker, Celery result backend) authenticates automatically without
        each caller needing to pass credentials separately.

        The rewrite is idempotent: if the URL already contains credentials
        (e.g. ``redis://:existing@host:port/db``) the existing credentials
        are replaced with the configured password.

        No-op when ``REDIS_PASSWORD`` is empty (development default).
        """
        if not self.REDIS_PASSWORD:
            return self

        password = self.REDIS_PASSWORD

        def _embed_password(url: str) -> str:
            """Embed *password* into the authority component of *url*."""
            parsed = urlparse(url)
            # Replace netloc: strip any existing userinfo, then prepend :password@
            host_port = parsed.hostname or "localhost"
            if parsed.port:
                host_port = f"{host_port}:{parsed.port}"
            new_netloc = f":{password}@{host_port}"
            new_parsed = parsed._replace(netloc=new_netloc)
            return urlunparse(new_parsed)

        self.REDIS_URL = _embed_password(self.REDIS_URL)
        self.CELERY_BROKER_URL = _embed_password(self.CELERY_BROKER_URL)
        self.CELERY_RESULT_BACKEND = _embed_password(self.CELERY_RESULT_BACKEND)
        return self

    @model_validator(mode="after")
    def _generate_dev_secret_key(self) -> "Settings":
        """Auto-generate a random SECRET_KEY for development if not set.

        In development, operators often do not set SECRET_KEY.  Rather than
        failing startup, we generate a random key per-process.  This means
        WebSocket tokens issued before a restart are invalidated on restart,
        which is acceptable in development.

        This validator runs AFTER ``_validate_production_secrets`` so it
        only fires when the environment is NOT production/staging.
        """
        is_prod_like = self.ENVIRONMENT in ("production", "staging")
        if not is_prod_like and self.SECRET_KEY == _INSECURE_DEFAULT_SECRET:
            # Generate a cryptographically strong random key for this process
            self.SECRET_KEY = secrets.token_hex(32)
        return self


@lru_cache(maxsize=1)
def get_settings() -> "Settings":
    """Return a cached singleton Settings instance.

    Using lru_cache ensures the .env file is read only once per process.
    In tests, call ``get_settings.cache_clear()`` before patching env vars.
    """
    return Settings()
