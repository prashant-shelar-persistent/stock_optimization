"""Unit tests for app.data.cache.

Tests cover:
- CacheManager.set / get round-trip (pickle)
- CacheManager.set_json / get_json round-trip
- CacheManager.get_typed: type validation
- CacheManager.delete: key removal
- CacheManager.exists: key existence check
- CacheManager.increment: atomic counter
- CacheManager.ping: health check
- CacheManager.flush_namespace: namespace flush
- CacheManager._full_key: namespace prefix
- CacheManager._resolve_ttl: TTL resolution
- reset_pool: pool reset
- Graceful degradation: all operations return safe defaults on Redis error
"""

from unittest.mock import MagicMock, patch

import pytest

from app.data.cache import CacheManager, DEFAULT_NAMESPACE, reset_pool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cache_manager(namespace: str = "test:", default_ttl: int = 300) -> CacheManager:
    return CacheManager(namespace=namespace, default_ttl=default_ttl)


def _make_mock_redis_client(
    get_return=None,
    set_return=True,
    delete_return=1,
    exists_return=1,
    ping_return=True,
    incrby_return=1,
    scan_return=(0, []),
) -> MagicMock:
    """Build a mock Redis client with configurable return values."""
    client = MagicMock()
    client.get.return_value = get_return
    client.setex.return_value = set_return
    client.delete.return_value = delete_return
    client.exists.return_value = exists_return
    client.ping.return_value = ping_return
    client.incrby.return_value = incrby_return
    client.scan.return_value = scan_return
    return client


# ---------------------------------------------------------------------------
# _full_key
# ---------------------------------------------------------------------------

class TestFullKey:
    def test_namespace_prefix_applied(self):
        cache = _make_cache_manager(namespace="myapp:")
        assert cache._full_key("foo") == "myapp:foo"

    def test_default_namespace(self):
        cache = CacheManager()
        assert cache._full_key("bar") == f"{DEFAULT_NAMESPACE}bar"

    def test_empty_key(self):
        cache = _make_cache_manager(namespace="ns:")
        assert cache._full_key("") == "ns:"


# ---------------------------------------------------------------------------
# _resolve_ttl
# ---------------------------------------------------------------------------

class TestResolveTtl:
    def test_explicit_ttl_takes_priority(self):
        cache = _make_cache_manager(default_ttl=300)
        assert cache._resolve_ttl(600) == 600

    def test_default_ttl_used_when_none(self):
        cache = _make_cache_manager(default_ttl=300)
        assert cache._resolve_ttl(None) == 300

    def test_settings_ttl_used_when_no_default(self):
        """When default_ttl is None, falls back to settings.CACHE_TTL_SECONDS."""
        cache = CacheManager(default_ttl=None)
        # settings.CACHE_TTL_SECONDS defaults to 3600
        ttl = cache._resolve_ttl(None)
        assert ttl > 0


# ---------------------------------------------------------------------------
# set / get (pickle)
# ---------------------------------------------------------------------------

class TestSetGet:
    def test_set_returns_true_on_success(self):
        cache = _make_cache_manager()
        mock_client = _make_mock_redis_client()

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.set("key1", {"data": 42}, ttl=300)

        assert result is True
        mock_client.setex.assert_called_once()

    def test_set_returns_false_on_redis_error(self):
        cache = _make_cache_manager()
        mock_client = MagicMock()
        mock_client.setex.side_effect = ConnectionError("Redis down")

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.set("key1", {"data": 42}, ttl=300)

        assert result is False

    def test_get_returns_none_on_cache_miss(self):
        cache = _make_cache_manager()
        mock_client = _make_mock_redis_client(get_return=None)

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.get("missing_key")

        assert result is None

    def test_get_returns_none_on_redis_error(self):
        cache = _make_cache_manager()
        mock_client = MagicMock()
        mock_client.get.side_effect = ConnectionError("Redis down")

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.get("key1")

        assert result is None

    def test_set_and_get_round_trip(self):
        """set() then get() should return the original value."""
        import pickle

        cache = _make_cache_manager()
        original_value = {"portfolio": [0.4, 0.3, 0.3], "sharpe": 1.5}
        serialised = pickle.dumps(original_value, protocol=pickle.HIGHEST_PROTOCOL)

        mock_client = _make_mock_redis_client(get_return=serialised)

        with patch("app.data.cache._get_client", return_value=mock_client):
            cache.set("key1", original_value, ttl=300)
            result = cache.get("key1")

        assert result == original_value

    def test_set_uses_correct_ttl(self):
        cache = _make_cache_manager(default_ttl=300)
        mock_client = _make_mock_redis_client()

        with patch("app.data.cache._get_client", return_value=mock_client):
            cache.set("key1", "value", ttl=600)

        call_args = mock_client.setex.call_args
        # setex(key, ttl, value)
        assert call_args[0][1] == 600 or call_args.args[1] == 600


# ---------------------------------------------------------------------------
# get_typed
# ---------------------------------------------------------------------------

class TestGetTyped:
    def test_returns_value_when_type_matches(self):
        import pickle

        cache = _make_cache_manager()
        value = {"key": "value"}
        serialised = pickle.dumps(value)
        mock_client = _make_mock_redis_client(get_return=serialised)

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.get_typed("key1", dict)

        assert result == value

    def test_returns_none_when_type_mismatch(self):
        import pickle

        cache = _make_cache_manager()
        value = {"key": "value"}  # dict, not list
        serialised = pickle.dumps(value)
        mock_client = _make_mock_redis_client(get_return=serialised)

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.get_typed("key1", list)

        assert result is None

    def test_returns_none_on_cache_miss(self):
        cache = _make_cache_manager()
        mock_client = _make_mock_redis_client(get_return=None)

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.get_typed("missing", dict)

        assert result is None


# ---------------------------------------------------------------------------
# set_json / get_json
# ---------------------------------------------------------------------------

class TestSetGetJson:
    def test_set_json_returns_true_on_success(self):
        cache = _make_cache_manager()
        mock_client = _make_mock_redis_client()

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.set_json("key1", {"foo": "bar"}, ttl=300)

        assert result is True

    def test_set_json_returns_false_on_error(self):
        cache = _make_cache_manager()
        mock_client = MagicMock()
        mock_client.setex.side_effect = ConnectionError("Redis down")

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.set_json("key1", {"foo": "bar"}, ttl=300)

        assert result is False

    def test_get_json_returns_none_on_miss(self):
        cache = _make_cache_manager()
        mock_client = _make_mock_redis_client(get_return=None)

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.get_json("missing")

        assert result is None

    def test_get_json_round_trip(self):
        import json

        cache = _make_cache_manager()
        original = {"tickers": ["AAPL", "MSFT"], "budget": 100000}
        serialised = json.dumps(original).encode("utf-8")
        mock_client = _make_mock_redis_client(get_return=serialised)

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.get_json("key1")

        assert result == original

    def test_get_json_returns_none_on_redis_error(self):
        cache = _make_cache_manager()
        mock_client = MagicMock()
        mock_client.get.side_effect = ConnectionError("Redis down")

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.get_json("key1")

        assert result is None


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

class TestDelete:
    def test_delete_returns_true_when_key_deleted(self):
        cache = _make_cache_manager()
        mock_client = _make_mock_redis_client(delete_return=1)

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.delete("key1")

        assert result is True

    def test_delete_returns_false_when_key_not_found(self):
        cache = _make_cache_manager()
        mock_client = _make_mock_redis_client(delete_return=0)

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.delete("missing")

        assert result is False

    def test_delete_returns_false_on_redis_error(self):
        cache = _make_cache_manager()
        mock_client = MagicMock()
        mock_client.delete.side_effect = ConnectionError("Redis down")

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.delete("key1")

        assert result is False

    def test_delete_uses_namespaced_key(self):
        cache = _make_cache_manager(namespace="ns:")
        mock_client = _make_mock_redis_client(delete_return=1)

        with patch("app.data.cache._get_client", return_value=mock_client):
            cache.delete("mykey")

        mock_client.delete.assert_called_once_with("ns:mykey")


# ---------------------------------------------------------------------------
# exists
# ---------------------------------------------------------------------------

class TestExists:
    def test_exists_returns_true_when_key_present(self):
        cache = _make_cache_manager()
        mock_client = _make_mock_redis_client(exists_return=1)

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.exists("key1")

        assert result is True

    def test_exists_returns_false_when_key_absent(self):
        cache = _make_cache_manager()
        mock_client = _make_mock_redis_client(exists_return=0)

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.exists("missing")

        assert result is False

    def test_exists_returns_false_on_redis_error(self):
        cache = _make_cache_manager()
        mock_client = MagicMock()
        mock_client.exists.side_effect = ConnectionError("Redis down")

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.exists("key1")

        assert result is False


# ---------------------------------------------------------------------------
# ping
# ---------------------------------------------------------------------------

class TestPing:
    def test_ping_returns_true_when_redis_up(self):
        cache = _make_cache_manager()
        mock_client = _make_mock_redis_client(ping_return=True)

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.ping()

        assert result is True

    def test_ping_returns_false_when_redis_down(self):
        cache = _make_cache_manager()
        mock_client = MagicMock()
        mock_client.ping.side_effect = ConnectionError("Redis down")

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.ping()

        assert result is False


# ---------------------------------------------------------------------------
# increment
# ---------------------------------------------------------------------------

class TestIncrement:
    def test_increment_returns_new_value(self):
        cache = _make_cache_manager()
        mock_client = _make_mock_redis_client(incrby_return=5)

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.increment("counter", amount=1)

        assert result == 5

    def test_increment_with_custom_amount(self):
        cache = _make_cache_manager()
        mock_client = _make_mock_redis_client(incrby_return=10)

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.increment("counter", amount=5)

        mock_client.incrby.assert_called_once_with(
            cache._full_key("counter"), 5
        )
        assert result == 10

    def test_increment_returns_none_on_redis_error(self):
        cache = _make_cache_manager()
        mock_client = MagicMock()
        mock_client.incrby.side_effect = ConnectionError("Redis down")

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.increment("counter")

        assert result is None

    def test_increment_sets_ttl_when_provided(self):
        cache = _make_cache_manager()
        mock_client = _make_mock_redis_client(incrby_return=1)

        with patch("app.data.cache._get_client", return_value=mock_client):
            cache.increment("counter", amount=1, ttl=60)

        mock_client.expire.assert_called_once_with(
            cache._full_key("counter"), 60
        )


# ---------------------------------------------------------------------------
# flush_namespace
# ---------------------------------------------------------------------------

class TestFlushNamespace:
    def test_flush_namespace_returns_zero_when_no_keys(self):
        cache = _make_cache_manager(namespace="empty:")
        mock_client = MagicMock()
        mock_client.scan.return_value = (0, [])

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.flush_namespace()

        assert result == 0

    def test_flush_namespace_returns_count_of_deleted_keys(self):
        cache = _make_cache_manager(namespace="ns:")
        mock_client = MagicMock()
        # First scan returns 2 keys, cursor=0 means done
        mock_client.scan.return_value = (0, [b"ns:key1", b"ns:key2"])
        mock_client.delete.return_value = 2

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.flush_namespace()

        assert result == 2

    def test_flush_namespace_returns_zero_on_redis_error(self):
        cache = _make_cache_manager()
        mock_client = MagicMock()
        mock_client.scan.side_effect = ConnectionError("Redis down")

        with patch("app.data.cache._get_client", return_value=mock_client):
            result = cache.flush_namespace()

        assert result == 0


# ---------------------------------------------------------------------------
# reset_pool
# ---------------------------------------------------------------------------

class TestResetPool:
    def test_reset_pool_does_not_raise(self):
        """reset_pool should not raise even if pool is None."""
        reset_pool()  # Should not raise

    def test_reset_pool_clears_pool(self):
        """After reset_pool, the pool should be None."""
        import app.data.cache as cache_module

        # Force pool creation by calling _get_pool (but mock Redis)
        with patch("redis.ConnectionPool.from_url") as mock_pool:
            mock_pool.return_value = MagicMock()
            from app.data.cache import _get_pool
            _get_pool()

        reset_pool()
        assert cache_module._pool is None


# ---------------------------------------------------------------------------
# __repr__
# ---------------------------------------------------------------------------

class TestRepr:
    def test_repr_contains_namespace(self):
        cache = CacheManager(namespace="myapp:", default_ttl=300)
        repr_str = repr(cache)
        assert "myapp:" in repr_str

    def test_repr_contains_default_ttl(self):
        cache = CacheManager(namespace="myapp:", default_ttl=300)
        repr_str = repr(cache)
        assert "300" in repr_str
