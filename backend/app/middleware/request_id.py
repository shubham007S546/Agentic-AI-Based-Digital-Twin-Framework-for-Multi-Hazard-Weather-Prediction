"""
app/middleware/request_id.py
────────────────────────────
Request ID middleware — injects a unique UUID into every request.

Design decisions:
  • Each request gets an X-Request-ID header (checked first — if the client
    provides one, we reuse it; otherwise we generate one). This supports
    client-generated correlation IDs from Next.js.
  • The ID is stored in request.state.request_id so it's accessible to
    exception handlers, response loggers, and all downstream code.
  • The ID is echoed in the response header so the frontend can log it and
    users can provide it when reporting issues (support correlation).
  • Injected into structlog context so every log line during the request
    lifecycle carries the ID automatically.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.constants import REQUEST_ID_HEADER
from app.logging.structured_logger import set_log_context


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that assigns a unique request ID to every incoming request.

    Order: Should be the FIRST middleware registered so that all subsequent
    middleware and handlers have access to request.state.request_id.
    """

    def __init__(self, app: ASGIApp, header_name: str = REQUEST_ID_HEADER) -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Honor client-provided ID (e.g., from Next.js frontend) or generate new
        request_id = request.headers.get(self.header_name) or str(uuid.uuid4())

        # Store on request state — accessible everywhere via request.state
        request.state.request_id = request_id

        # Inject into structlog context for automatic log correlation
        set_log_context(request_id=request_id)

        response = await call_next(request)

        # Echo the ID in the response header
        response.headers[self.header_name] = request_id

        return response
