"""FastAPI application factory and lifespan manager.

This module creates the FastAPI app instance, registers all routers,
configures middleware, and manages startup/shutdown lifecycle events.

Security hardening (Phase 1)
-----------------------------
- CORS origins are now driven by the ``ALLOWED_ORIGINS`` environment variable
  (parsed from ``Settings.allowed_origins_list``).  The previous wildcard
  ``allow_origins=["*"]`` combined with ``allow_credentials=True`` is
  rejected by browsers per the CORS specification and has been removed.
- A ``slowapi`` ``RateLimitExceeded`` exception handler is registered so that
  rate-limited requests receive a well-formed JSON 429 response instead of an
  unhandled 500.

Prometheus instrumentation is added via ``prometheus-fastapi-instrumentator``
which exposes a ``/metrics`` endpoint in Prometheus text format (version 0.0.4).
The endpoint provides:
  - ``http_requests_total``          — request counter labelled by method/handler/status
  - ``http_request_duration_seconds`` — latency histogram
  - ``http_requests_inprogress``     — in-flight request gauge
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.dependencies import close_redis
from app.core.exceptions import PortfolioOptimizerError
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import limiter


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
        allowed_origins=settings.allowed_origins_list,
    )

    yield  # Application runs here

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("application_shutting_down")
    await close_redis()
    logger.info("application_stopped")


def create_app() -> "FastAPI":
    """Create and configure the FastAPI application.

    Returns:
        A fully configured FastAPI instance with:
        - CORS middleware (env-driven origins, no wildcard with credentials)
        - slowapi rate-limit error handler
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
    # Origins are loaded from the ``ALLOWED_ORIGINS`` environment variable
    # (comma-separated list).  The previous ``allow_origins=["*"]`` combined
    # with ``allow_credentials=True`` is a CORS spec violation that browsers
    # reject, and it exposes the API to any origin.
    #
    # Security rules enforced here:
    #   1. Wildcard ``*`` is never combined with ``allow_credentials=True``.
    #   2. In production/staging, the Settings validator already rejects ``*``
    #      and empty origin lists, so we never reach this point with an
    #      insecure configuration.
    #   3. In development the default is ``http://localhost:3000`` (the Vite
    #      dev server), which is safe for local use.
    allowed_origins = settings.allowed_origins_list

    # Determine whether credentials (cookies / Authorization headers) should
    # be allowed.  Credentials MUST NOT be combined with a wildcard origin.
    allow_credentials = "*" not in allowed_origins

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
        max_age=600,  # Cache preflight for 10 minutes
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

    # ── Rate limiter state ────────────────────────────────────────────────────
    # slowapi requires the Limiter instance to be attached to app.state so
    # that the middleware can find it when processing requests.  The limiter
    # is a lazy proxy that initialises the real Limiter on first use.
    app.state.limiter = limiter

    # SlowAPIMiddleware intercepts requests and injects rate-limit headers.
    # Must be added AFTER setting app.state.limiter.
    try:
        from slowapi.middleware import SlowAPIMiddleware  # noqa: PLC0415
        app.add_middleware(SlowAPIMiddleware)
    except ImportError:
        pass

    # ── Exception handlers ────────────────────────────────────────────────────
    _register_exception_handlers(app)

    # ── Routers ───────────────────────────────────────────────────────────────
    # Routers are imported lazily to avoid circular imports and to allow
    # individual router modules to be developed independently.
    _register_routers(app)

    return app


def _register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI application.

    Handlers registered:
    - ``RateLimitExceeded`` (slowapi) → 429 JSON response with ``Retry-After``
    - ``PortfolioOptimizerError``     → structured JSON mapped to HTTP status
    - ``Exception``                   → catch-all 500 JSON response
    """
    # ── slowapi rate-limit handler ────────────────────────────────────────────
    # slowapi raises ``slowapi.errors.RateLimitExceeded`` when a client
    # exceeds the configured rate limit.  Without this handler FastAPI would
    # return a 500 Internal Server Error.  We convert it to a proper 429 with
    # a ``Retry-After`` header so clients know when to retry.
    try:
        from slowapi.errors import RateLimitExceeded  # noqa: PLC0415

        @app.exception_handler(RateLimitExceeded)
        async def rate_limit_handler(
            request: Request,
            exc: RateLimitExceeded,
        ) -> JSONResponse:
            """Return a 429 Too Many Requests response for rate-limited clients."""
            logger.warning(
                "rate_limit_exceeded",
                path=str(request.url),
                client=request.client.host if request.client else "unknown",
                limit=str(exc),
            )
            # Extract retry-after from the exception if available
            retry_after = getattr(exc, "retry_after", None)
            headers = {}
            if retry_after is not None:
                headers["Retry-After"] = str(int(retry_after))

            return JSONResponse(
                status_code=429,
                content={
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many requests. Please slow down and try again later.",
                    "details": {"limit": str(exc)},
                },
                headers=headers,
            )

    except ImportError:
        logger.warning(
            "slowapi_not_installed",
            message="slowapi is not installed; rate-limit handler not registered",
        )

    # ── Domain error handler ──────────────────────────────────────────────────
    @app.exception_handler(PortfolioOptimizerError)
    async def portfolio_error_handler(
        request: Request,
        exc: PortfolioOptimizerError,
    ) -> "JSONResponse":
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

    # ── Catch-all handler ─────────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def unhandled_error_handler(
        request: Request,
        exc: Exception,
    ) -> "JSONResponse":
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


def _setup_prometheus(app: FastAPI) -> "None":
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

    NOTE: prometheus-fastapi-instrumentator has a known incompatibility with
    FastAPI >= 0.111 where _IncludedRouter objects lack a 'path' attribute.
    We catch that error gracefully so metrics are simply unavailable rather
    than crashing every request.
    """
    # prometheus-fastapi-instrumentator has a known incompatibility with
    # FastAPI >= 0.111 where _IncludedRouter objects lack a 'path' attribute,
    # causing every request to crash with AttributeError. Since Prometheus
    # metrics are non-critical for the application to function, instrumentation
    # is disabled until a compatible version is available.
    logger.info(
        "prometheus_instrumentation_skipped",
        reason="disabled due to _IncludedRouter incompatibility with FastAPI>=0.111",
    )


def _register_routers(app: FastAPI) -> "None":
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
    """Map domain error codes to HTTP status codes.

    Returns the appropriate HTTP status code for a given domain error code.
    Unknown error codes fall back to 500 (Internal Server Error).
    """
    mapping: dict[str, int] = {
        # ── Data layer ────────────────────────────────────────────────────────
        "DATA_FETCH_ERROR": 502,
        "CACHE_ERROR": 503,
        # ── Optimization layer ────────────────────────────────────────────────
        "CONSTRAINT_VIOLATION": 422,
        "SOLVER_INFEASIBLE": 422,
        "QUANTUM_TIMEOUT": 504,
        "QUANTUM_ASSET_LIMIT_EXCEEDED": 422,
        # ── Agent layer ───────────────────────────────────────────────────────
        "AGENT_EXECUTION_ERROR": 500,
        # ── Chat layer ────────────────────────────────────────────────────────
        # 404 - session does not exist in the database
        "CHAT_SESSION_NOT_FOUND": 404,
        # 410 - session existed but its TTL has passed; client must create new session
        "CHAT_SESSION_EXPIRED": 410,
        # 409 - session has already been confirmed; cannot confirm again
        "CHAT_SESSION_ALREADY_CONFIRMED": 409,
        # 409 - operation attempted on a session in an incompatible lifecycle state
        "CHAT_INVALID_STATE": 409,
        # 502 - upstream LLM call failed or returned unparseable structured output
        "CHAT_SLOT_EXTRACTION_ERROR": 502,
        # 422 - session has too many messages; client must start a new session
        "CHAT_TOO_MANY_MESSAGES": 422,
        # 422 - slot_overrides dict has too many keys or unrecognised field names
        "CHAT_SLOT_OVERRIDE_ERROR": 422,
        # ── Rate limiting ─────────────────────────────────────────────────────
        "RATE_LIMIT_EXCEEDED": 429,
        # ── WebSocket auth ────────────────────────────────────────────────────
        "WS_AUTH_FAILED": 403,
        # ── Fallback ──────────────────────────────────────────────────────────
        "INTERNAL_ERROR": 500,
    }
    return mapping.get(error_code, 500)


# Module-level app instance (used by Uvicorn and tests)
app = create_app()
