# ─────────────────────────────────────────────────────────────────────────────
# Portfolio Optimizer — Backend Dockerfile
#
# Multi-stage build:
#   base        — shared Python base with system deps
#   development — editable install + dev tools (hot-reload)
#   production  — optimised, non-root, minimal image
# ─────────────────────────────────────────────────────────────────────────────

# ── Base ──────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System dependencies required by scientific Python packages and asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    git \
    ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Configure pip to trust PyPI hosts (workaround for some Podman/macOS SSL setups)
ENV PIP_TRUSTED_HOST="pypi.org pypi.python.org files.pythonhosted.org"

WORKDIR /app

# Copy dependency manifest first (layer-cache friendly)
COPY pyproject.toml ./

# ── Development ───────────────────────────────────────────────────────────────
FROM base AS development

# Install all dependencies including dev extras
RUN pip install -e ".[dev]"

# Source code is mounted as a volume in docker-compose.yml
# so we don't COPY it here — changes are reflected immediately.
# Ensure /app (where the volume is mounted) is on PYTHONPATH so the
# `app` package resolves regardless of editable-install discovery quirks.
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Production ────────────────────────────────────────────────────────────────
FROM base AS production

# Install only production dependencies
RUN pip install .

# Copy application source
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Create a non-root user for security
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --no-create-home --shell /bin/false appuser && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

# Healthcheck — FastAPI /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--no-access-log"]
