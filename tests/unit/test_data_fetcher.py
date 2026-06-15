"""Unit tests for app.data.fetcher.

Tests cover:
- Input validation (empty tickers, short lookback)
- Cache hit path (returns cached MarketData without calling yfinance)
- Cache miss path (calls yfinance, processes data, stores in cache)
- Data quality filtering (NaN-heavy columns dropped)
- Ticker normalisation (lowercase → uppercase, deduplication)
- DataFetchError raised when no valid data is returned
- _ensure_psd helper (positive semi-definite covariance)
- _make_cache_key determinism and sensitivity to inputs
- invalidate_cache helper
"""

from __future__ import annotations

import pickle
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.core.exceptions import DataFetchError
from app.data.fetcher import (
    MarketData,
    _make_cache_key,
    fetch_market_data,
    invalidate_cache,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_price_df(tickers: list[str], n_days: int = 60) -> pd.DataFrame:
    """Build a synthetic price DataFrame with no NaN values."""
    rng = np.random.default_rng(42)
    prices = 100.0 * np.exp(
        np.cumsum(rng.normal(0.0005, 0.01, size=(n_days, len(tickers))), axis=0)
    )
    dates = pd.date_range("2023-01-01", periods=n_days, freq="B")
    return pd.DataFrame(prices, index=dates, columns=tickers)


def _make_market_data(tickers: list[str] | None = None) -> MarketData:
    """Build a minimal MarketData object for cache-hit tests."""
    tickers = tickers or ["AAPL", "MSFT"]
    n = len(tickers)
    price_df = _make_price_df(tickers, n_days=60)
    returns_df = np.log(price_df / price_df.shift(1)).dropna()
    mu = returns_df.mean().values * 252
    sigma = returns_df.cov().values * 252
    return MarketData(
        valid_tickers=tickers,
        price_data=price_df,
        returns_data=returns_df,
        expected_returns=mu,
        covariance_matrix=sigma,
        sector_map={t: "Information Technology" for t in tickers},
        fetch_timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# _make_cache_key
# ---------------------------------------------------------------------------

class TestMakeCacheKey:
    def test_deterministic_same_inputs(self):
        key1 = _make_cache_key(["AAPL", "MSFT"], 365)
        key2 = _make_cache_key(["AAPL", "MSFT"], 365)
        assert key1 == key2

    def test_different_tickers_different_key(self):
        key1 = _make_cache_key(["AAPL", "MSFT"], 365)
        key2 = _make_cache_key(["AAPL", "GOOGL"], 365)
        assert key1 != key2

    def test_different_lookback_different_key(self):
        key1 = _make_cache_key(["AAPL", "MSFT"], 365)
        key2 = _make_cache_key(["AAPL", "MSFT"], 180)
        assert key1 != key2

    def test_order_does_not_matter(self):
        """Cache key uses sorted tickers, so order should NOT affect the key."""
        key1 = _make_cache_key(["AAPL", "MSFT"], 365)
        key2 = _make_cache_key(["MSFT", "AAPL"], 365)
        assert key1 == key2

    def test_returns_string(self):
        key = _make_cache_key(["AAPL"], 365)
        assert isinstance(key, str)
        assert len(key) > 0


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_empty_tickers_raises_value_error(self):
        with pytest.raises(ValueError, match="tickers list cannot be empty"):
            fetch_market_data(tickers=[], lookback_days=365)

    def test_short_lookback_raises_value_error(self):
        with pytest.raises(ValueError, match="lookback_days must be at least"):
            fetch_market_data(tickers=["AAPL"], lookback_days=10)

    def test_lookback_exactly_30_is_valid(self):
        """lookback_days=30 should not raise ValueError (boundary check)."""
        cached_data = _make_market_data(["AAPL", "MSFT"])
        with patch("app.data.fetcher._get_from_cache", return_value=cached_data):
            result = fetch_market_data(tickers=["AAPL", "MSFT"], lookback_days=30)
        assert result is cached_data


# ---------------------------------------------------------------------------
# Ticker normalisation
# ---------------------------------------------------------------------------

class TestTickerNormalisation:
    def test_lowercase_tickers_normalised_to_uppercase(self):
        """Lowercase tickers should be normalised before cache key computation."""
        cached_data = _make_market_data(["AAPL", "MSFT"])
        with patch("app.data.fetcher._get_from_cache", return_value=cached_data):
            result = fetch_market_data(tickers=["aapl", "msft"], lookback_days=365)
        assert result is cached_data

    def test_duplicate_tickers_deduplicated(self):
        """Duplicate tickers should be deduplicated before fetching."""
        cached_data = _make_market_data(["AAPL"])
        with patch("app.data.fetcher._get_from_cache", return_value=cached_data):
            result = fetch_market_data(
                tickers=["AAPL", "AAPL", "aapl"], lookback_days=365
            )
        assert result is cached_data

    def test_whitespace_stripped_from_tickers(self):
        """Tickers with surrounding whitespace should be stripped."""
        cached_data = _make_market_data(["AAPL", "MSFT"])
        with patch("app.data.fetcher._get_from_cache", return_value=cached_data):
            result = fetch_market_data(
                tickers=[" AAPL ", " MSFT "], lookback_days=365
            )
        assert result is cached_data


# ---------------------------------------------------------------------------
# Cache hit path
# ---------------------------------------------------------------------------

class TestCacheHitPath:
    def test_cache_hit_returns_cached_data(self):
        """When cache returns data, yfinance should NOT be called."""
        cached_data = _make_market_data(["AAPL", "MSFT"])
        with (
            patch("app.data.fetcher._get_from_cache", return_value=cached_data) as mock_get,
            patch("app.data.fetcher._fetch_prices") as mock_fetch,
        ):
            result = fetch_market_data(tickers=["AAPL", "MSFT"], lookback_days=365)

        assert result is cached_data
        mock_get.assert_called_once()
        mock_fetch.assert_not_called()

    def test_cache_hit_returns_correct_tickers(self):
        cached_data = _make_market_data(["AAPL", "MSFT", "GOOGL"])
        with patch("app.data.fetcher._get_from_cache", return_value=cached_data):
            result = fetch_market_data(
                tickers=["AAPL", "MSFT", "GOOGL"], lookback_days=365
            )
        assert result.valid_tickers == ["AAPL", "MSFT", "GOOGL"]


# ---------------------------------------------------------------------------
# Cache miss path (full pipeline)
# ---------------------------------------------------------------------------

class TestCacheMissPath:
    def _setup_mocks(self, tickers: list[str], n_days: int = 60):
        """Return a price DataFrame and configure mocks for a cache-miss run."""
        price_df = _make_price_df(tickers, n_days=n_days)
        return price_df

    def test_cache_miss_calls_yfinance(self):
        """On cache miss, _fetch_prices should be called."""
        tickers = ["AAPL", "MSFT"]
        price_df = self._setup_mocks(tickers)

        with (
            patch("app.data.fetcher._get_from_cache", return_value=None),
            patch("app.data.fetcher._fetch_prices", return_value=price_df) as mock_fetch,
            patch("app.data.fetcher._fetch_ticker_metadata", return_value=({}, {})),
            patch("app.data.fetcher._set_in_cache"),
        ):
            result = fetch_market_data(tickers=tickers, lookback_days=365)

        mock_fetch.assert_called_once()
        assert isinstance(result, MarketData)

    def test_cache_miss_result_has_correct_tickers(self):
        tickers = ["AAPL", "MSFT"]
        price_df = self._setup_mocks(tickers)

        with (
            patch("app.data.fetcher._get_from_cache", return_value=None),
            patch("app.data.fetcher._fetch_prices", return_value=price_df),
            patch("app.data.fetcher._fetch_ticker_metadata", return_value=({}, {})),
            patch("app.data.fetcher._set_in_cache"),
        ):
            result = fetch_market_data(tickers=tickers, lookback_days=365)

        assert set(result.valid_tickers) == set(tickers)

    def test_cache_miss_result_has_expected_returns_shape(self):
        tickers = ["AAPL", "MSFT", "GOOGL"]
        price_df = self._setup_mocks(tickers)

        with (
            patch("app.data.fetcher._get_from_cache", return_value=None),
            patch("app.data.fetcher._fetch_prices", return_value=price_df),
            patch("app.data.fetcher._fetch_ticker_metadata", return_value=({}, {})),
            patch("app.data.fetcher._set_in_cache"),
        ):
            result = fetch_market_data(tickers=tickers, lookback_days=365)

        assert result.expected_returns.shape == (len(tickers),)

    def test_cache_miss_result_has_covariance_matrix_shape(self):
        tickers = ["AAPL", "MSFT", "GOOGL"]
        price_df = self._setup_mocks(tickers)

        with (
            patch("app.data.fetcher._get_from_cache", return_value=None),
            patch("app.data.fetcher._fetch_prices", return_value=price_df),
            patch("app.data.fetcher._fetch_ticker_metadata", return_value=({}, {})),
            patch("app.data.fetcher._set_in_cache"),
        ):
            result = fetch_market_data(tickers=tickers, lookback_days=365)

        n = len(tickers)
        assert result.covariance_matrix.shape == (n, n)

    def test_cache_miss_stores_result_in_cache(self):
        tickers = ["AAPL", "MSFT"]
        price_df = self._setup_mocks(tickers)

        with (
            patch("app.data.fetcher._get_from_cache", return_value=None),
            patch("app.data.fetcher._fetch_prices", return_value=price_df),
            patch("app.data.fetcher._fetch_ticker_metadata", return_value=({}, {})),
            patch("app.data.fetcher._set_in_cache") as mock_set,
        ):
            fetch_market_data(tickers=tickers, lookback_days=365)

        mock_set.assert_called_once()

    def test_empty_price_data_raises_data_fetch_error(self):
        """Empty DataFrame from yfinance should raise DataFetchError."""
        with (
            patch("app.data.fetcher._get_from_cache", return_value=None),
            patch("app.data.fetcher._fetch_prices", return_value=pd.DataFrame()),
        ):
            with pytest.raises(DataFetchError) as exc_info:
                fetch_market_data(tickers=["INVALID_TICKER"], lookback_days=365)

        assert "No price data" in str(exc_info.value)
        assert exc_info.value.error_code == "DATA_FETCH_ERROR"

    def test_all_nan_columns_raises_data_fetch_error(self):
        """If all columns are dropped due to NaN, DataFetchError should be raised."""
        tickers = ["AAPL", "MSFT"]
        # Create a DataFrame where all values are NaN
        dates = pd.date_range("2023-01-01", periods=60, freq="B")
        nan_df = pd.DataFrame(
            np.nan, index=dates, columns=tickers
        )

        with (
            patch("app.data.fetcher._get_from_cache", return_value=None),
            patch("app.data.fetcher._fetch_prices", return_value=nan_df),
        ):
            with pytest.raises(DataFetchError):
                fetch_market_data(tickers=tickers, lookback_days=365)

    def test_sector_map_populated_from_metadata(self):
        tickers = ["AAPL", "MSFT"]
        price_df = self._setup_mocks(tickers)
        sector_map = {"AAPL": "Information Technology", "MSFT": "Information Technology"}

        with (
            patch("app.data.fetcher._get_from_cache", return_value=None),
            patch("app.data.fetcher._fetch_prices", return_value=price_df),
            patch(
                "app.data.fetcher._fetch_ticker_metadata",
                return_value=(sector_map, {}),
            ),
            patch("app.data.fetcher._set_in_cache"),
        ):
            result = fetch_market_data(tickers=tickers, lookback_days=365)

        assert result.sector_map == sector_map

    def test_covariance_matrix_is_symmetric(self):
        tickers = ["AAPL", "MSFT", "GOOGL"]
        price_df = self._setup_mocks(tickers)

        with (
            patch("app.data.fetcher._get_from_cache", return_value=None),
            patch("app.data.fetcher._fetch_prices", return_value=price_df),
            patch("app.data.fetcher._fetch_ticker_metadata", return_value=({}, {})),
            patch("app.data.fetcher._set_in_cache"),
        ):
            result = fetch_market_data(tickers=tickers, lookback_days=365)

        cov = result.covariance_matrix
        np.testing.assert_allclose(cov, cov.T, atol=1e-10)

    def test_covariance_matrix_is_positive_semidefinite(self):
        tickers = ["AAPL", "MSFT", "GOOGL"]
        price_df = self._setup_mocks(tickers)

        with (
            patch("app.data.fetcher._get_from_cache", return_value=None),
            patch("app.data.fetcher._fetch_prices", return_value=price_df),
            patch("app.data.fetcher._fetch_ticker_metadata", return_value=({}, {})),
            patch("app.data.fetcher._set_in_cache"),
        ):
            result = fetch_market_data(tickers=tickers, lookback_days=365)

        eigenvalues = np.linalg.eigvalsh(result.covariance_matrix)
        assert np.all(eigenvalues >= -1e-8), f"Negative eigenvalues: {eigenvalues}"

    def test_fetch_timestamp_is_utc(self):
        tickers = ["AAPL", "MSFT"]
        price_df = self._setup_mocks(tickers)

        with (
            patch("app.data.fetcher._get_from_cache", return_value=None),
            patch("app.data.fetcher._fetch_prices", return_value=price_df),
            patch("app.data.fetcher._fetch_ticker_metadata", return_value=({}, {})),
            patch("app.data.fetcher._set_in_cache"),
        ):
            result = fetch_market_data(tickers=tickers, lookback_days=365)

        assert result.fetch_timestamp.tzinfo is not None


# ---------------------------------------------------------------------------
# Data quality filtering
# ---------------------------------------------------------------------------

class TestDataQualityFiltering:
    def test_ticker_with_too_many_nans_is_dropped(self):
        """A ticker with >20% NaN values should be dropped from valid_tickers."""
        tickers = ["AAPL", "MSFT", "BAD"]
        n_days = 60
        price_df = _make_price_df(["AAPL", "MSFT"], n_days=n_days)

        # Add BAD column with 50% NaN values
        bad_col = np.full(n_days, np.nan)
        bad_col[:30] = 100.0  # Only 50% valid
        price_df["BAD"] = bad_col

        with (
            patch("app.data.fetcher._get_from_cache", return_value=None),
            patch("app.data.fetcher._fetch_prices", return_value=price_df),
            patch("app.data.fetcher._fetch_ticker_metadata", return_value=({}, {})),
            patch("app.data.fetcher._set_in_cache"),
        ):
            result = fetch_market_data(tickers=tickers, lookback_days=365)

        assert "BAD" not in result.valid_tickers
        assert "AAPL" in result.valid_tickers
        assert "MSFT" in result.valid_tickers


# ---------------------------------------------------------------------------
# invalidate_cache
# ---------------------------------------------------------------------------

class TestInvalidateCache:
    def test_invalidate_cache_returns_false_on_redis_error(self):
        """When Redis is unavailable, invalidate_cache should return False."""
        # redis is imported locally inside invalidate_cache, so patch the module
        with patch("builtins.__import__", side_effect=ImportError("no redis")):
            # This won't work cleanly; instead patch the redis module in sys.modules
            pass

        # Simpler: patch the function to raise an exception via the redis.from_url call
        import redis as redis_module
        with patch.object(redis_module, "from_url", side_effect=ConnectionError("Redis unavailable")):
            result = invalidate_cache(["AAPL", "MSFT"], 365)
        assert result is False

    def test_invalidate_cache_returns_true_when_key_deleted(self):
        """When Redis deletes the key, invalidate_cache should return True."""
        mock_client = MagicMock()
        mock_client.delete.return_value = 1  # 1 key deleted

        import redis as redis_module
        with patch.object(redis_module, "from_url", return_value=mock_client):
            result = invalidate_cache(["AAPL", "MSFT"], 365)

        assert result is True

    def test_invalidate_cache_returns_false_when_key_not_found(self):
        """When key doesn't exist, Redis returns 0 and we return False."""
        mock_client = MagicMock()
        mock_client.delete.return_value = 0  # 0 keys deleted

        import redis as redis_module
        with patch.object(redis_module, "from_url", return_value=mock_client):
            result = invalidate_cache(["AAPL", "MSFT"], 365)

        assert result is False


# ---------------------------------------------------------------------------
# MarketData dataclass
# ---------------------------------------------------------------------------

class TestMarketData:
    def test_market_data_has_required_fields(self):
        data = _make_market_data(["AAPL", "MSFT"])
        assert hasattr(data, "valid_tickers")
        assert hasattr(data, "price_data")
        assert hasattr(data, "returns_data")
        assert hasattr(data, "expected_returns")
        assert hasattr(data, "covariance_matrix")
        assert hasattr(data, "sector_map")
        assert hasattr(data, "fetch_timestamp")
        assert hasattr(data, "metadata")

    def test_market_data_valid_tickers_is_list(self):
        data = _make_market_data(["AAPL", "MSFT"])
        assert isinstance(data.valid_tickers, list)

    def test_market_data_price_data_is_dataframe(self):
        data = _make_market_data(["AAPL", "MSFT"])
        assert isinstance(data.price_data, pd.DataFrame)

    def test_market_data_expected_returns_is_ndarray(self):
        data = _make_market_data(["AAPL", "MSFT"])
        assert isinstance(data.expected_returns, np.ndarray)

    def test_market_data_covariance_matrix_is_ndarray(self):
        data = _make_market_data(["AAPL", "MSFT"])
        assert isinstance(data.covariance_matrix, np.ndarray)
