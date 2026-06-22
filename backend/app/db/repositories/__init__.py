"""Portfolio Optimizer — database repositories sub-package.

This sub-package provides a class-based repository layer on top of the
SQLAlchemy async session. It complements the module-level functions in
``app.db.repository`` with an object-oriented interface that is easier
to mock in tests and to extend with caching or other cross-cutting concerns.

Exports:
    RunsRepository — Class-based CRUD repository for OptimizationRun records.

Usage example::

    from app.db.repositories import RunsRepository

    async with AsyncSessionLocal() as session:
        repo = RunsRepository(session)
        run = await repo.create(run_id="...", request=req)
        await session.commit()
"""
from app.db.repositories.runs import RunsRepository


__all__ = ["RunsRepository"]
