"""Pydantic v2 schemas for the classical optimization engine.

These models define the input and output contracts for the
:class:`~app.engines.classical.optimizer.ClassicalOptimizer`.

Design notes
------------
- ``OptimizationConstraints`` captures all user-configurable constraints
  that are passed to the CVXPY solver.
- ``ClassicalOptimizationInput`` bundles market data with constraints so
  the optimizer receives a single, validated object.
- ``ClassicalOptimizationResult`` is the canonical output type returned
  by :meth:`ClassicalOptimizer.optimize`. It is JSON-serialisable and
  can be stored directly in the run-history database.

Usage::

    from app.engines.classical.schemas import (
        OptimizationConstraints,
        ClassicalOptimizationInput,
        ClassicalOptimizationResult,
    )

    constraints = OptimizationConstraints(
        max_weight_per_asset=0.3,
        min_portfolio_return=0.08,
        sector_limits={"Technology": 0.5},
        risk_tolerance=0.5,
        budget=100_000.0,
    )

    inp = ClassicalOptimizationInput(
        tickers=["AAPL", "MSFT", "GOOGL"],
        expected_returns=[0.12, 0.10, 0.09],
        cov_matrix=[[...], [...], [...]],
        sector_tags={"AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Technology"},
        constraints=constraints,
    )
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OptimizationConstraints(BaseModel):
    """Constraints passed to the CVXPY Markowitz MVO solver.

    Attributes:
        max_weight_per_asset: Maximum fraction of the portfolio that can be
            allocated to any single asset. Must be in (0, 1]. Defaults to 0.4.
        min_portfolio_return: Minimum acceptable annualised portfolio return.
            ``None`` means no minimum return constraint is applied.
        sector_limits: Mapping of sector name → maximum allocation fraction
            for that sector. E.g. ``{"Technology": 0.5}`` caps the combined
            weight of all Technology assets at 50%.
        risk_tolerance: Blending parameter between pure variance minimisation
            (0.0) and pure return maximisation (1.0). Defaults to 0.5.
        budget: Total investment budget in USD. Used to compute dollar
            allocations from fractional weights. Defaults to 1.0 (fractional).
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    max_weight_per_asset: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Maximum fraction of portfolio allocated to any single asset",
    )
    min_portfolio_return: float | None = Field(
        default=None,
        ge=0.0,
        le=5.0,
        description="Minimum acceptable annualised portfolio return (0.0–1.0)",
    )
    sector_limits: dict[str, float] = Field(
        default_factory=dict,
        description="Sector name → maximum allocation fraction (0.0–1.0)",
    )
    risk_tolerance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Blending parameter: 0.0 = pure variance minimisation, "
            "1.0 = pure return maximisation"
        ),
    )
    budget: float = Field(
        default=1.0,
        gt=0.0,
        description="Total investment budget in USD (used for dollar allocation output)",
    )

    @model_validator(mode="after")
    def validate_sector_limits(self) -> OptimizationConstraints:
        """Ensure all sector limit values are in [0, 1]."""
        for sector, limit in self.sector_limits.items():
            if not (0.0 <= limit <= 1.0):
                raise ValueError(
                    f"Sector limit for '{sector}' must be in [0, 1], got {limit}"
                )
        return self


class ClassicalOptimizationInput(BaseModel):
    """Input bundle for the classical Markowitz MVO optimizer.

    Attributes:
        tickers: Ordered list of asset ticker symbols. Must have at least 2.
        expected_returns: Annualised expected returns, one per ticker.
            Must have the same length as ``tickers``.
        cov_matrix: Annualised covariance matrix as a 2-D list of floats,
            shape (n, n). Must be square and match the number of tickers.
        sector_tags: Mapping of ticker → GICS sector name. Used to apply
            ``sector_limits`` constraints. Tickers not in this map are
            treated as belonging to an unconstrained sector.
        constraints: Optimization constraints and solver parameters.
    """

    model_config = ConfigDict(populate_by_name=True)

    tickers: list[str] = Field(
        description="Ordered list of asset ticker symbols",
        min_length=2,
    )
    expected_returns: list[float] = Field(
        description="Annualised expected returns, one per ticker",
    )
    cov_matrix: list[list[float]] = Field(
        description="Annualised covariance matrix, shape (n, n)",
    )
    sector_tags: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of ticker → GICS sector name",
    )
    constraints: OptimizationConstraints = Field(
        default_factory=OptimizationConstraints,
        description="Optimization constraints and solver parameters",
    )

    @model_validator(mode="after")
    def validate_dimensions(self) -> ClassicalOptimizationInput:
        """Ensure expected_returns and cov_matrix match the number of tickers."""
        n = len(self.tickers)

        if len(self.expected_returns) != n:
            raise ValueError(
                f"expected_returns must have {n} elements (one per ticker), "
                f"got {len(self.expected_returns)}"
            )

        if len(self.cov_matrix) != n:
            raise ValueError(
                f"cov_matrix must have {n} rows (one per ticker), "
                f"got {len(self.cov_matrix)}"
            )
        for i, row in enumerate(self.cov_matrix):
            if len(row) != n:
                raise ValueError(
                    f"cov_matrix row {i} must have {n} columns, got {len(row)}"
                )

        return self


class ClassicalOptimizationResult(BaseModel):
    """Result returned by :meth:`ClassicalOptimizer.optimize`.

    Attributes:
        weights: Mapping of ticker → portfolio weight (fraction). Weights
            sum to 1.0 (within numerical tolerance). Only assets with
            weight > 1e-4 are included.
        portfolio_return: Annualised expected portfolio return.
        portfolio_volatility: Annualised portfolio volatility (std dev).
        sharpe_ratio: Sharpe ratio: (return - risk_free_rate) / volatility.
        solver_status: CVXPY solver status string (e.g. ``"optimal"``).
        solve_time_ms: Wall-clock time taken by the solver in milliseconds.
        max_drawdown: Maximum drawdown (negative fraction). ``None`` if
            historical returns data was not provided.
        sortino_ratio: Sortino ratio. ``None`` if historical returns data
            was not provided.
        var_95: Daily Value at Risk at 95% confidence. ``None`` if
            historical returns data was not provided.
        num_assets: Number of assets with non-negligible weight.
        extra: Additional solver metadata (e.g. objective value, iterations).
    """

    model_config = ConfigDict(populate_by_name=True)

    weights: dict[str, float] = Field(
        description="Ticker → portfolio weight (fraction). Sums to 1.0.",
    )
    portfolio_return: float = Field(
        description="Annualised expected portfolio return",
    )
    portfolio_volatility: float = Field(
        description="Annualised portfolio volatility (standard deviation)",
    )
    sharpe_ratio: float = Field(
        description="Sharpe ratio: (return - risk_free_rate) / volatility",
    )
    solver_status: str = Field(
        description="CVXPY solver status string",
    )
    solve_time_ms: float = Field(
        description="Wall-clock time taken by the solver in milliseconds",
        ge=0.0,
    )
    max_drawdown: float | None = Field(
        default=None,
        description="Maximum drawdown (negative fraction). None if no historical data.",
    )
    sortino_ratio: float | None = Field(
        default=None,
        description="Sortino ratio. None if no historical data.",
    )
    var_95: float | None = Field(
        default=None,
        description="Daily VaR at 95% confidence. None if no historical data.",
    )
    num_assets: int = Field(
        default=0,
        description="Number of assets with non-negligible weight (> 1e-4)",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional solver metadata",
    )
