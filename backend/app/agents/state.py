"""LangGraph agent state definition.

The AgentState TypedDict is the shared state object that flows through
all nodes in the optimization graph. Each node reads from and writes to
this state.

State lifecycle:
    1. Initialized by the graph entry point with the OptimizationRequest
    2. data_fetch node populates price_data, returns_data, covariance_matrix
    3. constraint_validation node validates and normalises constraints
    4. classical_optimization node populates classical_result
    5. quantum_dispatch node populates quantum_result (if run_quantum=True)
    6. comparison node populates comparison_summary
    7. llm_explanation node populates llm_explanation

Error handling:
    Any node that raises an exception should catch it, set ``error`` and
    ``failed_node`` on the state, and return the state so the graph can
    route to the error handler or terminal node gracefully.
"""

from typing import Any, TypedDict

import numpy as np
import pandas as pd


class AgentState(TypedDict, total=False):
    """Shared state flowing through the LangGraph optimization pipeline.

    All fields are optional (``total=False``) because each node only
    populates the fields it is responsible for. Downstream nodes must
    use ``state.get(...)`` with sensible defaults.
    """

    # ── Input ────────────────────────────────────────────────────────────────
    run_id: str
    tickers: list[str]
    budget: float
    request_params: dict[str, Any]

    # ── Data fetch node outputs ───────────────────────────────────────────────
    price_data: pd.DataFrame          # Shape: (days, n_assets)
    returns_data: pd.DataFrame        # Shape: (days-1, n_assets) — daily log returns
    expected_returns: np.ndarray      # Shape: (n_assets,) — annualised
    covariance_matrix: np.ndarray     # Shape: (n_assets, n_assets) — annualised
    sector_map: dict[str, str]        # ticker → sector name

    # ── Constraint validation node outputs ────────────────────────────────────
    validated_constraints: dict[str, Any]
    constraint_warnings: list[str]

    # ── Classical optimization node outputs ───────────────────────────────────
    classical_result: dict[str, Any]  # Serialised ClassicalResult

    # ── Quantum dispatch node outputs ─────────────────────────────────────────
    quantum_result: dict[str, Any]    # Serialised QuantumResult

    # ── Comparison node outputs ───────────────────────────────────────────────
    comparison_summary: dict[str, Any]  # Serialised ComparisonSummary

    # ── LLM explanation node outputs ──────────────────────────────────────────
    llm_explanation: str

    # ── Frontier report node outputs ──────────────────────────────────────────────────
    # Populated by the frontier_computation node when the request asks for
    # a Pareto frontier between two measures (see schemas.requests.FrontierRequest).
    frontier_report: dict[str, Any] | None

    # ── Progress tracking ─────────────────────────────────────────────────────
    # Ordered list of node names that have completed successfully.
    completed_nodes: list[str]
    # Wall-clock timing per node: {node_name: elapsed_ms}
    node_timings_ms: dict[str, float]

    # ── Error handling ────────────────────────────────────────────────────────
    # Human-readable error message set by the failing node.
    error: str | None
    # Name of the node that raised the error.
    failed_node: str | None
    # Structured error details for API responses.
    error_details: dict[str, Any] | None
