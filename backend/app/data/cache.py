"""Redis cache manager for the data layer.

Provides a reusable, connection-pooled Redis client with typed helpers for
storing and retrieving arbitrary Python objects (via pickle) and plain JSON
values. Designed to be used by the data fetcher and any other module that
needs short-lived caching.

Key design decisions
--------------------
- **Connection pooling**: A single ``redis.ConnectionPool`` is created per
  process (lazily on first use) and reused across calls. This avoids the
  overhead of creating a new TCP connection on every cache operation.
- **Graceful degradation**: All public functions catch Redis errors and log
  them as warnings rather than raising. Callers should treat caching as
  best-effort and always have a fallback path.
- **Namespace prefixes**: All keys are prefixed with a configurable namespace
  (default ``"portfolio_optimizer:"``) to avoid collisions with other
  applications sharing the same Redis instance.
- **Serialisation**: Arbitrary Python objects are serialised with ``pickle``
  (highest protocol). JSON helpers are provided for lightweight string/dict
  values that need to be human-readable in Redis.

Usage::

    from app.data.cache import CacheManager

    cache = CacheManager()

    # Store a Python object
    cache.set("my_key", {"foo": "bar"}, ttl=300)

    # Retrieve it
    value = cache.get("my_key")  # returns {"foo": "bar"} or None

    # Delete it
    cache.delete("my_key")

    # Check existence
    if cache.exists("my_key"):
        ...

    # Flush all keys in the namespace (useful in tests)
    cache.flush_namespace()
"""

import json
import pickle
import threading
from typing import Any

import redis
import redis.connection

from app.core.config import get_settings
from app.core.logging import get_logger


logger = get_logger(__name__)

# Module-level lock to protect pool initialisation in multi-threaded contexts
_pool_lock = threading.Lock()
_pool: redis.ConnectionPool | None = None

# Default namespace prefix applied to all keys
DEFAULT_NAMESPACE = "portfolio_optimizer:"


def _get_pool() -> redis.ConnectionPool:
    """Return the module-level connection pool, creating it on first call.

    Thread-safe: uses a lock to prevent double-initialisation.

    Returns:
        A ``redis.ConnectionPool`` configured from application settings.
    """
    global _pool  # noqa: PLW0603

    if _pool is not None:
        return _pool

    with _pool_lock:
        # Double-checked locking
        if _pool is not None:
            return _pool

        settings = get_settings()
        _pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=20,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=False,  # We handle bytes ourselves
        )
        logger.debug("redis_pool_created", url=settings.REDIS_URL)

    return _pool


def _get_client() -> redis.Redis:
    """Return a Redis client that uses the shared connection pool.

    Returns:
        A ``redis.Redis`` instance backed by the shared pool.
    """
    return redis.Redis(connection_pool=_get_pool())


def reset_pool() -> "None":
    """Disconnect and reset the module-level connection pool.

    Intended for use in tests or when the Redis URL changes at runtime.
    After calling this, the next cache operation will create a new pool.
    """
    global _pool  # noqa: PLW0603

    with _pool_lock:
        if _pool is not None:
            try:
                _pool.disconnect()
            except Exception:
                pass
            _pool = None
            logger.debug("redis_pool_reset")


class CacheManager:
    """High-level Redis cache manager with pickle and JSON serialisation.

    All keys are automatically prefixed with ``namespace`` to avoid
    collisions with other applications sharing the same Redis instance.

    Args:
        namespace: Key prefix applied to all operations. Defaults to
            ``"portfolio_optimizer:"``.
        default_ttl: Default TTL in seconds used when ``ttl`` is not
            explicitly passed to :meth:`set`. Defaults to the value of
            ``settings.CACHE_TTL_SECONDS``.

    Example::

        cache = CacheManager(namespace="my_app:")
        cache.set("result:abc123", result_object, ttl=600)
        obj = cache.get("result:abc123")
    """

    def __init__(
        self,
        namespace: str = DEFAULT_NAMESPACE,
        default_ttl: int | None = None,
    ) -> None:
        self._namespace = namespace
        self._default_ttl = default_ttl

    # ── Key helpers ──────────────────────────────────────────────────────────

    def _full_key(self, key: str) -> str:
        """Return the namespaced Redis key.

        Args:
            key: Logical key (without namespace prefix).

        Returns:
            Full Redis key with namespace prefix.
        """
        return f"{self._namespace}{key}"

    def _resolve_ttl(self, ttl: int | None) -> int:
        """Resolve TTL, falling back to default_ttl or settings value.

        Args:
            ttl: Explicit TTL in seconds, or None to use the default.

        Returns:
            TTL in seconds (always a positive integer).
        """
        if ttl is not None:
            return ttl
        if self._default_ttl is not None:
            return self._default_ttl
        return get_settings().CACHE_TTL_SECONDS

    # ── Pickle-based operations ───────────────────────────────────────────────

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Serialise ``value`` with pickle and store it in Redis.

        Args:
            key: Logical cache key (namespace prefix is added automatically).
            value: Any picklable Python object.
            ttl: Time-to-live in seconds. Uses ``default_ttl`` if not given.

        Returns:
            True if the value was stored successfully, False on error.
        """
        full_key = self._full_key(key)
        resolved_ttl = self._resolve_ttl(ttl)

        try:
            serialised = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
            client = _get_client()
            client.setex(full_key, resolved_ttl, serialised)
            logger.debug(
                "cache_set",
                key=key,
                ttl=resolved_ttl,
                size_bytes=len(serialised),
            )
            return True

        except Exception as exc:
            logger.warning("cache_set_failed", key=key, error=str(exc))
            return False

    def get(self, key: str) -> Any | None:
        """Retrieve and deserialise a pickled value from Redis.

        Args:
            key: Logical cache key (namespace prefix is added automatically).

        Returns:
            The deserialised Python object, or None if the key does not
            exist or an error occurs.
        """
        full_key = self._full_key(key)

        try:
            client = _get_client()
            raw = client.get(full_key)

            if raw is None:
                logger.debug("cache_miss", key=key)
                return None

            value = pickle.loads(raw)
            logger.debug("cache_hit", key=key)
            return value

        except Exception as exc:
            logger.warning("cache_get_failed", key=key, error=str(exc))
            return None

    def get_typed(self, key: str, expected_type: type) -> Any | None:
        """Retrieve a pickled value and validate its type.

        Like :meth:`get` but returns None (and logs a warning) if the
        deserialised value is not an instance of ``expected_type``.

        Args:
            key: Logical cache key.
            expected_type: Expected Python type of the cached value.

        Returns:
            The deserialised value if it matches ``expected_type``, else None.
        """
        value = self.get(key)
        if value is None:
            return None
        if not isinstance(value, expected_type):
            logger.warning(
                "cache_type_mismatch",
                key=key,
                expected=expected_type.__name__,
                actual=type(value).__name__,
            )
            return None
        return value

    # ── JSON-based operations ─────────────────────────────────────────────────

    def set_json(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Serialise ``value`` as JSON and store it in Redis.

        Suitable for lightweight, human-readable values (dicts, lists,
        strings, numbers). For complex Python objects use :meth:`set`.

        Args:
            key: Logical cache key.
            value: JSON-serialisable Python object.
            ttl: Time-to-live in seconds.

        Returns:
            True if stored successfully, False on error.
        """
        full_key = self._full_key(key)
        resolved_ttl = self._resolve_ttl(ttl)

        try:
            serialised = json.dumps(value, default=str).encode("utf-8")
            client = _get_client()
            client.setex(full_key, resolved_ttl, serialised)
            logger.debug(
                "cache_set_json",
                key=key,
                ttl=resolved_ttl,
                size_bytes=len(serialised),
            )
            return True

        except Exception as exc:
            logger.warning("cache_set_json_failed", key=key, error=str(exc))
            return False

    def get_json(self, key: str) -> Any | None:
        """Retrieve and JSON-deserialise a value from Redis.

        Args:
            key: Logical cache key.

        Returns:
            The deserialised Python object, or None if not found or on error.
        """
        full_key = self._full_key(key)

        try:
            client = _get_client()
            raw = client.get(full_key)

            if raw is None:
                logger.debug("cache_miss_json", key=key)
                return None

            value = json.loads(raw.decode("utf-8"))
            logger.debug("cache_hit_json", key=key)
            return value

        except Exception as exc:
            logger.warning("cache_get_json_failed", key=key, error=str(exc))
            return None

    # ── Existence / deletion ──────────────────────────────────────────────────

    def exists(self, key: str) -> bool:
        """Check whether a key exists in Redis.

        Args:
            key: Logical cache key.

        Returns:
            True if the key exists, False if it does not or on error.
        """
        full_key = self._full_key(key)

        try:
            client = _get_client()
            return bool(client.exists(full_key))

        except Exception as exc:
            logger.warning("cache_exists_failed", key=key, error=str(exc))
            return False

    def delete(self, key: str) -> bool:
        """Delete a key from Redis.

        Args:
            key: Logical cache key.

        Returns:
            True if the key was deleted (it existed), False otherwise or on error.
        """
        full_key = self._full_key(key)

        try:
            client = _get_client()
            deleted = client.delete(full_key)
            logger.debug("cache_delete", key=key, deleted=bool(deleted))
            return bool(deleted)

        except Exception as exc:
            logger.warning("cache_delete_failed", key=key, error=str(exc))
            return False

    def delete_many(self, keys: list[str]) -> int:
        """Delete multiple keys from Redis in a single pipeline call.

        Args:
            keys: List of logical cache keys to delete.

        Returns:
            Number of keys that were actually deleted (existed before deletion).
            Returns 0 on error.
        """
        if not keys:
            return 0

        full_keys = [self._full_key(k) for k in keys]

        try:
            client = _get_client()
            deleted = client.delete(*full_keys)
            logger.debug("cache_delete_many", count=len(keys), deleted=deleted)
            return int(deleted)

        except Exception as exc:
            logger.warning("cache_delete_many_failed", error=str(exc))
            return 0

    def ttl(self, key: str) -> int | None:
        """Return the remaining TTL of a key in seconds.

        Args:
            key: Logical cache key.

        Returns:
            Remaining TTL in seconds, -1 if the key has no expiry,
            -2 if the key does not exist, or None on error.
        """
        full_key = self._full_key(key)

        try:
            client = _get_client()
            return int(client.ttl(full_key))

        except Exception as exc:
            logger.warning("cache_ttl_failed", key=key, error=str(exc))
            return None

    def flush_namespace(self) -> int:
        """Delete all keys that belong to this manager's namespace.

        Uses Redis ``SCAN`` to avoid blocking the server with a ``KEYS``
        command on large databases.

        Returns:
            Number of keys deleted. Returns 0 on error.
        """
        pattern = f"{self._namespace}*"
        deleted_count = 0

        try:
            client = _get_client()
            cursor = 0

            while True:
                cursor, keys = client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    client.delete(*keys)
                    deleted_count += len(keys)
                if cursor == 0:
                    break

            logger.info(
                "cache_namespace_flushed",
                namespace=self._namespace,
                deleted=deleted_count,
            )
            return deleted_count

        except Exception as exc:
            logger.warning("cache_flush_namespace_failed", error=str(exc))
            return 0

    # ── Health check ──────────────────────────────────────────────────────────

    def ping(self) -> bool:
        """Check whether Redis is reachable.

        Returns:
            True if Redis responds to PING, False otherwise.
        """
        try:
            client = _get_client()
            return bool(client.ping())

        except Exception as exc:
            logger.warning("cache_ping_failed", error=str(exc))
            return False

    # ── Atomic increment / decrement ──────────────────────────────────────────

    def increment(self, key: str, amount: int = 1, ttl: int | None = None) -> int | None:
        """Atomically increment an integer counter stored at ``key``.

        If the key does not exist it is initialised to 0 before incrementing.
        Optionally sets a TTL on the key (only applied if the key is newly
        created or if ``ttl`` is explicitly provided).

        Args:
            key: Logical cache key.
            amount: Amount to increment by (default 1).
            ttl: Optional TTL to set on the key after incrementing.

        Returns:
            New integer value after increment, or None on error.
        """
        full_key = self._full_key(key)

        try:
            client = _get_client()
            new_value = client.incrby(full_key, amount)
            if ttl is not None:
                client.expire(full_key, ttl)
            return int(new_value)

        except Exception as exc:
            logger.warning("cache_increment_failed", key=key, error=str(exc))
            return None

    # ── Dunder helpers ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"CacheManager(namespace={self._namespace!r}, "
            f"default_ttl={self._default_ttl!r})"
        )


# ── Module-level singleton ────────────────────────────────────────────────────

# A default CacheManager instance for convenience. Modules can import this
# directly or create their own instance with a custom namespace.
default_cache = CacheManager()
