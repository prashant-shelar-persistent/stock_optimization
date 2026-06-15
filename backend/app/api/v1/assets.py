"""GET /api/v1/assets/search — Search for assets by ticker or name.

Uses a curated in-memory list of well-known tickers for fast lookups.
Falls back to yfinance for unknown tickers, with module-level caching
to avoid repeated API calls.

Design notes:
    - The in-memory list covers ~50 well-known S&P 500 constituents across
      all major sectors. This covers the vast majority of user queries.
    - For unknown tickers, yfinance is called synchronously in a thread pool
      executor to avoid blocking the async event loop.
    - Results from yfinance lookups are cached in a module-level dict to
      prevent repeated network calls for the same ticker.
    - The ``limit`` query parameter (default 10, max 50) controls the number
      of results returned.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query

from app.core.logging import get_logger
from app.schemas.responses import AssetSearchResult


logger = get_logger(__name__)
router = APIRouter(tags=["assets"])

# ── Curated asset list ────────────────────────────────────────────────────────
# Well-known tickers with sector metadata for fast lookup.
# Covers major S&P 500 constituents across all GICS sectors.
_KNOWN_ASSETS: list[dict[str, str]] = [
    # Technology
    {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology", "exchange": "NASDAQ"},
    {"ticker": "MSFT", "name": "Microsoft Corporation", "sector": "Technology", "exchange": "NASDAQ"},
    {"ticker": "GOOGL", "name": "Alphabet Inc. Class A", "sector": "Technology", "exchange": "NASDAQ"},
    {"ticker": "GOOG", "name": "Alphabet Inc. Class C", "sector": "Technology", "exchange": "NASDAQ"},
    {"ticker": "NVDA", "name": "NVIDIA Corporation", "sector": "Technology", "exchange": "NASDAQ"},
    {"ticker": "META", "name": "Meta Platforms Inc.", "sector": "Technology", "exchange": "NASDAQ"},
    {"ticker": "ADBE", "name": "Adobe Inc.", "sector": "Technology", "exchange": "NASDAQ"},
    {"ticker": "CRM", "name": "Salesforce Inc.", "sector": "Technology", "exchange": "NYSE"},
    {"ticker": "ORCL", "name": "Oracle Corporation", "sector": "Technology", "exchange": "NYSE"},
    {"ticker": "INTC", "name": "Intel Corporation", "sector": "Technology", "exchange": "NASDAQ"},
    {"ticker": "AMD", "name": "Advanced Micro Devices Inc.", "sector": "Technology", "exchange": "NASDAQ"},
    {"ticker": "QCOM", "name": "Qualcomm Inc.", "sector": "Technology", "exchange": "NASDAQ"},
    {"ticker": "AVGO", "name": "Broadcom Inc.", "sector": "Technology", "exchange": "NASDAQ"},
    {"ticker": "TXN", "name": "Texas Instruments Inc.", "sector": "Technology", "exchange": "NASDAQ"},
    {"ticker": "IBM", "name": "International Business Machines Corp.", "sector": "Technology", "exchange": "NYSE"},
    # Consumer Discretionary
    {"ticker": "AMZN", "name": "Amazon.com Inc.", "sector": "Consumer Discretionary", "exchange": "NASDAQ"},
    {"ticker": "TSLA", "name": "Tesla Inc.", "sector": "Consumer Discretionary", "exchange": "NASDAQ"},
    {"ticker": "HD", "name": "The Home Depot Inc.", "sector": "Consumer Discretionary", "exchange": "NYSE"},
    {"ticker": "MCD", "name": "McDonald's Corporation", "sector": "Consumer Discretionary", "exchange": "NYSE"},
    {"ticker": "NKE", "name": "Nike Inc.", "sector": "Consumer Discretionary", "exchange": "NYSE"},
    {"ticker": "SBUX", "name": "Starbucks Corporation", "sector": "Consumer Discretionary", "exchange": "NASDAQ"},
    {"ticker": "LOW", "name": "Lowe's Companies Inc.", "sector": "Consumer Discretionary", "exchange": "NYSE"},
    # Consumer Staples
    {"ticker": "PG", "name": "Procter & Gamble Co.", "sector": "Consumer Staples", "exchange": "NYSE"},
    {"ticker": "KO", "name": "The Coca-Cola Company", "sector": "Consumer Staples", "exchange": "NYSE"},
    {"ticker": "PEP", "name": "PepsiCo Inc.", "sector": "Consumer Staples", "exchange": "NASDAQ"},
    {"ticker": "COST", "name": "Costco Wholesale Corporation", "sector": "Consumer Staples", "exchange": "NASDAQ"},
    {"ticker": "WMT", "name": "Walmart Inc.", "sector": "Consumer Staples", "exchange": "NYSE"},
    {"ticker": "PM", "name": "Philip Morris International Inc.", "sector": "Consumer Staples", "exchange": "NYSE"},
    {"ticker": "MO", "name": "Altria Group Inc.", "sector": "Consumer Staples", "exchange": "NYSE"},
    # Financials
    {"ticker": "BRK.B", "name": "Berkshire Hathaway Inc. Class B", "sector": "Financials", "exchange": "NYSE"},
    {"ticker": "JPM", "name": "JPMorgan Chase & Co.", "sector": "Financials", "exchange": "NYSE"},
    {"ticker": "V", "name": "Visa Inc.", "sector": "Financials", "exchange": "NYSE"},
    {"ticker": "MA", "name": "Mastercard Inc.", "sector": "Financials", "exchange": "NYSE"},
    {"ticker": "BAC", "name": "Bank of America Corporation", "sector": "Financials", "exchange": "NYSE"},
    {"ticker": "WFC", "name": "Wells Fargo & Company", "sector": "Financials", "exchange": "NYSE"},
    {"ticker": "GS", "name": "The Goldman Sachs Group Inc.", "sector": "Financials", "exchange": "NYSE"},
    {"ticker": "MS", "name": "Morgan Stanley", "sector": "Financials", "exchange": "NYSE"},
    {"ticker": "AXP", "name": "American Express Company", "sector": "Financials", "exchange": "NYSE"},
    {"ticker": "BLK", "name": "BlackRock Inc.", "sector": "Financials", "exchange": "NYSE"},
    # Healthcare
    {"ticker": "JNJ", "name": "Johnson & Johnson", "sector": "Healthcare", "exchange": "NYSE"},
    {"ticker": "UNH", "name": "UnitedHealth Group Inc.", "sector": "Healthcare", "exchange": "NYSE"},
    {"ticker": "LLY", "name": "Eli Lilly and Company", "sector": "Healthcare", "exchange": "NYSE"},
    {"ticker": "ABBV", "name": "AbbVie Inc.", "sector": "Healthcare", "exchange": "NYSE"},
    {"ticker": "PFE", "name": "Pfizer Inc.", "sector": "Healthcare", "exchange": "NYSE"},
    {"ticker": "MRK", "name": "Merck & Co. Inc.", "sector": "Healthcare", "exchange": "NYSE"},
    {"ticker": "TMO", "name": "Thermo Fisher Scientific Inc.", "sector": "Healthcare", "exchange": "NYSE"},
    {"ticker": "ABT", "name": "Abbott Laboratories", "sector": "Healthcare", "exchange": "NYSE"},
    {"ticker": "DHR", "name": "Danaher Corporation", "sector": "Healthcare", "exchange": "NYSE"},
    # Energy
    {"ticker": "XOM", "name": "Exxon Mobil Corporation", "sector": "Energy", "exchange": "NYSE"},
    {"ticker": "CVX", "name": "Chevron Corporation", "sector": "Energy", "exchange": "NYSE"},
    {"ticker": "COP", "name": "ConocoPhillips", "sector": "Energy", "exchange": "NYSE"},
    {"ticker": "SLB", "name": "SLB (Schlumberger)", "sector": "Energy", "exchange": "NYSE"},
    # Communication Services
    {"ticker": "DIS", "name": "The Walt Disney Company", "sector": "Communication Services", "exchange": "NYSE"},
    {"ticker": "NFLX", "name": "Netflix Inc.", "sector": "Communication Services", "exchange": "NASDAQ"},
    {"ticker": "CMCSA", "name": "Comcast Corporation", "sector": "Communication Services", "exchange": "NASDAQ"},
    {"ticker": "T", "name": "AT&T Inc.", "sector": "Communication Services", "exchange": "NYSE"},
    {"ticker": "VZ", "name": "Verizon Communications Inc.", "sector": "Communication Services", "exchange": "NYSE"},
    # Industrials
    {"ticker": "CAT", "name": "Caterpillar Inc.", "sector": "Industrials", "exchange": "NYSE"},
    {"ticker": "BA", "name": "The Boeing Company", "sector": "Industrials", "exchange": "NYSE"},
    {"ticker": "HON", "name": "Honeywell International Inc.", "sector": "Industrials", "exchange": "NASDAQ"},
    {"ticker": "UPS", "name": "United Parcel Service Inc.", "sector": "Industrials", "exchange": "NYSE"},
    {"ticker": "GE", "name": "GE Aerospace", "sector": "Industrials", "exchange": "NYSE"},
    {"ticker": "MMM", "name": "3M Company", "sector": "Industrials", "exchange": "NYSE"},
    {"ticker": "RTX", "name": "RTX Corporation", "sector": "Industrials", "exchange": "NYSE"},
    # Materials
    {"ticker": "LIN", "name": "Linde plc", "sector": "Materials", "exchange": "NASDAQ"},
    {"ticker": "APD", "name": "Air Products and Chemicals Inc.", "sector": "Materials", "exchange": "NYSE"},
    {"ticker": "FCX", "name": "Freeport-McMoRan Inc.", "sector": "Materials", "exchange": "NYSE"},
    # Real Estate
    {"ticker": "AMT", "name": "American Tower Corporation", "sector": "Real Estate", "exchange": "NYSE"},
    {"ticker": "PLD", "name": "Prologis Inc.", "sector": "Real Estate", "exchange": "NYSE"},
    {"ticker": "EQIX", "name": "Equinix Inc.", "sector": "Real Estate", "exchange": "NASDAQ"},
    # Utilities
    {"ticker": "NEE", "name": "NextEra Energy Inc.", "sector": "Utilities", "exchange": "NYSE"},
    {"ticker": "DUK", "name": "Duke Energy Corporation", "sector": "Utilities", "exchange": "NYSE"},
    {"ticker": "SO", "name": "The Southern Company", "sector": "Utilities", "exchange": "NYSE"},
    # ETFs / Indices
    {"ticker": "SPY", "name": "SPDR S&P 500 ETF Trust", "sector": "ETF", "exchange": "NYSE"},
    {"ticker": "QQQ", "name": "Invesco QQQ Trust", "sector": "ETF", "exchange": "NASDAQ"},
    {"ticker": "IWM", "name": "iShares Russell 2000 ETF", "sector": "ETF", "exchange": "NYSE"},
    {"ticker": "GLD", "name": "SPDR Gold Shares", "sector": "ETF", "exchange": "NYSE"},
    {"ticker": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "sector": "ETF", "exchange": "NASDAQ"},
]

# Module-level cache for yfinance lookups to avoid repeated API calls
_yfinance_cache: dict[str, dict[str, str] | None] = {}


def _search_known_assets(
    query_upper: str,
    query_lower: str,
    limit: int,
) -> list[AssetSearchResult]:
    """Search the curated in-memory asset list.

    Matches on:
    1. Exact ticker prefix (highest priority)
    2. Ticker contains query
    3. Company name contains query (case-insensitive)

    Returns up to ``limit`` results.
    """
    exact_prefix: list[AssetSearchResult] = []
    ticker_contains: list[AssetSearchResult] = []
    name_contains: list[AssetSearchResult] = []

    for asset in _KNOWN_ASSETS:
        ticker = asset["ticker"].upper()
        name_lower = asset["name"].lower()

        if ticker == query_upper or ticker.startswith(query_upper):
            exact_prefix.append(
                AssetSearchResult(
                    ticker=asset["ticker"],
                    name=asset["name"],
                    sector=asset.get("sector"),
                    exchange=asset.get("exchange"),
                )
            )
        elif query_upper in ticker:
            ticker_contains.append(
                AssetSearchResult(
                    ticker=asset["ticker"],
                    name=asset["name"],
                    sector=asset.get("sector"),
                    exchange=asset.get("exchange"),
                )
            )
        elif query_lower in name_lower:
            name_contains.append(
                AssetSearchResult(
                    ticker=asset["ticker"],
                    name=asset["name"],
                    sector=asset.get("sector"),
                    exchange=asset.get("exchange"),
                )
            )

    # Combine in priority order and truncate to limit
    combined = exact_prefix + ticker_contains + name_contains
    return combined[:limit]


def _lookup_yfinance(ticker: str) -> dict[str, str] | None:
    """Look up a ticker via yfinance (synchronous, runs in thread pool).

    Returns a dict with ``ticker``, ``name``, ``sector``, ``exchange`` keys,
    or ``None`` if the ticker is not found or yfinance returns no useful data.
    """
    try:
        import yfinance as yf  # noqa: PLC0415

        info: dict[str, Any] = yf.Ticker(ticker).info
        long_name: str | None = info.get("longName") or info.get("shortName")
        if not long_name:
            return None

        return {
            "ticker": ticker.upper(),
            "name": long_name,
            "sector": info.get("sector") or info.get("sectorDisp"),
            "exchange": info.get("exchange"),
        }
    except Exception:
        return None


@router.get(
    "/assets/search",
    response_model=list[AssetSearchResult],
    summary="Search for assets",
    description=(
        "Search for assets by ticker symbol or company name. "
        "Searches a curated list of ~70 well-known tickers first. "
        "Falls back to yfinance for unknown tickers. "
        "Returns up to ``limit`` matching results (default 10, max 50)."
    ),
)
async def search_assets(
    q: str = Query(
        min_length=1,
        max_length=20,
        description="Ticker symbol or company name to search for",
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of results to return (default 10, max 50)",
    ),
) -> list[AssetSearchResult]:
    """Search for assets matching the query string.

    First searches the curated in-memory list for fast results.
    If no results are found and the query looks like a ticker symbol
    (≤ 10 chars, alphanumeric), falls back to yfinance for a live lookup.
    """
    query_upper = q.upper().strip()
    query_lower = q.lower().strip()

    # ── Search curated list ───────────────────────────────────────────────────
    matches = _search_known_assets(query_upper, query_lower, limit)

    # ── yfinance fallback for unknown tickers ─────────────────────────────────
    # Only attempt yfinance lookup if:
    # 1. No results found in the curated list
    # 2. The query looks like a ticker (short, alphanumeric + dots/hyphens)
    if not matches and len(query_upper) <= 10 and query_upper.replace(".", "").replace("-", "").isalnum():
        # Check module-level cache first
        if query_upper in _yfinance_cache:
            cached = _yfinance_cache[query_upper]
            if cached is not None:
                matches = [
                    AssetSearchResult(
                        ticker=cached["ticker"],
                        name=cached["name"],
                        sector=cached.get("sector"),
                        exchange=cached.get("exchange"),
                    )
                ]
        else:
            # Run yfinance lookup in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            yf_result = await loop.run_in_executor(
                None,
                _lookup_yfinance,
                query_upper,
            )
            # Cache the result (even None, to avoid repeated failed lookups)
            _yfinance_cache[query_upper] = yf_result

            if yf_result is not None:
                matches = [
                    AssetSearchResult(
                        ticker=yf_result["ticker"],
                        name=yf_result["name"],
                        sector=yf_result.get("sector"),
                        exchange=yf_result.get("exchange"),
                    )
                ]

    logger.debug(
        "asset_search",
        query=q,
        num_results=len(matches),
        limit=limit,
    )
    return matches
