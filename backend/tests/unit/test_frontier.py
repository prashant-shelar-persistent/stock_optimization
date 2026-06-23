"""Unit tests for the efficient frontier sweep module."""

import numpy as np
import pytest

from app.classical.frontier import compute_frontier
from app.schemas.responses import FrontierReport


@pytest.fixture
def five_asset_inputs():
    rng = np.random.default_rng(99)
    n = 252
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
    returns = np.column_stack([
        rng.normal(0.0005 + i * 0.0002, 0.015 + i * 0.003, n)
        for i in range(5)
    ])
    mu = returns.mean(axis=0) * 252
    cov = np.cov(returns.T) * 252
    return {"mu": mu, "cov": cov, "tickers": tickers, "budget": 50000.0}


def _base_constraints(**overrides):
    base = {
        "max_weight_per_asset": 1.0,
        "min_weight_per_asset": 0.0,
        "min_return": None,
        "max_volatility": None,
        "sector_constraints": [],
        "objectives": [],
    }
    base.update(overrides)
    return base


def _frontier_cfg(**overrides):
    base = {
        "enabled": True,
        "x_measure": "volatility",
        "y_measure": "return",
        "num_points": 10,
    }
    base.update(overrides)
    return base


class TestFrontierBasic:
    def test_returns_frontier_report(self, five_asset_inputs):
        report = compute_frontier(
            tickers=five_asset_inputs["tickers"],
            expected_returns=five_asset_inputs["mu"],
            covariance_matrix=five_asset_inputs["cov"],
            budget=five_asset_inputs["budget"],
            constraints=_base_constraints(),
            frontier_cfg=_frontier_cfg(),
        )
        assert isinstance(report, FrontierReport)

    def test_points_count_at_most_num_points(self, five_asset_inputs):
        num_points = 15
        report = compute_frontier(
            tickers=five_asset_inputs["tickers"],
            expected_returns=five_asset_inputs["mu"],
            covariance_matrix=five_asset_inputs["cov"],
            budget=five_asset_inputs["budget"],
            constraints=_base_constraints(),
            frontier_cfg=_frontier_cfg(num_points=num_points),
        )
        total = report.num_dominant + report.num_dominated
        assert total <= num_points

    def test_dominant_points_exist(self, five_asset_inputs):
        report = compute_frontier(
            tickers=five_asset_inputs["tickers"],
            expected_returns=five_asset_inputs["mu"],
            covariance_matrix=five_asset_inputs["cov"],
            budget=five_asset_inputs["budget"],
            constraints=_base_constraints(),
            frontier_cfg=_frontier_cfg(num_points=20),
        )
        dominant = [p for p in report.points if p.is_dominant]
        assert len(dominant) >= 1

    def test_weights_sum_to_one_for_each_point(self, five_asset_inputs):
        report = compute_frontier(
            tickers=five_asset_inputs["tickers"],
            expected_returns=five_asset_inputs["mu"],
            covariance_matrix=five_asset_inputs["cov"],
            budget=five_asset_inputs["budget"],
            constraints=_base_constraints(),
            frontier_cfg=_frontier_cfg(num_points=10),
        )
        for point in report.points:
            total = sum(aw.weight for aw in point.weights)
            assert abs(total - 1.0) < 1e-3

    def test_report_has_measure_names(self, five_asset_inputs):
        report = compute_frontier(
            tickers=five_asset_inputs["tickers"],
            expected_returns=five_asset_inputs["mu"],
            covariance_matrix=five_asset_inputs["cov"],
            budget=five_asset_inputs["budget"],
            constraints=_base_constraints(),
            frontier_cfg=_frontier_cfg(x_measure="volatility", y_measure="return"),
        )
        assert report.x_measure == "volatility"
        assert report.y_measure == "return"

    def test_points_have_x_and_y_values(self, five_asset_inputs):
        report = compute_frontier(
            tickers=five_asset_inputs["tickers"],
            expected_returns=five_asset_inputs["mu"],
            covariance_matrix=five_asset_inputs["cov"],
            budget=five_asset_inputs["budget"],
            constraints=_base_constraints(),
            frontier_cfg=_frontier_cfg(num_points=10),
        )
        for point in report.points:
            assert point.x is not None
            assert point.y is not None

    def test_knee_point_tagged(self, five_asset_inputs):
        report = compute_frontier(
            tickers=five_asset_inputs["tickers"],
            expected_returns=five_asset_inputs["mu"],
            covariance_matrix=five_asset_inputs["cov"],
            budget=five_asset_inputs["budget"],
            constraints=_base_constraints(),
            frontier_cfg=_frontier_cfg(num_points=20),
        )
        knee_points = [p for p in report.points if p.is_knee]
        assert len(knee_points) <= 1


class TestFrontierMeasures:
    @pytest.mark.parametrize("x_measure,y_measure", [
        ("volatility", "return"),
        ("volatility", "sharpe"),
        ("diversification_hhi", "return"),
    ])
    def test_supported_measure_pairs(self, five_asset_inputs, x_measure, y_measure):
        report = compute_frontier(
            tickers=five_asset_inputs["tickers"],
            expected_returns=five_asset_inputs["mu"],
            covariance_matrix=five_asset_inputs["cov"],
            budget=five_asset_inputs["budget"],
            constraints=_base_constraints(),
            frontier_cfg=_frontier_cfg(x_measure=x_measure, y_measure=y_measure, num_points=10),
        )
        assert isinstance(report, FrontierReport)
        assert (report.num_dominant + report.num_dominated) > 0


class TestFrontierConstraints:
    def test_max_weight_respected_in_frontier(self, five_asset_inputs):
        max_w = 0.35
        report = compute_frontier(
            tickers=five_asset_inputs["tickers"],
            expected_returns=five_asset_inputs["mu"],
            covariance_matrix=five_asset_inputs["cov"],
            budget=five_asset_inputs["budget"],
            constraints=_base_constraints(max_weight_per_asset=max_w),
            frontier_cfg=_frontier_cfg(num_points=10),
        )
        for point in report.points:
            for aw in point.weights:
                assert aw.weight <= max_w + 1e-3
