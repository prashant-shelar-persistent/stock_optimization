"""Portfolio Optimizer — data layer package.

Public API
----------
The data layer is responsible for:

1. Fetching historical OHLCV price data from yfinance.
2. Computing daily log returns, annualised expected returns, and the
   annualised covariance matrix.
3. Tagging each asset with its market sector via yfinance metadata.
4. Caching results in Redis to avoid rate-limiting on repeated requests.
5. Computing comprehensive portfolio performance metrics (Sharpe ratio,
   max drawdown, VaR, CVaR, Sortino ratio, etc.).

Typical usage::

    from app.data import fetch_market_data, compute_portfolio_metrics

    # Fetch and process market data
    market_data = fetch_market_data(
        tickers=["AAPL", "MSFT", "GOOGL"],
        lookback_days=365,
    )

    # Compute metrics for a given weight vector
    import numpy as np
    weights = np.array([0.4, 0.35, 0.25])
    metrics = compute_portfolio_metrics(
        weights=weights,
        expected_returns=market_data.expected_returns,
        covariance_matrix=market_data.covariance_matrix,
        returns_data=market_data.returns_data,
        risk_free_rate=0.02,
    )
    print(f"Sharpe ratio: {metrics.sharpe_ratio:.3f}")
    print(f"Max drawdown: {metrics.max_drawdown:.2%}")

    # Look up sector for a ticker
    from app.data import get_sector, enrich_sector_map
    sector = get_sector("AAPL")  # "Information Technology"

    # Convert MarketData to a JSON-safe schema
    from app.data import market_data_to_schema
    schema = market_data_to_schema(market_data)
    json_str = schema.model_dump_json()

    # Use the cache manager directly
    from app.data import CacheManager
    cache = CacheManager(namespace="my_module:")
    cache.set("key", {"value": 42}, ttl=300)
"""
from app.data.cache import CacheManager, default_cache, reset_pool
from app.data.fetcher import (
    MarketData,
    fetch_market_data,
    invalidate_cache,
)
from app.data.metrics import (
    PortfolioMetricsResult,
    annualise_returns,
    annualise_volatility,
    compute_cvar,
    compute_efficient_frontier_points,
    compute_max_drawdown,
    compute_portfolio_metrics,
    compute_portfolio_return,
    compute_portfolio_volatility,
    compute_sharpe_ratio,
    compute_var,
)
from app.data.schemas import (
    AssetInfoSchema,
    AssetMetadataSchema,
    CovarianceMatrixSchema,
    DataFetchRequestSchema,
    MarketDataSchema,
    PriceSeriesSchema,
    ReturnSeriesSchema,
    SectorAllocationSchema,
    SectorSummarySchema,
    compute_sector_summary,
    market_data_to_schema,
)
from app.data.sector_tags import (
    GICS_SECTORS,
    SECTOR_MAP,
    enrich_sector_map,
    get_sector,
    get_tickers_by_sector,
    is_valid_gics_sector,
    normalise_sector_name,
)


__all__ = [
    # ── Fetcher ──────────────────────────────────────────────────────────────
    "MarketData",
    "fetch_market_data",
    "invalidate_cache",
    # ── Metrics ──────────────────────────────────────────────────────────────
    "PortfolioMetricsResult",
    "annualise_returns",
    "annualise_volatility",
    "compute_cvar",
    "compute_efficient_frontier_points",
    "compute_max_drawdown",
    "compute_portfolio_metrics",
    "compute_portfolio_return",
    "compute_portfolio_volatility",
    "compute_sharpe_ratio",
    "compute_var",
    # ── Cache ─────────────────────────────────────────────────────────────────
    "CacheManager",
    "default_cache",
    "reset_pool",
    # ── Sector tags ───────────────────────────────────────────────────────────
    "GICS_SECTORS",
    "SECTOR_MAP",
    "enrich_sector_map",
    "get_sector",
    "get_tickers_by_sector",
    "is_valid_gics_sector",
    "normalise_sector_name",
    # ── Schemas ───────────────────────────────────────────────────────────────
    "AssetInfoSchema",
    "AssetMetadataSchema",
    "CovarianceMatrixSchema",
    "DataFetchRequestSchema",
    "MarketDataSchema",
    "PriceSeriesSchema",
    "ReturnSeriesSchema",
    "SectorAllocationSchema",
    "SectorSummarySchema",
    "compute_sector_summary",
    "market_data_to_schema",
]
