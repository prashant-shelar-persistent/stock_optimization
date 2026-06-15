"""Portfolio Optimizer — database layer package.

Exports:
    Base              — SQLAlchemy declarative base (used by Alembic env.py)
    OptimizationRun   — ORM model for the optimization_runs table
    engine            — Async SQLAlchemy engine singleton
    AsyncSessionLocal — Async session factory
    repository        — Data access layer (CRUD operations)
"""
from __future__ import annotations

from app.db.models import Base, OptimizationRun
from app.db.session import AsyncSessionLocal, engine


__all__ = [
    "AsyncSessionLocal",
    "Base",
    "OptimizationRun",
    "engine",
]
