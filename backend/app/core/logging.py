"""Structured logging configuration using structlog.

Provides JSON output in production/staging and human-readable console output
in development. All loggers are bound with the module name automatically.

Usage::

    from app.core.logging import get_logger

    logger = get_logger(__name__)
    logger.info("optimization_started", run_id=str(run_id), tickers=tickers)
"""

import logging
import sys
from typing import Any

import structlog


def configure_logging(log_level: str = "INFO", environment: str = "development") -> "None":
    """Configure structlog and stdlib logging.

    Call this once at application startup (in ``main.py`` lifespan).

    Args:
        log_level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL.
        environment: ``development`` uses ConsoleRenderer; all others use JSONRenderer.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if environment == "development":
        # Human-readable coloured output for local development
        renderer: Any = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # Machine-parseable JSON for production / staging
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog BoundLogger bound with the given module name.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A structlog BoundLogger instance.

    Example::

        logger = get_logger(__name__)
        logger.info("event", key="value")
    """
    return structlog.get_logger(name)  # type: ignore[return-value]
