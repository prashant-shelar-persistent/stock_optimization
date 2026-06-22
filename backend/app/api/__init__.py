"""Portfolio Optimizer — API layer package.

This package contains all FastAPI routers and WebSocket handlers:

    api/
    ├── health.py          — GET /health
    ├── websocket.py       — WS /ws/runs/{run_id}/progress
    ├── __init__.py        — Package marker
    └── v1/
        ├── __init__.py    — Aggregates v1 sub-routers
        ├── optimize.py    — POST /api/v1/optimize
        ├── runs.py        — GET /api/v1/runs, /runs/{run_id}, /runs/{run_id}/status
        └── assets.py      — GET /api/v1/assets/search
"""

