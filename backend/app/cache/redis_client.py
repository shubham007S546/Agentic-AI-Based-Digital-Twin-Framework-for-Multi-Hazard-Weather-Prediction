"""
app/cache/redis_client.py
──────────────────────────
Redis connection management using redis-py async client.

Design decisions:
  • Uses redis-py's built-in connection pool — no need for aioredis anymore;
    redis-py >= 4.2 supports full asyncio.
  • hiredis is used as the parser (10-20x faster than the pure-Python parser)
    when installed (it's in our dependencies).
  • A single Redis client instance is created per database index and shared
    across the application via dependency injection.
  • The client is created lazily at first use (not at import time) to avoid
    connection errors during testing when Redis is unavailable.
  • Connection health is verified via ping() before the application enters the
    ready state (readiness probe).

Usage:
    from app.cache.redis_client import get_cache_client

    async def some_service(redis = Depends(get_cache_client)):
        await redis.set("key", "value", ex=300)
        value = await redis.get("key")
"""

from __future__ import annotations

from functools import lru_cache
from typing import AsyncGenerator, Optional

import structlog
from redis.asyncio import Redis, ConnectionPool
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, RedisError, TimeoutError

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

# Module-level pool — shared across all client instances
_pool: Optional[ConnectionPool] = None
_rate_limit_pool: Optional[ConnectionPool] = None


def _build_pool(url: str, max_connections: int, socket_timeout: int) -> ConnectionPool:
    """Build a connection pool with retry and health settings."""
    retry = Retry(ExponentialBackoff(base=0.1, cap=1.0), retries=3)
    return ConnectionPool.from_url(
        url,
        max_connections=max_connections,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_timeout,
        retry=retry,
        retry_on_error=[ConnectionError, TimeoutError],
        decode_responses=True,  # All values are strings unless overridden
        health_check_interval=30,  # Background ping every 30s to keep connections alive
    )


def init_redis_pools() -> None:
    """
    Initialize Redis connection pools.
    Must be called during application startup (lifespan context).
    """
    global _pool, _rate_limit_pool
    settings = get_settings()

    _pool = _build_pool(
        url=settings.redis.cache_url,
        max_connections=settings.redis.max_connections,
        socket_timeout=settings.redis.socket_timeout,
    )

    _rate_limit_pool = _build_pool(
        url=settings.redis.rate_limit_url,
        max_connections=10,  # Rate limiter needs fewer connections
        socket_timeout=settings.redis.socket_timeout,
    )

    logger.info("Redis connection pools initialized", cache_url=settings.redis.cache_url)


async def close_redis_pools() -> None:
    """
    Close all Redis connection pools.
    Called during application shutdown to clean up connections.
    """
    global _pool, _rate_limit_pool
    if _pool:
        await _pool.aclose()
        logger.info("Redis cache pool closed")
    if _rate_limit_pool:
        await _rate_limit_pool.aclose()
        logger.info("Redis rate-limit pool closed")


def get_cache_client() -> Redis:
    """
    Return the Redis client for application caching.

    This is a synchronous factory — the pool is pre-initialized at startup.
    The returned client is not a persistent connection; it's a pool-backed handle.
    """
    if _pool is None:
        raise RuntimeError("Redis pool not initialized. Call init_redis_pools() at startup.")
    return Redis(connection_pool=_pool)


def get_rate_limit_client() -> Redis:
    """Return the Redis client for rate limiting counters (separate DB index)."""
    if _rate_limit_pool is None:
        raise RuntimeError("Redis rate-limit pool not initialized.")
    return Redis(connection_pool=_rate_limit_pool)


async def ping_redis() -> bool:
    """
    Health check: verify Redis connectivity.
    Used by the /health/ready endpoint and MonitoringAgent.
    """
    try:
        client = get_cache_client()
        await client.ping()
        return True
    except (RedisError, RuntimeError) as exc:
        logger.warning("Redis ping failed", error=str(exc))
        return False
