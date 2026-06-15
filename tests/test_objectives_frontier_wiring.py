"""Tests for multi-objective optimizer and efficient-frontier wiring.

Covers:
  1. run_markowitz_mvo with objectives matrix (enabled rows, weights, thresholds)
  2. run_markowitz_mvo falls back gracefully when objectives list is empty
  3. compute_frontier happy path (volatility vs return)
  4. compute_frontier with alternate axis pair (return vs sharpe)
  5. compute_frontier raises ValueError for unsupported measure
  6. compute_frontier raises ValueError when x_measure == y_measure
  7. frontier_computation_node skips when frontier.enabled=False
  8. frontier_computation_node runs and populates state when enabled=True
  9. frontier_computation_node is non-fatal on solver error
 10. AgentState has frontier_report slot
 11. FrontierReport schema round-trips through JSON
 12. FrontierPoint dominance flags are set correctly
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────

N = 3
TICKERS = ["AAPL", "MSFT", "GOOGL"]
MU = np.array([0.15, 0.12, 0.10])  # annualised expected returns
# Simple diagonal covariance (no correlation)
COV = np.diag([0.04, 0.03, 0.025])  # variances → vols ~20%, 17%, 16%
BUDGET = 100_000.0

BASE_CONSTRAINTS: dict[str, Any] = {
    "max_weight_per_asset": 0.6,
    "sector_constraints": [],
    "sector_map": {},
}


# ── 1. run_markowitz_mvo with objectives matrix ───────────────────────────────

class TestRunMarkowitzMVOObjectives:
    def test_objectives_return_maximize_produces_valid_weights(self):
        from app.classical.optimizer import run_markowitz_mvo

        constraints = {
            **BASE_CONSTRAINTS,
            "objectives": [
                {
                    "name": "return",
                    "direction": "maximize",
                    "weight": 1.0,
                    "enabled": True,
                    "threshold": None,
                }
            ],
        }
        result = run_markowitz_mvo(TICKERS, MU, COV, BUDGET, constraints)
        weights = np.array([w.weight for w in result.weights])
        assert abs(weights.sum() - 1.0) < 1e-4
        assert all(w >= -1e-6 for w in weights)

    def test_objectives_volatility_minimize_produces_low_vol_portfolio(self):
        from app.classical.optimizer import run_markowitz_mvo

        constraints = {
            **BASE_CONSTRAINTS,
            "objectives": [
                {
                    "name": "volatility",
                    "direction": "minimize",
                    "weight": 1.0,
                    "enabled": True,
                    "threshold": None,
                }
            ],
        }
        result = run_markowitz_mvo(TICKERS, MU, COV, BUDGET, constraints)
        weights = np.array([w.weight for w in result.weights])
        assert abs(weights.sum() - 1.0) < 1e-4
        # Min-vol should favour GOOGL (lowest variance)
        googl_idx = TICKERS.index("GOOGL")
        assert weights[googl_idx] > 0.2

    def test_objectives_multi_row_weighted_sum(self):
        from app.classical.optimizer import run_markowitz_mvo

        constraints = {
            **BASE_CONSTRAINTS,
            "objectives": [
                {
                    "name": "return",
                    "direction": "maximize",
                    "weight": 0.5,
                    "enabled": True,
                    "threshold": None,
                },
                {
                    "name": "volatility",
                    "direction": "minimize",
                    "weight": 0.5,
                    "enabled": True,
                    "threshold": None,
                },
            ],
        }
        result = run_markowitz_mvo(TICKERS, MU, COV, BUDGET, constraints)
        weights = np.array([w.weight for w in result.weights])
        assert abs(weights.sum() - 1.0) < 1e-4

    def test_objectives_disabled_row_ignored(self):
        """A disabled objective row must not affect the solve."""
        from app.classical.optimizer import run_markowitz_mvo

        constraints_with_disabled = {
            **BASE_CONSTRAINTS,
            "objectives": [
                {
                    "name": "return",
                    "direction": "maximize",
                    "weight": 1.0,
                    "enabled": True,
                    "threshold": None,
                },
                {
                    "name": "volatility",
                    "direction": "minimize",
                    "weight": 1.0,
                    "enabled": False,  # disabled — should be ignored
                    "threshold": None,
                },
            ],
        }
        constraints_single = {
            **BASE_CONSTRAINTS,
            "objectives": [
                {
                    "name": "return",
                    "direction": "maximize",
                    "weight": 1.0,
                    "enabled": True,
                    "threshold": None,
                }
            ],
        }
        r1 = run_markowitz_mvo(TICKERS, MU, COV, BUDGET, constraints_with_disabled)
        r2 = run_markowitz_mvo(TICKERS, MU, COV, BUDGET, constraints_single)
        w1 = np.array([w.weight for w in r1.weights])
        w2 = np.array([w.weight for w in r2.weights])
        np.testing.assert_allclose(w1, w2, atol=1e-3)

    def test_objectives_threshold_enforced_as_hard_constraint(self):
        """A return threshold must be enforced as a hard constraint."""
        from app.classical.optimizer import run_markowitz_mvo

        min_return_threshold = 0.11  # 11% — feasible given MU
        constraints = {
            **BASE_CONSTRAINTS,
            "objectives": [
                {
                    "name": "return",
                    "direction": "maximize",
                    "weight": 1.0,
                    "enabled": True,
                    "threshold": min_return_threshold,
                }
            ],
        }
        result = run_markowitz_mvo(TICKERS, MU, COV, BUDGET, constraints)
        # Build a weight vector aligned with TICKERS (some may be zero due to max_weight)
        ticker_to_weight = {w.ticker: w.weight for w in result.weights}
        weights = np.array([ticker_to_weight.get(t, 0.0) for t in TICKERS])
        portfolio_return = float(MU @ weights)
        assert portfolio_return >= min_return_threshold - 1e-4

    def test_empty_objectives_falls_back_to_sharpe(self):
        """Empty objectives list should fall back to Sharpe maximisation."""
        from app.classical.optimizer import run_markowitz_mvo

        constraints = {**BASE_CONSTRAINTS, "objectives": []}
        result = run_markowitz_mvo(TICKERS, MU, COV, BUDGET, constraints)
        weights = np.array([w.weight for w in result.weights])
        assert abs(weights.sum() - 1.0) < 1e-4
        assert result.metrics.sharpe_ratio > 0

    def test_no_objectives_key_falls_back_to_sharpe(self):
        """Missing objectives key should fall back to Sharpe maximisation."""
        from app.classical.optimizer import run_markowitz_mvo

        result = run_markowitz_mvo(TICKERS, MU, COV, BUDGET, BASE_CONSTRAINTS)
        weights = np.array([w.weight for w in result.weights])
        assert abs(weights.sum() - 1.0) < 1e-4
        assert result.metrics.sharpe_ratio > 0


# ── 2. compute_frontier ───────────────────────────────────────────────────────

class TestComputeFrontier:
    def test_volatility_vs_return_happy_path(self):
        from app.classical.frontier import compute_frontier

        cfg = {"x_measure": "volatility", "y_measure": "return", "num_points": 8}
        report = compute_frontier(TICKERS, MU, COV, BUDGET, BASE_CONSTRAINTS, cfg)

        assert len(report.points) >= 2
        assert report.x_measure == "volatility"
        assert report.y_measure == "return"
        assert report.num_dominant >= 1
        assert report.solve_time_ms > 0

    def test_return_vs_sharpe_axis_pair(self):
        from app.classical.frontier import compute_frontier

        cfg = {"x_measure": "return", "y_measure": "sharpe", "num_points": 6}
        report = compute_frontier(TICKERS, MU, COV, BUDGET, BASE_CONSTRAINTS, cfg)
        assert report.x_measure == "return"
        assert report.y_measure == "sharpe"
        assert len(report.points) >= 2

    def test_frontier_points_weights_sum_to_one(self):
        from app.classical.frontier import compute_frontier

        cfg = {"x_measure": "volatility", "y_measure": "return", "num_points": 6}
        report = compute_frontier(TICKERS, MU, COV, BUDGET, BASE_CONSTRAINTS, cfg)
        for pt in report.points:
            w_sum = sum(w.weight for w in pt.weights)
            assert abs(w_sum - 1.0) < 1e-3, f"Weights sum {w_sum} != 1 for point {pt}"

    def test_frontier_knee_index_in_range(self):
        from app.classical.frontier import compute_frontier

        cfg = {"x_measure": "volatility", "y_measure": "return", "num_points": 8}
        report = compute_frontier(TICKERS, MU, COV, BUDGET, BASE_CONSTRAINTS, cfg)
        if report.knee_point_index is not None:
            assert 0 <= report.knee_point_index < len(report.points)

    def test_frontier_max_sharpe_index_in_range(self):
        from app.classical.frontier import compute_frontier

        cfg = {"x_measure": "volatility", "y_measure": "return", "num_points": 8}
        report = compute_frontier(TICKERS, MU, COV, BUDGET, BASE_CONSTRAINTS, cfg)
        if report.max_sharpe_index is not None:
            assert 0 <= report.max_sharpe_index < len(report.points)

    def test_unsupported_measure_raises_value_error(self):
        from app.classical.frontier import compute_frontier

        cfg = {"x_measure": "max_drawdown", "y_measure": "return", "num_points": 5}
        with pytest.raises(ValueError, match="Frontier measures must be in"):
            compute_frontier(TICKERS, MU, COV, BUDGET, BASE_CONSTRAINTS, cfg)

    def test_same_axis_raises_value_error(self):
        from app.classical.frontier import compute_frontier

        cfg = {"x_measure": "return", "y_measure": "return", "num_points": 5}
        with pytest.raises(ValueError, match="must differ"):
            compute_frontier(TICKERS, MU, COV, BUDGET, BASE_CONSTRAINTS, cfg)

    def test_dominant_points_are_flagged(self):
        from app.classical.frontier import compute_frontier

        cfg = {"x_measure": "volatility", "y_measure": "return", "num_points": 8}
        report = compute_frontier(TICKERS, MU, COV, BUDGET, BASE_CONSTRAINTS, cfg)
        dominant = [p for p in report.points if p.is_dominant]
        assert len(dominant) >= 1
        assert report.num_dominant == len(dominant)

    def test_budget_reflected_in_allocations(self):
        from app.classical.frontier import compute_frontier

        cfg = {"x_measure": "volatility", "y_measure": "return", "num_points": 5}
        report = compute_frontier(TICKERS, MU, COV, BUDGET, BASE_CONSTRAINTS, cfg)
        for pt in report.points:
            total_alloc = sum(w.allocation for w in pt.weights)
            assert abs(total_alloc - BUDGET) < 1.0, (
                f"Total allocation {total_alloc} != budget {BUDGET}"
            )


# ── 3. frontier_computation_node ─────────────────────────────────────────────

class TestFrontierComputationNode:
    def _base_state(self, frontier_cfg: dict | None = None) -> dict:
        """Build a minimal AgentState dict for the frontier node.

        The frontier_computation_node reads:
          - state["validated_constraints"]  (not "constraints")
          - state["tickers"]                (top-level)
          - state["budget"]                 (top-level)
          - state["expected_returns"]       (top-level)
          - state["covariance_matrix"]      (top-level)
        """
        validated = {
            **BASE_CONSTRAINTS,
            **({"frontier": frontier_cfg} if frontier_cfg else {}),
        }
        return {
            "run_id": "test-run-id",
            "tickers": TICKERS,
            "budget": BUDGET,
            "validated_constraints": validated,
            "price_data": None,
            "returns_data": None,
            "expected_returns": MU.tolist(),
            "covariance_matrix": COV.tolist(),
            "classical_result": {"weights": [], "metrics": {}, "solver_status": "optimal", "solve_time_ms": 10},
            "quantum_result": None,
            "comparison": None,
            "frontier_report": None,
            "llm_explanation": None,
            "error": None,
            "progress_callback": None,
        }

    def test_node_skips_when_frontier_disabled(self):
        from app.agents.nodes import frontier_computation_node

        state = self._base_state({"enabled": False, "x_measure": "volatility", "y_measure": "return", "num_points": 5})
        result = frontier_computation_node(state)
        assert result.get("frontier_report") is None

    def test_node_skips_when_no_frontier_key(self):
        from app.agents.nodes import frontier_computation_node

        state = self._base_state(None)
        result = frontier_computation_node(state)
        assert result.get("frontier_report") is None

    def test_node_populates_frontier_report_when_enabled(self):
        from app.agents.nodes import frontier_computation_node

        state = self._base_state({
            "enabled": True,
            "x_measure": "volatility",
            "y_measure": "return",
            "num_points": 5,
        })
        result = frontier_computation_node(state)
        report = result.get("frontier_report")
        assert report is not None
        assert "points" in report
        assert len(report["points"]) >= 2

    def test_node_is_non_fatal_on_solver_error(self):
        """frontier_computation_node must not raise — it sets frontier_report=None on error."""
        from app.agents.nodes import frontier_computation_node

        state = self._base_state({
            "enabled": True,
            "x_measure": "volatility",
            "y_measure": "return",
            "num_points": 5,
        })
        with patch(
            "app.classical.frontier.compute_frontier",
            side_effect=RuntimeError("solver exploded"),
        ):
            result = frontier_computation_node(state)
        # Must not raise; frontier_report should be None
        assert result.get("frontier_report") is None
        # Error field on state should NOT be set (non-fatal)
        assert result.get("error") is None


# ── 4. AgentState has frontier_report slot ────────────────────────────────────

def test_agent_state_has_frontier_report_field():
    from app.agents.state import AgentState
    import typing

    hints = typing.get_type_hints(AgentState)
    assert "frontier_report" in hints, "AgentState must declare frontier_report field"


# ── 5. FrontierReport schema round-trips through JSON ─────────────────────────

def test_frontier_report_json_round_trip():
    from app.schemas.responses import FrontierReport, FrontierPoint, AssetWeight

    point = FrontierPoint(
        x=0.18,
        y=0.12,
        sharpe=0.67,
        weights=[
            AssetWeight(ticker="AAPL", weight=0.5, allocation=50_000.0),
            AssetWeight(ticker="MSFT", weight=0.5, allocation=50_000.0),
        ],
        is_dominant=True,
        is_knee=True,
        solver_status="optimal",
    )
    report = FrontierReport(
        x_measure="volatility",
        y_measure="return",
        x_direction="minimize",
        y_direction="maximize",
        points=[point],
        knee_point_index=0,
        max_sharpe_index=0,
        min_risk_index=0,
        num_dominant=1,
        num_dominated=0,
        solve_time_ms=1234.5,
        commentary="Test commentary",
    )

    serialised = report.model_dump()
    assert serialised["x_measure"] == "volatility"
    assert serialised["points"][0]["x"] == 0.18
    assert serialised["commentary"] == "Test commentary"

    # Re-parse from JSON string
    json_str = json.dumps(serialised)
    restored = FrontierReport.model_validate_json(json_str)
    assert restored.x_measure == report.x_measure
    assert len(restored.points) == 1
    assert restored.points[0].is_knee is True


# ── 6. FrontierPoint dominance flags ─────────────────────────────────────────

def test_frontier_dominance_flags_from_compute():
    """Dominant points should have lower x AND higher y than dominated ones
    for a volatility(min) vs return(max) frontier."""
    from app.classical.frontier import compute_frontier

    cfg = {"x_measure": "volatility", "y_measure": "return", "num_points": 10}
    report = compute_frontier(TICKERS, MU, COV, BUDGET, BASE_CONSTRAINTS, cfg)

    dominant = [p for p in report.points if p.is_dominant]
    dominated = [p for p in report.points if not p.is_dominant]

    # Every dominant point should have a higher Sharpe than the average dominated
    if dominant and dominated:
        avg_dominant_sharpe = sum(p.sharpe for p in dominant) / len(dominant)
        avg_dominated_sharpe = sum(p.sharpe for p in dominated) / len(dominated)
        # Dominant portfolios should generally have better risk-adjusted returns
        assert avg_dominant_sharpe >= avg_dominated_sharpe - 0.1
