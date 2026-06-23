"""Security tests for rate limiting and cache deserialization safety.

Tests the following security controls:

1. **Rate limiting module** — ``app.core.rate_limit``
   - Limiter factory returns a valid Limiter instance.
   - Client IP extraction from ``X-Forwarded-For`` header.
   - Client IP fallback to direct connection IP.
   - Rate limit constants are defined and non-empty.

2. **Cache deserialization safety** — ``app.data.cache``
   - ``CacheManager.get()`` rejects legacy pickle blobs (no JSON prefix).
   - ``CacheManager.get()`` accepts valid JSON blobs with the correct prefix.
   - ``CacheManager.set()`` writes the JSON prefix.
   - ``CacheManager.get_typed()`` validates the type of the cached value.

3. **Fetcher cache safety** — ``app.data.fetcher``
   - ``_get_from_cache`` rejects blobs without the ``_FETCHER_JSON_PREFIX``.
   - ``_set_in_cache`` writes the ``_FETCHER_JSON_PREFIX``.
   - Round-trip serialisation of ``MarketData`` preserves all fields.

These tests do NOT require a running Redis instance — they use mocks
for the Redis client.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# ── Rate limit module tests ───────────────────────────────────────────────────

class TestRateLimitModule:
    """Tests for ``app.core.rate_limit``."""

    def test_rate_limit_constants_defined(self) -> None:
        """All rate limit constants are defined and non-empty strings."""
        from app.core.rate_limit import (  # noqa: PLC0415
            RATE_LIMIT_CHAT,
            RATE_LIMIT_CHAT_CREATE,
            RATE_LIMIT_READ,
            RATE_LIMIT_WRITE,
        )

        for name, value in [
            ("RATE_LIMIT_READ", RATE_LIMIT_READ),
            ("RATE_LIMIT_WRITE", RATE_LIMIT_WRITE),
            ("RATE_LIMIT_CHAT", RATE_LIMIT_CHAT),
            ("RATE_LIMIT_CHAT_CREATE", RATE_LIMIT_CHAT_CREATE),
        ]:
            assert isinstance(value, str), f"{name} should be a string"
            assert len(value) > 0, f"{name} should not be empty"
            # Should follow the "N/period" format
            assert "/" in value, f"{name} should contain '/' (e.g. '60/minute')"

    def test_rate_limit_format_valid(self) -> None:
        """Rate limit strings follow the 'N/period' format."""
        from app.core.rate_limit import (  # noqa: PLC0415
            RATE_LIMIT_CHAT,
            RATE_LIMIT_CHAT_CREATE,
            RATE_LIMIT_READ,
            RATE_LIMIT_WRITE,
        )

        valid_periods = {"second", "minute", "hour", "day"}
        for limit_str in [RATE_LIMIT_READ, RATE_LIMIT_WRITE, RATE_LIMIT_CHAT, RATE_LIMIT_CHAT_CREATE]:
            parts = limit_str.split("/")
            assert len(parts) == 2, f"'{limit_str}' should be 'N/period'"
            count_str, period = parts
            assert count_str.isdigit(), f"'{count_str}' should be a number"
            assert int(count_str) > 0, f"Rate limit count should be positive"
            assert period in valid_periods, f"'{period}' is not a valid period"

    def test_write_limit_more_restrictive_than_read(self) -> None:
        """Write endpoints have a lower rate limit than read endpoints."""
        from app.core.rate_limit import RATE_LIMIT_READ, RATE_LIMIT_WRITE  # noqa: PLC0415

        read_count = int(RATE_LIMIT_READ.split("/")[0])
        write_count = int(RATE_LIMIT_WRITE.split("/")[0])
        assert write_count <= read_count, (
            f"Write limit ({RATE_LIMIT_WRITE}) should be <= read limit ({RATE_LIMIT_READ})"
        )

    def test_get_client_ip_from_forwarded_for(self) -> None:
        """_get_client_ip extracts the first IP from X-Forwarded-For."""
        from app.core.rate_limit import _get_client_ip  # noqa: PLC0415

        mock_request = MagicMock()
        mock_request.headers = {"X-Forwarded-For": "1.2.3.4, 5.6.7.8, 9.10.11.12"}
        mock_request.client = None

        ip = _get_client_ip(mock_request)
        assert ip == "1.2.3.4"

    def test_get_client_ip_strips_whitespace(self) -> None:
        """_get_client_ip strips whitespace from the extracted IP."""
        from app.core.rate_limit import _get_client_ip  # noqa: PLC0415

        mock_request = MagicMock()
        mock_request.headers = {"X-Forwarded-For": "  1.2.3.4  , 5.6.7.8"}
        mock_request.client = None

        ip = _get_client_ip(mock_request)
        assert ip == "1.2.3.4"

    def test_get_client_ip_fallback_to_direct_connection(self) -> None:
        """_get_client_ip falls back to request.client.host when no X-Forwarded-For."""
        from app.core.rate_limit import _get_client_ip  # noqa: PLC0415

        mock_request = MagicMock()
        mock_request.headers = {}  # No X-Forwarded-For
        mock_request.client.host = "192.168.1.100"

        ip = _get_client_ip(mock_request)
        assert ip == "192.168.1.100"

    def test_get_client_ip_unknown_when_no_client(self) -> None:
        """_get_client_ip returns 'unknown' when no client info is available."""
        from app.core.rate_limit import _get_client_ip  # noqa: PLC0415

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client = None

        ip = _get_client_ip(mock_request)
        assert ip == "unknown"

    def test_limiter_singleton_is_importable(self) -> None:
        """The module-level ``limiter`` singleton is importable."""
        from app.core.rate_limit import limiter  # noqa: PLC0415

        assert limiter is not None

    def test_limiter_has_limit_method(self) -> None:
        """The limiter has a ``limit`` method (used as a decorator)."""
        from app.core.rate_limit import limiter  # noqa: PLC0415

        assert hasattr(limiter, "limit")
        assert callable(limiter.limit)


# ── Cache deserialization safety tests ────────────────────────────────────────

class TestCacheDeserializationSafety:
    """Tests that ``CacheManager`` rejects legacy pickle blobs.

    These tests mock the Redis client to inject controlled byte payloads
    and verify that the cache manager handles them safely.
    """

    def _make_cache_manager(self) -> Any:
        """Create a CacheManager instance for testing."""
        from app.data.cache import CacheManager  # noqa: PLC0415

        return CacheManager(namespace="test:")

    def test_json_prefix_constant_defined(self) -> None:
        """The JSON prefix constant is defined and starts with a null byte."""
        from app.data.cache import _JSON_PREFIX  # noqa: PLC0415

        assert isinstance(_JSON_PREFIX, bytes)
        assert len(_JSON_PREFIX) > 0
        # Should start with a null byte to distinguish from pickle
        assert _JSON_PREFIX[0:1] == b"\x00"

    def test_set_writes_json_prefix(self) -> None:
        """CacheManager.set() prepends the JSON prefix to stored bytes."""
        from app.data.cache import CacheManager, _JSON_PREFIX  # noqa: PLC0415

        cache = CacheManager(namespace="test:")
        stored_value: bytes | None = None

        def mock_setex(key: str, ttl: int, value: bytes) -> None:
            nonlocal stored_value
            stored_value = value

        mock_client = MagicMock()
        mock_client.setex.side_effect = mock_setex

        with patch("app.data.cache._get_client", return_value=mock_client):
            cache.set("test_key", {"hello": "world"}, ttl=60)

        assert stored_value is not None
        assert stored_value.startswith(_JSON_PREFIX), (
            "Stored bytes should start with the JSON prefix"
        )

    def test_get_accepts_valid_json_blob(self) -> None:
        """CacheManager.get() correctly deserialises a valid JSON blob."""
        import orjson  # noqa: PLC0415

        from app.data.cache import CacheManager, _JSON_PREFIX  # noqa: PLC0415

        cache = CacheManager(namespace="test:")
        test_data = {"ticker": "AAPL", "price": 150.0, "count": 42}
        valid_blob = _JSON_PREFIX + orjson.dumps(test_data)

        mock_client = MagicMock()
        mock_client.get.return_value = valid_blob

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.get("test_key")

        assert result == test_data

    def test_get_rejects_pickle_blob(self) -> None:
        """CacheManager.get() returns None for a legacy pickle blob.

        A pickle blob starts with 0x80 (protocol >= 2) which is NOT the
        JSON prefix.  The cache manager should detect this and return None
        rather than calling pickle.loads().
        """
        import pickle  # noqa: PLC0415

        from app.data.cache import CacheManager  # noqa: PLC0415

        cache = CacheManager(namespace="test:")
        # Create a real pickle blob
        pickle_blob = pickle.dumps({"malicious": "payload"}, protocol=2)
        assert pickle_blob[0:1] == b"\x80", "Pickle protocol 2 starts with 0x80"

        mock_client = MagicMock()
        mock_client.get.return_value = pickle_blob
        mock_client.delete.return_value = 1

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.get("test_key")

        # Should return None (not deserialise the pickle blob)
        assert result is None
        # Should have attempted to delete the stale entry
        mock_client.delete.assert_called_once()

    def test_get_rejects_arbitrary_bytes(self) -> None:
        """CacheManager.get() returns None for arbitrary bytes without JSON prefix."""
        from app.data.cache import CacheManager  # noqa: PLC0415

        cache = CacheManager(namespace="test:")
        arbitrary_bytes = b"\xff\xfe\xfd\xfc" + b"some arbitrary data"

        mock_client = MagicMock()
        mock_client.get.return_value = arbitrary_bytes
        mock_client.delete.return_value = 1

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.get("test_key")

        assert result is None

    def test_get_returns_none_for_missing_key(self) -> None:
        """CacheManager.get() returns None when the key does not exist."""
        from app.data.cache import CacheManager  # noqa: PLC0415

        cache = CacheManager(namespace="test:")
        mock_client = MagicMock()
        mock_client.get.return_value = None

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.get("nonexistent_key")

        assert result is None

    def test_get_typed_validates_type(self) -> None:
        """CacheManager.get_typed() returns None if type does not match."""
        import orjson  # noqa: PLC0415

        from app.data.cache import CacheManager, _JSON_PREFIX  # noqa: PLC0415

        cache = CacheManager(namespace="test:")
        # Store a dict but expect a list
        test_data = {"key": "value"}
        valid_blob = _JSON_PREFIX + orjson.dumps(test_data)

        mock_client = MagicMock()
        mock_client.get.return_value = valid_blob

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.get_typed("test_key", expected_type=list)

        assert result is None  # Type mismatch → None

    def test_get_typed_returns_value_on_type_match(self) -> None:
        """CacheManager.get_typed() returns the value if type matches."""
        import orjson  # noqa: PLC0415

        from app.data.cache import CacheManager, _JSON_PREFIX  # noqa: PLC0415

        cache = CacheManager(namespace="test:")
        test_data = {"key": "value"}
        valid_blob = _JSON_PREFIX + orjson.dumps(test_data)

        mock_client = MagicMock()
        mock_client.get.return_value = valid_blob

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.get_typed("test_key", expected_type=dict)

        assert result == test_data

    def test_set_get_roundtrip_dict(self) -> None:
        """CacheManager set/get round-trip preserves a dict value."""
        from app.data.cache import CacheManager  # noqa: PLC0415

        cache = CacheManager(namespace="test:")
        stored: dict[str, bytes] = {}

        def mock_setex(key: str, ttl: int, value: bytes) -> None:
            stored[key] = value

        def mock_get(key: str) -> bytes | None:
            return stored.get(key)

        mock_client = MagicMock()
        mock_client.setex.side_effect = mock_setex
        mock_client.get.side_effect = mock_get

        test_data = {"tickers": ["AAPL", "MSFT"], "budget": 100000.0, "count": 3}

        with patch("app.data.cache._get_client", return_value=mock_client):
            cache.set("roundtrip_key", test_data, ttl=60)
            result = cache.get("roundtrip_key")

        assert result == test_data

    def test_set_get_roundtrip_list(self) -> None:
        """CacheManager set/get round-trip preserves a list value."""
        from app.data.cache import CacheManager  # noqa: PLC0415

        cache = CacheManager(namespace="test:")
        stored: dict[str, bytes] = {}

        def mock_setex(key: str, ttl: int, value: bytes) -> None:
            stored[key] = value

        def mock_get(key: str) -> bytes | None:
            return stored.get(key)

        mock_client = MagicMock()
        mock_client.setex.side_effect = mock_setex
        mock_client.get.side_effect = mock_get

        test_data = [1, 2, 3, "hello", None, True]

        with patch("app.data.cache._get_client", return_value=mock_client):
            cache.set("list_key", test_data, ttl=60)
            result = cache.get("list_key")

        assert result == test_data


# ── Fetcher cache safety tests ────────────────────────────────────────────────

class TestFetcherCacheSafety:
    """Tests for the JSON-based cache in ``app.data.fetcher``."""

    def _make_market_data(self) -> Any:
        """Create a minimal MarketData object for testing."""
        from app.data.fetcher import MarketData  # noqa: PLC0415

        tickers = ["AAPL", "MSFT"]
        n = 10
        dates = pd.date_range("2024-01-01", periods=n)

        price_data = pd.DataFrame(
            np.random.default_rng(42).uniform(100, 200, (n, 2)),
            index=dates,
            columns=tickers,
        )
        returns_data = pd.DataFrame(
            np.random.default_rng(42).normal(0, 0.01, (n - 1, 2)),
            index=dates[1:],
            columns=tickers,
        )

        return MarketData(
            valid_tickers=tickers,
            price_data=price_data,
            returns_data=returns_data,
            expected_returns=np.array([0.12, 0.10]),
            covariance_matrix=np.array([[0.04, 0.01], [0.01, 0.03]]),
            sector_map={"AAPL": "Technology", "MSFT": "Technology"},
            fetch_timestamp=datetime.now(UTC),
            metadata={"AAPL": {"name": "Apple Inc."}, "MSFT": {"name": "Microsoft"}},
        )

    def test_fetcher_json_prefix_defined(self) -> None:
        """The fetcher JSON prefix constant is defined."""
        from app.data.fetcher import _FETCHER_JSON_PREFIX  # noqa: PLC0415

        assert isinstance(_FETCHER_JSON_PREFIX, bytes)
        assert len(_FETCHER_JSON_PREFIX) > 0
        assert _FETCHER_JSON_PREFIX[0:1] == b"\x00"

    def test_set_in_cache_writes_prefix(self) -> None:
        """_set_in_cache prepends the JSON prefix to stored bytes."""
        from app.data.fetcher import _FETCHER_JSON_PREFIX, _set_in_cache  # noqa: PLC0415

        market_data = self._make_market_data()
        stored_value: bytes | None = None

        def mock_setex(key: str, ttl: int, value: bytes) -> None:
            nonlocal stored_value
            stored_value = value

        mock_redis = MagicMock()
        mock_redis.setex.side_effect = mock_setex

        with patch("app.data.fetcher.redis") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis
            _set_in_cache("test_cache_key", market_data)

        assert stored_value is not None
        assert stored_value.startswith(_FETCHER_JSON_PREFIX), (
            "Stored bytes should start with the fetcher JSON prefix"
        )

    def test_get_from_cache_rejects_pickle_blob(self) -> None:
        """_get_from_cache returns None for a legacy pickle blob."""
        import pickle  # noqa: PLC0415

        from app.data.fetcher import _get_from_cache  # noqa: PLC0415

        market_data = self._make_market_data()
        pickle_blob = pickle.dumps(market_data, protocol=2)

        mock_redis = MagicMock()
        mock_redis.get.return_value = pickle_blob
        mock_redis.delete.return_value = 1

        with patch("app.data.fetcher.redis") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis
            result = _get_from_cache("test_cache_key")

        # Should return None (not deserialise the pickle blob)
        assert result is None
        # Should have attempted to delete the stale entry
        mock_redis.delete.assert_called_once()

    def test_get_from_cache_rejects_arbitrary_bytes(self) -> None:
        """_get_from_cache returns None for arbitrary bytes without prefix."""
        from app.data.fetcher import _get_from_cache  # noqa: PLC0415

        arbitrary_bytes = b"\xff\xfe\xfd" + b"some data"

        mock_redis = MagicMock()
        mock_redis.get.return_value = arbitrary_bytes
        mock_redis.delete.return_value = 1

        with patch("app.data.fetcher.redis") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis
            result = _get_from_cache("test_cache_key")

        assert result is None

    def test_market_data_roundtrip(self) -> None:
        """MarketData can be serialised and deserialised without data loss."""
        from app.data.fetcher import (  # noqa: PLC0415
            _dict_to_market_data,
            _market_data_to_dict,
        )

        original = self._make_market_data()
        serialised = _market_data_to_dict(original)
        restored = _dict_to_market_data(serialised)

        # Check tickers
        assert restored.valid_tickers == original.valid_tickers

        # Check numpy arrays (within floating point tolerance)
        np.testing.assert_allclose(
            restored.expected_returns,
            original.expected_returns,
            rtol=1e-10,
        )
        np.testing.assert_allclose(
            restored.covariance_matrix,
            original.covariance_matrix,
            rtol=1e-10,
        )

        # Check DataFrames
        pd.testing.assert_frame_equal(
            restored.price_data,
            original.price_data,
            check_exact=False,
            rtol=1e-10,
        )
        pd.testing.assert_frame_equal(
            restored.returns_data,
            original.returns_data,
            check_exact=False,
            rtol=1e-10,
        )

        # Check metadata
        assert restored.sector_map == original.sector_map
        assert restored.metadata == original.metadata

    def test_market_data_to_dict_structure(self) -> None:
        """_market_data_to_dict produces the expected dict structure."""
        from app.data.fetcher import _market_data_to_dict  # noqa: PLC0415

        market_data = self._make_market_data()
        d = _market_data_to_dict(market_data)

        assert "valid_tickers" in d
        assert "price_data" in d
        assert "returns_data" in d
        assert "expected_returns" in d
        assert "covariance_matrix" in d
        assert "sector_map" in d
        assert "fetch_timestamp" in d
        assert "metadata" in d

        # price_data should have index, columns, data
        assert "index" in d["price_data"]
        assert "columns" in d["price_data"]
        assert "data" in d["price_data"]

        # expected_returns should be a list (not numpy array)
        assert isinstance(d["expected_returns"], list)

        # covariance_matrix should be a list of lists
        assert isinstance(d["covariance_matrix"], list)
        assert isinstance(d["covariance_matrix"][0], list)

    def test_full_cache_roundtrip_via_redis_mock(self) -> None:
        """Full set/get round-trip through mocked Redis preserves MarketData."""
        from app.data.fetcher import _get_from_cache, _set_in_cache  # noqa: PLC0415

        original = self._make_market_data()
        stored: dict[str, bytes] = {}

        def mock_setex(key: str, ttl: int, value: bytes) -> None:
            stored[key] = value

        def mock_get(key: str) -> bytes | None:
            return stored.get(key)

        mock_redis = MagicMock()
        mock_redis.setex.side_effect = mock_setex
        mock_redis.get.side_effect = mock_get

        with patch("app.data.fetcher.redis") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis
            _set_in_cache("roundtrip_key", original)
            restored = _get_from_cache("roundtrip_key")

        assert restored is not None
        assert restored.valid_tickers == original.valid_tickers
        np.testing.assert_allclose(
            restored.expected_returns,
            original.expected_returns,
            rtol=1e-10,
        )


# ── No pickle imports in security-critical modules ────────────────────────────

class TestNoPickleInCacheModules:
    """Verify that pickle is not imported in cache-related modules."""

    def test_cache_py_does_not_import_pickle(self) -> None:
        """app.data.cache does not import pickle."""
        import ast  # noqa: PLC0415
        import pathlib  # noqa: PLC0415

        cache_path = pathlib.Path(__file__).parent.parent / "backend" / "app" / "data" / "cache.py"
        if not cache_path.exists():
            # Try relative path
            cache_path = pathlib.Path(__file__).parent.parent / "app" / "data" / "cache.py"

        if cache_path.exists():
            source = cache_path.read_text()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        names = [alias.name for alias in node.names]
                    else:
                        names = [node.module or ""]
                    assert "pickle" not in names, (
                        "app.data.cache should not import pickle (security risk)"
                    )

    def test_fetcher_py_does_not_import_pickle(self) -> None:
        """app.data.fetcher does not import pickle."""
        import ast  # noqa: PLC0415
        import pathlib  # noqa: PLC0415

        fetcher_path = pathlib.Path(__file__).parent.parent / "backend" / "app" / "data" / "fetcher.py"
        if not fetcher_path.exists():
            fetcher_path = pathlib.Path(__file__).parent.parent / "app" / "data" / "fetcher.py"

        if fetcher_path.exists():
            source = fetcher_path.read_text()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        names = [alias.name for alias in node.names]
                    else:
                        names = [node.module or ""]
                    assert "pickle" not in names, (
                        "app.data.fetcher should not import pickle (security risk)"
                    )
