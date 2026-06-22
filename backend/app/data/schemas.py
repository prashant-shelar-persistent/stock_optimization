"""Pydantic v2 schemas for the data layer.

These models are used to:
1. Validate and serialise ``MarketData`` objects for API responses and
   inter-process communication (e.g. Celery task results).
2. Provide typed request/response models for the asset-search endpoint.
3. Define the structure of cached metadata returned to the agent layer.

Design notes
------------
- ``MarketData`` (the internal dataclass in ``fetcher.py``) uses NumPy arrays
  and Pandas DataFrames which are not directly JSON-serialisable. The Pydantic
  schemas here provide a JSON-safe representation that can be sent over the
  wire or stored in the database.
- All float arrays are represented as ``list[float]`` and 2-D matrices as
  ``list[list[float]]`` for maximum compatibility with JSON consumers.
- Timestamps are always UTC-aware ``datetime`` objects.

Usage::

    from app.data.schemas import (
        MarketDataSchema,
        AssetMetadataSchema,
        AssetInfoSchema,
        SectorSummarySchema,
        market_data_to_schema,
    )

    # Convert internal MarketData to a JSON-safe schema
    schema = market_data_to_schema(market_data)
    json_str = schema.model_dump_json()

    # Validate incoming asset metadata
    meta = AssetMetadataSchema(
        ticker="AAPL",
        name="Apple Inc.",
        sector="Information Technology",
        industry="Consumer Electronics",
        exchange="NASDAQ",
        currency="USD",
        market_cap=3_000_000_000_000,
        country="United States",
    )
"""
from __future__ import annotations


from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


if TYPE_CHECKING:
    from app.data.fetcher import MarketData


# ── Asset-level schemas ───────────────────────────────────────────────────────


class AssetMetadataSchema(BaseModel):
    """Per-asset metadata fetched from yfinance or the static sector map.

    Attributes:
        ticker: Normalised uppercase ticker symbol.
        name: Human-readable company name.
        sector: GICS sector (e.g. ``"Information Technology"``).
        industry: GICS industry sub-group.
        exchange: Exchange where the asset is listed (e.g. ``"NASDAQ"``).
        currency: Trading currency (e.g. ``"USD"``).
        market_cap: Market capitalisation in the asset's trading currency.
            ``None`` if unavailable.
        country: Country of incorporation.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    ticker: str = Field(
        description="Normalised uppercase ticker symbol",
        min_length=1,
        max_length=20,
    )
    name: str = Field(
        default="",
        description="Human-readable company or fund name",
    )
    sector: str = Field(
        default="Unknown",
        description="GICS sector name",
    )
    industry: str = Field(
        default="Unknown",
        description="GICS industry sub-group",
    )
    exchange: str = Field(
        default="Unknown",
        description="Exchange where the asset is listed",
    )
    currency: str = Field(
        default="USD",
        description="Trading currency (ISO 4217 code)",
        max_length=10,
    )
    market_cap: float | None = Field(
        default=None,
        description="Market capitalisation in trading currency",
        ge=0.0,
    )
    country: str = Field(
        default="Unknown",
        description="Country of incorporation",
    )

    @field_validator("ticker")
    @classmethod
    def normalise_ticker(cls, v: str) -> str:
        """Ensure ticker is uppercase and stripped."""
        return v.strip().upper()

    @field_validator("sector", "industry", "exchange", "country", mode="before")
    @classmethod
    def coerce_none_to_unknown(cls, v: Any) -> str:
        """Replace None or empty string with 'Unknown'."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return "Unknown"
        return v


class AssetInfoSchema(BaseModel):
    """Lightweight asset info for search results and autocomplete.

    A slimmed-down version of :class:`AssetMetadataSchema` suitable for
    returning in list endpoints where full metadata is not needed.
    """

    model_config = ConfigDict(populate_by_name=True)

    ticker: str = Field(description="Ticker symbol")
    name: str = Field(default="", description="Company name")
    sector: str | None = Field(default=None, description="GICS sector")
    exchange: str | None = Field(default=None, description="Exchange")
    currency: str = Field(default="USD", description="Trading currency")

    @field_validator("ticker")
    @classmethod
    def normalise_ticker(cls, v: str) -> str:
        return v.strip().upper()


# ── Market data schemas ───────────────────────────────────────────────────────


class PriceSeriesSchema(BaseModel):
    """Adjusted close price series for a single asset.

    Attributes:
        ticker: Asset ticker symbol.
        dates: ISO-8601 date strings (``YYYY-MM-DD``), one per trading day.
        prices: Adjusted close prices corresponding to each date.
    """

    model_config = ConfigDict(populate_by_name=True)

    ticker: str = Field(description="Asset ticker symbol")
    dates: list[str] = Field(
        description="ISO-8601 date strings (YYYY-MM-DD)",
        default_factory=list,
    )
    prices: list[float] = Field(
        description="Adjusted close prices",
        default_factory=list,
    )

    @model_validator(mode="after")
    def validate_lengths_match(self) -> "PriceSeriesSchema":
        """Ensure dates and prices have the same length."""
        if len(self.dates) != len(self.prices):
            raise ValueError(
                f"dates and prices must have the same length, "
                f"got {len(self.dates)} dates and {len(self.prices)} prices"
            )
        return self


class ReturnSeriesSchema(BaseModel):
    """Daily log return series for a single asset.

    Attributes:
        ticker: Asset ticker symbol.
        dates: ISO-8601 date strings for each return observation.
        returns: Daily log returns (ln(P_t / P_{t-1})).
    """

    model_config = ConfigDict(populate_by_name=True)

    ticker: str = Field(description="Asset ticker symbol")
    dates: list[str] = Field(
        description="ISO-8601 date strings",
        default_factory=list,
    )
    returns: list[float] = Field(
        description="Daily log returns",
        default_factory=list,
    )

    @model_validator(mode="after")
    def validate_lengths_match(self) -> "ReturnSeriesSchema":
        """Ensure dates and returns have the same length."""
        if len(self.dates) != len(self.returns):
            raise ValueError(
                f"dates and returns must have the same length, "
                f"got {len(self.dates)} dates and {len(self.returns)} returns"
            )
        return self


class CovarianceMatrixSchema(BaseModel):
    """Annualised covariance matrix in JSON-serialisable form.

    Attributes:
        tickers: Ordered list of ticker symbols (row/column labels).
        matrix: 2-D list of floats, shape (n, n).
    """

    model_config = ConfigDict(populate_by_name=True)

    tickers: list[str] = Field(
        description="Ordered ticker symbols (row and column labels)",
    )
    matrix: list[list[float]] = Field(
        description="Annualised covariance matrix values, shape (n, n)",
    )

    @model_validator(mode="after")
    def validate_matrix_shape(self) -> "CovarianceMatrixSchema":
        """Ensure the matrix is square and matches the number of tickers."""
        n = len(self.tickers)
        if len(self.matrix) != n:
            raise ValueError(
                f"matrix must have {n} rows (one per ticker), "
                f"got {len(self.matrix)}"
            )
        for i, row in enumerate(self.matrix):
            if len(row) != n:
                raise ValueError(
                    f"matrix row {i} must have {n} columns, got {len(row)}"
                )
        return self


class MarketDataSchema(BaseModel):
    """JSON-serialisable representation of a ``MarketData`` object.

    This schema is used to:
    - Return market data summaries via the API.
    - Serialise data for storage in the run history database.
    - Pass data between the FastAPI layer and Celery workers.

    Note that the full price and returns DataFrames are *not* included by
    default (they can be large). Use :func:`market_data_to_schema` with
    ``include_series=True`` to include them.

    Attributes:
        valid_tickers: Tickers that passed the data quality filter.
        expected_returns: Annualised expected returns, one per ticker.
        covariance_matrix: Annualised covariance matrix.
        sector_map: Mapping of ticker → GICS sector name.
        fetch_timestamp: UTC timestamp when the data was fetched.
        metadata: Per-ticker metadata (name, exchange, currency, etc.).
        num_trading_days: Number of trading days in the price series.
        price_series: Per-asset price series (only if ``include_series=True``).
        return_series: Per-asset return series (only if ``include_series=True``).
    """

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=False,
    )

    valid_tickers: list[str] = Field(
        description="Tickers that passed the data quality filter",
    )
    expected_returns: list[float] = Field(
        description="Annualised expected returns, one per ticker",
    )
    covariance_matrix: CovarianceMatrixSchema = Field(
        description="Annualised covariance matrix",
    )
    sector_map: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of ticker → GICS sector name",
    )
    fetch_timestamp: datetime = Field(
        description="UTC timestamp when the data was fetched",
    )
    metadata: dict[str, AssetMetadataSchema] = Field(
        default_factory=dict,
        description="Per-ticker metadata",
    )
    num_trading_days: int = Field(
        default=0,
        description="Number of trading days in the price series",
        ge=0,
    )
    price_series: list[PriceSeriesSchema] | None = Field(
        default=None,
        description="Per-asset adjusted close price series (optional)",
    )
    return_series: list[ReturnSeriesSchema] | None = Field(
        default=None,
        description="Per-asset daily log return series (optional)",
    )

    @model_validator(mode="after")
    def validate_expected_returns_length(self) -> "MarketDataSchema":
        """Ensure expected_returns has one entry per valid ticker."""
        if len(self.expected_returns) != len(self.valid_tickers):
            raise ValueError(
                f"expected_returns must have {len(self.valid_tickers)} entries "
                f"(one per valid ticker), got {len(self.expected_returns)}"
            )
        return self


# ── Sector summary schema ─────────────────────────────────────────────────────


class SectorAllocationSchema(BaseModel):
    """Sector allocation summary for a portfolio.

    Attributes:
        sector: GICS sector name.
        tickers: Tickers in this sector that are in the portfolio.
        total_weight: Sum of weights for all tickers in this sector.
        num_assets: Number of assets in this sector.
    """

    model_config = ConfigDict(populate_by_name=True)

    sector: str = Field(description="GICS sector name")
    tickers: list[str] = Field(
        description="Tickers in this sector",
        default_factory=list,
    )
    total_weight: float = Field(
        description="Total portfolio weight allocated to this sector",
        ge=0.0,
        le=1.0,
    )
    num_assets: int = Field(
        description="Number of assets in this sector",
        ge=0,
    )


class SectorSummarySchema(BaseModel):
    """Summary of sector allocations across a portfolio.

    Attributes:
        allocations: Per-sector allocation details, sorted by total_weight desc.
        num_sectors: Number of distinct sectors represented.
        largest_sector: Name of the sector with the highest total weight.
        sector_concentration: Herfindahl-Hirschman Index (HHI) of sector weights.
            A value of 1.0 means all weight is in one sector; lower values
            indicate more diversification.
    """

    model_config = ConfigDict(populate_by_name=True)

    allocations: list[SectorAllocationSchema] = Field(
        description="Per-sector allocation details",
        default_factory=list,
    )
    num_sectors: int = Field(
        description="Number of distinct sectors represented",
        ge=0,
    )
    largest_sector: str | None = Field(
        default=None,
        description="Sector with the highest total weight",
    )
    sector_concentration: float | None = Field(
        default=None,
        description="Herfindahl-Hirschman Index of sector weights (0–1)",
        ge=0.0,
        le=1.0,
    )


# ── Data fetch request schema ─────────────────────────────────────────────────


class DataFetchRequestSchema(BaseModel):
    """Parameters for a market data fetch operation.

    Used internally by the agent layer to pass fetch parameters between nodes.

    Attributes:
        tickers: List of ticker symbols to fetch.
        lookback_days: Number of calendar days of history to fetch.
    """

    model_config = ConfigDict(populate_by_name=True)

    tickers: list[str] = Field(
        description="Ticker symbols to fetch",
        min_length=1,
        max_length=50,
    )
    lookback_days: int = Field(
        default=365,
        description="Calendar days of history to fetch",
        ge=30,
        le=3650,
    )

    @field_validator("tickers")
    @classmethod
    def normalise_tickers(cls, v: list[str]) -> list[str]:
        """Normalise tickers to uppercase and deduplicate."""
        seen: set[str] = set()
        result: list[str] = []
        for ticker in v:
            upper = ticker.strip().upper()
            if upper and upper not in seen:
                seen.add(upper)
                result.append(upper)
        if not result:
            raise ValueError("At least one valid ticker symbol is required")
        return result


# ── Conversion helpers ────────────────────────────────────────────────────────


def market_data_to_schema(
    market_data: MarketData,
    include_series: bool = False,
) -> "MarketDataSchema":
    """Convert an internal ``MarketData`` dataclass to a ``MarketDataSchema``.

    Args:
        market_data: The internal ``MarketData`` object from the fetcher.
        include_series: If True, include the full price and return series
            in the schema. This can significantly increase the payload size
            for large universes or long lookback periods. Defaults to False.

    Returns:
        A ``MarketDataSchema`` instance ready for JSON serialisation.

    Example::

        from app.data.fetcher import fetch_market_data
        from app.data.schemas import market_data_to_schema

        data = fetch_market_data(["AAPL", "MSFT"], lookback_days=365)
        schema = market_data_to_schema(data, include_series=True)
        print(schema.model_dump_json(indent=2))
    """
    tickers = market_data.valid_tickers

    # ── Covariance matrix ──────────────────────────────────────────────────
    cov_array = np.asarray(market_data.covariance_matrix, dtype=float)
    cov_schema = CovarianceMatrixSchema(
        tickers=tickers,
        matrix=cov_array.tolist(),
    )

    # ── Per-ticker metadata ────────────────────────────────────────────────
    metadata_schemas: dict[str, AssetMetadataSchema] = {}
    for ticker in tickers:
        raw_meta = market_data.metadata.get(ticker, {})
        metadata_schemas[ticker] = AssetMetadataSchema(
            ticker=ticker,
            name=raw_meta.get("name", ticker),
            sector=raw_meta.get("sector", "Unknown"),
            industry=raw_meta.get("industry", "Unknown"),
            exchange=raw_meta.get("exchange", "Unknown"),
            currency=raw_meta.get("currency", "USD"),
            market_cap=raw_meta.get("market_cap"),
            country=raw_meta.get("country", "Unknown"),
        )

    # ── Optional price and return series ──────────────────────────────────
    price_series: list[PriceSeriesSchema] | None = None
    return_series: list[ReturnSeriesSchema] | None = None

    if include_series:
        price_df: pd.DataFrame = market_data.price_data
        returns_df: pd.DataFrame = market_data.returns_data

        price_series = []
        for ticker in tickers:
            if ticker in price_df.columns:
                col = price_df[ticker]
                price_series.append(
                    PriceSeriesSchema(
                        ticker=ticker,
                        dates=[d.strftime("%Y-%m-%d") for d in col.index],
                        prices=[float(p) for p in col.values],
                    )
                )

        return_series = []
        for ticker in tickers:
            if ticker in returns_df.columns:
                col = returns_df[ticker]
                return_series.append(
                    ReturnSeriesSchema(
                        ticker=ticker,
                        dates=[d.strftime("%Y-%m-%d") for d in col.index],
                        returns=[float(r) for r in col.values],
                    )
                )

    # ── Fetch timestamp ────────────────────────────────────────────────────
    fetch_ts = market_data.fetch_timestamp
    if fetch_ts.tzinfo is None:
        fetch_ts = fetch_ts.replace(tzinfo=UTC)

    return MarketDataSchema(
        valid_tickers=tickers,
        expected_returns=[float(r) for r in market_data.expected_returns],
        covariance_matrix=cov_schema,
        sector_map=dict(market_data.sector_map),
        fetch_timestamp=fetch_ts,
        metadata=metadata_schemas,
        num_trading_days=len(market_data.price_data),
        price_series=price_series,
        return_series=return_series,
    )


def compute_sector_summary(
    weights: dict[str, float],
    sector_map: dict[str, str],
) -> "SectorSummarySchema":
    """Compute a sector allocation summary for a portfolio.

    Args:
        weights: Dict of ``{ticker: weight}`` for the portfolio.
            Weights should sum to approximately 1.0.
        sector_map: Dict of ``{ticker: sector}`` for all assets.

    Returns:
        A :class:`SectorSummarySchema` with per-sector allocation details,
        the number of sectors, the largest sector, and the HHI concentration.

    Example::

        weights = {"AAPL": 0.4, "MSFT": 0.3, "JPM": 0.3}
        sector_map = {
            "AAPL": "Information Technology",
            "MSFT": "Information Technology",
            "JPM": "Financials",
        }
        summary = compute_sector_summary(weights, sector_map)
        # summary.num_sectors == 2
        # summary.largest_sector == "Information Technology"
    """
    # Group tickers by sector
    sector_tickers: dict[str, list[str]] = {}
    sector_weights: dict[str, float] = {}

    for ticker, weight in weights.items():
        if weight <= 0.0:
            continue
        sector = sector_map.get(ticker, "Unknown")
        if sector not in sector_tickers:
            sector_tickers[sector] = []
            sector_weights[sector] = 0.0
        sector_tickers[sector].append(ticker)
        sector_weights[sector] += weight

    # Build allocation list sorted by weight descending
    allocations: list[SectorAllocationSchema] = []
    for sector in sorted(sector_weights, key=lambda s: sector_weights[s], reverse=True):
        allocations.append(
            SectorAllocationSchema(
                sector=sector,
                tickers=sorted(sector_tickers[sector]),
                total_weight=round(sector_weights[sector], 6),
                num_assets=len(sector_tickers[sector]),
            )
        )

    num_sectors = len(allocations)
    largest_sector = allocations[0].sector if allocations else None

    # Herfindahl-Hirschman Index (HHI) of sector weights
    hhi: float | None = None
    if allocations:
        hhi = float(sum(a.total_weight ** 2 for a in allocations))

    return SectorSummarySchema(
        allocations=allocations,
        num_sectors=num_sectors,
        largest_sector=largest_sector,
        sector_concentration=hhi,
    )
