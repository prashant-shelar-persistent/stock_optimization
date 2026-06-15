"""FastAPI application factory and lifespan manager.

This module creates the FastAPI app instance, registers all routers,
configures middleware, and manages startup/shutdown lifecycle events.

Prometheus instrumentation is added via ``prometheus-fastapi-instrumentator``
which exposes a ``/metrics`` endpoint in Prometheus text format (version 0.0.4).
The endpoint provides:
  - ``http_requests_total``          — request counter labelled by method/handler/status
  - ``http_request_duration_seconds`` — latency histogram
  - ``http_requests_inprogress``     — in-flight request gauge
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.dependencies import close_redis
from app.core.exceptions import PortfolioOptimizerError
from app.core.logging import configure_logging, get_logger


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Manage application startup and shutdown.

    Startup:
        - Configure structured logging
        - Run database migrations (via Alembic, handled by Docker CMD)
        - Log service readiness

    Shutdown:
        - Close Redis connection pool
    """
    settings = get_settings()

    # Configure logging first so all subsequent messages are structured
    configure_logging(
        log_level=settings.LOG_LEVEL,
        environment=settings.ENVIRONMENT,
    )

    logger.info(
        "application_starting",
        environment=settings.ENVIRONMENT,
        log_level=settings.LOG_LEVEL,
    )

    yield  # Application runs here

    # ── Shutdown ────────────────────────────────────────────────────────────
    logger.info("application_shutting_down")
    await close_redis()
    logger.info("application_stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        A fully configured FastAPI instance with:
        - CORS middleware
        - Prometheus instrumentation (``/metrics`` endpoint)
        - Domain exception handlers
        - All API routers registered
    """
    settings = get_settings()

    app = FastAPI(
        title="Portfolio Optimizer API",
        description=(
            "Production-grade Portfolio Optimization Simulator — "
            "Classical (Markowitz MVO) + Quantum (QAOA/VQE) + Agent-First (LangGraph)"
        ),
        version="0.1.0",
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
        openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    # In development, allow all origins. In production, restrict to the
    # frontend domain via the ALLOWED_ORIGINS env var (future enhancement).
    allowed_origins = (
        ["*"]
        if settings.ENVIRONMENT == "development"
        else [
            "https://portfolio-optimizer.example.com",
        ]
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Prometheus instrumentation ────────────────────────────────────────────
    # ``prometheus-fastapi-instrumentator`` wraps the ASGI app to collect
    # per-route HTTP metrics and exposes them at ``/metrics`` in the standard
    # Prometheus text exposition format (Content-Type: text/plain; version=0.0.4).
    #
    # The import is guarded so that the application still starts if the package
    # is not installed (e.g., in a minimal test environment), though the
    # ``/metrics`` endpoint will simply be absent in that case.
    _setup_prometheus(app)

    # ── Exception handlers ────────────────────────────────────────────────────
    @app.exception_handler(PortfolioOptimizerError)
    async def portfolio_error_handler(
        request: Request,
        exc: PortfolioOptimizerError,
    ) -> JSONResponse:
        """Convert domain exceptions to structured JSON error responses."""
        logger.warning(
            "domain_error",
            error_code=exc.error_code,
            message=exc.message,
            path=str(request.url),
        )
        return JSONResponse(
            status_code=_error_code_to_http_status(exc.error_code),
            content=exc.to_dict(),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Catch-all handler for unexpected exceptions."""
        logger.error(
            "unhandled_exception",
            exc_type=type(exc).__name__,
            message=str(exc),
            path=str(request.url),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again.",
                "details": {},
            },
        )

    # ── Routers ───────────────────────────────────────────────────────────────
    # Routers are registered here. Individual router modules are created in
    # the API layer phase.
    _register_routers(app)

    return app


def _setup_prometheus(app: FastAPI) -> None:
    """Attach Prometheus instrumentation to the FastAPI application.

    Instruments the app with ``prometheus-fastapi-instrumentator`` and
    exposes a ``/metrics`` endpoint that returns Prometheus text-format
    metrics including:

    - ``http_requests_total``           — labelled by method, handler, status_code
    - ``http_request_duration_seconds`` — latency histogram (buckets: 0.005 … 10 s)
    - ``http_requests_inprogress``      — current in-flight requests gauge

    The ``/metrics`` endpoint itself is excluded from instrumentation to
    avoid self-referential metric noise.

    If ``prometheus-fastapi-instrumentator`` is not installed the function
    logs a warning and returns without raising, so the rest of the application
    continues to work normally.
    """
    try:
        from prometheus_fastapi_instrumentator import Instrumentator  # noqa: PLC0415

        Instrumentator(
            # Exclude the /metrics endpoint itself from being tracked
            excluded_handlers=["/metrics"],
        ).instrument(app).expose(
            app,
            endpoint="/metrics",
            include_in_schema=False,  # Hide from OpenAPI docs — it's a Prometheus endpoint
            tags=["monitoring"],
        )

        logger.info(
            "prometheus_instrumentation_enabled",
            endpoint="/metrics",
        )
    except ImportError:
        logger.warning(
            "prometheus_instrumentation_unavailable",
            reason="prometheus-fastapi-instrumentator is not installed; "
            "the /metrics endpoint will not be available",
        )


def _register_routers(app: FastAPI) -> None:
    """Register all API routers with the FastAPI application.

    Routers are imported lazily to avoid circular imports and to allow
    individual router modules to be developed independently.
    """
    from app.api.health import router as health_router  # noqa: PLC0415
    from app.api.v1 import router as api_v1_router  # noqa: PLC0415
    from app.api.websocket import router as ws_router  # noqa: PLC0415

    app.include_router(health_router)
    app.include_router(api_v1_router, prefix="/api/v1")
    app.include_router(ws_router)


def _error_code_to_http_status(error_code: str) -> int:
    """Map domain error codes to HTTP status codes."""
    mapping: dict[str, int] = {
        "DATA_FETCH_ERROR": 502,
        "CACHE_ERROR": 503,
        "CONSTRAINT_VIOLATION": 422,
        "SOLVER_INFEASIBLE": 422,
        "QUANTUM_TIMEOUT": 504,
        "QUANTUM_ASSET_LIMIT_EXCEEDED": 422,
        "AGENT_EXECUTION_ERROR": 500,
        "INTERNAL_ERROR": 500,
    }
    return mapping.get(error_code, 500)


# Module-level app instance (used by Uvicorn and tests)
app = create_app()
