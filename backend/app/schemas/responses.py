"""Pydantic v2 response schemas for the Portfolio Optimizer API.

These models define the JSON structure of all API responses.
They mirror the TypeScript types in frontend/src/types/api.ts.

Phase 1 additions:
    - FrontierPoint        — single (x, y) Pareto-frontier sample.
    - FrontierReport       — full bundle (points, dominant set,
                             knee/reference portfolios, commentary).
    - OptimizationRunDetail gains a `frontier_report` field.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Enums ───────────────────────────────────────────────────────────────────

OptimizationStatus = Literal["pending", "running", "completed", "failed"]

FrontierMeasureName = Literal[
    "return",
    "volatility",
    "sharpe",
    "max_drawdown",
    "diversification_hhi",
    "esg_score",
    "sector_concentration",
]


# ── Shared sub-models ───────────────────────────────────────────────────────


class AssetWeight(BaseModel):
    """Weight and dollar allocation for a single asset."""

    ticker: str
    weight: float = Field(ge=0.0, le=1.0)
    allocation: float = Field(ge=0.0, description="Dollar amount allocated")
    sector: str | None = None


class PortfolioMetrics(BaseModel):
    """Key performance metrics for a portfolio."""

    expected_return: float = Field(description="Annualised expected return")
    volatility: float = Field(description="Annualised volatility (std dev)")
    sharpe_ratio: float = Field(description="Sharpe ratio")
    max_drawdown: float | None = Field(default=None, description="Maximum drawdown")
    num_assets: int = Field(description="Number of assets with non-zero weight")


class ClassicalResult(BaseModel):
    """Result from the Markowitz MVO classical optimizer."""

    weights: list[AssetWeight]
    metrics: PortfolioMetrics
    solver_status: str
    solve_time_ms: float


class QAOAResult(BaseModel):
    """Result from the QAOA quantum optimizer (Qiskit)."""

    selected_assets: list[str]
    weights: list[AssetWeight]
    metrics: PortfolioMetrics
    circuit_depth: int
    num_qubits: int
    solve_time_ms: float


class VQEResult(BaseModel):
    """Result from the VQE-style quantum optimizer (PennyLane)."""

    selected_assets: list[str]
    weights: list[AssetWeight]
    metrics: PortfolioMetrics
    num_qubits: int
    solve_time_ms: float


class QuantumResult(BaseModel):
    """Combined quantum optimization results."""

    qaoa: QAOAResult | None = None
    vqe: VQEResult | None = None


class ComparisonSummary(BaseModel):
    """Side-by-side comparison of classical vs quantum results."""

    sharpe_improvement_qaoa: float | None = None
    sharpe_improvement_vqe: float | None = None
    return_diff_qaoa: float | None = None
    return_diff_vqe: float | None = None
    volatility_diff_qaoa: float | None = None
    volatility_diff_vqe: float | None = None
    recommendation: str


# ── Efficient frontier ─────────────────────────────────────────────────────


class FrontierPoint(BaseModel):
    """Single sample on the efficient frontier.

    Each point corresponds to one parametric solve of the multi-objective
    problem at a fixed level of the Y-measure (the X-measure is then
    optimised).  The ``weights`` payload allows the UI to surface the
    full allocation when the user clicks a point.

    Fields:
        x             — Value of the X-axis measure at this point.
        y             — Value of the Y-axis measure at this point.
        sharpe        — Sharpe ratio of this portfolio (always
                        populated for ranking convenience).
        weights       — Asset allocation for this frontier portfolio.
        is_dominant   — True if the point is Pareto-efficient given the
                        chosen objective directions.
        is_knee       — True if this is the algorithmically chosen
                        "knee" point (maximum-curvature trade-off).
        solver_status — Status string from CVXPY for traceability.
    """

    x: float = Field(description="X-axis measure value")
    y: float = Field(description="Y-axis measure value")
    sharpe: float = Field(description="Sharpe ratio for ranking and tooltips")
    weights: list[AssetWeight] = Field(
        default_factory=list,
        description="Full asset allocation for this frontier portfolio",
    )
    is_dominant: bool = Field(
        default=True,
        description="True when the point is Pareto-efficient",
    )
    is_knee: bool = Field(
        default=False,
        description="True for the algorithmically chosen knee point",
    )
    solver_status: str = Field(
        default="optimal",
        description="CVXPY solver status (optimal / optimal_inaccurate / infeasible)",
    )


class FrontierReport(BaseModel):
    """Full bundle returned by the frontier sweep node.

    Contains everything the UI needs to render the chart, table, export
    button, and LLM commentary without further server round-trips.
    """

    x_measure: FrontierMeasureName = Field(
        description="Canonical name of the X-axis measure",
    )
    y_measure: FrontierMeasureName = Field(
        description="Canonical name of the Y-axis measure",
    )
    x_direction: Literal["maximize", "minimize"] = Field(
        description="Optimisation direction for the X measure",
    )
    y_direction: Literal["maximize", "minimize"] = Field(
        description="Optimisation direction for the Y measure",
    )
    points: list[FrontierPoint] = Field(
        description="All sampled points (dominant + dominated)",
    )
    knee_point_index: int | None = Field(
        default=None,
        description="Index into `points` of the chosen knee portfolio, if any",
    )
    max_sharpe_index: int | None = Field(
        default=None,
        description="Index of the max-Sharpe reference portfolio, if any",
    )
    min_risk_index: int | None = Field(
        default=None,
        description="Index of the minimum-risk reference portfolio, if any",
    )
    num_dominant: int = Field(
        default=0,
        description="Number of Pareto-dominant points",
    )
    num_dominated: int = Field(
        default=0,
        description="Number of dominated points",
    )
    solve_time_ms: float = Field(
        default=0.0,
        description="Total wall-clock time spent sweeping the frontier",
    )
    commentary: str | None = Field(
        default=None,
        description="LLM-generated natural-language summary of the frontier",
    )


# ── Run response models ────────────────────────────────────────────────────


class OptimizationSubmitResponse(BaseModel):
    """Response for POST /api/v1/optimize.

    Security note (Phase 2)
    -----------------------
    ``ws_token`` is a short-lived HMAC-SHA256 signed token scoped to this
    specific ``run_id``.  The frontend must pass it as the ``?token=`` query
    parameter when opening the WebSocket connection at
    ``/ws/runs/{run_id}/progress``.

    The token is issued by ``app.core.security.create_ws_token`` and verified
    by the WebSocket handler before ``websocket.accept()`` is called.  A token
    for run A cannot be used to subscribe to run B.

    Token lifetime: 300 seconds (5 minutes) from issuance.
    """

    run_id: str = Field(description="UUID of the submitted optimization run")
    ws_token: str | None = Field(
        default=None,
        description=(
            "Short-lived HMAC-signed token for WebSocket authentication. "
            "Pass as ?token=<ws_token> when connecting to "
            "/ws/runs/{run_id}/progress. Valid for 300 seconds. "
            "None if token generation failed (non-fatal)."
        ),
    )


class RunStatusResponse(BaseModel):
    """Lightweight status response for GET /api/v1/runs/{run_id}/status.

    Returns only the lifecycle fields without the full result payload,
    making it suitable for efficient polling from the frontend.
    """

    run_id: str = Field(description="UUID of the optimization run")
    status: OptimizationStatus = Field(description="Current lifecycle status")
    created_at: datetime = Field(description="UTC timestamp when the run was submitted")
    completed_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when the run finished (null if still in progress)",
    )


class OptimizationRunSummary(BaseModel):
    """Summary row for the run history list."""

    model_config = ConfigDict(from_attributes=True)

    run_id: str
    status: OptimizationStatus
    tickers: list[str]
    budget: float
    created_at: datetime
    completed_at: datetime | None = None
    classical_sharpe: float | None = None
    quantum_sharpe: float | None = None


class OptimizationRunDetail(OptimizationRunSummary):
    """Full detail of a completed optimization run."""

    classical_result: ClassicalResult | None = None
    quantum_result: QuantumResult | None = None
    comparison: ComparisonSummary | None = None
    llm_explanation: str | None = None
    error_message: str | None = None
    frontier_report: FrontierReport | None = Field(
        default=None,
        description=(
            "Efficient-frontier report (only populated when the request "
            "had `frontier.enabled = true`)."
        ),
    )


class PaginatedRunsResponse(BaseModel):
    """Paginated list of optimization run summaries."""

    items: list[OptimizationRunSummary]
    total: int = Field(description="Total number of runs")
    page: int = Field(description="Current page number (1-based)")
    page_size: int = Field(description="Items per page")


# ── Asset search ───────────────────────────────────────────────────────────


class AssetSearchResult(BaseModel):
    """Single asset search result."""

    ticker: str
    name: str
    sector: str | None = None
    exchange: str | None = None


# ── Health ─────────────────────────────────────────────────────────────────


class ServiceStatus(BaseModel):
    database: Literal["up", "down"]
    redis: Literal["up", "down"]
    celery: Literal["up", "down"]


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    version: str
    services: ServiceStatus
