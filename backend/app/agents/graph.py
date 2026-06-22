"""LangGraph optimization pipeline graph.

Defines the stateful agent graph that orchestrates the full portfolio
optimization workflow:

    data_fetch
        ↓
    constraint_validation
        ↓
    classical_optimization
        ↓
    quantum_dispatch (conditional — skipped if run_quantum=False or too many assets)
        ↓
    comparison
        ↓
    llm_explanation
        ↓
    END

Error routing:
    - data_fetch failure → END immediately (no market data = no optimization)
    - constraint_validation failure → END immediately (infeasible constraints)
    - classical_optimization failure → END immediately (no baseline result)
    - quantum_dispatch failure → comparison (non-fatal, continues without quantum)
    - comparison failure → llm_explanation (non-fatal, continues without comparison)
    - llm_explanation failure → END (non-fatal, explanation is best-effort)

Each node is a deterministic Python function except llm_explanation which
calls GPT-4o (with a template-based fallback if OPENAI_API_KEY is not set).

Usage::

    from app.agents.graph import run_agent_graph

    result = await run_agent_graph(
        run_id="...",
        request=OptimizationRequest(...),
        progress_callback=lambda node, status, msg: ...,
    )
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.state import AgentState
from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.requests import OptimizationRequest
from app.schemas.responses import OptimizationRunDetail


logger = get_logger(__name__)

ProgressCallback = Callable[[str, str, str], None]


def _make_graph(
    progress_callback: ProgressCallback | None = None,
) -> "Any":
    """Build and compile the LangGraph optimization graph.

    Args:
        progress_callback: Optional callable(node_name, status, message)
                           called at each node transition.

    Returns:
        A compiled LangGraph StateGraph.
    """
    from app.agents.nodes import (  # noqa: PLC0415
        classical_optimization_node,
        comparison_node,
        constraint_validation_node,
        data_fetch_node,
        frontier_computation_node,
        llm_explanation_node,
        quantum_dispatch_node,
    )

    def wrap_node(
        node_fn: Callable[[AgentState], AgentState],
        node_name: str,
    ) -> Callable[[AgentState], AgentState]:
        """Wrap a node function with progress event publishing.

        The wrapper:
        1. Publishes a "started" event before calling the node.
        2. Calls the node function.
        3. Publishes "completed" or "failed" based on whether the node
           set ``state["error"]`` (for fatal errors) or raised an exception.
        """

        def wrapped(state: AgentState) -> "AgentState":
            # Skip execution if a fatal error was already set by a prior node
            if state.get("error") and state.get("failed_node"):
                # Only skip if this is not the node that set the error
                if state.get("failed_node") != node_name:
                    logger.debug(
                        "node_skipped_due_to_prior_error",
                        node=node_name,
                        failed_node=state.get("failed_node"),
                    )
                    return state

            if progress_callback:
                progress_callback(
                    node_name,
                    "started",
                    _node_start_message(node_name),
                )

            try:
                result = node_fn(state)

                # Check if the node itself set an error (non-exception failure)
                if result.get("error") and result.get("failed_node") == node_name:
                    if progress_callback:
                        progress_callback(
                            node_name,
                            "failed",
                            result.get("error", f"{node_name} failed"),
                        )
                else:
                    if progress_callback:
                        progress_callback(
                            node_name,
                            "completed",
                            _node_complete_message(node_name, result),
                        )

                return result

            except Exception as exc:
                # Unexpected exception not caught by the node itself
                logger.error(
                    "node_unexpected_exception",
                    node=node_name,
                    error=str(exc),
                    error_type=type(exc).__name__,
                    exc_info=True,
                )
                if progress_callback:
                    progress_callback(node_name, "failed", str(exc))

                # Set error state and return
                updated = dict(state)
                updated["error"] = str(exc)
                updated["failed_node"] = node_name
                updated["error_details"] = {
                    "node": node_name,
                    "error_type": type(exc).__name__,
                }
                return updated  # type: ignore[return-value]

        return wrapped

    graph = StateGraph(AgentState)

    # ── Register nodes ────────────────────────────────────────────────────────
    graph.add_node("data_fetch", wrap_node(data_fetch_node, "data_fetch"))
    graph.add_node(
        "constraint_validation",
        wrap_node(constraint_validation_node, "constraint_validation"),
    )
    graph.add_node(
        "classical_optimization",
        wrap_node(classical_optimization_node, "classical_optimization"),
    )
    graph.add_node(
        "quantum_dispatch",
        wrap_node(quantum_dispatch_node, "quantum_dispatch"),
    )
    graph.add_node("comparison", wrap_node(comparison_node, "comparison"))
    graph.add_node(
        "frontier_computation",
        wrap_node(frontier_computation_node, "frontier_computation"),
    )
    graph.add_node(
        "llm_explanation",
        wrap_node(llm_explanation_node, "llm_explanation"),
    )

    # ── Define edges ──────────────────────────────────────────────────────────
    graph.set_entry_point("data_fetch")

    # data_fetch → constraint_validation (or END on fatal error)
    graph.add_conditional_edges(
        "data_fetch",
        _route_after_fatal_node,
        {
            "continue": "constraint_validation",
            "end": END,
        },
    )

    # constraint_validation → classical_optimization (or END on fatal error)
    graph.add_conditional_edges(
        "constraint_validation",
        _route_after_fatal_node,
        {
            "continue": "classical_optimization",
            "end": END,
        },
    )

    # classical_optimization → quantum_dispatch or comparison (conditional)
    # Also routes to END if classical optimization failed fatally.
    graph.add_conditional_edges(
        "classical_optimization",
        _route_after_classical,
        {
            "quantum": "quantum_dispatch",
            "skip_quantum": "comparison",
            "end": END,
        },
    )

    # quantum_dispatch → comparison (always — quantum failure is non-fatal)
    graph.add_edge("quantum_dispatch", "comparison")

    # comparison → frontier_computation OR llm_explanation (conditional on
    # whether the request enabled the efficient-frontier sweep).
    graph.add_conditional_edges(
        "comparison",
        _route_after_comparison,
        {
            "frontier": "frontier_computation",
            "skip_frontier": "llm_explanation",
        },
    )

    # frontier_computation → llm_explanation (always — frontier failure is non-fatal)
    graph.add_edge("frontier_computation", "llm_explanation")

    # llm_explanation → END (always)
    graph.add_edge("llm_explanation", END)

    return graph.compile()


def _route_after_fatal_node(state: AgentState) -> str:
    """Route to END if the previous node set a fatal error, else continue."""
    if state.get("error") and state.get("failed_node"):
        return "end"
    return "continue"


def _route_after_classical(state: AgentState) -> str:
    """Route after classical optimization.

    Returns:
        'end'          — if classical optimization failed fatally
        'quantum'      — if quantum should run
        'skip_quantum' — if quantum should be skipped
    """
    # Fatal error from classical optimization
    if state.get("error") and state.get("failed_node") == "classical_optimization":
        return "end"

    # Also end if a prior node set a fatal error
    if state.get("error") and state.get("failed_node") in (
        "data_fetch",
        "constraint_validation",
    ):
        return "end"

    return _should_run_quantum(state)


def _route_after_comparison(state: AgentState) -> str:
    """Route after the comparison node.

    Returns 'frontier' when the request enabled the efficient-frontier
    sweep (and the classical optimisation succeeded), otherwise
    'skip_frontier' to go straight to the explanation node.

    Frontier computation is a *bonus* — it must never block the run.
    If the classical optimisation itself failed we still want the
    explanation node to fire so the user gets a useful error report.
    """
    constraints = state.get("validated_constraints") or {}
    frontier_cfg = constraints.get("frontier")
    if not frontier_cfg or not frontier_cfg.get("enabled"):
        return "skip_frontier"

    # Require a valid classical result — without it the same data pipeline
    # that would feed the sweep is missing.
    if not state.get("classical_result"):
        logger.info(
            "frontier_skipped_no_classical_result",
            run_id=state.get("run_id"),
        )
        return "skip_frontier"

    return "frontier"


def _should_run_quantum(state: AgentState) -> str:
    """Decide whether to run quantum optimization.

    Returns 'quantum' if quantum should run, 'skip_quantum' otherwise.
    """
    request_params = state.get("request_params", {})
    run_quantum = request_params.get("run_quantum", True)

    if not run_quantum:
        logger.info(
            "quantum_skipped_disabled",
            run_id=state.get("run_id"),
        )
        return "skip_quantum"

    settings = get_settings()
    tickers = state.get("tickers", [])
    if len(tickers) > settings.MAX_QUANTUM_ASSETS:
        logger.warning(
            "quantum_skipped_too_many_assets",
            run_id=state.get("run_id"),
            num_assets=len(tickers),
            max_assets=settings.MAX_QUANTUM_ASSETS,
        )
        return "skip_quantum"

    return "quantum"


def _node_start_message(node_name: str) -> str:
    """Return a human-readable start message for a node."""
    messages: dict[str, str] = {
        "data_fetch": "Fetching market data from yfinance…",
        "constraint_validation": "Validating optimization constraints…",
        "classical_optimization": "Running Markowitz Mean-Variance Optimization…",
        "quantum_dispatch": "Running quantum optimization (QAOA + VQE)…",
        "comparison": "Comparing classical and quantum results…",
        "frontier_computation": "Tracing the efficient frontier…",
        "llm_explanation": "Generating portfolio explanation…",
    }
    return messages.get(node_name, f"Starting {node_name}…")


def _node_complete_message(node_name: str, state: AgentState) -> str:
    """Return a human-readable completion message for a node."""
    if node_name == "data_fetch":
        tickers = state.get("tickers", [])
        return f"Market data fetched for {len(tickers)} assets"

    if node_name == "constraint_validation":
        warnings = state.get("constraint_warnings", [])
        if warnings:
            return f"Constraints validated with {len(warnings)} warning(s)"
        return "Constraints validated successfully"

    if node_name == "classical_optimization":
        classical = state.get("classical_result", {})
        metrics = classical.get("metrics", {})
        sharpe = metrics.get("sharpe_ratio", 0.0)
        return f"Classical optimization complete (Sharpe: {sharpe:.3f})"

    if node_name == "quantum_dispatch":
        quantum = state.get("quantum_result", {})
        qaoa_ok = quantum.get("qaoa") is not None
        vqe_ok = quantum.get("vqe") is not None
        parts = []
        if qaoa_ok:
            parts.append("QAOA")
        if vqe_ok:
            parts.append("VQE")
        if parts:
            return f"Quantum optimization complete ({', '.join(parts)})"
        return "Quantum optimization complete (no results)"

    if node_name == "comparison":
        comparison = state.get("comparison_summary", {})
        rec = comparison.get("recommendation", "")
        return f"Comparison complete: {rec[:60]}…" if len(rec) > 60 else f"Comparison complete: {rec}"

    if node_name == "frontier_computation":
        fr = state.get("frontier_report") or {}
        pts = fr.get("points") or []
        if pts:
            return (
                f"Frontier sweep complete ({len(pts)} points, "
                f"{fr.get('num_dominant', 0)} Pareto-dominant)"
            )
        return "Frontier sweep produced no feasible points"

    if node_name == "llm_explanation":
        explanation = state.get("llm_explanation", "")
        return f"Explanation generated ({len(explanation)} chars)"

    return f"Completed {node_name}"


async def run_agent_graph(
    run_id: str,
    request: OptimizationRequest,
    progress_callback: ProgressCallback | None = None,
) -> "OptimizationRunDetail":
    """Execute the full optimization agent graph.

    Runs the LangGraph pipeline in a thread pool executor to avoid
    blocking the asyncio event loop (LangGraph nodes are synchronous).

    Args:
        run_id: UUID of the optimization run.
        request: Validated optimization request.
        progress_callback: Optional callable for progress events.
            Signature: (node_name: str, status: str, message: str) -> None
            Status values: "started" | "completed" | "failed"

    Returns:
        Completed OptimizationRunDetail with all results populated.

    Raises:
        AgentExecutionError: If the graph encounters an unrecoverable error
            in a fatal node (data_fetch, constraint_validation, or
            classical_optimization).
    """
    initial_state: AgentState = {
        "run_id": run_id,
        "tickers": request.tickers,
        "budget": request.budget,
        "request_params": request.model_dump(),
        "completed_nodes": [],
        "node_timings_ms": {},
        "error": None,
        "failed_node": None,
        "error_details": None,
    }

    compiled_graph = _make_graph(progress_callback=progress_callback)

    logger.info(
        "agent_graph_started",
        run_id=run_id,
        tickers=request.tickers,
        budget=request.budget,
        run_quantum=request.run_quantum,
    )

    # Run synchronous LangGraph in thread pool to avoid blocking event loop
    loop = asyncio.get_running_loop()
    final_state: AgentState = await loop.run_in_executor(
        None,
        lambda: compiled_graph.invoke(initial_state),
    )

    logger.info(
        "agent_graph_completed",
        run_id=run_id,
        completed_nodes=final_state.get("completed_nodes", []),
        has_error=bool(final_state.get("error")),
        failed_node=final_state.get("failed_node"),
        total_timings_ms=final_state.get("node_timings_ms", {}),
    )

    # Build the response from the final state
    return _state_to_run_detail(run_id, request, final_state)


def _state_to_run_detail(
    run_id: str,
    request: OptimizationRequest,
    state: AgentState,
) -> "OptimizationRunDetail":
    """Convert the final agent state to an OptimizationRunDetail response.

    Args:
        run_id: UUID of the optimization run.
        request: Original optimization request.
        state: Final agent state after graph execution.

    Returns:
        OptimizationRunDetail with all available results populated.
    """
    from app.schemas.responses import (  # noqa: PLC0415
        ClassicalResult,
        ComparisonSummary,
        FrontierReport,
        OptimizationRunDetail,
        QuantumResult,
    )

    classical_result = None
    if state.get("classical_result"):
        try:
            classical_result = ClassicalResult.model_validate(
                state["classical_result"]
            )
        except Exception as exc:
            logger.warning(
                "classical_result_deserialisation_failed",
                run_id=run_id,
                error=str(exc),
            )

    quantum_result = None
    if state.get("quantum_result"):
        try:
            quantum_result = QuantumResult.model_validate(state["quantum_result"])
        except Exception as exc:
            logger.warning(
                "quantum_result_deserialisation_failed",
                run_id=run_id,
                error=str(exc),
            )

    comparison = None
    if state.get("comparison_summary"):
        try:
            comparison = ComparisonSummary.model_validate(state["comparison_summary"])
        except Exception as exc:
            logger.warning(
                "comparison_deserialisation_failed",
                run_id=run_id,
                error=str(exc),
            )

    frontier_report = None
    if state.get("frontier_report"):
        try:
            frontier_report = FrontierReport.model_validate(state["frontier_report"])
        except Exception as exc:
            logger.warning(
                "frontier_report_deserialisation_failed",
                run_id=run_id,
                error=str(exc),
            )

    # Determine Sharpe ratios for summary fields
    classical_sharpe: float | None = None
    if classical_result:
        classical_sharpe = classical_result.metrics.sharpe_ratio

    quantum_sharpe: float | None = None
    if quantum_result:
        if quantum_result.qaoa:
            quantum_sharpe = quantum_result.qaoa.metrics.sharpe_ratio
        elif quantum_result.vqe:
            quantum_sharpe = quantum_result.vqe.metrics.sharpe_ratio

    # Determine run status
    has_error = bool(state.get("error"))
    status = "failed" if has_error else "completed"

    # Build error message — include error details if available
    error_message: str | None = state.get("error")
    if error_message and state.get("failed_node"):
        error_message = (
            f"[{state['failed_node']}] {error_message}"
        )

    now = datetime.now(UTC)

    return OptimizationRunDetail(
        run_id=run_id,
        status=status,  # type: ignore[arg-type]
        tickers=request.tickers,
        budget=request.budget,
        created_at=now,
        completed_at=now,
        classical_sharpe=classical_sharpe,
        quantum_sharpe=quantum_sharpe,
        classical_result=classical_result,
        quantum_result=quantum_result,
        comparison=comparison,
        llm_explanation=state.get("llm_explanation"),
        frontier_report=frontier_report,
        error_message=error_message,
    )
