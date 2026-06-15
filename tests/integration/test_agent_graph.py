"""Integration tests for the LangGraph agent graph.

Tests cover:
1.  _route_after_fatal_node returns 'end' when error + failed_node are set
2.  _route_after_fatal_node returns 'continue' when no error
3.  _route_after_fatal_node returns 'continue' when error is None
4.  _route_after_fatal_node returns 'continue' when only error is set (no failed_node)
5.  _route_after_classical returns 'end' on classical_optimization failure
6.  _route_after_classical returns 'end' on data_fetch failure (prior fatal)
7.  _route_after_classical returns 'end' on constraint_validation failure
8.  _route_after_classical returns 'quantum' when run_quantum=True and few assets
9.  _route_after_classical returns 'skip_quantum' when run_quantum=False
10. _should_run_quantum returns 'quantum' for small portfolio with quantum enabled
11. _should_run_quantum returns 'skip_quantum' when run_quantum=False
12. _should_run_quantum returns 'skip_quantum' when too many assets
13. _should_run_quantum defaults to 'quantum' when run_quantum param is missing
14. AgentState TypedDict accepts all required input fields
15. AgentState error fields default to None via .get()
16. AgentState error fields can be set
17. run_agent_graph returns OptimizationRunDetail on success (all nodes mocked)
18. run_agent_graph returns status='failed' when data_fetch fails
19. run_agent_graph returns status='completed' when quantum fails (non-fatal)
20. Progress callback is invoked for each node
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.agents.graph import (
    _route_after_classical,
    _route_after_fatal_node,
    _should_run_quantum,
)
from app.agents.state import AgentState
from app.schemas.requests import OptimizationRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(**kwargs: Any) -> AgentState:
    """Build a minimal AgentState for testing routing functions."""
    base: AgentState = {
        "run_id": str(uuid.uuid4()),
        "tickers": ["AAPL", "MSFT", "GOOGL"],
        "budget": 100_000.0,
        "request_params": {"run_quantum": True},
        "completed_nodes": [],
        "node_timings_ms": {},
        "error": None,
        "failed_node": None,
        "error_details": None,
    }
    base.update(kwargs)  # type: ignore[typeddict-item]
    return base


def _make_request(
    tickers: list[str] | None = None,
    budget: float = 100_000.0,
    run_quantum: bool = False,
) -> OptimizationRequest:
    """Build a minimal OptimizationRequest."""
    return OptimizationRequest(
        tickers=tickers or ["AAPL", "MSFT", "GOOGL"],
        budget=budget,
        run_quantum=run_quantum,
    )


def _make_minimal_classical_result() -> dict[str, Any]:
    """Return a minimal valid ClassicalResult dict."""
    return {
        "weights": [
            {
                "ticker": "AAPL",
                "weight": 0.6,
                "allocation": 60_000.0,
                "sector": "Technology",
            },
            {
                "ticker": "MSFT",
                "weight": 0.4,
                "allocation": 40_000.0,
                "sector": "Technology",
            },
        ],
        "metrics": {
            "expected_return": 0.11,
            "volatility": 0.17,
            "sharpe_ratio": 1.30,
            "max_drawdown": -0.12,
            "num_assets": 2,
        },
        "solver_status": "optimal",
        "solve_time_ms": 35.0,
    }


def _make_minimal_comparison() -> dict[str, Any]:
    """Return a minimal valid ComparisonSummary dict."""
    return {
        "sharpe_improvement_qaoa": None,
        "sharpe_improvement_vqe": None,
        "return_diff_qaoa": None,
        "return_diff_vqe": None,
        "volatility_diff_qaoa": None,
        "volatility_diff_vqe": None,
        "recommendation": "Classical portfolio recommended.",
    }


# ---------------------------------------------------------------------------
# _route_after_fatal_node tests
# ---------------------------------------------------------------------------


def test_route_after_fatal_node_returns_end_when_error_set() -> None:
    """Returns 'end' when both error and failed_node are set."""
    state = _make_state(error="Data fetch failed", failed_node="data_fetch")
    result = _route_after_fatal_node(state)
    assert result == "end"


def test_route_after_fatal_node_returns_continue_when_no_error() -> None:
    """Returns 'continue' when state has no error."""
    state = _make_state()
    result = _route_after_fatal_node(state)
    assert result == "continue"


def test_route_after_fatal_node_returns_continue_when_error_is_none() -> None:
    """Returns 'continue' when error is explicitly None."""
    state = _make_state(error=None, failed_node=None)
    result = _route_after_fatal_node(state)
    assert result == "continue"


def test_route_after_fatal_node_returns_continue_when_only_error_set() -> None:
    """Returns 'continue' when error is set but failed_node is not (edge case)."""
    state = _make_state(error="Something failed")
    # failed_node is not set — should not route to end
    result = _route_after_fatal_node(state)
    assert result == "continue"


# ---------------------------------------------------------------------------
# _route_after_classical tests
# ---------------------------------------------------------------------------


def test_route_after_classical_returns_end_on_classical_failure() -> None:
    """Returns 'end' when classical_optimization node failed."""
    state = _make_state(
        error="CVXPY solver failed",
        failed_node="classical_optimization",
    )
    result = _route_after_classical(state)
    assert result == "end"


def test_route_after_classical_returns_end_on_data_fetch_failure() -> None:
    """Returns 'end' when data_fetch node failed (prior fatal error)."""
    state = _make_state(
        error="yfinance timeout",
        failed_node="data_fetch",
    )
    result = _route_after_classical(state)
    assert result == "end"


def test_route_after_classical_returns_end_on_constraint_failure() -> None:
    """Returns 'end' when constraint_validation node failed."""
    state = _make_state(
        error="Infeasible constraints",
        failed_node="constraint_validation",
    )
    result = _route_after_classical(state)
    assert result == "end"


def test_route_after_classical_returns_quantum_when_enabled() -> None:
    """Returns 'quantum' when run_quantum=True and few assets."""
    state = _make_state(
        request_params={"run_quantum": True},
        tickers=["AAPL", "MSFT", "GOOGL"],
        error=None,
        failed_node=None,
    )
    result = _route_after_classical(state)
    assert result == "quantum"


def test_route_after_classical_returns_skip_quantum_when_disabled() -> None:
    """Returns 'skip_quantum' when run_quantum=False."""
    state = _make_state(
        request_params={"run_quantum": False},
        tickers=["AAPL", "MSFT", "GOOGL"],
        error=None,
        failed_node=None,
    )
    result = _route_after_classical(state)
    assert result == "skip_quantum"


# ---------------------------------------------------------------------------
# _should_run_quantum tests
# ---------------------------------------------------------------------------


def test_should_run_quantum_returns_quantum_for_small_portfolio() -> None:
    """Returns 'quantum' for small portfolio with quantum enabled."""
    state = _make_state(
        request_params={"run_quantum": True},
        tickers=["AAPL", "MSFT"],
    )
    result = _should_run_quantum(state)
    assert result == "quantum"


def test_should_run_quantum_returns_skip_when_disabled() -> None:
    """Returns 'skip_quantum' when run_quantum=False."""
    state = _make_state(
        request_params={"run_quantum": False},
        tickers=["AAPL", "MSFT"],
    )
    result = _should_run_quantum(state)
    assert result == "skip_quantum"


def test_should_run_quantum_returns_skip_when_too_many_assets() -> None:
    """Returns 'skip_quantum' when tickers exceed MAX_QUANTUM_ASSETS."""
    many_tickers = [f"TICK{i}" for i in range(100)]
    state = _make_state(
        request_params={"run_quantum": True},
        tickers=many_tickers,
    )
    result = _should_run_quantum(state)
    assert result == "skip_quantum"


def test_should_run_quantum_defaults_to_quantum_when_param_missing() -> None:
    """Returns 'quantum' when run_quantum param is missing (defaults to True)."""
    state = _make_state(
        request_params={},  # no run_quantum key
        tickers=["AAPL", "MSFT"],
    )
    result = _should_run_quantum(state)
    # Default is True → should run quantum for small portfolio
    assert result == "quantum"


# ---------------------------------------------------------------------------
# AgentState TypedDict tests
# ---------------------------------------------------------------------------


def test_agent_state_accepts_required_input_fields() -> None:
    """AgentState TypedDict accepts all required input fields."""
    state: AgentState = {
        "run_id": "test-run-id",
        "tickers": ["AAPL", "MSFT"],
        "budget": 50_000.0,
        "request_params": {"run_quantum": False},
    }
    assert state["run_id"] == "test-run-id"
    assert state["tickers"] == ["AAPL", "MSFT"]
    assert state["budget"] == 50_000.0


def test_agent_state_error_fields_default_to_none() -> None:
    """Error fields are optional and default to None via .get()."""
    state: AgentState = {
        "run_id": "test-run-id",
        "tickers": ["AAPL"],
        "budget": 10_000.0,
        "request_params": {},
    }
    assert state.get("error") is None
    assert state.get("failed_node") is None
    assert state.get("error_details") is None


def test_agent_state_can_set_error_fields() -> None:
    """Error fields can be set on the state dict."""
    state: AgentState = {
        "run_id": "test-run-id",
        "tickers": ["AAPL"],
        "budget": 10_000.0,
        "request_params": {},
        "error": "Something went wrong",
        "failed_node": "data_fetch",
        "error_details": {"node": "data_fetch", "error_type": "ValueError"},
    }
    assert state["error"] == "Something went wrong"
    assert state["failed_node"] == "data_fetch"
    assert state["error_details"]["node"] == "data_fetch"


# ---------------------------------------------------------------------------
# run_agent_graph integration tests (with mocked nodes)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_graph_returns_optimization_run_detail() -> None:
    """run_agent_graph returns OptimizationRunDetail on success (all nodes mocked)."""
    from app.agents.graph import run_agent_graph
    from app.schemas.responses import OptimizationRunDetail

    request = _make_request(run_quantum=False)
    run_id = str(uuid.uuid4())

    classical_result = _make_minimal_classical_result()
    comparison = _make_minimal_comparison()

    def mock_data_fetch(state: AgentState) -> AgentState:
        state["price_data"] = pd.DataFrame(
            {"AAPL": [150.0, 152.0, 151.0], "MSFT": [300.0, 302.0, 301.0]}
        )
        state["returns_data"] = pd.DataFrame(
            {"AAPL": [0.01, -0.005], "MSFT": [0.007, -0.003]}
        )
        state["expected_returns"] = np.array([0.12, 0.10])
        state["covariance_matrix"] = np.array([[0.04, 0.01], [0.01, 0.03]])
        state["sector_map"] = {"AAPL": "Technology", "MSFT": "Technology"}
        state["tickers"] = ["AAPL", "MSFT"]
        _append_completed(state, "data_fetch")
        return state

    def mock_constraint_validation(state: AgentState) -> AgentState:
        state["validated_constraints"] = {"max_weight_per_asset": 1.0}
        state["constraint_warnings"] = []
        _append_completed(state, "constraint_validation")
        return state

    def mock_classical_optimization(state: AgentState) -> AgentState:
        state["classical_result"] = classical_result
        _append_completed(state, "classical_optimization")
        return state

    def mock_comparison(state: AgentState) -> AgentState:
        state["comparison_summary"] = comparison
        _append_completed(state, "comparison")
        return state

    def mock_llm_explanation(state: AgentState) -> AgentState:
        state["llm_explanation"] = "This portfolio is well-diversified."
        _append_completed(state, "llm_explanation")
        return state

    with (
        patch("app.agents.nodes.data_fetch_node", side_effect=mock_data_fetch),
        patch(
            "app.agents.nodes.constraint_validation_node",
            side_effect=mock_constraint_validation,
        ),
        patch(
            "app.agents.nodes.classical_optimization_node",
            side_effect=mock_classical_optimization,
        ),
        patch("app.agents.nodes.comparison_node", side_effect=mock_comparison),
        patch(
            "app.agents.nodes.llm_explanation_node",
            side_effect=mock_llm_explanation,
        ),
    ):
        result = await run_agent_graph(
            run_id=run_id,
            request=request,
            progress_callback=None,
        )

    assert isinstance(result, OptimizationRunDetail)
    assert result.run_id == run_id
    assert result.status == "completed"
    assert result.classical_result is not None
    assert result.classical_result.metrics.sharpe_ratio == 1.30
    assert result.llm_explanation == "This portfolio is well-diversified."


@pytest.mark.asyncio
async def test_run_agent_graph_returns_failed_when_data_fetch_fails() -> None:
    """run_agent_graph returns status='failed' when data_fetch node fails."""
    from app.agents.graph import run_agent_graph

    request = _make_request(run_quantum=False)
    run_id = str(uuid.uuid4())

    def mock_data_fetch_fail(state: AgentState) -> AgentState:
        state["error"] = "yfinance connection timeout"
        state["failed_node"] = "data_fetch"
        state["error_details"] = {
            "node": "data_fetch",
            "error_type": "ConnectionError",
        }
        return state

    with (
        patch("app.agents.nodes.data_fetch_node", side_effect=mock_data_fetch_fail),
    ):
        result = await run_agent_graph(
            run_id=run_id,
            request=request,
            progress_callback=None,
        )

    assert result.status == "failed"
    assert result.error_message is not None
    assert "data_fetch" in result.error_message
    assert result.classical_result is None


@pytest.mark.asyncio
async def test_run_agent_graph_completed_when_quantum_fails() -> None:
    """run_agent_graph returns status='completed' when quantum fails (non-fatal)."""
    from app.agents.graph import run_agent_graph

    request = _make_request(run_quantum=True)
    run_id = str(uuid.uuid4())

    classical_result = _make_minimal_classical_result()
    comparison = _make_minimal_comparison()

    def mock_data_fetch(state: AgentState) -> AgentState:
        state["price_data"] = pd.DataFrame(
            {"AAPL": [150.0, 152.0], "MSFT": [300.0, 302.0]}
        )
        state["returns_data"] = pd.DataFrame({"AAPL": [0.01], "MSFT": [0.007]})
        state["expected_returns"] = np.array([0.12, 0.10])
        state["covariance_matrix"] = np.array([[0.04, 0.01], [0.01, 0.03]])
        state["sector_map"] = {"AAPL": "Technology", "MSFT": "Technology"}
        state["tickers"] = ["AAPL", "MSFT"]
        _append_completed(state, "data_fetch")
        return state

    def mock_constraint_validation(state: AgentState) -> AgentState:
        state["validated_constraints"] = {}
        state["constraint_warnings"] = []
        _append_completed(state, "constraint_validation")
        return state

    def mock_classical_optimization(state: AgentState) -> AgentState:
        state["classical_result"] = classical_result
        _append_completed(state, "classical_optimization")
        return state

    def mock_quantum_dispatch_fail(state: AgentState) -> AgentState:
        # Quantum fails but does NOT set error/failed_node (non-fatal)
        # It just returns state without quantum_result
        _append_completed(state, "quantum_dispatch")
        return state

    def mock_comparison(state: AgentState) -> AgentState:
        state["comparison_summary"] = comparison
        _append_completed(state, "comparison")
        return state

    def mock_llm_explanation(state: AgentState) -> AgentState:
        state["llm_explanation"] = "Portfolio explanation."
        _append_completed(state, "llm_explanation")
        return state

    with (
        patch("app.agents.nodes.data_fetch_node", side_effect=mock_data_fetch),
        patch(
            "app.agents.nodes.constraint_validation_node",
            side_effect=mock_constraint_validation,
        ),
        patch(
            "app.agents.nodes.classical_optimization_node",
            side_effect=mock_classical_optimization,
        ),
        patch(
            "app.agents.nodes.quantum_dispatch_node",
            side_effect=mock_quantum_dispatch_fail,
        ),
        patch("app.agents.nodes.comparison_node", side_effect=mock_comparison),
        patch(
            "app.agents.nodes.llm_explanation_node",
            side_effect=mock_llm_explanation,
        ),
    ):
        result = await run_agent_graph(
            run_id=run_id,
            request=request,
            progress_callback=None,
        )

    # Run should still complete successfully even without quantum results
    assert result.status == "completed"
    assert result.classical_result is not None
    assert result.quantum_result is None


@pytest.mark.asyncio
async def test_run_agent_graph_progress_callback_invoked() -> None:
    """Progress callback is invoked for each node that executes."""
    from app.agents.graph import run_agent_graph

    request = _make_request(run_quantum=False)
    run_id = str(uuid.uuid4())

    classical_result = _make_minimal_classical_result()
    comparison = _make_minimal_comparison()

    progress_events: list[tuple[str, str, str]] = []

    def progress_callback(node: str, status: str, message: str) -> None:
        progress_events.append((node, status, message))

    def mock_data_fetch(state: AgentState) -> AgentState:
        state["price_data"] = pd.DataFrame({"AAPL": [150.0], "MSFT": [300.0]})
        state["returns_data"] = pd.DataFrame({"AAPL": [0.01], "MSFT": [0.007]})
        state["expected_returns"] = np.array([0.12, 0.10])
        state["covariance_matrix"] = np.array([[0.04, 0.01], [0.01, 0.03]])
        state["sector_map"] = {"AAPL": "Technology", "MSFT": "Technology"}
        state["tickers"] = ["AAPL", "MSFT"]
        _append_completed(state, "data_fetch")
        return state

    def mock_constraint_validation(state: AgentState) -> AgentState:
        state["validated_constraints"] = {}
        state["constraint_warnings"] = []
        _append_completed(state, "constraint_validation")
        return state

    def mock_classical_optimization(state: AgentState) -> AgentState:
        state["classical_result"] = classical_result
        _append_completed(state, "classical_optimization")
        return state

    def mock_comparison(state: AgentState) -> AgentState:
        state["comparison_summary"] = comparison
        _append_completed(state, "comparison")
        return state

    def mock_llm_explanation(state: AgentState) -> AgentState:
        state["llm_explanation"] = "Explanation."
        _append_completed(state, "llm_explanation")
        return state

    with (
        patch("app.agents.nodes.data_fetch_node", side_effect=mock_data_fetch),
        patch(
            "app.agents.nodes.constraint_validation_node",
            side_effect=mock_constraint_validation,
        ),
        patch(
            "app.agents.nodes.classical_optimization_node",
            side_effect=mock_classical_optimization,
        ),
        patch("app.agents.nodes.comparison_node", side_effect=mock_comparison),
        patch(
            "app.agents.nodes.llm_explanation_node",
            side_effect=mock_llm_explanation,
        ),
    ):
        await run_agent_graph(
            run_id=run_id,
            request=request,
            progress_callback=progress_callback,
        )

    # At least one progress event should have been fired
    assert len(progress_events) > 0, "No progress events were fired"

    # Each event should be a 3-tuple of strings
    for node, status, message in progress_events:
        assert isinstance(node, str), f"node is not str: {node!r}"
        assert isinstance(status, str), f"status is not str: {status!r}"
        assert isinstance(message, str), f"message is not str: {message!r}"

    # Verify that at least the data_fetch node fired a 'started' event
    started_nodes = {node for node, status, _ in progress_events if status == "started"}
    assert "data_fetch" in started_nodes, (
        f"Expected 'data_fetch' in started nodes, got: {started_nodes}"
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _append_completed(state: AgentState, node_name: str) -> None:
    """Append node_name to state['completed_nodes'] (mutates in place)."""
    completed = list(state.get("completed_nodes") or [])
    if node_name not in completed:
        completed.append(node_name)
    state["completed_nodes"] = completed  # type: ignore[typeddict-unknown-key]
