"""
app/exceptions/base.py
──────────────────────
Base exception hierarchy for the entire application.

Design decisions:
  • Every exception carries a structured error_code (from ErrorCode enum) so
    the API always returns machine-parseable error identifiers — not just messages.
  • AppException is the single base that all domain exceptions extend.
  • details dict allows attaching arbitrary structured context (e.g., field name
    for validation errors, district for prediction errors) without subclassing.
  • This file has zero application imports to avoid circular dependency risks.
"""

from __future__ import annotations

from typing import Any

from app.core.enums import ErrorCode


class AppException(Exception):
    """
    Base exception for all application-level errors.

    Every exception in the system must inherit from this.
    The global exception handler (middleware) catches AppException
    and maps it to a structured JSON API response.
    """

    def __init__(
        self,
        *,
        status_code: int = 500,
        error_code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        message: str = "An unexpected error occurred.",
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        self.headers = headers or {}
        super().__init__(message)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"status_code={self.status_code}, "
            f"error_code={self.error_code}, "
            f"message={self.message!r})"
        )


class NotFoundError(AppException):
    """Resource does not exist in the system."""

    def __init__(
        self,
        resource: str,
        identifier: Any = None,
        error_code: ErrorCode = ErrorCode.NOT_FOUND,
    ) -> None:
        detail_msg = f"{resource} not found"
        if identifier is not None:
            detail_msg = f"{resource} with id '{identifier}' not found"
        super().__init__(
            status_code=404,
            error_code=error_code,
            message=detail_msg,
            details={"resource": resource, "identifier": str(identifier) if identifier else None},
        )


class ConflictError(AppException):
    """Resource already exists or state conflict."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            status_code=409,
            error_code=ErrorCode.USER_ALREADY_EXISTS,
            message=message,
            details=details,
        )


class ValidationError(AppException):
    """Input validation failure — not a Pydantic error, but a business-rule violation."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            status_code=422,
            error_code=ErrorCode.VALIDATION_ERROR,
            message=message,
            details=details,
        )


class PermissionDeniedError(AppException):
    """Authenticated user lacks the required permission."""

    def __init__(self, required_permission: str | None = None) -> None:
        details = {}
        if required_permission:
            details["required_permission"] = required_permission
        super().__init__(
            status_code=403,
            error_code=ErrorCode.INSUFFICIENT_PERMISSIONS,
            message="You do not have permission to perform this action.",
            details=details,
        )


class ServiceUnavailableError(AppException):
    """Downstream service or infrastructure is unavailable."""

    def __init__(self, service: str, reason: str | None = None) -> None:
        super().__init__(
            status_code=503,
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            message=f"Service '{service}' is currently unavailable.",
            details={"service": service, "reason": reason},
        )


class ExternalAPIError(AppException):
    """Error communicating with an external API (weather source, etc.)."""

    def __init__(
        self,
        service: str,
        status_code: int = 502,
        reason: str | None = None,
    ) -> None:
        super().__init__(
            status_code=status_code,
            error_code=ErrorCode.EXTERNAL_API_ERROR,
            message=f"External API error from '{service}'.",
            details={"service": service, "reason": reason},
        )


class TimeoutError(AppException):
    """Operation timed out."""

    def __init__(self, operation: str, timeout_seconds: int | None = None) -> None:
        super().__init__(
            status_code=504,
            error_code=ErrorCode.INFERENCE_TIMEOUT,
            message=f"Operation '{operation}' timed out.",
            details={"operation": operation, "timeout_seconds": timeout_seconds},
        )


class DatabaseError(AppException):
    """Unrecoverable database error (not a 404 or conflict)."""

    def __init__(self, message: str = "A database error occurred.", details: dict[str, Any] | None = None) -> None:
        super().__init__(
            status_code=500,
            error_code=ErrorCode.DATABASE_ERROR,
            message=message,
            details=details,
        )


class RateLimitExceededError(AppException):
    """Client has exceeded the rate limit for this endpoint."""

    def __init__(self, retry_after: int = 60) -> None:
        super().__init__(
            status_code=429,
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            message="Rate limit exceeded. Please slow down.",
            details={"retry_after_seconds": retry_after},
            headers={"Retry-After": str(retry_after)},
        )
