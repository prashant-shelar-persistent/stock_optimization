"""API v1 router — aggregates all v1 sub-routers.

All sub-routers are included here with no prefix. The ``/api/v1`` prefix
is applied at the ``main.py`` level when this router is registered with
the FastAPI application.

Routes exposed:
    GET    /api/v1/health                    — Health check (alias for /health)
    POST   /api/v1/optimize                  — Submit optimization run
    GET    /api/v1/runs                      — List run history (paginated)
    GET    /api/v1/runs/{run_id}             — Get full run detail
    GET    /api/v1/runs/{run_id}/status      — Get lightweight run status
    GET    /api/v1/assets/search             — Search for assets
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from app.api.v1.assets import router as assets_router
from app.api.v1.optimize import router as optimize_router
from app.api.v1.runs import router as runs_router


router = APIRouter()

# Health check alias — /api/v1/health redirects to /health for ALB compatibility
@router.get("/health", include_in_schema=False, tags=["health"])
async def health_alias() -> RedirectResponse:
    """Redirect /api/v1/health to /health for load balancer compatibility."""
    return RedirectResponse(url="/health", status_code=307)


router.include_router(optimize_router)
router.include_router(runs_router)
router.include_router(assets_router)
