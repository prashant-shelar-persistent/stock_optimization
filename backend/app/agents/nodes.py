"""LangGraph agent node implementations.

Each function takes an AgentState and returns an updated AgentState.
Nodes are synchronous (LangGraph requirement); async operations are
handled by the graph runner in graph.py.

Nodes:
    data_fetch_node              — Fetch price data via yfinance
    constraint_validation_node   — Validate and normalise constraints
    classical_optimization_node  — Run Markowitz MVO via CVXPY
    quantum_dispatch_node        — Run QAOA (Qiskit) + VQE (PennyLane)
    comparison_node              — Compare classical vs quantum results
    llm_explanation_node         — Generate LLM explanation via GPT-4o

Error handling:
    Each node wraps its logic in a try/except block. On failure it sets
    ``state["error"]`` and ``state["failed_node"]`` and returns the
    (partially updated) state. The graph's conditional routing then
    decides whether to skip downstream nodes or attempt partial results.

    Nodes that are not critical (quantum_dispatch, llm_explanation) log
    the error and continue with a degraded result rather than failing the
    entire run.
"""

from __future__ import annotations

import time
from typing import Any

from app.agents.state import AgentState
from app.core.logging import get_logger


logger = get_logger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _record_timing(state: AgentState, node_name: str, elapsed_ms: float) -> None:
    """Record node execution time in the state (mutates in place)."""
    timings: dict[str, float] = dict(state.get("node_timings_ms") or {})
    timings[node_name] = elapsed_ms
    state["node_timings_ms"] = timings  # type: ignore[typeddict-unknown-key]


def _record_completed(state: AgentState, node_name: str) -> None:
    """Append node_name to the completed_nodes list in state."""
    completed: list[str] = list(state.get("completed_nodes") or [])
    if node_name not in completed:
        completed.append(node_name)
    state["completed_nodes"] = completed  # type: ignore[typeddict-unknown-key]


# ── Data fetch node ───────────────────────────────────────────────────────────


def data_fetch_node(state: AgentState) -> AgentState:
    """Fetch historical price data and compute returns/covariance.

    Uses yfinance with Redis caching. Populates:
        - price_data
        - returns_data
        - expected_returns
        - covariance_matrix
        - sector_map
        - tickers (updated to only include tickers with valid data)

    On failure, sets ``state["error"]`` and ``state["failed_node"]``
    and returns the state. The graph will route to END on data fetch
    failure since no downstream node can proceed without market data.
    """
    from app.data.fetcher import fetch_market_data  # noqa: PLC0415

    node_name = "data_fetch"
    tickers = state["tickers"]
    request_params = state.get("request_params", {})
    lookback_days = request_params.get("lookback_days", 365)

    logger.info(
        "data_fetch_started",
        run_id=state.get("run_id"),
        tickers=tickers,
        lookback_days=lookback_days,
    )

    start_ms = time.perf_counter() * 1000

    try:
        market_data = fetch_market_data(tickers=tickers, lookback_days=lookback_days)
    except Exception as exc:
        elapsed_ms = time.perf_counter() * 1000 - start_ms
        logger.error(
            "data_fetch_failed",
            run_id=state.get("run_id"),
            error=str(exc),
            error_type=type(exc).__name__,
            elapsed_ms=round(elapsed_ms, 1),
            exc_info=True,
        )
        updated = dict(state)
        updated["error"] = str(exc)
        updated["failed_node"] = node_name
        updated["error_details"] = {
            "node": node_name,
            "error_type": type(exc).__name__,
            "tickers": tickers,
        }
        _record_timing(updated, node_name, elapsed_ms)  # type: ignore[arg-type]
        return updated  # type: ignore[return-value]

    elapsed_ms = time.perf_counter() * 1000 - start_ms

    logger.info(
        "data_fetch_completed",
        run_id=state.get("run_id"),
        valid_tickers=market_data.valid_tickers,
        num_days=len(market_data.price_data),
        elapsed_ms=round(elapsed_ms, 1),
    )

    updated = dict(state)
    updated["price_data"] = market_data.price_data
    updated["returns_data"] = market_data.returns_data
    updated["expected_returns"] = market_data.expected_returns
    updated["covariance_matrix"] = market_data.covariance_matrix
    updated["sector_map"] = market_data.sector_map
    # Update tickers to only include those with valid data
    updated["tickers"] = market_data.valid_tickers
    _record_timing(updated, node_name, elapsed_ms)  # type: ignore[arg-type]
    _record_completed(updated, node_name)  # type: ignore[arg-type]
    return updated  # type: ignore[return-value]


# ── Constraint validation node ────────────────────────────────────────────────


def constraint_validation_node(state: AgentState) -> AgentState:
    """Validate and normalise optimization constraints.

    Checks for logical consistency (e.g. min_return not exceeding max
    achievable return) and emits warnings for near-infeasible constraints.

    Also injects the ``sector_map`` from the data fetch node into the
    validated constraints dict so the classical optimizer can apply
    sector-level weight limits.

    On hard constraint violations (logically impossible constraints),
    sets ``state["error"]`` and returns. On soft warnings, continues
    with the warnings recorded in ``state["constraint_warnings"]``.
    """
    from app.classical.constraints import validate_constraints  # noqa: PLC0415

    node_name = "constraint_validation"
    request_params = state.get("request_params", {})
    tickers = state["tickers"]
    expected_returns = state["expected_returns"]
    covariance_matrix = state["covariance_matrix"]

    logger.info(
        "constraint_validation_started",
        run_id=state.get("run_id"),
        num_tickers=len(tickers),
    )

    start_ms = time.perf_counter() * 1000

    try:
        validated, warnings = validate_constraints(
            request_params=request_params,
            tickers=tickers,
            expected_returns=expected_returns,
            covariance_matrix=covariance_matrix,
        )
    except Exception as exc:
        elapsed_ms = time.perf_counter() * 1000 - start_ms
        logger.error(
            "constraint_validation_failed",
            run_id=state.get("run_id"),
            error=str(exc),
            error_type=type(exc).__name__,
            elapsed_ms=round(elapsed_ms, 1),
            exc_info=True,
        )
        updated = dict(state)
        updated["error"] = str(exc)
        updated["failed_node"] = node_name
        updated["error_details"] = {
            "node": node_name,
            "error_type": type(exc).__name__,
        }
        _record_timing(updated, node_name, elapsed_ms)  # type: ignore[arg-type]
        return updated  # type: ignore[return-value]

    elapsed_ms = time.perf_counter() * 1000 - start_ms

    # Inject sector_map from data fetch into validated constraints so the
    # classical optimizer can apply sector-level weight limits correctly.
    sector_map: dict[str, str] = state.get("sector_map") or {}
    validated["sector_map"] = sector_map

    if warnings:
        logger.warning(
            "constraint_warnings_detected",
            run_id=state.get("run_id"),
            warnings=warnings,
        )

    logger.info(
        "constraint_validation_completed",
        run_id=state.get("run_id"),
        num_warnings=len(warnings),
        elapsed_ms=round(elapsed_ms, 1),
    )

    updated = dict(state)
    updated["validated_constraints"] = validated
    updated["constraint_warnings"] = warnings
    _record_timing(updated, node_name, elapsed_ms)  # type: ignore[arg-type]
    _record_completed(updated, node_name)  # type: ignore[arg-type]
    return updated  # type: ignore[return-value]


# ── Classical optimization node ───────────────────────────────────────────────


def classical_optimization_node(state: AgentState) -> AgentState:
    """Run Markowitz Mean-Variance Optimization via CVXPY.

    Populates classical_result with weights, metrics, and solver status.

    On failure, sets ``state["error"]`` and ``state["failed_node"]``.
    Classical optimization failure is considered fatal — the comparison
    and explanation nodes cannot produce meaningful output without it.
    """
    from app.classical.optimizer import run_markowitz_mvo  # noqa: PLC0415

    node_name = "classical_optimization"
    tickers = state["tickers"]
    expected_returns = state["expected_returns"]
    covariance_matrix = state["covariance_matrix"]
    constraints = state.get("validated_constraints", {})
    budget = state["budget"]

    logger.info(
        "classical_optimization_started",
        run_id=state.get("run_id"),
        num_tickers=len(tickers),
        budget=budget,
    )

    start_ms = time.perf_counter() * 1000

    try:
        result = run_markowitz_mvo(
            tickers=tickers,
            expected_returns=expected_returns,
            covariance_matrix=covariance_matrix,
            budget=budget,
            constraints=constraints,
        )
    except Exception as exc:
        elapsed_ms = time.perf_counter() * 1000 - start_ms
        logger.error(
            "classical_optimization_failed",
            run_id=state.get("run_id"),
            error=str(exc),
            error_type=type(exc).__name__,
            elapsed_ms=round(elapsed_ms, 1),
            exc_info=True,
        )
        updated = dict(state)
        updated["error"] = str(exc)
        updated["failed_node"] = node_name
        updated["error_details"] = {
            "node": node_name,
            "error_type": type(exc).__name__,
            "num_tickers": len(tickers),
        }
        _record_timing(updated, node_name, elapsed_ms)  # type: ignore[arg-type]
        return updated  # type: ignore[return-value]

    elapsed_ms = time.perf_counter() * 1000 - start_ms

    logger.info(
        "classical_optimization_completed",
        run_id=state.get("run_id"),
        sharpe=round(result.metrics.sharpe_ratio, 4),
        expected_return=round(result.metrics.expected_return, 4),
        volatility=round(result.metrics.volatility, 4),
        num_assets=result.metrics.num_assets,
        solver_status=result.solver_status,
        elapsed_ms=round(elapsed_ms, 1),
    )

    updated = dict(state)
    updated["classical_result"] = result.model_dump()
    _record_timing(updated, node_name, elapsed_ms)  # type: ignore[arg-type]
    _record_completed(updated, node_name)  # type: ignore[arg-type]
    return updated  # type: ignore[return-value]


# ── Quantum dispatch node ─────────────────────────────────────────────────────


def quantum_dispatch_node(state: AgentState) -> AgentState:
    """Run QAOA (Qiskit) and VQE-style (PennyLane) quantum optimization.

    Converts the asset selection problem to QUBO and runs both quantum
    solvers. Populates quantum_result with QAOA and VQE results.

    This node is non-fatal: if quantum optimization fails entirely, the
    run continues with only the classical result. The error is logged
    but ``state["error"]`` is NOT set (to avoid blocking comparison/
    explanation nodes).

    If the asset count exceeds MAX_QUANTUM_ASSETS, the node is skipped
    by the graph's conditional routing before this function is called.
    """
    from app.quantum.dispatcher import run_quantum_optimization  # noqa: PLC0415

    node_name = "quantum_dispatch"
    tickers = state["tickers"]
    expected_returns = state["expected_returns"]
    covariance_matrix = state["covariance_matrix"]
    constraints = state.get("validated_constraints", {})
    budget = state["budget"]

    logger.info(
        "quantum_dispatch_started",
        run_id=state.get("run_id"),
        num_tickers=len(tickers),
    )

    start_ms = time.perf_counter() * 1000

    try:
        result = run_quantum_optimization(
            tickers=tickers,
            expected_returns=expected_returns,
            covariance_matrix=covariance_matrix,
            budget=budget,
            constraints=constraints,
        )
    except Exception as exc:
        elapsed_ms = time.perf_counter() * 1000 - start_ms
        # Quantum failure is non-fatal — log and continue without quantum result
        logger.error(
            "quantum_dispatch_failed",
            run_id=state.get("run_id"),
            error=str(exc),
            error_type=type(exc).__name__,
            elapsed_ms=round(elapsed_ms, 1),
            exc_info=True,
        )
        updated = dict(state)
        # Do NOT set state["error"] — quantum failure is non-fatal
        # Record a warning in constraint_warnings so the explanation node
        # can mention that quantum optimization was unavailable.
        existing_warnings: list[str] = list(state.get("constraint_warnings") or [])
        existing_warnings.append(
            f"Quantum optimization failed: {type(exc).__name__}: {exc}"
        )
        updated["constraint_warnings"] = existing_warnings
        _record_timing(updated, node_name, elapsed_ms)  # type: ignore[arg-type]
        _record_completed(updated, node_name)  # type: ignore[arg-type]
        return updated  # type: ignore[return-value]

    elapsed_ms = time.perf_counter() * 1000 - start_ms

    logger.info(
        "quantum_dispatch_completed",
        run_id=state.get("run_id"),
        qaoa_ok=result.qaoa is not None,
        vqe_ok=result.vqe is not None,
        elapsed_ms=round(elapsed_ms, 1),
    )

    updated = dict(state)
    updated["quantum_result"] = result.model_dump()
    _record_timing(updated, node_name, elapsed_ms)  # type: ignore[arg-type]
    _record_completed(updated, node_name)  # type: ignore[arg-type]
    return updated  # type: ignore[return-value]


# ── Comparison node ───────────────────────────────────────────────────────────


def comparison_node(state: AgentState) -> AgentState:
    """Compare classical and quantum optimization results.

    Computes Sharpe ratio improvements, return/volatility differences,
    and generates a recommendation string.

    This node is non-fatal: if comparison fails, the run continues with
    only the classical and quantum results. The explanation node will
    generate a partial explanation without the comparison summary.
    """
    from app.agents.comparison import compute_comparison  # noqa: PLC0415

    node_name = "comparison"
    classical_result = state.get("classical_result")
    quantum_result = state.get("quantum_result")

    logger.info(
        "comparison_started",
        run_id=state.get("run_id"),
        has_classical=classical_result is not None,
        has_quantum=quantum_result is not None,
    )

    start_ms = time.perf_counter() * 1000

    try:
        comparison = compute_comparison(
            classical_result=classical_result,
            quantum_result=quantum_result,
        )
    except Exception as exc:
        elapsed_ms = time.perf_counter() * 1000 - start_ms
        # Comparison failure is non-fatal
        logger.error(
            "comparison_failed",
            run_id=state.get("run_id"),
            error=str(exc),
            error_type=type(exc).__name__,
            elapsed_ms=round(elapsed_ms, 1),
            exc_info=True,
        )
        updated = dict(state)
        _record_timing(updated, node_name, elapsed_ms)  # type: ignore[arg-type]
        _record_completed(updated, node_name)  # type: ignore[arg-type]
        return updated  # type: ignore[return-value]

    elapsed_ms = time.perf_counter() * 1000 - start_ms

    logger.info(
        "comparison_completed",
        run_id=state.get("run_id"),
        recommendation_preview=comparison.recommendation[:80],
        elapsed_ms=round(elapsed_ms, 1),
    )

    updated = dict(state)
    updated["comparison_summary"] = comparison.model_dump()
    _record_timing(updated, node_name, elapsed_ms)  # type: ignore[arg-type]
    _record_completed(updated, node_name)  # type: ignore[arg-type]
    return updated  # type: ignore[return-value]


# ── LLM explanation node ──────────────────────────────────────────────────────


def llm_explanation_node(state: AgentState) -> AgentState:
    """Generate a natural-language explanation of the optimization results.

    Uses GPT-4o if OPENAI_API_KEY is configured, otherwise falls back to
    a deterministic template-based explanation.

    This node is non-fatal: if explanation generation fails, the run
    completes with an empty explanation rather than failing entirely.
    """
    from app.agents.explainer import generate_explanation  # noqa: PLC0415

    node_name = "llm_explanation"

    logger.info(
        "llm_explanation_started",
        run_id=state.get("run_id"),
    )

    start_ms = time.perf_counter() * 1000

    try:
        explanation = generate_explanation(
            tickers=state["tickers"],
            budget=state["budget"],
            classical_result=state.get("classical_result"),
            quantum_result=state.get("quantum_result"),
            comparison_summary=state.get("comparison_summary"),
            constraint_warnings=state.get("constraint_warnings", []),
        )
    except Exception as exc:
        elapsed_ms = time.perf_counter() * 1000 - start_ms
        # Explanation failure is non-fatal — provide a minimal fallback
        logger.error(
            "llm_explanation_failed",
            run_id=state.get("run_id"),
            error=str(exc),
            error_type=type(exc).__name__,
            elapsed_ms=round(elapsed_ms, 1),
            exc_info=True,
        )
        explanation = (
            "Portfolio optimization completed. "
            "An explanation could not be generated at this time."
        )
        updated = dict(state)
        updated["llm_explanation"] = explanation
        _record_timing(updated, node_name, elapsed_ms)  # type: ignore[arg-type]
        _record_completed(updated, node_name)  # type: ignore[arg-type]
        return updated  # type: ignore[return-value]

    elapsed_ms = time.perf_counter() * 1000 - start_ms

    logger.info(
        "llm_explanation_completed",
        run_id=state.get("run_id"),
        explanation_length=len(explanation),
        elapsed_ms=round(elapsed_ms, 1),
    )

    updated = dict(state)
    updated["llm_explanation"] = explanation
    _record_timing(updated, node_name, elapsed_ms)  # type: ignore[arg-type]
    _record_completed(updated, node_name)  # type: ignore[arg-type]
    return updated  # type: ignore[return-value]


# ── Frontier computation node ──────────────────────────────────────────────────


def frontier_computation_node(state: AgentState) -> AgentState:
    """Compute the Pareto frontier between two user-selected measures.

    This node runs ONLY when the request includes a non-null
    ``frontier`` config with ``enabled=true``. The graph's conditional
    routing decides whether to invoke it.

    The node is non-fatal: if the sweep fails (infeasible anchors,
    solver errors, unsupported measure) it logs the error and continues
    with ``frontier_report=None``.  The main classical result is already
    in place by this point, so a missing frontier never blocks the run.
    """
    from app.classical.frontier import compute_frontier  # noqa: PLC0415

    node_name = "frontier_computation"

    constraints = state.get("validated_constraints") or {}
    frontier_cfg = constraints.get("frontier")
    if not frontier_cfg or not frontier_cfg.get("enabled"):
        # Routing should have skipped us — defensive no-op.
        updated = dict(state)
        updated["frontier_report"] = None
        _record_completed(updated, node_name)  # type: ignore[arg-type]
        return updated  # type: ignore[return-value]

    tickers = state["tickers"]
    expected_returns = state["expected_returns"]
    covariance_matrix = state["covariance_matrix"]
    budget = state["budget"]

    logger.info(
        "frontier_computation_started",
        run_id=state.get("run_id"),
        x_measure=frontier_cfg.get("x_measure"),
        y_measure=frontier_cfg.get("y_measure"),
        num_points=frontier_cfg.get("num_points"),
    )

    start_ms = time.perf_counter() * 1000

    try:
        report = compute_frontier(
            tickers=tickers,
            expected_returns=expected_returns,
            covariance_matrix=covariance_matrix,
            budget=budget,
            constraints=constraints,
            frontier_cfg=frontier_cfg,
        )
    except Exception as exc:
        elapsed_ms = time.perf_counter() * 1000 - start_ms
        # Frontier failure is non-fatal — log, drop the report, continue.
        logger.error(
            "frontier_computation_failed",
            run_id=state.get("run_id"),
            error=str(exc),
            error_type=type(exc).__name__,
            elapsed_ms=round(elapsed_ms, 1),
            exc_info=True,
        )
        existing_warnings: list[str] = list(state.get("constraint_warnings") or [])
        existing_warnings.append(
            f"Efficient-frontier sweep failed: {type(exc).__name__}: {exc}"
        )
        updated = dict(state)
        updated["frontier_report"] = None
        updated["constraint_warnings"] = existing_warnings
        _record_timing(updated, node_name, elapsed_ms)  # type: ignore[arg-type]
        _record_completed(updated, node_name)  # type: ignore[arg-type]
        return updated  # type: ignore[return-value]

    elapsed_ms = time.perf_counter() * 1000 - start_ms

    logger.info(
        "frontier_computation_completed",
        run_id=state.get("run_id"),
        num_points=len(report.points),
        num_dominant=report.num_dominant,
        knee_index=report.knee_point_index,
        elapsed_ms=round(elapsed_ms, 1),
    )

    updated = dict(state)
    updated["frontier_report"] = report.model_dump()
    _record_timing(updated, node_name, elapsed_ms)  # type: ignore[arg-type]
    _record_completed(updated, node_name)  # type: ignore[arg-type]
    return updated  # type: ignore[return-value]
