"""Custom exception hierarchy for the Portfolio Optimizer.

All domain exceptions carry structured metadata so that FastAPI exception
handlers can return consistent JSON error responses with ``error_code``,
``message``, and ``details`` fields.
"""

from __future__ import annotations

from typing import Any


class PortfolioOptimizerError(Exception):
    """Base class for all application-level exceptions."""

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details: dict[str, Any] = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-serialisable dict for API error responses."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


# ── Data layer ────────────────────────────────────────────────────────────────


class DataFetchError(PortfolioOptimizerError):
    """Raised when yfinance fails to return usable price data.

    Examples:
        - Empty DataFrame returned for all requested tickers
        - Network timeout after all retries exhausted
        - All columns dropped due to excessive NaN values
    """

    def __init__(
        self,
        message: str,
        tickers: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="DATA_FETCH_ERROR",
            details={**(details or {}), "tickers": tickers or []},
        )
        self.tickers = tickers or []


class CacheError(PortfolioOptimizerError):
    """Raised when Redis cache operations fail unexpectedly."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, error_code="CACHE_ERROR", details=details)


# ── Optimization layer ────────────────────────────────────────────────────────


class OptimizationError(PortfolioOptimizerError):
    """Base class for optimization engine failures."""

    def __init__(
        self,
        message: str,
        error_code: str = "OPTIMIZATION_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, error_code=error_code, details=details)


class ConstraintViolationError(OptimizationError):
    """Raised when user-supplied constraints are logically invalid.

    Examples:
        - ``min_portfolio_return`` exceeds the maximum achievable return
        - ``max_weight_per_asset`` is so small that budget constraint cannot be met
        - Sector limits sum to less than 1.0 making full budget allocation impossible
    """

    def __init__(
        self,
        message: str,
        violated_constraints: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="CONSTRAINT_VIOLATION",
            details={
                **(details or {}),
                "violated_constraints": violated_constraints or [],
            },
        )
        self.violated_constraints = violated_constraints or []


class SolverInfeasibleError(OptimizationError):
    """Raised when the CVXPY solver cannot find a feasible solution.

    This typically means the constraints are over-specified or contradictory.
    The ``relaxation_suggestions`` field provides hints for the user.
    """

    def __init__(
        self,
        message: str,
        solver_status: str = "infeasible",
        relaxation_suggestions: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="SOLVER_INFEASIBLE",
            details={
                **(details or {}),
                "solver_status": solver_status,
                "relaxation_suggestions": relaxation_suggestions or [],
            },
        )
        self.solver_status = solver_status
        self.relaxation_suggestions = relaxation_suggestions or []


class QuantumTimeoutError(OptimizationError):
    """Raised when a quantum optimization job exceeds the configured timeout."""

    def __init__(
        self,
        message: str,
        timeout_seconds: int = 60,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="QUANTUM_TIMEOUT",
            details={**(details or {}), "timeout_seconds": timeout_seconds},
        )
        self.timeout_seconds = timeout_seconds


class QuantumAssetLimitError(OptimizationError):
    """Raised when the number of assets exceeds MAX_QUANTUM_ASSETS."""

    def __init__(
        self,
        num_assets: int,
        max_assets: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=(
                f"Quantum optimization supports at most {max_assets} assets, "
                f"but {num_assets} were provided. "
                "Reduce the asset list or use classical optimization."
            ),
            error_code="QUANTUM_ASSET_LIMIT_EXCEEDED",
            details={
                **(details or {}),
                "num_assets": num_assets,
                "max_assets": max_assets,
            },
        )


# ── Agent layer ───────────────────────────────────────────────────────────────


class AgentExecutionError(PortfolioOptimizerError):
    """Raised when the LangGraph agent graph encounters an unrecoverable error."""

    def __init__(
        self,
        message: str,
        node_name: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="AGENT_EXECUTION_ERROR",
            details={**(details or {}), "node_name": node_name},
        )
        self.node_name = node_name
