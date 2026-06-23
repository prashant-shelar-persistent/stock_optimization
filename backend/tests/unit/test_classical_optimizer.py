"""Unit tests for the classical Markowitz MVO optimizer."""

import numpy as np
import pytest

from app.classical.optimizer import run_markowitz_mvo, ClassicalResult


@pytest.fixture
def two_asset_inputs():
    rng = np.random.default_rng(42)
    n = 252
    returns = np.column_stack([
        rng.normal(0.001, 0.02, n),
        rng.normal(0.0003, 0.005, n),
    ])
    mu = returns.mean(axis=0) * 252
    cov = np.cov(returns.T) * 252
    return {"tickers": ["A", "B"], "mu": mu, "cov": cov, "budget": 10000.0}


@pytest.fixture
def five_asset_inputs():
    rng = np.random.default_rng(7)
    n = 252
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
    returns = np.column_stack([
        rng.normal(0.0005 + i * 0.0002, 0.015 + i * 0.003, n)
        for i in range(5)
    ])
    mu = returns.mean(axis=0) * 252
    cov = np.cov(returns.T) * 252
    return {"tickers": tickers, "mu": mu, "cov": cov, "budget": 50000.0}


def _base_constraints(**overrides):
    base = {
        "risk_tolerance": 0.5,
        "min_return": None,
        "max_volatility": None,
        "max_weight_per_asset": 1.0,
        "min_weight_per_asset": 0.0,
        "lookback_days": 252,
        "objectives": [],
        "frontier": None,
        "sector_constraints": [],
        "num_assets_to_select": None,
    }
    base.update(overrides)
    return base


class TestBasicOptimization:
    def test_returns_classical_result(self, two_asset_inputs):
        result = run_markowitz_mvo(
            tickers=two_asset_inputs["tickers"],
            expected_returns=two_asset_inputs["mu"],
            covariance_matrix=two_asset_inputs["cov"],
            budget=two_asset_inputs["budget"],
            constraints=_base_constraints(),
        )
        assert isinstance(result, ClassicalResult)

    def test_weights_sum_to_one(self, two_asset_inputs):
        result = run_markowitz_mvo(
            tickers=two_asset_inputs["tickers"],
            expected_returns=two_asset_inputs["mu"],
            covariance_matrix=two_asset_inputs["cov"],
            budget=two_asset_inputs["budget"],
            constraints=_base_constraints(),
        )
        total = sum(aw.weight for aw in result.weights)
        assert abs(total - 1.0) < 1e-4

    def test_all_weights_non_negative(self, two_asset_inputs):
        result = run_markowitz_mvo(
            tickers=two_asset_inputs["tickers"],
            expected_returns=two_asset_inputs["mu"],
            covariance_matrix=two_asset_inputs["cov"],
            budget=two_asset_inputs["budget"],
            constraints=_base_constraints(),
        )
        for aw in result.weights:
            assert aw.weight >= -1e-6

    def test_status_is_optimal(self, two_asset_inputs):
        result = run_markowitz_mvo(
            tickers=two_asset_inputs["tickers"],
            expected_returns=two_asset_inputs["mu"],
            covariance_matrix=two_asset_inputs["cov"],
            budget=two_asset_inputs["budget"],
            constraints=_base_constraints(),
        )
        assert result.solver_status == "optimal"

    def test_sharpe_ratio_present(self, two_asset_inputs):
        result = run_markowitz_mvo(
            tickers=two_asset_inputs["tickers"],
            expected_returns=two_asset_inputs["mu"],
            covariance_matrix=two_asset_inputs["cov"],
            budget=two_asset_inputs["budget"],
            constraints=_base_constraints(),
        )
        assert result.metrics.sharpe_ratio is not None

    def test_expected_return_present(self, two_asset_inputs):
        result = run_markowitz_mvo(
            tickers=two_asset_inputs["tickers"],
            expected_returns=two_asset_inputs["mu"],
            covariance_matrix=two_asset_inputs["cov"],
            budget=two_asset_inputs["budget"],
            constraints=_base_constraints(),
        )
        assert result.metrics.expected_return is not None

    def test_volatility_positive(self, two_asset_inputs):
        result = run_markowitz_mvo(
            tickers=two_asset_inputs["tickers"],
            expected_returns=two_asset_inputs["mu"],
            covariance_matrix=two_asset_inputs["cov"],
            budget=two_asset_inputs["budget"],
            constraints=_base_constraints(),
        )
        assert result.metrics.volatility > 0


class TestMaxWeightConstraint:
    def test_max_weight_respected(self, five_asset_inputs):
        max_w = 0.30
        result = run_markowitz_mvo(
            tickers=five_asset_inputs["tickers"],
            expected_returns=five_asset_inputs["mu"],
            covariance_matrix=five_asset_inputs["cov"],
            budget=five_asset_inputs["budget"],
            constraints=_base_constraints(max_weight_per_asset=max_w),
        )
        for aw in result.weights:
            assert aw.weight <= max_w + 1e-4

    def test_equal_weight_when_max_is_tight(self, two_asset_inputs):
        result = run_markowitz_mvo(
            tickers=two_asset_inputs["tickers"],
            expected_returns=two_asset_inputs["mu"],
            covariance_matrix=two_asset_inputs["cov"],
            budget=two_asset_inputs["budget"],
            constraints=_base_constraints(max_weight_per_asset=0.5),
        )
        for aw in result.weights:
            assert aw.weight <= 0.5 + 1e-4


class TestMinReturnConstraint:
    def test_min_return_satisfied(self, five_asset_inputs):
        unconstrained = run_markowitz_mvo(
            tickers=five_asset_inputs["tickers"],
            expected_returns=five_asset_inputs["mu"],
            covariance_matrix=five_asset_inputs["cov"],
            budget=five_asset_inputs["budget"],
            constraints=_base_constraints(),
        )
        target = unconstrained.metrics.expected_return * 0.5
        result = run_markowitz_mvo(
            tickers=five_asset_inputs["tickers"],
            expected_returns=five_asset_inputs["mu"],
            covariance_matrix=five_asset_inputs["cov"],
            budget=five_asset_inputs["budget"],
            constraints=_base_constraints(min_return=target),
        )
        assert result.solver_status == "optimal"
        assert result.metrics.expected_return >= target - 1e-4


class TestMultiObjective:
    def test_return_maximize_objective(self, five_asset_inputs):
        objectives = [{"name": "return", "direction": "maximize",
                       "weight": 1.0, "enabled": True, "threshold": None, "target": None}]
        result = run_markowitz_mvo(
            tickers=five_asset_inputs["tickers"],
            expected_returns=five_asset_inputs["mu"],
            covariance_matrix=five_asset_inputs["cov"],
            budget=five_asset_inputs["budget"],
            constraints=_base_constraints(objectives=objectives),
        )
        assert result.solver_status == "optimal"

    def test_volatility_minimize_objective(self, five_asset_inputs):
        unconstrained = run_markowitz_mvo(
            tickers=five_asset_inputs["tickers"],
            expected_returns=five_asset_inputs["mu"],
            covariance_matrix=five_asset_inputs["cov"],
            budget=five_asset_inputs["budget"],
            constraints=_base_constraints(),
        )
        objectives = [{"name": "volatility", "direction": "minimize",
                       "weight": 1.0, "enabled": True, "threshold": None, "target": None}]
        result = run_markowitz_mvo(
            tickers=five_asset_inputs["tickers"],
            expected_returns=five_asset_inputs["mu"],
            covariance_matrix=five_asset_inputs["cov"],
            budget=five_asset_inputs["budget"],
            constraints=_base_constraints(objectives=objectives),
        )
        assert result.solver_status == "optimal"
        assert result.metrics.volatility <= unconstrained.metrics.volatility + 1e-3

    def test_disabled_objective_ignored(self, five_asset_inputs):
        objectives = [{"name": "return", "direction": "maximize",
                       "weight": 1.0, "enabled": False, "threshold": None, "target": None}]
        result_disabled = run_markowitz_mvo(
            tickers=five_asset_inputs["tickers"],
            expected_returns=five_asset_inputs["mu"],
            covariance_matrix=five_asset_inputs["cov"],
            budget=five_asset_inputs["budget"],
            constraints=_base_constraints(objectives=objectives),
        )
        result_none = run_markowitz_mvo(
            tickers=five_asset_inputs["tickers"],
            expected_returns=five_asset_inputs["mu"],
            covariance_matrix=five_asset_inputs["cov"],
            budget=five_asset_inputs["budget"],
            constraints=_base_constraints(),
        )
        assert abs(result_disabled.metrics.expected_return
                   - result_none.metrics.expected_return) < 1e-3
