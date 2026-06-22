"""Pydantic v2 schemas for the quantum optimization engine.

These models define the input and output contracts for the quantum
optimization pipeline (QUBO formulation → QAOA → VQE → dispatcher).

Design notes
------------
- ``QuantumOptimizationConstraints`` captures all user-configurable
  parameters for the quantum solvers (QUBO tuning, circuit depth, etc.).
- ``QuantumOptimizationInput`` bundles market data with constraints so
  the dispatcher receives a single, validated object.
- ``QuantumAssetResult`` represents the result for a single quantum
  algorithm (QAOA or VQE) with full portfolio metrics.
- ``QuantumOptimizationResult`` is the canonical output type returned
  by :class:`QuantumDispatcher.optimize`. It is JSON-serialisable and
  can be stored directly in the run-history database.

Usage::

    from app.engines.quantum.schemas import (
        QuantumOptimizationConstraints,
        QuantumOptimizationInput,
        QuantumOptimizationResult,
    )

    constraints = QuantumOptimizationConstraints(
        num_assets_to_select=3,
        qaoa_p=2,
        vqe_layers=2,
        vqe_max_iterations=100,
    )

    inp = QuantumOptimizationInput(
        tickers=["AAPL", "MSFT", "GOOGL", "AMZN"],
        expected_returns=[0.12, 0.10, 0.09, 0.15],
        cov_matrix=[[...], ...],
        sector_tags={"AAPL": "Technology", ...},
        constraints=constraints,
        budget=100_000.0,
    )
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QuantumOptimizationConstraints(BaseModel):
    """Constraints and tuning parameters for the quantum optimization engine.

    Attributes:
        num_assets_to_select: Target number of assets k to select from the
            universe. Must be in [1, n]. If ``None``, defaults to
            ``max(2, int(n * 0.5))`` where n is the total number of assets.
        lambda_return: QUBO weight for the return maximisation term.
            Higher values push the solver toward high-return assets.
            Defaults to 1.0.
        lambda_risk: QUBO weight for the risk minimisation term.
            Higher values push the solver toward low-correlation assets.
            Defaults to 1.0.
        lambda_cardinality: QUBO penalty weight for the cardinality
            constraint (exactly k assets selected). Must be large enough
            to dominate the objective. Defaults to 5.0.
        qaoa_p: QAOA circuit depth (number of QAOA layers / repetitions).
            Higher p generally improves solution quality at the cost of
            longer circuit execution time. Defaults to 2.
        vqe_layers: Number of variational ansatz layers for VQE. Each
            layer consists of Ry rotations on all qubits followed by a
            CNOT entanglement chain. Defaults to 2.
        vqe_max_iterations: Maximum number of gradient descent steps for
            VQE parameter optimisation. Defaults to 100.
        run_qaoa: Whether to run the QAOA solver. Defaults to True.
        run_vqe: Whether to run the VQE solver. Defaults to True.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    num_assets_to_select: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Target number of assets k to select. "
            "If None, defaults to max(2, int(n * 0.5))."
        ),
    )
    lambda_return: float = Field(
        default=1.0,
        gt=0.0,
        description="QUBO weight for the return maximisation term",
    )
    lambda_risk: float = Field(
        default=1.0,
        gt=0.0,
        description="QUBO weight for the risk minimisation term",
    )
    lambda_cardinality: float = Field(
        default=5.0,
        gt=0.0,
        description="QUBO penalty weight for the cardinality constraint",
    )
    qaoa_p: int = Field(
        default=2,
        ge=1,
        le=10,
        description="QAOA circuit depth (number of QAOA layers)",
    )
    vqe_layers: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Number of VQE variational ansatz layers",
    )
    vqe_max_iterations: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Maximum gradient descent steps for VQE",
    )
    run_qaoa: bool = Field(
        default=True,
        description="Whether to run the QAOA (Qiskit) solver",
    )
    run_vqe: bool = Field(
        default=True,
        description="Whether to run the VQE (PennyLane) solver",
    )


class QuantumOptimizationInput(BaseModel):
    """Input bundle for the quantum optimization dispatcher.

    Attributes:
        tickers: Ordered list of asset ticker symbols. Must have at least 2
            and at most ``MAX_QUANTUM_ASSETS`` (default: 8).
        expected_returns: Annualised expected returns, one per ticker.
            Must have the same length as ``tickers``.
        cov_matrix: Annualised covariance matrix as a 2-D list of floats,
            shape (n, n). Must be square and match the number of tickers.
        sector_tags: Mapping of ticker → GICS sector name. Used for
            sector-level reporting in the result. Tickers not in this map
            are tagged as "Unknown".
        constraints: Quantum solver constraints and tuning parameters.
        budget: Total investment budget in USD. Used to compute dollar
            allocations from fractional weights. Defaults to 1.0.
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
    constraints: QuantumOptimizationConstraints = Field(
        default_factory=QuantumOptimizationConstraints,
        description="Quantum solver constraints and tuning parameters",
    )
    budget: float = Field(
        default=1.0,
        gt=0.0,
        description="Total investment budget in USD",
    )

    @model_validator(mode="after")
    def validate_dimensions(self) -> "QuantumOptimizationInput":
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

        # Validate num_assets_to_select if explicitly provided
        if self.constraints.num_assets_to_select is not None:
            if self.constraints.num_assets_to_select > n:
                raise ValueError(
                    f"num_assets_to_select ({self.constraints.num_assets_to_select}) "
                    f"cannot exceed the number of tickers ({n})"
                )

        return self


class QuantumAssetWeight(BaseModel):
    """Weight and dollar allocation for a single asset in a quantum portfolio.

    Attributes:
        ticker: Asset ticker symbol.
        weight: Portfolio weight (fraction). In [0, 1].
        allocation: Dollar amount allocated (weight × budget).
        sector: GICS sector name. ``None`` if not available.
    """

    model_config = ConfigDict(populate_by_name=True)

    ticker: str = Field(description="Asset ticker symbol")
    weight: float = Field(ge=0.0, le=1.0, description="Portfolio weight (fraction)")
    allocation: float = Field(ge=0.0, description="Dollar amount allocated")
    sector: str | None = Field(default=None, description="GICS sector name")


class QuantumPortfolioMetrics(BaseModel):
    """Portfolio performance metrics for a quantum-selected portfolio.

    Attributes:
        expected_return: Annualised expected portfolio return.
        volatility: Annualised portfolio volatility (standard deviation).
        sharpe_ratio: Sharpe ratio: (return - risk_free_rate) / volatility.
        max_drawdown: Maximum drawdown (negative fraction). ``None`` if
            historical returns data was not provided.
        num_assets: Number of selected assets.
        qubo_energy: QUBO objective value for the selected solution.
            Lower is better. ``None`` if not computed.
    """

    model_config = ConfigDict(populate_by_name=True)

    expected_return: float = Field(description="Annualised expected portfolio return")
    volatility: float = Field(description="Annualised portfolio volatility")
    sharpe_ratio: float = Field(description="Sharpe ratio")
    max_drawdown: float | None = Field(
        default=None,
        description="Maximum drawdown (negative fraction)",
    )
    num_assets: int = Field(description="Number of selected assets")
    qubo_energy: float | None = Field(
        default=None,
        description="QUBO objective value for the selected solution (lower is better)",
    )


class QuantumAssetResult(BaseModel):
    """Result from a single quantum optimization algorithm (QAOA or VQE).

    Attributes:
        algorithm: Algorithm name: ``"QAOA"`` or ``"VQE"``.
        selected_assets: List of selected ticker symbols.
        weights: Per-asset weight and dollar allocation.
        metrics: Portfolio performance metrics.
        solve_time_ms: Wall-clock time for the solve in milliseconds.
        num_qubits: Number of qubits used (= number of assets in universe).
        circuit_depth: Estimated circuit depth. For QAOA: 2 * p * n.
            For VQE: num_layers * n. ``None`` for VQE (not directly comparable).
        solver_used: Specific solver/backend used (e.g. ``"qiskit_aer"``
            or ``"pennylane_default.qubit"``).
        fallback_used: Whether the greedy fallback was used instead of the
            quantum solver (e.g. because Qiskit/PennyLane was unavailable).
        extra: Additional solver metadata.
    """

    model_config = ConfigDict(populate_by_name=True)

    algorithm: str = Field(description="Algorithm name: 'QAOA' or 'VQE'")
    selected_assets: list[str] = Field(
        description="List of selected ticker symbols",
    )
    weights: list[QuantumAssetWeight] = Field(
        description="Per-asset weight and dollar allocation",
    )
    metrics: QuantumPortfolioMetrics = Field(
        description="Portfolio performance metrics",
    )
    solve_time_ms: float = Field(
        ge=0.0,
        description="Wall-clock time for the solve in milliseconds",
    )
    num_qubits: int = Field(
        description="Number of qubits used (= number of assets in universe)",
    )
    circuit_depth: int | None = Field(
        default=None,
        description="Estimated circuit depth",
    )
    solver_used: str = Field(
        default="unknown",
        description="Specific solver/backend used",
    )
    fallback_used: bool = Field(
        default=False,
        description="Whether the greedy fallback was used instead of the quantum solver",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional solver metadata",
    )


class QuantumOptimizationResult(BaseModel):
    """Result returned by :meth:`QuantumDispatcher.optimize`.

    Contains results from both QAOA and VQE solvers (either may be ``None``
    if the corresponding solver failed or was disabled). Also includes
    the QUBO matrix metadata and the best overall result.

    Attributes:
        qaoa: QAOA (Qiskit) result. ``None`` if QAOA was disabled or failed.
        vqe: VQE (PennyLane) result. ``None`` if VQE was disabled or failed.
        best_algorithm: Name of the algorithm with the highest Sharpe ratio
            (``"QAOA"`` or ``"VQE"``). ``None`` if both failed.
        best_sharpe: Sharpe ratio of the best algorithm. ``None`` if both failed.
        num_assets_universe: Total number of assets in the input universe.
        num_assets_selected: Number of assets selected (= k).
        qubo_shape: Shape of the QUBO matrix as [n, n].
        total_solve_time_ms: Total wall-clock time for both solvers.
        extra: Additional metadata (e.g. QUBO statistics).
    """

    model_config = ConfigDict(populate_by_name=True)

    qaoa: QuantumAssetResult | None = Field(
        default=None,
        description="QAOA (Qiskit) result",
    )
    vqe: QuantumAssetResult | None = Field(
        default=None,
        description="VQE (PennyLane) result",
    )
    best_algorithm: str | None = Field(
        default=None,
        description="Name of the algorithm with the highest Sharpe ratio",
    )
    best_sharpe: float | None = Field(
        default=None,
        description="Sharpe ratio of the best algorithm",
    )
    num_assets_universe: int = Field(
        description="Total number of assets in the input universe",
    )
    num_assets_selected: int = Field(
        description="Number of assets selected (= k)",
    )
    qubo_shape: list[int] = Field(
        description="Shape of the QUBO matrix as [n, n]",
    )
    total_solve_time_ms: float = Field(
        ge=0.0,
        description="Total wall-clock time for both solvers in milliseconds",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (e.g. QUBO statistics)",
    )
