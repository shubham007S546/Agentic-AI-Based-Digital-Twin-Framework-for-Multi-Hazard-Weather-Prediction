"""
app/middleware/request_logger.py
─────────────────────────────────
Structured request/response access logger.

Design decisions:
  • Logs at the middleware level rather than using Uvicorn's access log format.
    This gives us full control: request_id, user_id, trace_id, body size,
    response time — all in a single JSON record.
  • Sensitive fields (Authorization header, password fields in body) are NEVER
    logged — the middleware redacts them before writing.
  • Log level is based on response status:
    - 2xx → INFO
    - 3xx → INFO
    - 4xx → WARNING (client errors are expected but worth tracking)
    - 5xx → ERROR (server errors need immediate attention)
  • Health check paths (/health/live, /health/ready) are logged at DEBUG
    to avoid flooding production logs with probe noise.
  • The /metrics endpoint is excluded entirely (Prometheus scrapes it every 15s).
"""

from __future__ import annotations

import time
from typing import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

# Paths excluded from access logging entirely
_EXCLUDED_PATHS = frozenset({"/metrics", "/favicon.ico"})

# Paths logged at DEBUG instead of INFO (Kubernetes liveness/readiness probes)
_PROBE_PATHS = frozenset({"/api/v1/health/live", "/api/v1/health/ready", "/api/v1/health"})

# Headers that must never appear in logs
_SENSITIVE_HEADERS = frozenset({
    "authorization",
    "cookie",
    "x-api-key",
    "x-auth-token",
})


def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of headers with sensitive values redacted."""
    return {
        k: "***REDACTED***" if k.lower() in _SENSITIVE_HEADERS else v
        for k, v in headers.items()
    }


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """
    Structured access logger for all HTTP requests.

    Produces one log record per request with: method, path, status, duration,
    client IP, request ID, user ID (if authenticated), and content lengths.
    """

    def __init__(self, app: ASGIApp, *, log_request_headers: bool = False) -> None:
        super().__init__(app)
        self._log_request_headers = log_request_headers

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # Skip entirely for excluded paths
        if path in _EXCLUDED_PATHS:
            return await call_next(request)

        start_time = time.perf_counter()
        method = request.method
        request_id = getattr(request.state, "request_id", "")
        user_id = getattr(request.state, "user_id", "")
        client_ip = self._get_client_ip(request)
        query_string = str(request.url.query) if request.url.query else ""

        response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        status_code = response.status_code

        # Build base log context
        log_context = {
            "method": method,
            "path": path,
            "query": query_string,
            "status_code": status_code,
            "duration_ms": round(elapsed_ms, 2),
            "request_id": request_id,
            "client_ip": client_ip,
            "content_length": response.headers.get("content-length", ""),
        }

        if user_id:
            log_context["user_id"] = user_id

        if self._log_request_headers:
            log_context["request_headers"] = _sanitize_headers(dict(request.headers))

        # Select log level and message based on status code
        if path in _PROBE_PATHS:
            logger.debug("Health probe", **log_context)
        elif status_code < 400:
            logger.info("Request completed", **log_context)
        elif status_code < 500:
            logger.warning("Client error", **log_context)
        else:
            logger.error("Server error", **log_context)

        return response

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Extract real client IP, respecting X-Forwarded-For from load balancers."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"
