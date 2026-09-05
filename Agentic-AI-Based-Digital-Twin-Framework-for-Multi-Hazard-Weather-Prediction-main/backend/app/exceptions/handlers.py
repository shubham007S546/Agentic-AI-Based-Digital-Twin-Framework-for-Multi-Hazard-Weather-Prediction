"""
app/exceptions/handlers.py
──────────────────────────
Global FastAPI exception handlers.

Design decisions:
  • All handlers return a CONSISTENT JSON envelope:
    {
      "success": false,
      "error": {
        "code": "AUTH_001",
        "message": "...",
        "details": {...}
      },
      "request_id": "...",
      "timestamp": "..."
    }
  • This consistency allows the Next.js frontend to handle ALL errors with a
    single error interceptor in React Query / Axios.
  • Pydantic validation errors are transformed to match this envelope instead of
    FastAPI's default nested format.
  • Unhandled exceptions are caught, logged with full traceback, and returned
    as a safe 500 without leaking implementation details.
  • Request IDs are extracted from the request state (set by RequestIDMiddleware)
    and included in every error response for log correlation.
"""

from __future__ import annotations

import traceback
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.enums import ErrorCode
from app.exceptions.base import AppException

logger = structlog.get_logger(__name__)


# ── Response builder ──────────────────────────────────────────────────────────

def _error_response(
    request: Request,
    *,
    status_code: int,
    error_code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> ORJSONResponse:
    """Build the standardized error response envelope."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    body: dict[str, Any] = {
        "success": False,
        "error": {
            "code": error_code,
            "message": message,
            "details": details or {},
        },
        "request_id": request_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    return ORJSONResponse(
        status_code=status_code,
        content=body,
        headers=headers,
    )


# ── Handler: AppException (all domain errors) ─────────────────────────────────

async def app_exception_handler(request: Request, exc: AppException) -> ORJSONResponse:
    """
    Handles all intentional application errors raised by service and repo layers.
    These are expected errors — we log at WARNING level, not ERROR.
    """
    logger.warning(
        "Application exception",
        error_code=exc.error_code,
        message=exc.message,
        status_code=exc.status_code,
        path=request.url.path,
        method=request.method,
        request_id=getattr(request.state, "request_id", None),
    )
    return _error_response(
        request,
        status_code=exc.status_code,
        error_code=exc.error_code,
        message=exc.message,
        details=exc.details,
        headers=exc.headers or None,
    )


# ── Handler: Starlette HTTPException (404, 405, etc.) ─────────────────────────

async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> ORJSONResponse:
    """
    Converts Starlette's raw HTTPException into our structured envelope.
    Raised by FastAPI's routing layer (e.g., 404 for unknown routes).
    """
    error_code_map = {
        400: ErrorCode.VALIDATION_ERROR,
        401: ErrorCode.AUTHENTICATION_FAILED,
        403: ErrorCode.INSUFFICIENT_PERMISSIONS,
        404: ErrorCode.NOT_FOUND,
        405: ErrorCode.VALIDATION_ERROR,
        429: ErrorCode.RATE_LIMIT_EXCEEDED,
        500: ErrorCode.INTERNAL_ERROR,
        503: ErrorCode.SERVICE_UNAVAILABLE,
    }
    error_code = error_code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    logger.info(
        "HTTP exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
    )
    return _error_response(
        request,
        status_code=exc.status_code,
        error_code=error_code,
        message=str(exc.detail),
        headers=dict(exc.headers) if exc.headers else None,
    )


# ── Handler: Pydantic RequestValidationError ──────────────────────────────────

async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> ORJSONResponse:
    """
    Transforms FastAPI's verbose Pydantic validation error format into our
    consistent error envelope.

    Produces a list of field-level errors in `details.fields` so the frontend
    can highlight specific form inputs.
    """
    field_errors: list[dict[str, Any]] = []
    for error in exc.errors():
        # `loc` is a tuple like ('body', 'email') — join to "body.email"
        field_path = ".".join(str(loc) for loc in error["loc"])
        field_errors.append(
            {
                "field": field_path,
                "message": error["msg"],
                "type": error["type"],
                "input": error.get("input"),
            }
        )

    logger.info(
        "Validation error",
        path=request.url.path,
        field_count=len(field_errors),
    )
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error_code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed. Check the 'fields' array for details.",
        details={"fields": field_errors},
    )


# ── Handler: Unhandled Python exceptions ──────────────────────────────────────

async def unhandled_exception_handler(request: Request, exc: Exception) -> ORJSONResponse:
    """
    Catch-all for any exception not caught by other handlers.

    These are genuine bugs — logged at ERROR with full traceback, but the
    response never reveals the traceback to the client (security).
    """
    tb = traceback.format_exc()
    logger.error(
        "Unhandled exception",
        exc_type=type(exc).__name__,
        exc_message=str(exc),
        traceback=tb,
        path=request.url.path,
        method=request.method,
        request_id=getattr(request.state, "request_id", None),
    )
    return _error_response(
        request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code=ErrorCode.INTERNAL_ERROR,
        message="An internal server error occurred. Our team has been notified.",
    )


# ── Registration helper ───────────────────────────────────────────────────────

def register_exception_handlers(app: Any) -> None:
    """
    Attach all exception handlers to the FastAPI application.

    Call this in the application factory (main.py) after creating the app.
    Handler registration ORDER matters — FastAPI checks handlers in registration
    order for matching exception types.
    """
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    # Must be last — catches everything else
    app.add_exception_handler(Exception, unhandled_exception_handler)
