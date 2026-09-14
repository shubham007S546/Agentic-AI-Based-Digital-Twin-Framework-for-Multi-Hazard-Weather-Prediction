"""
Result cache -- matches the diagram's "Internal Cache (Redis) / Fast Access
Cache" and "Cache Result ... for faster future access" workflow step.
Falls back to an in-process TTL dict if REDIS_URL isn't set.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)


class _InMemoryTTLCache:
    def __init__(self):
        self._store: Dict[str, tuple] = {}  # key -> (expires_at, value)

    def get(self, key: str) -> Optional[dict]:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: dict, ttl_seconds: int) -> None:
        self._store[key] = (time.time() + ttl_seconds, value)


class _RedisCache:
    def __init__(self, url: str):
        import redis
        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._fallback = _InMemoryTTLCache()

    def get(self, key: str) -> Optional[dict]:
        try:
            raw = self._client.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.debug("Redis read failed (%s); using in-memory cache", exc)
            return self._fallback.get(key)

    def set(self, key: str, value: dict, ttl_seconds: int) -> None:
        try:
            self._client.set(key, json.dumps(value), ex=ttl_seconds)
        except Exception as exc:
            logger.debug("Redis write failed (%s); using in-memory cache", exc)
            self._fallback.set(key, value, ttl_seconds)


class WeatherCache:
    def __init__(self):
        if settings.has_redis:
            try:
                self._store = _RedisCache(settings.redis_url)
                logger.info("WeatherCache using Redis at %s", settings.redis_url)
            except Exception as exc:
                logger.warning("Redis unavailable (%s); falling back to in-process cache.", exc)
                self._store = _InMemoryTTLCache()
        else:
            self._store = _InMemoryTTLCache()
            logger.info("WeatherCache using in-process store (set REDIS_URL for shared/persistent cache).")

    @staticmethod
    def make_key(location: str, latitude: Optional[float], longitude: Optional[float], forecast_hours: int) -> str:
        return f"weather:{location.lower()}:{latitude}:{longitude}:{forecast_hours}"

    def get(self, key: str) -> Optional[dict]:
        return self._store.get(key)

    def set(self, key: str, value: dict) -> None:
        self._store.set(key, value, settings.cache_ttl_seconds)


weather_cache = WeatherCache()
