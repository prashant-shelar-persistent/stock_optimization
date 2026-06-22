"""Pydantic v2 request schemas for the Portfolio Optimizer API.

All input validation is handled here. FastAPI uses these models to
parse and validate incoming JSON request bodies.

Phase 1 changes:
    - Added BusinessObjective (multi-objective matrix row)
    - Added FrontierConfig (X/Y measure pair sweep config)
    - OptimizationRequest now accepts `objectives` and `frontier`
    - Legacy scalar fields (min_return, max_volatility) are auto-normalised
      into a default `objectives` list when the new field is omitted.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Objective type aliases ──────────────────────────────────────────────────

ObjectiveName = Literal[
    "return",
    "volatility",
    "sharpe",
    "max_drawdown",
    "diversification_hhi",
    "esg_score",
    "sector_concentration",
]
"""Canonical set of business-objective measure names.

These match the keys used by the classical optimizer's scalarisation
layer and the frontier sweep module.  Adding a new measure here requires
a corresponding implementation in ``backend/app/classical/optimizer.py``.
"""


ObjectiveDirection = Literal["maximize", "minimize"]
"""Optimisation direction for a single objective row."""


# ── BusinessObjective ───────────────────────────────────────────────────────


class BusinessObjective(BaseModel):
    """Single row in the multi-objective optimisation matrix.

    Each row represents one user-selected business goal, e.g.::

        {"name": "return", "direction": "maximize", "weight": 0.6,
         "target": 0.10, "threshold": None, "enabled": True}

    Fields:
        name        — Canonical measure name (see ObjectiveName).
        direction   — Whether to maximise or minimise this measure.
        weight      — Relative importance in the scalarised objective
                      (0.0–1.0).  The sum across enabled rows should be
                      in (0, 1.0]; the server will auto-normalise if not.
        target      — Optional desired value (used as a soft anchor in
                      the LLM commentary, not a hard constraint).
        threshold   — Optional hard floor/ceiling.  If direction is
                      "maximize", value ≥ threshold is enforced; if
                      "minimize", value ≤ threshold is enforced.
        enabled     — When False, the row is ignored by the optimiser
                      but kept in the request payload for round-trips.
    """

    name: ObjectiveName = Field(
        description="Canonical business-objective measure name",
    )
    direction: ObjectiveDirection = Field(
        description="Whether the measure should be maximised or minimised",
    )
    weight: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Relative importance of this objective in the scalarised "
            "composite (0.0–1.0). Auto-normalised if enabled weights do "
            "not sum to 1."
        ),
    )
    target: float | None = Field(
        default=None,
        description=(
            "Optional target value used as a soft anchor for the LLM "
            "commentary and the frontier knee-point label."
        ),
    )
    threshold: float | None = Field(
        default=None,
        description=(
            "Optional hard limit. For 'maximize' objectives it is a "
            "minimum acceptable value; for 'minimize' a maximum."
        ),
    )
    enabled: bool = Field(
        default=True,
        description=(
            "When False, the objective is ignored by the optimiser but "
            "retained in the payload for UI round-trips."
        ),
    )


# ── FrontierConfig ──────────────────────────────────────────────────────────


class FrontierConfig(BaseModel):
    """Configuration for the efficient-frontier sweep.

    When ``enabled`` is True, the backend will execute an
    epsilon-constraint sweep across ``num_points`` levels of the
    ``y_measure`` and minimise the ``x_measure`` (or vice versa,
    depending on the natural direction of each measure), producing a
    Pareto-efficient frontier between the two measures.
    """

    enabled: bool = Field(
        default=False,
        description="Whether to compute and return an efficient frontier",
    )
    x_measure: ObjectiveName = Field(
        default="volatility",
        description="Measure plotted on the X-axis of the frontier scatter",
    )
    y_measure: ObjectiveName = Field(
        default="return",
        description="Measure plotted on the Y-axis of the frontier scatter",
    )
    num_points: int = Field(
        default=25,
        ge=5,
        le=100,
        description=(
            "Number of parametric solves used to trace the frontier. "
            "Higher values give a smoother curve at the cost of latency."
        ),
    )

    @model_validator(mode="after")
    def validate_distinct_axes(self) -> "FrontierConfig":
        """Ensure the X and Y measures are distinct when enabled."""
        if self.enabled and self.x_measure == self.y_measure:
            raise ValueError(
                "Frontier x_measure and y_measure must be different "
                f"(both are '{self.x_measure}')."
            )
        return self


# ── SectorConstraint (unchanged) ────────────────────────────────────────────


class SectorConstraint(BaseModel):
    """Maximum allocation constraint for a specific market sector."""

    sector: str = Field(
        description="Sector name (e.g. 'Technology', 'Healthcare')",
        min_length=1,
        max_length=100,
    )
    max_weight: float = Field(
        description="Maximum allocation fraction for this sector (0.0–1.0)",
        ge=0.0,
        le=1.0,
    )


# ── OptimizationRequest ─────────────────────────────────────────────────────


class OptimizationRequest(BaseModel):
    """Request body for POST /api/v1/optimize.

    Defines the portfolio universe, budget, and all optimization
    constraints. Supports both the legacy scalar API (``min_return`` /
    ``max_volatility``) and the new multi-objective matrix
    (``objectives`` + ``frontier``).  When only legacy fields are
    provided they are auto-normalised into a two-row objectives matrix
    by :py:meth:`normalize_legacy_constraints`.
    """

    tickers: list[str] = Field(
        description="List of ticker symbols to include in the optimization universe",
        min_length=2,
        max_length=50,
    )
    budget: float = Field(
        description="Total investment budget in USD",
        gt=0.0,
        le=1_000_000_000.0,
    )

    # ── New multi-objective fields ──────────────────────────────────────
    objectives: list[BusinessObjective] | None = Field(
        default=None,
        description=(
            "Multi-objective matrix. Each row defines one business "
            "objective (return, volatility, ESG, …) with direction and "
            "weight. If omitted, a default two-row matrix is built from "
            "the legacy min_return / max_volatility fields."
        ),
        max_length=20,
    )
    frontier: FrontierConfig | None = Field(
        default=None,
        description="Optional efficient-frontier sweep configuration",
    )

    # ── Legacy scalar fields (deprecated but still accepted) ───────────
    min_return: float | None = Field(
        default=None,
        description=(
            "DEPRECATED — use `objectives` instead. "
            "Minimum acceptable annualised portfolio return (0.0–5.0)."
        ),
        ge=0.0,
        le=5.0,
    )
    max_volatility: float | None = Field(
        default=None,
        description=(
            "DEPRECATED — use `objectives` instead. "
            "Maximum acceptable annualised portfolio volatility (0.0–5.0)."
        ),
        ge=0.0,
        le=5.0,
    )
    max_weight_per_asset: float | None = Field(
        default=None,
        description="Maximum weight for any single asset (0.0–1.0)",
        ge=0.0,
        le=1.0,
    )
    min_weight_per_asset: float | None = Field(
        default=None,
        description="Minimum weight for any included asset (0.0–1.0)",
        ge=0.0,
        le=1.0,
    )
    sector_constraints: list[SectorConstraint] | None = Field(
        default=None,
        description="Sector-level maximum allocation constraints",
        max_length=20,
    )
    num_assets_to_select: int | None = Field(
        default=None,
        description=(
            "Number of assets to select for the portfolio. "
            "Used in the QUBO formulation for quantum optimization."
        ),
        ge=2,
        le=50,
    )
    lookback_days: int = Field(
        default=365,
        description="Historical data lookback period in calendar days",
        ge=30,
        le=3650,
    )
    run_quantum: bool = Field(
        default=True,
        description="Whether to run quantum optimization (QAOA + VQE) in addition to classical",
    )

    # ── Validators ──────────────────────────────────────────────────────

    @field_validator("tickers")
    @classmethod
    def validate_tickers(cls, v: list[str]) -> list[str]:
        """Normalise tickers to uppercase and remove duplicates."""
        seen: set[str] = set()
        result: list[str] = []
        for ticker in v:
            normalised = ticker.strip().upper()
            if not normalised:
                raise ValueError("Ticker symbols cannot be empty strings")
            if len(normalised) > 10:
                raise ValueError(
                    f"Ticker '{normalised}' exceeds maximum length of 10 characters"
                )
            if normalised not in seen:
                seen.add(normalised)
                result.append(normalised)
        return result

    @model_validator(mode="after")
    def validate_weight_constraints(self) -> "OptimizationRequest":
        """Ensure min_weight < max_weight when both are specified."""
        if (
            self.min_weight_per_asset is not None
            and self.max_weight_per_asset is not None
            and self.min_weight_per_asset >= self.max_weight_per_asset
        ):
            raise ValueError(
                "min_weight_per_asset must be strictly less than max_weight_per_asset"
            )
        return self

    @model_validator(mode="after")
    def validate_num_assets_vs_tickers(self) -> "OptimizationRequest":
        """Ensure num_assets_to_select does not exceed the number of tickers."""
        if (
            self.num_assets_to_select is not None
            and self.num_assets_to_select > len(self.tickers)
        ):
            raise ValueError(
                f"num_assets_to_select ({self.num_assets_to_select}) cannot exceed "
                f"the number of tickers ({len(self.tickers)})"
            )
        return self

    @model_validator(mode="after")
    def validate_objectives_weights_sum(self) -> "OptimizationRequest":
        """Ensure the sum of enabled objective weights is in (0, 1.0].

        If the sum exceeds 1.0 by a small floating-point margin we
        tolerate it (callers normalise downstream). If it is exactly 0
        we reject — at least one enabled objective must contribute.
        """
        if self.objectives is None:
            return self

        # Disallow duplicate objective names — the optimiser would
        # otherwise silently combine them in non-obvious ways.
        names = [o.name for o in self.objectives]
        if len(names) != len(set(names)):
            duplicates = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(
                "Duplicate objective names are not allowed: "
                f"{', '.join(duplicates)}"
            )

        enabled = [o for o in self.objectives if o.enabled]
        if not enabled:
            raise ValueError(
                "At least one objective must be enabled when `objectives` "
                "is provided."
            )

        total = sum(o.weight for o in enabled)
        if total <= 0.0:
            raise ValueError(
                "Sum of enabled objective weights must be greater than 0."
            )
        # Allow tiny float overshoot above 1.0 (e.g. 1.0000001) — the
        # optimiser auto-normalises.  Anything substantially above 1 is
        # almost certainly a user error.
        if total > 1.0 + 1e-6:
            raise ValueError(
                f"Sum of enabled objective weights must be ≤ 1.0 "
                f"(got {total:.4f}). Weights will be auto-normalised "
                f"server-side if you wish to express relative priorities."
            )
        return self

    @model_validator(mode="after")
    def normalize_legacy_constraints(self) -> "OptimizationRequest":
        """Build a default ``objectives`` list from legacy scalar fields.

        Runs only when no explicit ``objectives`` matrix is provided and
        at least one of ``min_return`` / ``max_volatility`` is set.
        The result is a balanced (0.5 / 0.5) two-row matrix that
        reproduces the historical Markowitz behaviour while letting the
        rest of the pipeline operate on the unified multi-objective
        representation.
        """
        if self.objectives is not None:
            return self
        if self.min_return is None and self.max_volatility is None:
            # Nothing to translate; leave objectives as None so the
            # optimiser falls back to its built-in default
            # (max-Sharpe / max-return tilt).
            return self

        legacy: list[BusinessObjective] = [
            BusinessObjective(
                name="return",
                direction="maximize",
                weight=0.5,
                target=self.min_return,
                threshold=self.min_return,
                enabled=True,
            ),
            BusinessObjective(
                name="volatility",
                direction="minimize",
                weight=0.5,
                target=self.max_volatility,
                threshold=self.max_volatility,
                enabled=True,
            ),
        ]
        # Use object.__setattr__ because Pydantic models are otherwise
        # immutable from inside an ``after`` validator only when frozen;
        # this model is mutable so a plain assignment works.
        self.objectives = legacy
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"],
                "budget": 100000.0,
                "objectives": [
                    {
                        "name": "return",
                        "direction": "maximize",
                        "weight": 0.5,
                        "target": 0.12,
                        "threshold": 0.08,
                        "enabled": True,
                    },
                    {
                        "name": "volatility",
                        "direction": "minimize",
                        "weight": 0.3,
                        "target": 0.18,
                        "threshold": 0.25,
                        "enabled": True,
                    },
                    {
                        "name": "diversification_hhi",
                        "direction": "minimize",
                        "weight": 0.2,
                        "target": None,
                        "threshold": None,
                        "enabled": True,
                    },
                ],
                "frontier": {
                    "enabled": True,
                    "x_measure": "volatility",
                    "y_measure": "return",
                    "num_points": 25,
                },
                "max_weight_per_asset": 0.4,
                "sector_constraints": [
                    {"sector": "Technology", "max_weight": 0.6}
                ],
                "num_assets_to_select": 3,
                "lookback_days": 365,
                "run_quantum": True,
            }
        }
    }
