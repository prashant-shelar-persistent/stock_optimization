"""Market data fetcher using yfinance with Redis caching.

Fetches historical OHLCV data for a list of tickers, computes daily
log returns, annualised expected returns, and the annualised covariance
matrix. Results are cached in Redis to avoid rate-limiting.

The module is intentionally synchronous so it can be called from both
FastAPI route handlers (via ``asyncio.to_thread``) and Celery workers.
Redis caching uses the synchronous ``redis-py`` client.

Usage::

    from app.data.fetcher import fetch_market_data

    data = fetch_market_data(tickers=["AAPL", "MSFT"], lookback_days=365)
    print(data.expected_returns)
    print(data.covariance_matrix)
    print(data.sector_map)
"""

from __future__ import annotations

import hashlib
import json
import pickle
import time
import warnings
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from app.core.config import get_settings
from app.core.exceptions import DataFetchError
from app.core.logging import get_logger

# ---------------------------------------------------------------------------
# SSL workaround for containerised environments where the system CA bundle
# may be incomplete (e.g. Podman/Docker on macOS with corporate proxies).
# yfinance >= 0.2 uses curl_cffi internally; we patch its Session class to
# disable certificate verification when the standard bundle is unavailable.
# This is safe for a local development / demo environment.
# ---------------------------------------------------------------------------
try:
    import curl_cffi.requests as _cffi_requests  # type: ignore[import]

    _OrigSession = _cffi_requests.Session

    class _NoVerifySession(_OrigSession):  # type: ignore[misc]
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs.setdefault("verify", False)
            super().__init__(*args, **kwargs)

    _cffi_requests.Session = _NoVerifySession  # type: ignore[assignment]
except ImportError:
    pass  # curl_cffi not installed - yfinance will use requests instead


logger = get_logger(__name__)

# Trading days per year (approximate)
TRADING_DAYS_PER_YEAR = 252

# Minimum number of trading days required for meaningful statistics
MIN_TRADING_DAYS = 30

# Maximum fraction of NaN values allowed per ticker column before dropping
MAX_NAN_FRACTION = 0.20


@dataclass
class MarketData:
    """Container for fetched and processed market data.

    Attributes:
        valid_tickers: Tickers that survived the data quality filter.
        price_data: Adjusted close prices, shape (days, n_assets).
        returns_data: Daily log returns, shape (days-1, n_assets).
        expected_returns: Annualised expected returns, shape (n_assets,).
        covariance_matrix: Annualised covariance matrix, shape (n, n).
        sector_map: Mapping of ticker -> sector name (e.g. "Technology").
        fetch_timestamp: UTC timestamp when the data was fetched.
        metadata: Additional per-ticker metadata (name, exchange, currency).
    """

    valid_tickers: list[str]
    price_data: pd.DataFrame
    returns_data: pd.DataFrame
    expected_returns: np.ndarray
    covariance_matrix: np.ndarray
    sector_map: dict[str, str] = field(default_factory=dict)
    fetch_timestamp: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )
    metadata: dict[str, dict[str, Any]] = field(default_factory=dict)


def fetch_market_data(
    tickers: list[str],
    lookback_days: int = 365,
) -> MarketData:
    """Fetch market data for the given tickers with Redis caching.

    Args:
        tickers: List of ticker symbols (e.g. ["AAPL", "MSFT"]).
        lookback_days: Number of calendar days of history to fetch.

    Returns:
        MarketData with price data, returns, covariance matrix, and
        sector metadata for all tickers that had sufficient data.

    Raises:
        DataFetchError: If no valid price data can be fetched.
        ValueError: If tickers is empty or lookback_days < 30.
    """
    if not tickers:
        raise ValueError("tickers list cannot be empty")
    if lookback_days < MIN_TRADING_DAYS:
        raise ValueError(
            f"lookback_days must be at least {MIN_TRADING_DAYS}, got {lookback_days}"
        )

    # Normalise tickers to uppercase and deduplicate (preserve order)
    seen: set[str] = set()
    normalised: list[str] = []
    for t in tickers:
        upper = t.strip().upper()
        if upper and upper not in seen:
            seen.add(upper)
            normalised.append(upper)
    tickers = normalised

    cache_key = _make_cache_key(tickers, lookback_days)

    # Try cache first
    cached = _get_from_cache(cache_key)
    if cached is not None:
        logger.info("market_data_cache_hit", cache_key=cache_key[:16])
        return cached

    logger.info(
        "market_data_fetching",
        tickers=tickers,
        lookback_days=lookback_days,
    )

    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=lookback_days)

    price_data = _fetch_prices(
        tickers=tickers,
        start=start_date,
        end=end_date,
    )

    if price_data.empty:
        raise DataFetchError(
            message=(
                "No price data returned for any of the requested tickers. "
                "Check that the ticker symbols are valid and the market was "
                "open during the requested period."
            ),
            tickers=tickers,
        )

    # Drop tickers with too many missing values
    min_valid_rows = int((1.0 - MAX_NAN_FRACTION) * len(price_data))
    price_data = price_data.dropna(axis=1, thresh=min_valid_rows)

    if price_data.empty:
        raise DataFetchError(
            message=(
                f"All tickers were dropped because more than "
                f"{MAX_NAN_FRACTION * 100:.0f}% of their price data was missing."
            ),
            tickers=tickers,
        )

    valid_tickers = list(price_data.columns)
    dropped = set(tickers) - set(valid_tickers)
    if dropped:
        logger.warning(
            "tickers_dropped_insufficient_data",
            dropped=sorted(dropped),
            reason=f">{MAX_NAN_FRACTION * 100:.0f}% NaN values",
        )

    # Forward-fill then back-fill remaining NaN values
    price_data = price_data.ffill().bfill()
    price_data = price_data.dropna(axis=1, how="all")
    valid_tickers = list(price_data.columns)

    if len(price_data) < MIN_TRADING_DAYS:
        raise DataFetchError(
            message=(
                f"Only {len(price_data)} trading days of data available after "
                f"cleaning. At least {MIN_TRADING_DAYS} days are required."
            ),
            tickers=valid_tickers,
        )

    # Daily log returns: ln(P_t / P_{t-1})
    returns_data = np.log(price_data / price_data.shift(1)).dropna()

    if returns_data.empty:
        raise DataFetchError(
            message="Could not compute returns — price data has insufficient rows.",
            tickers=valid_tickers,
        )

    # Annualised expected returns and covariance matrix
    expected_returns = returns_data.mean().values * TRADING_DAYS_PER_YEAR
    covariance_matrix = returns_data.cov().values * TRADING_DAYS_PER_YEAR
    covariance_matrix = _ensure_psd(covariance_matrix)

    # Fetch sector metadata
    sector_map, metadata = _fetch_ticker_metadata(valid_tickers)

    market_data = MarketData(
        valid_tickers=valid_tickers,
        price_data=price_data,
        returns_data=returns_data,
        expected_returns=expected_returns,
        covariance_matrix=covariance_matrix,
        sector_map=sector_map,
        fetch_timestamp=datetime.now(UTC),
        metadata=metadata,
    )

    _set_in_cache(cache_key, market_data)

    logger.info(
        "market_data_fetched",
        valid_tickers=valid_tickers,
        num_days=len(price_data),
        num_return_days=len(returns_data),
        dropped_tickers=sorted(dropped),
    )

    return market_data


def _fetch_prices(
    tickers: list[str],
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Fetch adjusted close prices from yfinance with fallback strategy.

    Strategy:
      1. Try yf.download() batch (no custom session — avoids 429 rate limiting).
      2. If batch returns empty, fall back to per-ticker Ticker.history() calls.
    """
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    prices = _download_with_retry(tickers, start_str, end_str)
    if not prices.empty:
        return prices

    logger.warning(
        "yfinance_batch_download_empty_trying_per_ticker_fallback",
        tickers=tickers,
    )
    return _fetch_per_ticker(tickers, start_str, end_str)


def _download_with_retry(
    tickers: list[str],
    start_str: str,
    end_str: str,
    max_attempts: int = 3,
) -> pd.DataFrame:
    """Call yf.download without a custom session to avoid Yahoo 429 rate limits."""
    delay = 5
    last_exc = None

    for attempt in range(1, max_attempts + 1):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                # NOTE: Do NOT pass a custom session here.
                # curl_cffi sessions trigger HTTP 429 (Too Many Requests) from
                # Yahoo Finance. Plain yf.download uses yfinance's built-in
                # cookie/crumb handling which works correctly.
                raw = yf.download(
                    tickers=tickers,
                    start=start_str,
                    end=end_str,
                    auto_adjust=True,
                    progress=False,
                    threads=False,
                )

            if raw is None or raw.empty:
                logger.warning("yfinance_download_empty", attempt=attempt, tickers=tickers)
                return pd.DataFrame()

            prices = _extract_close(raw, tickers)
            if not prices.empty:
                logger.info(
                    "yfinance_download_success",
                    attempt=attempt,
                    tickers=list(prices.columns),
                    rows=len(prices),
                )
                return prices

            return pd.DataFrame()

        except Exception as exc:
            last_exc = exc
            logger.warning(
                "yfinance_download_attempt_failed",
                attempt=attempt,
                error=str(exc),
                tickers=tickers,
            )
            if attempt < max_attempts:
                wait = delay * (2 ** (attempt - 1))
                logger.info("yfinance_retry_wait", seconds=wait)
                time.sleep(wait)

    logger.error("yfinance_download_all_attempts_failed", tickers=tickers, last_error=str(last_exc))
    return pd.DataFrame()


def _fetch_per_ticker(
    tickers: list[str],
    start_str: str,
    end_str: str,
) -> pd.DataFrame:
    """Fetch each ticker individually via Ticker.history() as a fallback."""
    frames: dict[str, Any] = {}

    for ticker in tickers:
        for attempt in range(1, 4):
            try:
                # No custom session — avoids 429 rate limiting
                t = yf.Ticker(ticker)
                hist = t.history(start=start_str, end=end_str, auto_adjust=True)
                if hist is not None and not hist.empty and "Close" in hist.columns:
                    series = hist["Close"].copy()
                    series.name = ticker
                    if not isinstance(series.index, pd.DatetimeIndex):
                        series.index = pd.to_datetime(series.index)
                    if hasattr(series.index, "tz") and series.index.tz is not None:
                        series.index = series.index.tz_localize(None)
                    frames[ticker] = series
                    logger.info("yfinance_per_ticker_success", ticker=ticker, rows=len(series))
                    break
                else:
                    logger.warning("yfinance_per_ticker_empty", ticker=ticker, attempt=attempt)
                    break
            except Exception as exc:
                logger.warning(
                    "yfinance_per_ticker_failed",
                    ticker=ticker,
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt < 3:
                    time.sleep(5 * attempt)

    if not frames:
        return pd.DataFrame()

    df = pd.DataFrame(frames)
    df.index = pd.to_datetime(df.index)
    if hasattr(df.index, "tz") and df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df


def _extract_close(raw: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Extract the Close/Adj Close column from a yfinance download result.

    Handles both:
    - New yfinance (>=0.2.x): MultiIndex columns like ('Close', 'AAPL')
    - Old yfinance: flat columns like 'Close' or 'Adj Close'
    """
    if isinstance(raw.columns, pd.MultiIndex):
        # New yfinance format: MultiIndex with (field, ticker) tuples
        # e.g. [('Close', 'AAPL'), ('Close', 'MSFT'), ('High', 'AAPL'), ...]
        level0_values = raw.columns.get_level_values(0).unique().tolist()

        # Prefer 'Close' (auto_adjust=True renames 'Adj Close' to 'Close')
        price_field = "Close" if "Close" in level0_values else (
            "Adj Close" if "Adj Close" in level0_values else level0_values[0]
        )

        try:
            prices = raw[price_field].copy()
        except KeyError:
            # Fallback: grab first level-0 group
            prices = raw.xs(level0_values[0], axis=1, level=0).copy()

        # Ensure column names are plain strings (ticker symbols)
        prices.columns = [str(c) for c in prices.columns]

        # Keep only requested tickers that are present
        available = [t for t in tickers if t in prices.columns]
        if available:
            prices = prices[available]

    else:
        # Old flat-column format
        if "Close" in raw.columns:
            prices = raw[["Close"]].copy()
        elif "Adj Close" in raw.columns:
            prices = raw[["Adj Close"]].copy()
        else:
            prices = raw.iloc[:, :1].copy()

        # Rename the single column to the ticker symbol
        prices.columns = tickers[:1]

    # Normalise the DatetimeIndex (remove timezone)
    if not isinstance(prices.index, pd.DatetimeIndex):
        prices.index = pd.to_datetime(prices.index)
    if hasattr(prices.index, "tz") and prices.index.tz is not None:
        prices.index = prices.index.tz_localize(None)

    return prices


def _fetch_ticker_metadata(
    tickers: list[str],
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Fetch sector and other metadata for each ticker from yfinance."""
    sector_map: dict[str, str] = {}
    metadata: dict[str, dict[str, Any]] = {}

    for ticker in tickers:
        try:
            # No custom session — avoids 429 rate limiting
            info = yf.Ticker(ticker).info

            sector = info.get("sector") or "Unknown"
            sector_map[ticker] = sector

            metadata[ticker] = {
                "name": info.get("longName") or info.get("shortName") or ticker,
                "sector": sector,
                "industry": info.get("industry") or "Unknown",
                "exchange": info.get("exchange") or "Unknown",
                "currency": info.get("currency") or "USD",
                "market_cap": info.get("marketCap"),
            }
        except Exception as exc:
            logger.warning(
                "ticker_metadata_fetch_failed",
                ticker=ticker,
                error=str(exc),
            )
            sector_map[ticker] = "Unknown"
            metadata[ticker] = {
                "name": ticker,
                "sector": "Unknown",
                "industry": "Unknown",
                "exchange": "Unknown",
                "currency": "USD",
                "market_cap": None,
            }

    return sector_map, metadata


def _ensure_psd(matrix: np.ndarray) -> np.ndarray:
    """Ensure a matrix is positive semi-definite by clipping negative eigenvalues."""
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    eigenvalues = np.maximum(eigenvalues, 0)
    return eigenvectors @ np.diag(eigenvalues) @ eigenvectors.T


def _make_cache_key(tickers: list[str], lookback_days: int) -> str:
    """Generate a deterministic cache key for the given parameters."""
    key_data = json.dumps({"tickers": sorted(tickers), "lookback_days": lookback_days})
    return "market_data:" + hashlib.sha256(key_data.encode()).hexdigest()


def _get_from_cache(cache_key: str) -> MarketData | None:
    """Try to retrieve a MarketData object from Redis cache."""
    try:
        import redis

        settings = get_settings()
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        data = r.get(cache_key)
        if data:
            return pickle.loads(data)  # noqa: S301
    except Exception as exc:
        logger.debug("cache_get_failed", error=str(exc))
    return None


def _set_in_cache(cache_key: str, market_data: MarketData) -> None:
    """Store a MarketData object in Redis cache with TTL."""
    try:
        import redis

        settings = get_settings()
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        ttl = getattr(settings, "CACHE_TTL_SECONDS", 3600)
        r.setex(cache_key, ttl, pickle.dumps(market_data))
        logger.debug("cache_set", cache_key=cache_key[:16], ttl=ttl)
    except Exception as exc:
        logger.debug("cache_set_failed", error=str(exc))


def invalidate_cache(tickers: list[str], lookback_days: int = 365) -> bool:
    """Remove a cached MarketData entry from Redis.

    Args:
        tickers: The ticker list used when the data was originally fetched.
        lookback_days: The lookback_days used when the data was fetched.

    Returns:
        True if the key existed and was deleted, False otherwise.
    """
    cache_key = _make_cache_key(tickers, lookback_days)
    try:
        import redis

        settings = get_settings()
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        result = r.delete(cache_key)
        logger.info("cache_invalidated", cache_key=cache_key[:16], deleted=bool(result))
        return bool(result)
    except Exception as exc:
        logger.warning("cache_invalidate_failed", error=str(exc))
        return False
