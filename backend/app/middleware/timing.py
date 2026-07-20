"""
app/middleware/timing.py
─────────────────────────
Request timing middleware — measures total request processing time.

Design decisions:
  • Uses time.perf_counter() (high-resolution monotonic clock) rather than
    time.time() for accurate latency measurements unaffected by wall clock changes.
  • Adds X-Process-Time header in milliseconds (ms) — frontend devtools and
    API clients can read this to detect slow endpoints immediately.
  • Observes the Prometheus HTTP_REQUEST_DURATION_SECONDS histogram so Grafana
    can display p50/p95/p99 latency percentiles per endpoint.
  • Uses a coarsened endpoint label (strips UUIDs and IDs from path) to keep
    Prometheus cardinality bounded. e.g., /api/v1/users/uuid-here → /api/v1/users/{id}
"""

from __future__ import annotations

import re
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.monitoring.metrics import HTTP_REQUEST_DURATION_SECONDS, HTTP_REQUESTS_IN_PROGRESS

# Regex patterns for normalizing dynamic path segments
_PATH_ID_PATTERNS = [
    # UUID v4
    (re.compile(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"), "/{id}"),
    # Numeric IDs
    (re.compile(r"/\d+"), "/{id}"),
]


def _normalize_path(path: str) -> str:
    """
    Replace dynamic path segments with placeholders.

    This keeps Prometheus label cardinality bounded — without this,
    every unique UUID or user ID would become a separate time series,
    causing Prometheus OOM.
    """
    for pattern, replacement in _PATH_ID_PATTERNS:
        path = pattern.sub(replacement, path)
    return path


class TimingMiddleware(BaseHTTPMiddleware):
    """
    Measures end-to-end request processing time.

    Order: Should be registered AFTER RequestIDMiddleware but BEFORE logging
    middleware so it captures the full request lifecycle.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        method = request.method
        normalized_path = _normalize_path(request.url.path)

        # Track in-progress gauge for concurrency monitoring
        HTTP_REQUESTS_IN_PROGRESS.labels(method=method, endpoint=normalized_path).inc()

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            # Even on unhandled exceptions, ensure gauge is decremented
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method, endpoint=normalized_path).dec()
            raise

        elapsed_seconds = time.perf_counter() - start_time
        elapsed_ms = elapsed_seconds * 1000

        # Add response header (useful in browser devtools and API testing)
        response.headers["X-Process-Time"] = f"{elapsed_ms:.2f}ms"

        # Record Prometheus histogram observation
        status_code = str(response.status_code)
        HTTP_REQUEST_DURATION_SECONDS.labels(
            method=method,
            endpoint=normalized_path,
            status_code=status_code,
        ).observe(elapsed_seconds)

        HTTP_REQUESTS_IN_PROGRESS.labels(method=method, endpoint=normalized_path).dec()

        return response
