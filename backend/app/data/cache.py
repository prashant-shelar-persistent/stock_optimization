"""Redis cache manager for the data layer.

Provides a reusable, connection-pooled Redis client with typed helpers for
storing and retrieving arbitrary Python objects and plain JSON values.
Designed to be used by the data fetcher and any other module that needs
short-lived caching.

Security hardening (Phase 3)
-----------------------------
**Pickle has been removed entirely.**  The previous implementation used
``pickle.loads()`` / ``pickle.dumps()`` to serialise cached values.  This is
a critical security vulnerability: if Redis is compromised or the key
namespace is shared with an untrusted process, an attacker can inject
arbitrary pickle payloads that execute code when deserialised
(``pickle.loads`` is equivalent to ``eval`` for binary data).

Replacement strategy:
- ``set()`` / ``get()`` now use ``orjson`` for serialisation.  ``orjson``
  handles ``numpy`` arrays, ``pandas`` DataFrames, ``datetime`` objects, and
  standard Python types natively and is significantly faster than ``json``.
- A custom ``_orjson_default`` encoder handles types that ``orjson`` does not
  support natively (e.g. ``numpy.ndarray`` → list, ``pandas.DataFrame`` →
  dict of lists).
- The ``get_typed()`` method validates the deserialised type after loading,
  providing an additional safety layer.
- The ``set_json()`` / ``get_json()`` methods are preserved unchanged for
  callers that already use them.

Key design decisions
--------------------
- **Connection pooling**: A single ``redis.ConnectionPool`` is created per
  process (lazily on first use) and reused across calls.
- **Graceful degradation**: All public functions catch Redis errors and log
  them as warnings rather than raising.  Callers should treat caching as
  best-effort and always have a fallback path.
- **Namespace prefixes**: All keys are prefixed with a configurable namespace
  (default ``"portfolio_optimizer:"``) to avoid collisions with other
  applications sharing the same Redis instance.
- **Serialisation**: ``orjson`` is used for all serialisation.  It is safe to
  deserialise from any source because JSON cannot carry executable code.

Usage::

    from app.data.cache import CacheManager

    cache = CacheManager()

    # Store a Python object (dict, list, numpy array, etc.)
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

import threading
from typing import Any

import orjson
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

# Magic prefix written into every cached value so we can detect and reject
# legacy pickle blobs that may still be present in Redis from before this
# security fix was deployed.
_JSON_PREFIX = b"\x00json\x00"


def _orjson_default(obj: Any) -> Any:
    """Custom encoder for types not natively supported by orjson.

    Called by ``orjson.dumps`` when it encounters an unsupported type.
    Converts the object to a JSON-serialisable form.

    Supported conversions:
    - ``numpy.ndarray``   → nested Python list (preserves shape)
    - ``numpy.integer``   → Python ``int``
    - ``numpy.floating``  → Python ``float``
    - ``pandas.DataFrame``→ dict of column → list of values
    - ``pandas.Series``   → list of values
    - ``set``             → sorted list (deterministic ordering)
    - Any object with ``__dict__`` → its ``__dict__``

    Args:
        obj: The object that orjson could not serialise.

    Returns:
        A JSON-serialisable representation of ``obj``.

    Raises:
        TypeError: If the object cannot be converted.
    """
    # numpy types — imported lazily to avoid hard dependency at module level
    try:
        import numpy as np  # noqa: PLC0415

        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
    except ImportError:
        pass

    # pandas types
    try:
        import pandas as pd  # noqa: PLC0415

        if isinstance(obj, pd.DataFrame):
            # Serialise as {column: [values...]} dict
            return obj.to_dict(orient="list")
        if isinstance(obj, pd.Series):
            return obj.tolist()
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
    except ImportError:
        pass

    # datetime objects (orjson handles these natively, but just in case)
    import datetime  # noqa: PLC0415

    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()

    # sets → sorted list
    if isinstance(obj, (set, frozenset)):
        return sorted(obj, key=str)

    # Fallback: use __dict__ if available
    if hasattr(obj, "__dict__"):
        return obj.__dict__

    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")


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


def _get_client() -> redis.Redis:  # type: ignore[type-arg]
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
    """High-level Redis cache manager with JSON serialisation.

    All keys are automatically prefixed with ``namespace`` to avoid
    collisions with other applications sharing the same Redis instance.

    Serialisation uses ``orjson`` which:
    - Is safe to deserialise from any source (no code execution risk)
    - Handles ``numpy`` arrays, ``pandas`` DataFrames, and ``datetime`` objects
    - Is significantly faster than the standard ``json`` module

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

    # ── Key helpers ───────────────────────────────────────────────────────────

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

    # ── JSON-based primary operations ─────────────────────────────────────────
    # These replace the previous pickle-based set()/get() methods.
    # orjson is used for serialisation: it is safe, fast, and handles numpy/pandas.

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Serialise ``value`` with orjson and store it in Redis.

        Replaces the previous pickle-based implementation.  ``orjson`` is
        safe to deserialise from any source — unlike pickle, JSON cannot
        carry executable code.

        A magic prefix (``_JSON_PREFIX``) is prepended to the stored bytes
        so that :meth:`get` can detect and reject legacy pickle blobs that
        may still be present in Redis from before this security fix.

        Args:
            key: Logical cache key (namespace prefix is added automatically).
            value: Any orjson-serialisable Python object (dicts, lists,
                numpy arrays, pandas DataFrames, datetimes, etc.).
            ttl: Time-to-live in seconds. Uses ``default_ttl`` if not given.

        Returns:
            True if the value was stored successfully, False on error.
        """
        full_key = self._full_key(key)
        resolved_ttl = self._resolve_ttl(ttl)

        try:
            # orjson.dumps returns bytes; prepend magic prefix
            serialised = _JSON_PREFIX + orjson.dumps(
                value,
                default=_orjson_default,
                option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY,
            )
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
        """Retrieve and deserialise a JSON value from Redis.

        Replaces the previous pickle-based implementation.  Detects and
        rejects legacy pickle blobs (identified by the absence of the
        ``_JSON_PREFIX`` magic prefix) to prevent deserialization attacks
        from stale cache entries.

        Args:
            key: Logical cache key (namespace prefix is added automatically).

        Returns:
            The deserialised Python object, or None if the key does not
            exist, the value is a legacy pickle blob, or an error occurs.
        """
        full_key = self._full_key(key)

        try:
            client = _get_client()
            raw = client.get(full_key)

            if raw is None:
                logger.debug("cache_miss", key=key)
                return None

            # Detect and reject legacy pickle blobs.
            # Pickle blobs start with a protocol opcode byte (0x80 for
            # protocol >= 2, or 0x28 '(' for protocol 0).  Our JSON blobs
            # start with _JSON_PREFIX (\x00json\x00).  Any blob that does
            # not start with our prefix is treated as untrusted and discarded.
            if not raw.startswith(_JSON_PREFIX):
                logger.warning(
                    "cache_legacy_blob_rejected",
                    key=key,
                    reason=(
                        "Cached value does not have the expected JSON prefix. "
                        "This may be a legacy pickle blob from before the "
                        "security hardening migration. Discarding."
                    ),
                )
                # Delete the stale entry so it is re-fetched cleanly
                try:
                    client.delete(full_key)
                except Exception:
                    pass
                return None

            json_bytes = raw[len(_JSON_PREFIX):]
            value = orjson.loads(json_bytes)
            logger.debug("cache_hit", key=key)
            return value

        except Exception as exc:
            logger.warning("cache_get_failed", key=key, error=str(exc))
            return None

    def get_typed(self, key: str, expected_type: type) -> Any | None:
        """Retrieve a JSON value and validate its type.

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

    # ── JSON-based operations (legacy API, preserved for compatibility) ────────

    def set_json(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Serialise ``value`` as JSON and store it in Redis.

        Suitable for lightweight, human-readable values (dicts, lists,
        strings, numbers).  This method uses the standard ``json`` module
        (not orjson) to preserve the existing behaviour for callers that
        depend on the exact serialisation format.

        Args:
            key: Logical cache key.
            value: JSON-serialisable Python object.
            ttl: Time-to-live in seconds.

        Returns:
            True if stored successfully, False on error.
        """
        import json  # noqa: PLC0415

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
        import json  # noqa: PLC0415

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
                    deleted_count += client.delete(*keys)
                if cursor == 0:
                    break

            logger.debug(
                "cache_flush_namespace",
                namespace=self._namespace,
                deleted=deleted_count,
            )
            return deleted_count

        except Exception as exc:
            logger.warning("cache_flush_namespace_failed", error=str(exc))
            return 0


# ── Module-level default cache instance ───────────────────────────────────────
# A convenience singleton for callers that do not need a custom namespace.
# Equivalent to ``CacheManager(namespace=DEFAULT_NAMESPACE)``.
#
# Usage::
#
#     from app.data.cache import default_cache
#     default_cache.set("my_key", my_value, ttl=300)
#
default_cache: CacheManager = CacheManager(namespace=DEFAULT_NAMESPACE)
