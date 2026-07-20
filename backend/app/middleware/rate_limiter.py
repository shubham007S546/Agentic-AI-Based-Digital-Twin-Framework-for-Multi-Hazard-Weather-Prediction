"""
app/middleware/rate_limiter.py
───────────────────────────────
Sliding window rate limiter using Redis.

Design decisions:
  • Sliding window algorithm (not fixed window) prevents the "burst at boundary"
    attack where a client makes N requests at 00:59 and N more at 01:00, sending
    2N requests in 2 seconds.
  • Implementation: sorted set in Redis where each member is a timestamp.
    ZADD → ZREMRANGEBYSCORE → ZCARD in a Lua script (atomic, single RTT).
  • Rate limit keys are scoped by: IP address (unauthenticated) or user_id
    (authenticated). Authenticated users get higher limits.
  • Endpoint-specific limits override the default (stricter for auth endpoints
    to prevent brute force, looser for read-only weather endpoints).
  • When Redis is unreachable, the middleware FAILS OPEN (passes all requests)
    rather than blocking all users — this is a deliberate availability tradeoff
    for a disaster management system where blocking legitimate users during a
    crisis could have life-safety implications.
  • X-RateLimit-* headers are included for API clients to implement backoff.

Redis Lua script (atomic sliding window):
  1. ZADD key now (add current timestamp as score)
  2. ZREMRANGEBYSCORE key 0 (now - window) (remove old entries)
  3. ZCARD key (count current window entries)
  4. EXPIRE key window (auto-clean if key goes stale)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.constants import RATE_LIMIT_KEY_PREFIX
from app.exceptions.base import RateLimitExceededError

logger = structlog.get_logger(__name__)

# Lua script for atomic sliding window rate limiting
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

-- Remove timestamps outside the window
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- Count current requests in window
local count = redis.call('ZCARD', key)

if count >= limit then
    return {0, count, redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')}
end

-- Add current timestamp
redis.call('ZADD', key, now, now .. ':' .. math.random())
redis.call('EXPIRE', key, window + 1)

return {1, count + 1, {}}
"""


@dataclass
class RateLimitConfig:
    """Configuration for a rate limit rule."""
    requests: int           # Max requests allowed in window
    window_seconds: int     # Sliding window duration in seconds
    key_prefix: str = ""    # Optional prefix to differentiate rule contexts


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiter middleware.

    Configured via RateLimiterMiddleware(..., configs={path_prefix: RateLimitConfig(...)}).
    Falls back to default config when no specific rule matches.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        redis_client,
        default_config: RateLimitConfig,
        path_configs: dict[str, RateLimitConfig] | None = None,
        enabled: bool = True,
    ) -> None:
        super().__init__(app)
        self._redis = redis_client
        self._default_config = default_config
        self._path_configs = path_configs or {}
        self._enabled = enabled
        self._lua_sha: str | None = None

    def _get_config_for_path(self, path: str) -> RateLimitConfig:
        """Find the most specific rate limit config for the given path."""
        for prefix, config in self._path_configs.items():
            if path.startswith(prefix):
                return config
        return self._default_config

    def _get_client_key(self, request: Request) -> str:
        """
        Build the Redis key for rate limiting.
        Authenticated requests use user_id (higher limits).
        Unauthenticated requests use IP address.
        """
        user_id = getattr(getattr(request, "state", None), "user_id", None)
        if user_id:
            identifier = f"user:{user_id}"
        else:
            # Try X-Forwarded-For (behind load balancer) first, then direct IP
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                identifier = f"ip:{forwarded_for.split(',')[0].strip()}"
            else:
                client_host = request.client.host if request.client else "unknown"
                identifier = f"ip:{client_host}"
        return identifier

    async def _load_lua_script(self) -> str:
        """Load the Lua script into Redis and cache the SHA1 hash."""
        if self._lua_sha is None:
            self._lua_sha = await self._redis.script_load(_SLIDING_WINDOW_LUA)
        return self._lua_sha

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip rate limiting if disabled (test environment)
        if not self._enabled:
            return await call_next(request)

        # Skip rate limiting for health checks and metrics (probes must always pass)
        if request.url.path in ("/api/v1/health/live", "/api/v1/health/ready", "/metrics"):
            return await call_next(request)

        config = self._get_config_for_path(request.url.path)
        client_key = self._get_client_key(request)
        redis_key = f"{RATE_LIMIT_KEY_PREFIX}{config.key_prefix}{client_key}:{request.url.path}"

        try:
            sha = await self._load_lua_script()
            now_ms = int(time.time() * 1000)
            window_ms = config.window_seconds * 1000

            result = await self._redis.evalsha(
                sha,
                1,  # number of keys
                redis_key,
                now_ms,
                window_ms,
                config.requests,
            )

            allowed, current_count = result[0], result[1]

            # Set informational headers regardless of allow/deny
            remaining = max(0, config.requests - current_count)
            reset_at = int(time.time()) + config.window_seconds

        except Exception as exc:
            # FAIL OPEN — Redis unavailable should not block users in a disaster system
            logger.warning(
                "Rate limiter Redis error — allowing request",
                error=str(exc),
                path=request.url.path,
            )
            return await call_next(request)

        if not allowed:
            raise RateLimitExceededError(retry_after=config.window_seconds)

        response = await call_next(request)

        # Standard rate limit headers (RFC 6585 / IETF draft)
        response.headers["X-RateLimit-Limit"] = str(config.requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_at)
        response.headers["X-RateLimit-Window"] = f"{config.window_seconds}s"

        return response
