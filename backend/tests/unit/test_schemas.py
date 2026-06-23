"""Unit tests for request/response schemas.

Tests cover:
- OptimizationRequest validation
- BusinessObjective validation
- FrontierConfig validation
- FrontierReport serialisation
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.requests import OptimizationRequest, BusinessObjective, FrontierConfig
from app.schemas.responses import FrontierReport, FrontierPoint, AssetWeight


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_asset_weight(ticker: str = "AAPL", weight: float = 0.6,
                       allocation: float = 30000.0) -> AssetWeight:
    return AssetWeight(ticker=ticker, weight=weight, allocation=allocation)


def _make_point(x: float = 0.15, y: float = 0.20,
                dominant: bool = True, knee: bool = False) -> FrontierPoint:
    return FrontierPoint(
        x=x,
        y=y,
        sharpe=1.0,
        is_dominant=dominant,
        is_knee=knee,
        weights=[
            _make_asset_weight("AAPL", 0.6, 30000.0),
            _make_asset_weight("MSFT", 0.4, 20000.0),
        ],
    )


# ---------------------------------------------------------------------------
# OptimizationRequest
# ---------------------------------------------------------------------------

class TestOptimizationRequest:
    def test_minimal_valid_request(self):
        req = OptimizationRequest(tickers=["AAPL", "MSFT"], budget=50000.0)
        assert req.tickers == ["AAPL", "MSFT"]
        assert req.budget == 50000.0

    def test_budget_must_be_positive(self):
        with pytest.raises(ValidationError):
            OptimizationRequest(tickers=["AAPL", "MSFT"], budget=-100)

    def test_budget_zero_rejected(self):
        with pytest.raises(ValidationError):
            OptimizationRequest(tickers=["AAPL", "MSFT"], budget=0)

    def test_single_ticker_rejected(self):
        with pytest.raises(ValidationError):
            OptimizationRequest(tickers=["AAPL"], budget=10000)

    def test_empty_tickers_rejected(self):
        with pytest.raises(ValidationError):
            OptimizationRequest(tickers=[], budget=10000)

    def test_risk_tolerance_not_required(self):
        req = OptimizationRequest(tickers=["AAPL", "MSFT"], budget=10000)
        assert req is not None

    def test_run_quantum_is_bool(self):
        req = OptimizationRequest(tickers=["AAPL", "MSFT"], budget=10000)
        assert isinstance(req.run_quantum, bool)

    def test_objectives_defaults_none_or_empty(self):
        req = OptimizationRequest(tickers=["AAPL", "MSFT"], budget=10000)
        assert req.objectives is None or req.objectives == []

    def test_frontier_defaults_none(self):
        req = OptimizationRequest(tickers=["AAPL", "MSFT"], budget=10000)
        assert req.frontier is None

    def test_full_request_with_objectives_and_frontier(self):
        req = OptimizationRequest(
            tickers=["AAPL", "MSFT", "GOOGL"],
            budget=50000.0,
            risk_tolerance=0.6,
            min_return=0.10,
            objectives=[
                BusinessObjective(
                    name="return", direction="maximize", weight=0.7, enabled=True
                ),
                BusinessObjective(
                    name="volatility", direction="minimize", weight=0.3, enabled=True
                ),
            ],
            frontier=FrontierConfig(
                x_measure="volatility", y_measure="return",
                num_points=20, enabled=True
            ),
        )
        assert len(req.objectives) == 2
        assert req.frontier is not None
        assert req.frontier.num_points == 20


# ---------------------------------------------------------------------------
# BusinessObjective
# ---------------------------------------------------------------------------

class TestBusinessObjective:
    def test_valid_maximize_return(self):
        obj = BusinessObjective(
            name="return", direction="maximize", weight=1.0, enabled=True
        )
        assert obj.name == "return"
        assert obj.direction == "maximize"

    def test_valid_minimize_volatility(self):
        obj = BusinessObjective(
            name="volatility", direction="minimize", weight=0.5, enabled=True
        )
        assert obj.direction == "minimize"

    def test_valid_sharpe_maximize(self):
        obj = BusinessObjective(
            name="sharpe", direction="maximize", weight=1.0, enabled=True
        )
        assert obj.name == "sharpe"

    def test_invalid_measure_rejected(self):
        with pytest.raises(ValidationError):
            BusinessObjective(
                name="unknown_metric", direction="maximize", weight=1.0, enabled=True
            )

    def test_invalid_direction_rejected(self):
        with pytest.raises(ValidationError):
            BusinessObjective(
                name="return", direction="sideways", weight=1.0, enabled=True
            )

    def test_negative_weight_rejected(self):
        with pytest.raises(ValidationError):
            BusinessObjective(
                name="return", direction="maximize", weight=-0.1, enabled=True
            )

    def test_zero_weight_allowed(self):
        obj = BusinessObjective(
            name="return", direction="maximize", weight=0.0, enabled=True
        )
        assert obj.weight == 0.0

    def test_threshold_optional_none(self):
        obj = BusinessObjective(
            name="sharpe", direction="maximize", weight=1.0, enabled=True, threshold=None
        )
        assert obj.threshold is None

    def test_threshold_accepted(self):
        obj = BusinessObjective(
            name="return", direction="maximize", weight=1.0, enabled=True, threshold=0.10
        )
        assert obj.threshold == pytest.approx(0.10)

    def test_disabled_objective_valid(self):
        obj = BusinessObjective(
            name="return", direction="maximize", weight=1.0, enabled=False
        )
        assert obj.enabled is False

    @pytest.mark.parametrize("measure", [
        "return", "volatility", "sharpe", "diversification_hhi",
        "sector_concentration", "max_drawdown", "esg_score"
    ])
    def test_all_valid_measures_accepted(self, measure):
        obj = BusinessObjective(
            name=measure, direction="maximize", weight=1.0, enabled=True
        )
        assert obj.name == measure


# ---------------------------------------------------------------------------
# FrontierConfig
# ---------------------------------------------------------------------------

class TestFrontierConfig:
    def test_valid_config(self):
        cfg = FrontierConfig(
            x_measure="volatility", y_measure="return", num_points=20, enabled=True
        )
        assert cfg.x_measure == "volatility"
        assert cfg.y_measure == "return"
        assert cfg.num_points == 20

    def test_num_points_too_few_rejected(self):
        # min is 5
        with pytest.raises(ValidationError):
            FrontierConfig(
                x_measure="volatility", y_measure="return", num_points=1, enabled=True
            )

    def test_num_points_too_many_rejected(self):
        # max is 100
        with pytest.raises(ValidationError):
            FrontierConfig(
                x_measure="volatility", y_measure="return", num_points=200, enabled=True
            )

    def test_num_points_at_min_boundary(self):
        cfg = FrontierConfig(
            x_measure="volatility", y_measure="return", num_points=5, enabled=True
        )
        assert cfg.num_points == 5

    def test_num_points_at_max_boundary(self):
        cfg = FrontierConfig(
            x_measure="volatility", y_measure="return", num_points=100, enabled=True
        )
        assert cfg.num_points == 100

    def test_disabled_config_valid(self):
        cfg = FrontierConfig(
            x_measure="volatility", y_measure="return", num_points=20, enabled=False
        )
        assert cfg.enabled is False

    @pytest.mark.parametrize("x,y", [
        ("volatility", "return"),
        ("volatility", "sharpe"),
        ("diversification_hhi", "return"),
        ("sector_concentration", "return"),
    ])
    def test_valid_measure_pairs(self, x, y):
        cfg = FrontierConfig(x_measure=x, y_measure=y, num_points=20, enabled=True)
        assert cfg.x_measure == x
        assert cfg.y_measure == y


# ---------------------------------------------------------------------------
# AssetWeight
# ---------------------------------------------------------------------------

class TestAssetWeight:
    def test_valid_asset_weight(self):
        aw = AssetWeight(ticker="AAPL", weight=0.6, allocation=30000.0)
        assert aw.ticker == "AAPL"
        assert aw.weight == pytest.approx(0.6)
        assert aw.allocation == pytest.approx(30000.0)

    def test_sector_optional(self):
        aw = AssetWeight(ticker="MSFT", weight=0.4, allocation=20000.0, sector=None)
        assert aw.sector is None

    def test_sector_set(self):
        aw = AssetWeight(ticker="MSFT", weight=0.4, allocation=20000.0, sector="Technology")
        assert aw.sector == "Technology"


# ---------------------------------------------------------------------------
# FrontierPoint
# ---------------------------------------------------------------------------

class TestFrontierPoint:
    def test_valid_point(self):
        point = _make_point()
        assert point.x == pytest.approx(0.15)
        assert point.y == pytest.approx(0.20)
        assert point.sharpe == pytest.approx(1.0)
        assert point.is_dominant is True
        assert point.is_knee is False

    def test_weights_accessible(self):
        point = _make_point()
        assert len(point.weights) == 2
        assert point.weights[0].ticker == "AAPL"
        assert point.weights[0].weight == pytest.approx(0.6)

    def test_solver_status_defaults_optimal(self):
        point = _make_point()
        assert point.solver_status == "optimal"


# ---------------------------------------------------------------------------
# FrontierReport
# ---------------------------------------------------------------------------

class TestFrontierReport:
    def _make_report(self, points=None, num_dominant=1, num_dominated=0) -> FrontierReport:
        if points is None:
            points = [_make_point(knee=True)]
        return FrontierReport(
            x_measure="volatility",
            y_measure="return",
            x_direction="minimize",
            y_direction="maximize",
            points=points,
            num_dominant=num_dominant,
            num_dominated=num_dominated,
            solve_time_ms=50.0,
        )

    def test_report_serialises_to_dict(self):
        report = self._make_report()
        d = report.model_dump()
        assert "points" in d
        assert d["x_measure"] == "volatility"
        assert d["y_measure"] == "return"
        assert len(d["points"]) == 1

    def test_report_json_round_trip(self):
        report = self._make_report()
        json_str = report.model_dump_json()
        restored = FrontierReport.model_validate_json(json_str)
        assert restored.x_measure == report.x_measure
        assert len(restored.points) == 1
        assert restored.points[0].x == pytest.approx(0.15)

    def test_num_dominant_and_dominated(self):
        report = self._make_report(
            points=[
                _make_point(x=0.10, y=0.15, dominant=True, knee=True),
                _make_point(x=0.20, y=0.25, dominant=True),
                _make_point(x=0.30, y=0.20, dominant=False),
            ],
            num_dominant=2,
            num_dominated=1,
        )
        assert report.num_dominant == 2
        assert report.num_dominated == 1

    def test_optional_indices_default_none(self):
        report = self._make_report()
        assert report.knee_point_index is None
        assert report.max_sharpe_index is None
        assert report.min_risk_index is None

    def test_knee_index_set(self):
        report = FrontierReport(
            x_measure="volatility",
            y_measure="return",
            x_direction="minimize",
            y_direction="maximize",
            points=[_make_point(knee=True)],
            num_dominant=1,
            num_dominated=0,
            solve_time_ms=10.0,
            knee_point_index=0,
        )
        assert report.knee_point_index == 0

    def test_commentary_optional(self):
        report = self._make_report()
        assert report.commentary is None

    def test_solve_time_ms_present(self):
        report = self._make_report()
        assert report.solve_time_ms == pytest.approx(50.0)
