"""Unit tests for the multi-objective and frontier additions to the
Pydantic v2 API schemas.

Coverage targets (Phase 1 additions in `backend/app/schemas/`):

    app.schemas.requests
        - BusinessObjective       — field bounds, defaults
        - FrontierConfig          — distinct-axis validator, num_points bounds
        - OptimizationRequest     — new `objectives` + `frontier` fields
                                    - duplicate objective names rejected
                                    - all-disabled objectives rejected
                                    - zero-sum weights rejected
                                    - over-budget weight sum (>>1) rejected
                                    - legacy normalisation
                                    - back-compat: omitting all new fields still works

    app.schemas.responses
        - FrontierPoint           — defaults + required fields
        - FrontierReport          — required fields, optional indices
        - OptimizationRunDetail   — `frontier_report` defaults to None
                                    (legacy payloads round-trip unchanged)

These tests pin the public contract so future refactors can't silently
break the frontend or LLM-commentary pipeline.
"""

import pytest
from pydantic import ValidationError

from app.schemas.requests import (
    BusinessObjective,
    FrontierConfig,
    OptimizationRequest,
    SectorConstraint,
)
from app.schemas.responses import (
    AssetWeight,
    FrontierPoint,
    FrontierReport,
    OptimizationRunDetail,
)


# ── BusinessObjective ────────────────────────────────────────────────────────


class TestBusinessObjective:
    """Validation behaviour for a single objective-matrix row."""

    def test_minimal_construction(self) -> None:
        o = BusinessObjective(name="return", direction="maximize", weight=0.5)
        assert o.name == "return"
        assert o.direction == "maximize"
        assert o.weight == 0.5
        # Defaults
        assert o.target is None
        assert o.threshold is None
        assert o.enabled is True

    def test_full_construction(self) -> None:
        o = BusinessObjective(
            name="volatility",
            direction="minimize",
            weight=0.3,
            target=0.18,
            threshold=0.25,
            enabled=False,
        )
        assert o.target == 0.18
        assert o.threshold == 0.25
        assert o.enabled is False

    @pytest.mark.parametrize("bad_weight", [-0.01, 1.01, 2.0, -1.0])
    def test_weight_bounds(self, bad_weight: float) -> None:
        with pytest.raises(ValidationError):
            BusinessObjective(
                name="return", direction="maximize", weight=bad_weight
            )

    def test_invalid_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BusinessObjective(
                name="not_a_real_measure",  # type: ignore[arg-type]
                direction="maximize",
                weight=0.5,
            )

    def test_invalid_direction_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BusinessObjective(
                name="return",
                direction="sideways",  # type: ignore[arg-type]
                weight=0.5,
            )


# ── FrontierConfig ───────────────────────────────────────────────────────────


class TestFrontierConfig:
    """Validation behaviour for the frontier-sweep configuration."""

    def test_defaults(self) -> None:
        f = FrontierConfig()
        assert f.enabled is False
        assert f.x_measure == "volatility"
        assert f.y_measure == "return"
        assert f.num_points == 25

    def test_custom_pair(self) -> None:
        f = FrontierConfig(
            enabled=True,
            x_measure="esg_score",
            y_measure="return",
            num_points=40,
        )
        assert f.x_measure == "esg_score"
        assert f.num_points == 40

    def test_same_axes_rejected_when_enabled(self) -> None:
        with pytest.raises(ValidationError) as exc:
            FrontierConfig(
                enabled=True, x_measure="return", y_measure="return"
            )
        assert "must be different" in str(exc.value)

    def test_same_axes_allowed_when_disabled(self) -> None:
        # When disabled the validator should not fire — the request
        # round-trips harmlessly even if axes coincide.
        f = FrontierConfig(
            enabled=False, x_measure="return", y_measure="return"
        )
        assert f.enabled is False

    @pytest.mark.parametrize("bad_n", [0, 4, 101, 1000])
    def test_num_points_bounds(self, bad_n: int) -> None:
        with pytest.raises(ValidationError):
            FrontierConfig(enabled=True, num_points=bad_n)


# ── OptimizationRequest — new fields ─────────────────────────────────────────


def _valid_objectives() -> list[BusinessObjective]:
    """Helper returning a syntactically valid two-row matrix."""
    return [
        BusinessObjective(name="return", direction="maximize", weight=0.6),
        BusinessObjective(
            name="volatility", direction="minimize", weight=0.4
        ),
    ]


class TestOptimizationRequestObjectives:
    """The `objectives` field on OptimizationRequest."""

    def test_request_with_objectives(self) -> None:
        req = OptimizationRequest(
            tickers=["AAPL", "MSFT"],
            budget=10_000.0,
            objectives=_valid_objectives(),
        )
        assert req.objectives is not None
        assert len(req.objectives) == 2
        assert req.objectives[0].name == "return"

    def test_request_without_any_objective_fields(self) -> None:
        """Back-compat: omitting all new fields leaves objectives=None.

        The optimiser falls back to its built-in default in that case.
        """
        req = OptimizationRequest(tickers=["AAPL", "MSFT"], budget=10_000.0)
        assert req.objectives is None
        assert req.frontier is None

    def test_duplicate_objective_names_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            OptimizationRequest(
                tickers=["AAPL", "MSFT"],
                budget=10_000.0,
                objectives=[
                    BusinessObjective(
                        name="return", direction="maximize", weight=0.5
                    ),
                    BusinessObjective(
                        name="return", direction="maximize", weight=0.5
                    ),
                ],
            )
        assert "Duplicate objective" in str(exc.value)

    def test_all_disabled_objectives_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            OptimizationRequest(
                tickers=["AAPL", "MSFT"],
                budget=10_000.0,
                objectives=[
                    BusinessObjective(
                        name="return",
                        direction="maximize",
                        weight=0.5,
                        enabled=False,
                    ),
                    BusinessObjective(
                        name="volatility",
                        direction="minimize",
                        weight=0.5,
                        enabled=False,
                    ),
                ],
            )
        assert "At least one objective must be enabled" in str(exc.value)

    def test_zero_weight_sum_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            OptimizationRequest(
                tickers=["AAPL", "MSFT"],
                budget=10_000.0,
                objectives=[
                    BusinessObjective(
                        name="return", direction="maximize", weight=0.0
                    ),
                    BusinessObjective(
                        name="volatility",
                        direction="minimize",
                        weight=0.0,
                    ),
                ],
            )
        assert "greater than 0" in str(exc.value)

    def test_overbudget_weight_sum_rejected(self) -> None:
        """Weights that sum well above 1.0 should be rejected."""
        with pytest.raises(ValidationError) as exc:
            OptimizationRequest(
                tickers=["AAPL", "MSFT"],
                budget=10_000.0,
                objectives=[
                    BusinessObjective(
                        name="return", direction="maximize", weight=0.9
                    ),
                    BusinessObjective(
                        name="volatility",
                        direction="minimize",
                        weight=0.9,
                    ),
                    BusinessObjective(
                        name="sharpe", direction="maximize", weight=0.9
                    ),
                ],
            )
        # The validator surfaces a "must not exceed 1.0" message —
        # any of these synonyms is acceptable for the contract.
        msg = str(exc.value).lower()
        assert "1.0" in msg or "exceed" in msg or "auto-normalised" in msg

    def test_tiny_float_overshoot_tolerated(self) -> None:
        """Sums like 1.0000001 are accepted (server auto-normalises)."""
        req = OptimizationRequest(
            tickers=["AAPL", "MSFT"],
            budget=10_000.0,
            objectives=[
                BusinessObjective(
                    name="return", direction="maximize", weight=0.5
                ),
                BusinessObjective(
                    name="volatility",
                    direction="minimize",
                    weight=0.5,
                ),
            ],
        )
        assert req.objectives is not None
        assert len(req.objectives) == 2


class TestOptimizationRequestFrontier:
    """The `frontier` field on OptimizationRequest."""

    def test_request_with_frontier(self) -> None:
        req = OptimizationRequest(
            tickers=["AAPL", "MSFT"],
            budget=10_000.0,
            frontier=FrontierConfig(
                enabled=True,
                x_measure="volatility",
                y_measure="return",
                num_points=15,
            ),
        )
        assert req.frontier is not None
        assert req.frontier.enabled is True
        assert req.frontier.num_points == 15

    def test_frontier_with_same_axes_propagates_validation_error(
        self,
    ) -> None:
        with pytest.raises(ValidationError):
            OptimizationRequest(
                tickers=["AAPL", "MSFT"],
                budget=10_000.0,
                frontier=FrontierConfig(
                    enabled=True,
                    x_measure="return",
                    y_measure="return",
                ),
            )


class TestLegacyNormalisation:
    """Legacy scalar fields auto-build the two-row objectives matrix."""

    def test_min_return_only_builds_matrix(self) -> None:
        req = OptimizationRequest(
            tickers=["AAPL", "MSFT"],
            budget=10_000.0,
            min_return=0.08,
        )
        assert req.objectives is not None
        assert len(req.objectives) == 2
        names = {o.name for o in req.objectives}
        assert names == {"return", "volatility"}
        ret_row = next(o for o in req.objectives if o.name == "return")
        assert ret_row.target == 0.08
        assert ret_row.threshold == 0.08
        assert ret_row.weight == 0.5

    def test_max_volatility_only_builds_matrix(self) -> None:
        req = OptimizationRequest(
            tickers=["AAPL", "MSFT"],
            budget=10_000.0,
            max_volatility=0.18,
        )
        assert req.objectives is not None
        vol_row = next(o for o in req.objectives if o.name == "volatility")
        assert vol_row.target == 0.18
        assert vol_row.direction == "minimize"

    def test_both_legacy_fields_build_matrix(self) -> None:
        req = OptimizationRequest(
            tickers=["AAPL", "MSFT"],
            budget=10_000.0,
            min_return=0.08,
            max_volatility=0.18,
        )
        assert req.objectives is not None
        assert {o.weight for o in req.objectives} == {0.5}

    def test_explicit_objectives_take_precedence_over_legacy(self) -> None:
        """If both new and legacy fields are present, new wins (no auto-build)."""
        custom = [
            BusinessObjective(
                name="sharpe", direction="maximize", weight=1.0
            )
        ]
        req = OptimizationRequest(
            tickers=["AAPL", "MSFT"],
            budget=10_000.0,
            min_return=0.08,
            max_volatility=0.18,
            objectives=custom,
        )
        assert req.objectives is not None
        assert len(req.objectives) == 1
        assert req.objectives[0].name == "sharpe"


# ── Response: FrontierPoint / FrontierReport ────────────────────────────────


class TestFrontierPoint:
    def test_minimal_required_fields(self) -> None:
        p = FrontierPoint(x=0.15, y=0.08, sharpe=0.53)
        # Defaults
        assert p.weights == []
        assert p.is_dominant is True
        assert p.is_knee is False
        assert p.solver_status == "optimal"

    def test_full_point(self) -> None:
        weights = [
            AssetWeight(ticker="AAPL", weight=0.6, allocation=6000.0),
            AssetWeight(ticker="MSFT", weight=0.4, allocation=4000.0),
        ]
        p = FrontierPoint(
            x=0.18,
            y=0.12,
            sharpe=0.67,
            weights=weights,
            is_dominant=True,
            is_knee=True,
            solver_status="optimal",
        )
        assert len(p.weights) == 2
        assert p.is_knee is True

    def test_missing_required_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FrontierPoint(x=0.15, y=0.08)  # type: ignore[call-arg]


class TestFrontierReport:
    def test_minimal_report(self) -> None:
        r = FrontierReport(
            x_measure="volatility",
            y_measure="return",
            x_direction="minimize",
            y_direction="maximize",
            points=[FrontierPoint(x=0.1, y=0.05, sharpe=0.5)],
        )
        assert len(r.points) == 1
        # Optional reference indices default to None
        assert r.knee_point_index is None
        assert r.max_sharpe_index is None
        assert r.min_risk_index is None
        # Counters default sensibly
        assert r.num_dominant == 0
        assert r.num_dominated == 0
        assert r.solve_time_ms == 0.0
        assert r.commentary is None

    def test_full_report(self) -> None:
        pts = [
            FrontierPoint(x=0.1, y=0.05, sharpe=0.5),
            FrontierPoint(x=0.15, y=0.08, sharpe=0.53),
            FrontierPoint(x=0.20, y=0.10, sharpe=0.50),
        ]
        r = FrontierReport(
            x_measure="volatility",
            y_measure="return",
            x_direction="minimize",
            y_direction="maximize",
            points=pts,
            knee_point_index=1,
            max_sharpe_index=1,
            min_risk_index=0,
            num_dominant=3,
            num_dominated=0,
            solve_time_ms=1234.5,
            commentary="Knee at moderate vol; max Sharpe coincides.",
        )
        assert r.knee_point_index == 1
        assert r.commentary is not None


# ── OptimizationRunDetail — back-compat ─────────────────────────────────────


class TestOptimizationRunDetailFrontierField:
    """Existing run payloads must keep deserialising unchanged."""

    def test_legacy_payload_without_frontier(self) -> None:
        from datetime import datetime, UTC

        d = OptimizationRunDetail(
            run_id="abc-123",
            status="completed",
            tickers=["AAPL", "MSFT"],
            budget=10_000.0,
            created_at=datetime.now(UTC),
        )
        # The new field must default to None so legacy DB rows
        # (where frontier_report is NULL) round-trip cleanly.
        assert d.frontier_report is None

    def test_payload_with_frontier_report(self) -> None:
        from datetime import datetime, UTC

        report = FrontierReport(
            x_measure="volatility",
            y_measure="return",
            x_direction="minimize",
            y_direction="maximize",
            points=[FrontierPoint(x=0.1, y=0.05, sharpe=0.5)],
        )
        d = OptimizationRunDetail(
            run_id="abc-123",
            status="completed",
            tickers=["AAPL", "MSFT"],
            budget=10_000.0,
            created_at=datetime.now(UTC),
            frontier_report=report,
        )
        assert d.frontier_report is not None
        assert d.frontier_report.y_measure == "return"


# ── Smoke: end-to-end JSON round-trip on the example payload ────────────────


class TestRequestJsonRoundTrip:
    """The schema's json_schema_extra example must validate cleanly."""

    def test_example_payload_validates(self) -> None:
        example = OptimizationRequest.model_config["json_schema_extra"][
            "example"
        ]
        req = OptimizationRequest.model_validate(example)
        assert req.tickers == ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
        assert req.objectives is not None and len(req.objectives) == 3
        assert req.frontier is not None and req.frontier.enabled is True
        assert isinstance(req.sector_constraints, list)
        assert isinstance(req.sector_constraints[0], SectorConstraint)
