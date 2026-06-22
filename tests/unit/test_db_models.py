"""Unit tests for app.db.models.

Tests cover:
- OptimizationRun: instantiation with required fields
- OptimizationRun.mark_running: status transition
- OptimizationRun.mark_completed: status + completed_at
- OptimizationRun.mark_failed: status + error_message + completed_at
- OptimizationRun.is_terminal: True for completed/failed, False for pending/running
- OptimizationRun.duration_seconds: correct calculation
- OptimizationRun.__repr__: contains run_id and status
- OptimizationRun: default values for optional fields
- Base: shared declarative base
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db.models import Base, OptimizationRun


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run(
    run_id: str | None = None,
    status: str = "pending",
    tickers: list | None = None,
    budget: float = 100_000.0,
) -> OptimizationRun:
    """Create a minimal OptimizationRun instance for testing."""
    return OptimizationRun(
        run_id=run_id or str(uuid.uuid4()),
        status=status,
        tickers=tickers or ["AAPL", "MSFT"],
        budget=budget,
        request_params={"tickers": tickers or ["AAPL", "MSFT"], "budget": budget},
    )


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------

class TestOptimizationRunInstantiation:
    def test_can_create_with_required_fields(self):
        run = _make_run()
        assert run is not None

    def test_run_id_is_set(self):
        run_id = str(uuid.uuid4())
        run = _make_run(run_id=run_id)
        assert run.run_id == run_id

    def test_status_is_set(self):
        run = _make_run(status="pending")
        assert run.status == "pending"

    def test_tickers_is_set(self):
        tickers = ["AAPL", "MSFT", "GOOGL"]
        run = _make_run(tickers=tickers)
        assert run.tickers == tickers

    def test_budget_is_set(self):
        run = _make_run(budget=50_000.0)
        assert run.budget == 50_000.0

    def test_optional_fields_default_to_none(self):
        run = _make_run()
        assert run.classical_result is None
        assert run.quantum_result is None
        assert run.comparison is None
        assert run.llm_explanation is None
        assert run.classical_sharpe is None
        assert run.quantum_sharpe is None
        assert run.error_message is None
        assert run.completed_at is None

    def test_request_params_is_set(self):
        params = {"tickers": ["AAPL"], "budget": 10000}
        run = OptimizationRun(
            run_id=str(uuid.uuid4()),
            status="pending",
            tickers=["AAPL"],
            budget=10000.0,
            request_params=params,
        )
        assert run.request_params == params


# ---------------------------------------------------------------------------
# mark_running
# ---------------------------------------------------------------------------

class TestMarkRunning:
    def test_sets_status_to_running(self):
        run = _make_run(status="pending")
        run.mark_running()
        assert run.status == "running"

    def test_does_not_set_completed_at(self):
        run = _make_run(status="pending")
        run.mark_running()
        assert run.completed_at is None


# ---------------------------------------------------------------------------
# mark_completed
# ---------------------------------------------------------------------------

class TestMarkCompleted:
    def test_sets_status_to_completed(self):
        run = _make_run(status="running")
        run.mark_completed()
        assert run.status == "completed"

    def test_sets_completed_at_to_now_by_default(self):
        before = datetime.now(timezone.utc)
        run = _make_run(status="running")
        run.mark_completed()
        after = datetime.now(timezone.utc)
        assert run.completed_at is not None
        assert before <= run.completed_at <= after

    def test_accepts_explicit_completed_at(self):
        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        run = _make_run(status="running")
        run.mark_completed(completed_at=ts)
        assert run.completed_at == ts

    def test_does_not_set_error_message(self):
        run = _make_run(status="running")
        run.mark_completed()
        assert run.error_message is None


# ---------------------------------------------------------------------------
# mark_failed
# ---------------------------------------------------------------------------

class TestMarkFailed:
    def test_sets_status_to_failed(self):
        run = _make_run(status="running")
        run.mark_failed("Something went wrong")
        assert run.status == "failed"

    def test_sets_error_message(self):
        error_msg = "CVXPY solver failed: infeasible"
        run = _make_run(status="running")
        run.mark_failed(error_msg)
        assert run.error_message == error_msg

    def test_sets_completed_at_to_now_by_default(self):
        before = datetime.now(timezone.utc)
        run = _make_run(status="running")
        run.mark_failed("Error")
        after = datetime.now(timezone.utc)
        assert run.completed_at is not None
        assert before <= run.completed_at <= after

    def test_accepts_explicit_completed_at(self):
        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        run = _make_run(status="running")
        run.mark_failed("Error", completed_at=ts)
        assert run.completed_at == ts


# ---------------------------------------------------------------------------
# is_terminal
# ---------------------------------------------------------------------------

class TestIsTerminal:
    def test_pending_is_not_terminal(self):
        run = _make_run(status="pending")
        assert run.is_terminal is False

    def test_running_is_not_terminal(self):
        run = _make_run(status="running")
        assert run.is_terminal is False

    def test_completed_is_terminal(self):
        run = _make_run(status="completed")
        assert run.is_terminal is True

    def test_failed_is_terminal(self):
        run = _make_run(status="failed")
        assert run.is_terminal is True

    def test_after_mark_completed_is_terminal(self):
        run = _make_run(status="running")
        run.mark_completed()
        assert run.is_terminal is True

    def test_after_mark_failed_is_terminal(self):
        run = _make_run(status="running")
        run.mark_failed("Error")
        assert run.is_terminal is True


# ---------------------------------------------------------------------------
# duration_seconds
# ---------------------------------------------------------------------------

class TestDurationSeconds:
    def test_returns_none_when_not_completed(self):
        run = _make_run(status="pending")
        assert run.duration_seconds is None

    def test_returns_none_when_completed_at_is_none(self):
        run = _make_run(status="running")
        run.completed_at = None
        assert run.duration_seconds is None

    def test_returns_correct_duration(self):
        run = _make_run(status="running")
        created = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        completed = datetime(2024, 1, 15, 12, 0, 30, tzinfo=timezone.utc)
        run.created_at = created
        run.completed_at = completed
        assert abs(run.duration_seconds - 30.0) < 0.001

    def test_handles_naive_datetimes(self):
        """Naive datetimes should be treated as UTC."""
        run = _make_run(status="completed")
        run.created_at = datetime(2024, 1, 15, 12, 0, 0)  # naive
        run.completed_at = datetime(2024, 1, 15, 12, 1, 0)  # naive, 60s later
        assert abs(run.duration_seconds - 60.0) < 0.001

    def test_duration_is_positive_for_completed_run(self):
        run = _make_run(status="running")
        run.mark_completed()
        run.created_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        assert run.duration_seconds is not None
        assert run.duration_seconds >= 0.0


# ---------------------------------------------------------------------------
# __repr__
# ---------------------------------------------------------------------------

class TestRepr:
    def test_repr_contains_run_id(self):
        run_id = str(uuid.uuid4())
        run = _make_run(run_id=run_id)
        assert run_id in repr(run)

    def test_repr_contains_status(self):
        run = _make_run(status="pending")
        assert "pending" in repr(run)

    def test_repr_contains_tickers(self):
        run = _make_run(tickers=["AAPL", "MSFT"])
        repr_str = repr(run)
        assert "AAPL" in repr_str or "MSFT" in repr_str

    def test_repr_is_string(self):
        run = _make_run()
        assert isinstance(repr(run), str)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class TestBase:
    def test_optimization_run_inherits_from_base(self):
        assert issubclass(OptimizationRun, Base)

    def test_table_name_is_optimization_runs(self):
        assert OptimizationRun.__tablename__ == "optimization_runs"

    def test_base_has_metadata(self):
        assert hasattr(Base, "metadata")


# ---------------------------------------------------------------------------
# Full lifecycle
# ---------------------------------------------------------------------------

class TestFullLifecycle:
    def test_pending_to_running_to_completed(self):
        run = _make_run(status="pending")
        assert run.status == "pending"
        assert run.is_terminal is False

        run.mark_running()
        assert run.status == "running"
        assert run.is_terminal is False

        run.mark_completed()
        assert run.status == "completed"
        assert run.is_terminal is True
        assert run.completed_at is not None

    def test_pending_to_running_to_failed(self):
        run = _make_run(status="pending")
        run.mark_running()
        run.mark_failed("Quantum solver timed out")
        assert run.status == "failed"
        assert run.error_message == "Quantum solver timed out"
        assert run.is_terminal is True

    def test_result_fields_can_be_set(self):
        run = _make_run(status="running")
        run.classical_result = {"weights": {"AAPL": 0.5, "MSFT": 0.5}}
        run.quantum_result = {"qaoa": {"selected_assets": ["AAPL"]}}
        run.classical_sharpe = 1.5
        run.quantum_sharpe = 1.2
        run.llm_explanation = "The portfolio is well-diversified."
        run.mark_completed()

        assert run.classical_result["weights"]["AAPL"] == 0.5
        assert run.quantum_result["qaoa"]["selected_assets"] == ["AAPL"]
        assert run.classical_sharpe == 1.5
        assert run.quantum_sharpe == 1.2
        assert "well-diversified" in run.llm_explanation
        assert run.status == "completed"
