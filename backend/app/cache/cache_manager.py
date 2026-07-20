"""
app/cache/cache_manager.py
───────────────────────────
High-level caching abstraction over Redis.

Design decisions:
  • CacheManager wraps the raw Redis client with domain-aware methods:
    typed get/set with automatic JSON serialization, namespace prefixes,
    cache-aside pattern (get_or_set), and bulk operations.
  • All cache keys are namespaced: "{namespace}:{key}" to avoid collisions
    between different features (weather vs predictions vs user profiles).
  • TTLs are taken from constants.py — no magic numbers in service code.
  • Pydantic models are serialized via .model_dump_json() for correctness
    and deserialized via model.model_validate_json().
  • Cache decorators (cached, cache_invalidate) are provided for use on
    service methods.
  • Failures are logged but never propagated — cache is an optimization,
    not a correctness requirement. Services must work without it.

Usage:
    cache = CacheManager(redis_client, namespace="weather")
    await cache.set("current:mandi", weather_data, ttl=300)
    data = await cache.get("current:mandi")
    # Or:
    data = await cache.get_or_set("current:mandi", fetch_fn, ttl=300)
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional, Type, TypeVar

import structlog
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.monitoring.metrics import CACHE_HITS_TOTAL, CACHE_MISSES_TOTAL

logger = structlog.get_logger(__name__)

T = TypeVar("T")
PydanticT = TypeVar("PydanticT", bound=BaseModel)


class CacheManager:
    """
    Domain-aware Redis cache manager.

    Provides type-safe get/set/delete with automatic serialization,
    namespace isolation, and Prometheus metrics for hit/miss rates.
    """

    def __init__(self, redis: Redis, *, namespace: str) -> None:
        self._redis = redis
        self._namespace = namespace

    def _key(self, key: str) -> str:
        """Produce namespaced key: '{namespace}:{key}'."""
        return f"{self._namespace}:{key}"

    # ── Primitive operations ──────────────────────────────────────────────────

    async def get(self, key: str) -> Optional[Any]:
        """Get a JSON-deserialized value. Returns None on miss or error."""
        full_key = self._key(key)
        try:
            raw = await self._redis.get(full_key)
            if raw is None:
                CACHE_MISSES_TOTAL.labels(cache_key_prefix=self._namespace).inc()
                return None
            CACHE_HITS_TOTAL.labels(cache_key_prefix=self._namespace).inc()
            return json.loads(raw)
        except (RedisError, json.JSONDecodeError) as exc:
            logger.warning("Cache get failed", key=full_key, error=str(exc))
            return None

    async def set(self, key: str, value: Any, *, ttl: int) -> bool:
        """Serialize value to JSON and store with TTL. Returns True on success."""
        full_key = self._key(key)
        try:
            if isinstance(value, BaseModel):
                serialized = value.model_dump_json()
            else:
                serialized = json.dumps(value, default=str)
            await self._redis.setex(full_key, ttl, serialized)
            return True
        except (RedisError, TypeError) as exc:
            logger.warning("Cache set failed", key=full_key, error=str(exc))
            return False

    async def delete(self, key: str) -> bool:
        """Delete a cache entry. Returns True if the key existed."""
        full_key = self._key(key)
        try:
            deleted = await self._redis.delete(full_key)
            return deleted > 0
        except RedisError as exc:
            logger.warning("Cache delete failed", key=full_key, error=str(exc))
            return False

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        try:
            return bool(await self._redis.exists(self._key(key)))
        except RedisError:
            return False

    async def ttl(self, key: str) -> int:
        """Return remaining TTL in seconds. -2 if missing, -1 if no expiry."""
        try:
            return await self._redis.ttl(self._key(key))
        except RedisError:
            return -2

    # ── Pydantic model support ────────────────────────────────────────────────

    async def get_model(self, key: str, model_class: Type[PydanticT]) -> Optional[PydanticT]:
        """
        Retrieve and deserialize a Pydantic model from cache.

        Args:
            key:         Cache key (namespace will be prepended).
            model_class: The Pydantic model class to deserialize into.

        Returns:
            Deserialized model or None if not cached.
        """
        full_key = self._key(key)
        try:
            raw = await self._redis.get(full_key)
            if raw is None:
                CACHE_MISSES_TOTAL.labels(cache_key_prefix=self._namespace).inc()
                return None
            CACHE_HITS_TOTAL.labels(cache_key_prefix=self._namespace).inc()
            return model_class.model_validate_json(raw)
        except (RedisError, Exception) as exc:
            logger.warning("Cache get_model failed", key=full_key, error=str(exc))
            return None

    # ── Cache-aside pattern ───────────────────────────────────────────────────

    async def get_or_set(
        self,
        key: str,
        fetch_fn: Callable,
        *,
        ttl: int,
    ) -> Any:
        """
        Cache-aside (lazy loading) pattern.

        Returns cached value if it exists; otherwise calls fetch_fn(),
        caches the result, and returns it.

        Args:
            key:      Cache key.
            fetch_fn: Async callable that produces the value on cache miss.
            ttl:      Cache TTL in seconds.
        """
        cached = await self.get(key)
        if cached is not None:
            return cached

        # Cache miss — call the source of truth
        value = await fetch_fn()
        if value is not None:
            await self.set(key, value, ttl=ttl)
        return value

    # ── Bulk operations ───────────────────────────────────────────────────────

    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a glob pattern within the namespace.

        WARNING: Uses SCAN (not KEYS) to avoid blocking Redis.
        Use sparingly — patterns that match many keys are expensive.

        Returns: count of deleted keys.
        """
        full_pattern = self._key(pattern)
        deleted = 0
        try:
            async for key in self._redis.scan_iter(match=full_pattern, count=100):
                await self._redis.delete(key)
                deleted += 1
        except RedisError as exc:
            logger.warning("Cache delete_pattern failed", pattern=full_pattern, error=str(exc))
        return deleted

    async def increment(self, key: str, amount: int = 1, *, ttl: Optional[int] = None) -> int:
        """Atomic increment. Useful for counters. Returns new value."""
        full_key = self._key(key)
        try:
            result = await self._redis.incrby(full_key, amount)
            if ttl and result == amount:  # Only set expiry on first increment
                await self._redis.expire(full_key, ttl)
            return result
        except RedisError as exc:
            logger.warning("Cache increment failed", key=full_key, error=str(exc))
            return 0
