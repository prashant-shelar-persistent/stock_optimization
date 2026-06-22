"""Integration tests for the LangGraph agent graph.

Tests cover:
1. _route_after_fatal_node returns 'end' when error is set
2. _route_after_fatal_node returns 'continue' when no error
3. _route_after_classical returns 'end' on classical failure
4. _route_after_classical returns 'quantum' when run_quantum=True and few assets
5. _route_after_classical returns 'skip_quantum' when run_quantum=False
6. _route_after_classical returns 'skip_quantum' when too many assets
7. _should_run_quantum returns 'quantum' for small portfolio with quantum enabled
8. _should_run_quantum returns 'skip_quantum' when run_quantum=False
9. _should_run_quantum returns 'skip_quantum' when too many assets
10. Graph wraps nodes with progress callback
11. run_agent_graph returns OptimizationRunDetail on success (all nodes mocked)
12. run_agent_graph returns failed status when data_fetch fails
13. run_agent_graph returns completed status when quantum fails (non-fatal)
14. Progress callback is called for each node
15. AgentState TypedDict has all required fields
"""

import asyncio
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

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


# ---------------------------------------------------------------------------
# _route_after_fatal_node tests
# ---------------------------------------------------------------------------


def test_route_after_fatal_node_returns_end_on_error() -> None:
    """Returns 'end' when state has error and failed_node set."""
    state = _make_state(error="Data fetch failed", failed_node="data_fetch")
    result = _route_after_fatal_node(state)
    assert result == "end"


def test_route_after_fatal_node_returns_continue_on_no_error() -> None:
    """Returns 'continue' when state has no error."""
    state = _make_state()
    result = _route_after_fatal_node(state)
    assert result == "continue"


def test_route_after_fatal_node_returns_continue_when_error_is_none() -> None:
    """Returns 'continue' when error is explicitly None."""
    state = _make_state(error=None, failed_node=None)
    result = _route_after_fatal_node(state)
    assert result == "continue"


def test_route_after_fatal_node_returns_end_only_when_both_set() -> None:
    """Returns 'end' only when BOTH error and failed_node are set."""
    # error set but no failed_node → continue
    state = _make_state(error="Something failed")
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
    )
    result = _route_after_classical(state)
    assert result == "quantum"


def test_route_after_classical_returns_skip_quantum_when_disabled() -> None:
    """Returns 'skip_quantum' when run_quantum=False."""
    state = _make_state(
        request_params={"run_quantum": False},
        tickers=["AAPL", "MSFT", "GOOGL"],
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
    # Create a large list of tickers that exceeds the limit
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


def test_agent_state_has_required_input_fields() -> None:
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
    """run_agent_graph returns OptimizationRunDetail on success."""
    from app.agents.graph import run_agent_graph
    from app.schemas.responses import OptimizationRunDetail

    request = _make_request(run_quantum=False)
    run_id = str(uuid.uuid4())

    # Mock all nodes to return minimal valid state
    mock_classical_result = {
        "weights": [
            {"ticker": "AAPL", "weight": 0.5, "allocation": 50000.0, "sector": "Technology"},
            {"ticker": "MSFT", "weight": 0.5, "allocation": 50000.0, "sector": "Technology"},
        ],
        "metrics": {
            "expected_return": 0.12,
            "volatility": 0.18,
            "sharpe_ratio": 1.25,
            "max_drawdown": -0.15,
            "num_assets": 2,
        },
        "solver_status": "optimal",
        "solve_time_ms": 42.5,
    }

    import numpy as np
    import pandas as pd

    def mock_data_fetch(state: AgentState) -> AgentState:
        state["price_data"] = pd.DataFrame(
            {"AAPL": [150.0, 151.0], "MSFT": [300.0, 302.0]}
        )
        state["returns_data"] = pd.DataFrame(
            {"AAPL": [0.006], "MSFT": [0.006]}
        )
        state["expected_returns"] = np.array([0.12, 0.12])
        state["covariance_matrix"] = np.eye(2) * 0.04
        state["sector_map"] = {"AAPL": "Technology", "MSFT": "Technology"}
        state["completed_nodes"] = ["data_fetch"]
        return state

    def mock_constraint_validation(state: AgentState) -> AgentState:
        state["validated_constraints"] = {}
        state["constraint_warnings"] = []
        completed = list(state.get("completed_nodes") or [])
        completed.append("constraint_validation")
        state["completed_nodes"] = completed
        return state

    def mock_classical_optimization(state: AgentState) -> AgentState:
        state["classical_result"] = mock_classical_result
        completed = list(state.get("completed_nodes") or [])
        completed.append("classical_optimization")
        state["completed_nodes"] = completed
        return state

    def mock_comparison(state: AgentState) -> AgentState:
        state["comparison_summary"] = {
            "sharpe_improvement_qaoa": None,
            "sharpe_improvement_vqe": None,
            "return_diff_qaoa": None,
            "return_diff_vqe": None,
            "volatility_diff_qaoa": None,
            "volatility_diff_vqe": None,
            "recommendation": "Classical portfolio is recommended.",
        }
        completed = list(state.get("completed_nodes") or [])
        completed.append("comparison")
        state["completed_nodes"] = completed
        return state

    def mock_llm_explanation(state: AgentState) -> AgentState:
        state["llm_explanation"] = "This is a well-diversified portfolio."
        completed = list(state.get("completed_nodes") or [])
        completed.append("llm_explanation")
        state["completed_nodes"] = completed
        return state

    with (
        patch("app.agents.nodes.data_fetch_node", side_effect=mock_data_fetch),
        patch("app.agents.nodes.constraint_validation_node", side_effect=mock_constraint_validation),
        patch("app.agents.nodes.classical_optimization_node", side_effect=mock_classical_optimization),
        patch("app.agents.nodes.comparison_node", side_effect=mock_comparison),
        patch("app.agents.nodes.llm_explanation_node", side_effect=mock_llm_explanation),
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
    assert result.classical_result.metrics.sharpe_ratio == 1.25
    assert result.llm_explanation == "This is a well-diversified portfolio."


@pytest.mark.asyncio
async def test_run_agent_graph_returns_failed_on_data_fetch_error() -> None:
    """run_agent_graph returns failed status when data_fetch fails."""
    from app.agents.graph import run_agent_graph

    request = _make_request(run_quantum=False)
    run_id = str(uuid.uuid4())

    def mock_data_fetch_fail(state: AgentState) -> AgentState:
        state["error"] = "yfinance connection timeout"
        state["failed_node"] = "data_fetch"
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
async def test_run_agent_graph_progress_callback_called() -> None:
    """Progress callback is called for each node that executes."""
    from app.agents.graph import run_agent_graph

    request = _make_request(run_quantum=False)
    run_id = str(uuid.uuid4())
    progress_events: list[tuple[str, str, str]] = []

    def progress_callback(node: str, status: str, message: str) -> None:
        progress_events.append((node, status, message))

    import numpy as np
    import pandas as pd

    def mock_data_fetch(state: AgentState) -> AgentState:
        state["price_data"] = pd.DataFrame({"AAPL": [150.0], "MSFT": [300.0]})
        state["returns_data"] = pd.DataFrame({"AAPL": [0.006], "MSFT": [0.006]})
        state["expected_returns"] = np.array([0.12, 0.12])
        state["covariance_matrix"] = np.eye(2) * 0.04
        state["sector_map"] = {"AAPL": "Technology", "MSFT": "Technology"}
        state["completed_nodes"] = ["data_fetch"]
        return state

    def mock_constraint_validation(state: AgentState) -> AgentState:
        state["validated_constraints"] = {}
        state["constraint_warnings"] = []
        completed = list(state.get("completed_nodes") or [])
        completed.append("constraint_validation")
        state["completed_nodes"] = completed
        return state

    def mock_classical_optimization(state: AgentState) -> AgentState:
        state["classical_result"] = {
            "weights": [{"ticker": "AAPL", "weight": 1.0, "allocation": 100000.0}],
            "metrics": {
                "expected_return": 0.12,
                "volatility": 0.18,
                "sharpe_ratio": 1.25,
                "max_drawdown": None,
                "num_assets": 1,
            },
            "solver_status": "optimal",
            "solve_time_ms": 10.0,
        }
        completed = list(state.get("completed_nodes") or [])
        completed.append("classical_optimization")
        state["completed_nodes"] = completed
        return state

    def mock_comparison(state: AgentState) -> AgentState:
        state["comparison_summary"] = {
            "recommendation": "Classical portfolio recommended.",
            "sharpe_improvement_qaoa": None,
            "sharpe_improvement_vqe": None,
            "return_diff_qaoa": None,
            "return_diff_vqe": None,
            "volatility_diff_qaoa": None,
            "volatility_diff_vqe": None,
        }
        completed = list(state.get("completed_nodes") or [])
        completed.append("comparison")
        state["completed_nodes"] = completed
        return state

    def mock_llm_explanation(state: AgentState) -> AgentState:
        state["llm_explanation"] = "Portfolio explanation."
        completed = list(state.get("completed_nodes") or [])
        completed.append("llm_explanation")
        state["completed_nodes"] = completed
        return state

    with (
        patch("app.agents.nodes.data_fetch_node", side_effect=mock_data_fetch),
        patch("app.agents.nodes.constraint_validation_node", side_effect=mock_constraint_validation),
        patch("app.agents.nodes.classical_optimization_node", side_effect=mock_classical_optimization),
        patch("app.agents.nodes.comparison_node", side_effect=mock_comparison),
        patch("app.agents.nodes.llm_explanation_node", side_effect=mock_llm_explanation),
    ):
        result = await run_agent_graph(
            run_id=run_id,
            request=request,
            progress_callback=progress_callback,
        )

    assert result.status == "completed"

    # Verify progress events were emitted
    assert len(progress_events) > 0

    # Check that we got started events for key nodes
    node_names = [event[0] for event in progress_events]
    assert "data_fetch" in node_names
    assert "classical_optimization" in node_names

    # Check event structure
    for node, status, message in progress_events:
        assert isinstance(node, str)
        assert status in ("started", "completed", "failed")
        assert isinstance(message, str)


@pytest.mark.asyncio
async def test_run_agent_graph_quantum_failure_is_non_fatal() -> None:
    """Quantum dispatch failure does not fail the entire run."""
    from app.agents.graph import run_agent_graph

    request = _make_request(run_quantum=True)
    run_id = str(uuid.uuid4())

    import numpy as np
    import pandas as pd

    def mock_data_fetch(state: AgentState) -> AgentState:
        state["price_data"] = pd.DataFrame({"AAPL": [150.0], "MSFT": [300.0]})
        state["returns_data"] = pd.DataFrame({"AAPL": [0.006], "MSFT": [0.006]})
        state["expected_returns"] = np.array([0.12, 0.12])
        state["covariance_matrix"] = np.eye(2) * 0.04
        state["sector_map"] = {"AAPL": "Technology", "MSFT": "Technology"}
        state["completed_nodes"] = ["data_fetch"]
        return state

    def mock_constraint_validation(state: AgentState) -> AgentState:
        state["validated_constraints"] = {}
        state["constraint_warnings"] = []
        completed = list(state.get("completed_nodes") or [])
        completed.append("constraint_validation")
        state["completed_nodes"] = completed
        return state

    def mock_classical_optimization(state: AgentState) -> AgentState:
        state["classical_result"] = {
            "weights": [{"ticker": "AAPL", "weight": 1.0, "allocation": 100000.0}],
            "metrics": {
                "expected_return": 0.12,
                "volatility": 0.18,
                "sharpe_ratio": 1.25,
                "max_drawdown": None,
                "num_assets": 1,
            },
            "solver_status": "optimal",
            "solve_time_ms": 10.0,
        }
        completed = list(state.get("completed_nodes") or [])
        completed.append("classical_optimization")
        state["completed_nodes"] = completed
        return state

    def mock_quantum_dispatch_fail(state: AgentState) -> AgentState:
        # Quantum fails but does NOT set error/failed_node (non-fatal)
        # It just returns state without quantum_result
        completed = list(state.get("completed_nodes") or [])
        completed.append("quantum_dispatch")
        state["completed_nodes"] = completed
        return state

    def mock_comparison(state: AgentState) -> AgentState:
        state["comparison_summary"] = {
            "recommendation": "Classical portfolio recommended.",
            "sharpe_improvement_qaoa": None,
            "sharpe_improvement_vqe": None,
            "return_diff_qaoa": None,
            "return_diff_vqe": None,
            "volatility_diff_qaoa": None,
            "volatility_diff_vqe": None,
        }
        completed = list(state.get("completed_nodes") or [])
        completed.append("comparison")
        state["completed_nodes"] = completed
        return state

    def mock_llm_explanation(state: AgentState) -> AgentState:
        state["llm_explanation"] = "Portfolio explanation."
        completed = list(state.get("completed_nodes") or [])
        completed.append("llm_explanation")
        state["completed_nodes"] = completed
        return state

    with (
        patch("app.agents.nodes.data_fetch_node", side_effect=mock_data_fetch),
        patch("app.agents.nodes.constraint_validation_node", side_effect=mock_constraint_validation),
        patch("app.agents.nodes.classical_optimization_node", side_effect=mock_classical_optimization),
        patch("app.agents.nodes.quantum_dispatch_node", side_effect=mock_quantum_dispatch_fail),
        patch("app.agents.nodes.comparison_node", side_effect=mock_comparison),
        patch("app.agents.nodes.llm_explanation_node", side_effect=mock_llm_explanation),
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


# ---------------------------------------------------------------------------
# _node_complete_message tests (covers missing lines 310, 320-330, 341)
# ---------------------------------------------------------------------------


def test_node_complete_message_data_fetch() -> None:
    """_node_complete_message returns correct message for data_fetch."""
    from app.agents.graph import _node_complete_message

    state = _make_state(tickers=["AAPL", "MSFT", "GOOGL"])
    msg = _node_complete_message("data_fetch", state)
    assert "3" in msg
    assert "asset" in msg.lower()


def test_node_complete_message_constraint_validation_no_warnings() -> None:
    """_node_complete_message returns success message when no warnings."""
    from app.agents.graph import _node_complete_message

    state = _make_state(constraint_warnings=[])
    msg = _node_complete_message("constraint_validation", state)
    assert "validated" in msg.lower()


def test_node_complete_message_constraint_validation_with_warnings() -> None:
    """_node_complete_message includes warning count when warnings present."""
    from app.agents.graph import _node_complete_message

    state = _make_state(constraint_warnings=["min_return too high", "budget too low"])
    msg = _node_complete_message("constraint_validation", state)
    assert "2" in msg
    assert "warning" in msg.lower()


def test_node_complete_message_classical_optimization() -> None:
    """_node_complete_message returns Sharpe ratio for classical_optimization."""
    from app.agents.graph import _node_complete_message

    state = _make_state(
        classical_result={
            "metrics": {"sharpe_ratio": 1.42},
            "weights": [],
            "solver_status": "optimal",
            "solve_time_ms": 10.0,
        }
    )
    msg = _node_complete_message("classical_optimization", state)
    assert "1.420" in msg
    assert "Sharpe" in msg


def test_node_complete_message_quantum_dispatch_with_results() -> None:
    """_node_complete_message shows QAOA/VQE when quantum results present."""
    from app.agents.graph import _node_complete_message

    state = _make_state(
        quantum_result={
            "qaoa": {"metrics": {"sharpe_ratio": 1.1}},
            "vqe": {"metrics": {"sharpe_ratio": 1.0}},
        }
    )
    msg = _node_complete_message("quantum_dispatch", state)
    assert "QAOA" in msg
    assert "VQE" in msg


def test_node_complete_message_quantum_dispatch_no_results() -> None:
    """_node_complete_message handles empty quantum results."""
    from app.agents.graph import _node_complete_message

    state = _make_state(quantum_result={})
    msg = _node_complete_message("quantum_dispatch", state)
    assert "no results" in msg.lower()


def test_node_complete_message_comparison() -> None:
    """_node_complete_message returns comparison recommendation."""
    from app.agents.graph import _node_complete_message

    state = _make_state(
        comparison_summary={"recommendation": "Classical portfolio is recommended."}
    )
    msg = _node_complete_message("comparison", state)
    assert "Classical" in msg


def test_node_complete_message_comparison_long_recommendation() -> None:
    """_node_complete_message truncates long recommendations."""
    from app.agents.graph import _node_complete_message

    long_rec = "A" * 100
    state = _make_state(comparison_summary={"recommendation": long_rec})
    msg = _node_complete_message("comparison", state)
    assert "…" in msg


def test_node_complete_message_llm_explanation() -> None:
    """_node_complete_message returns char count for llm_explanation."""
    from app.agents.graph import _node_complete_message

    state = _make_state(llm_explanation="This is a portfolio explanation.")
    msg = _node_complete_message("llm_explanation", state)
    assert "chars" in msg.lower()


def test_node_complete_message_unknown_node() -> None:
    """_node_complete_message returns fallback for unknown node names."""
    from app.agents.graph import _node_complete_message

    state = _make_state()
    msg = _node_complete_message("unknown_node", state)
    assert "unknown_node" in msg


# ---------------------------------------------------------------------------
# wrap_node exception handling tests (covers missing lines 137-157)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_graph_node_exception_sets_error_state() -> None:
    """When a node raises an unexpected exception, error state is set."""
    from app.agents.graph import run_agent_graph

    request = _make_request(run_quantum=False)
    run_id = str(uuid.uuid4())\

    def mock_data_fetch_raises(state: AgentState) -> AgentState:
        raise RuntimeError("Unexpected network error")

    with patch("app.agents.nodes.data_fetch_node", side_effect=mock_data_fetch_raises):
        result = await run_agent_graph(
            run_id=run_id,
            request=request,
            progress_callback=None,
        )

    assert result.status == "failed"
    assert result.error_message is not None
    assert "Unexpected network error" in result.error_message


@pytest.mark.asyncio
async def test_run_agent_graph_node_exception_calls_progress_failed() -> None:
    """When a node raises, progress callback is called with 'failed' status."""
    from app.agents.graph import run_agent_graph

    request = _make_request(run_quantum=False)
    run_id = str(uuid.uuid4())
    progress_events: list[tuple[str, str, str]] = []

    def progress_callback(node: str, status: str, message: str) -> None:
        progress_events.append((node, status, message))

    def mock_data_fetch_raises(state: AgentState) -> AgentState:
        raise ValueError("Data fetch exploded")

    with patch("app.agents.nodes.data_fetch_node", side_effect=mock_data_fetch_raises):
        result = await run_agent_graph(
            run_id=run_id,
            request=request,
            progress_callback=progress_callback,
        )

    assert result.status == "failed"
    # Should have a "started" event and a "failed" event for data_fetch
    data_fetch_events = [(n, s, m) for n, s, m in progress_events if n == "data_fetch"]
    statuses = [s for _, s, _ in data_fetch_events]
    assert "started" in statuses
    assert "failed" in statuses


@pytest.mark.asyncio
async def test_run_agent_graph_node_sets_error_in_state_calls_failed_callback() -> None:
    """When a node sets error in state (non-exception), progress callback gets 'failed'."""
    from app.agents.graph import run_agent_graph

    request = _make_request(run_quantum=False)
    run_id = str(uuid.uuid4())
    progress_events: list[tuple[str, str, str]] = []

    def progress_callback(node: str, status: str, message: str) -> None:
        progress_events.append((node, status, message))

    def mock_data_fetch_sets_error(state: AgentState) -> AgentState:
        updated = dict(state)
        updated["error"] = "Market data unavailable"
        updated["failed_node"] = "data_fetch"
        return updated  # type: ignore[return-value]

    with patch("app.agents.nodes.data_fetch_node", side_effect=mock_data_fetch_sets_error):
        result = await run_agent_graph(
            run_id=run_id,
            request=request,
            progress_callback=progress_callback,
        )

    assert result.status == "failed"
    data_fetch_events = [(n, s, m) for n, s, m in progress_events if n == "data_fetch"]
    statuses = [s for _, s, _ in data_fetch_events]
    assert "failed" in statuses


# ---------------------------------------------------------------------------
# _state_to_run_detail error handling tests (covers missing lines 439-478)
# ---------------------------------------------------------------------------


def test_state_to_run_detail_handles_invalid_classical_result() -> None:
    """_state_to_run_detail gracefully handles invalid classical_result dict."""
    from app.agents.graph import _state_to_run_detail

    request = _make_request()
    run_id = str(uuid.uuid4())

    # Invalid classical_result that will fail model_validate
    state = _make_state(
        classical_result={"invalid_field": "bad_data"},
        error=None,
        failed_node=None,
    )

    # Should not raise — just log a warning and set classical_result=None
    result = _state_to_run_detail(run_id, request, state)
    assert result.classical_result is None


def test_state_to_run_detail_handles_invalid_quantum_result() -> None:
    """_state_to_run_detail gracefully handles invalid quantum_result dict."""
    from app.agents.graph import _state_to_run_detail

    request = _make_request()
    run_id = str(uuid.uuid4())

    # QuantumResult has optional fields, so force a validation error
    # by passing a non-dict type that will fail model_validate
    state = _make_state(
        quantum_result="not-a-dict",  # type: ignore[arg-type]
        error=None,
        failed_node=None,
    )

    # Should not raise - just log a warning and set quantum_result=None
    result = _state_to_run_detail(run_id, request, state)
    assert result.quantum_result is None


def test_state_to_run_detail_handles_invalid_comparison_summary() -> None:
    """_state_to_run_detail gracefully handles invalid comparison_summary dict."""
    from app.agents.graph import _state_to_run_detail

    request = _make_request()
    run_id = str(uuid.uuid4())

    state = _make_state(
        comparison_summary={"invalid_field": "bad_data"},
        error=None,
        failed_node=None,
    )

    result = _state_to_run_detail(run_id, request, state)
    assert result.comparison is None


def test_state_to_run_detail_error_message_includes_failed_node() -> None:
    """_state_to_run_detail includes failed_node in error_message."""
    from app.agents.graph import _state_to_run_detail

    request = _make_request()
    run_id = str(uuid.uuid4())

    state = _make_state(
        error="Connection refused",
        failed_node="data_fetch",
    )

    result = _state_to_run_detail(run_id, request, state)
    assert result.status == "failed"
    assert result.error_message is not None
    assert "data_fetch" in result.error_message
    assert "Connection refused" in result.error_message


def test_state_to_run_detail_extracts_vqe_sharpe_when_no_qaoa() -> None:
    """_state_to_run_detail extracts quantum_sharpe from VQE when QAOA is absent."""
    from app.agents.graph import _state_to_run_detail

    request = _make_request()
    run_id = str(uuid.uuid4())

    # Build a valid QuantumResult with VQE only (no QAOA)
    vqe_result = {
        "qaoa": None,
        "vqe": {
            "selected_assets": ["AAPL"],
            "weights": [{"ticker": "AAPL", "weight": 1.0, "allocation": 100000.0}],
            "metrics": {
                "expected_return": 0.10,
                "volatility": 0.15,
                "sharpe_ratio": 0.95,
                "max_drawdown": None,
                "num_assets": 1,
            },
            "num_qubits": 2,
            "solve_time_ms": 200.0,
        },
    }

    state = _make_state(
        quantum_result=vqe_result,
        error=None,
        failed_node=None,
    )

    result = _state_to_run_detail(run_id, request, state)
    assert result.quantum_result is not None
    assert result.quantum_sharpe == pytest.approx(0.95)
