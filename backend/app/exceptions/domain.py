"""
app/exceptions/domain.py
────────────────────────
Domain-specific exceptions for each bounded context.

Every domain exception:
  1. Has a specific ErrorCode so API clients can handle errors programmatically.
  2. Carries relevant context in `details` for debugging.
  3. Maps to the correct HTTP status code.

Import pattern:
    from app.exceptions.domain import AuthenticationError, ModelNotFoundError
    raise AuthenticationError()
"""

from __future__ import annotations

from typing import Any

from app.core.enums import AgentName, ErrorCode
from app.exceptions.base import AppException


class ResourceNotFoundError(AppException):
    """Generic resource not found exception."""

    def __init__(self, message: str = "Resource not found.") -> None:
        super().__init__(
            status_code=404,
            error_code=ErrorCode.USER_NOT_FOUND, # Reusing a 404 error code, or we could add a generic one
            message=message,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Authentication & Authorization
# ══════════════════════════════════════════════════════════════════════════════

class AuthenticationError(AppException):
    """Generic authentication failure — credentials invalid or missing."""

    def __init__(self, message: str = "Authentication failed.") -> None:
        super().__init__(
            status_code=401,
            error_code=ErrorCode.AUTHENTICATION_FAILED,
            message=message,
            headers={"WWW-Authenticate": "Bearer"},
        )


class AuthorizationError(AppException):
    """Insufficient permissions to perform the requested action."""

    def __init__(self, message: str = "Insufficient permissions.") -> None:
        super().__init__(
            status_code=403,
            error_code=ErrorCode.INSUFFICIENT_PERMISSIONS,
            message=message,
        )


class TokenExpiredError(AppException):
    """JWT access token has passed its expiry time."""

    def __init__(self) -> None:
        super().__init__(
            status_code=401,
            error_code=ErrorCode.TOKEN_EXPIRED,
            message="Access token has expired. Please refresh your session.",
            headers={"WWW-Authenticate": "Bearer error='invalid_token'"},
        )


class TokenInvalidError(AppException):
    """JWT token is malformed, has wrong signature, or wrong algorithm."""

    def __init__(self, reason: str | None = None) -> None:
        super().__init__(
            status_code=401,
            error_code=ErrorCode.TOKEN_INVALID,
            message="Token is invalid.",
            details={"reason": reason},
            headers={"WWW-Authenticate": "Bearer error='invalid_token'"},
        )


class TokenBlacklistedError(AppException):
    """JWT token has been revoked (logout or session invalidation)."""

    def __init__(self) -> None:
        super().__init__(
            status_code=401,
            error_code=ErrorCode.TOKEN_BLACKLISTED,
            message="Token has been revoked. Please log in again.",
            headers={"WWW-Authenticate": "Bearer error='invalid_token'"},
        )


class RefreshTokenInvalidError(AppException):
    """Refresh token is invalid, expired, or already rotated."""

    def __init__(self) -> None:
        super().__init__(
            status_code=401,
            error_code=ErrorCode.REFRESH_TOKEN_INVALID,
            message="Refresh token is invalid or has expired.",
        )


class AccountLockedError(AppException):
    """Account has been locked due to too many failed login attempts."""

    def __init__(self, locked_until_minutes: int = 15) -> None:
        super().__init__(
            status_code=403,
            error_code=ErrorCode.ACCOUNT_LOCKED,
            message=f"Account is temporarily locked. Try again in {locked_until_minutes} minutes.",
            details={"locked_for_minutes": locked_until_minutes},
        )


class AccountInactiveError(AppException):
    """Account exists but has been deactivated by an administrator."""

    def __init__(self) -> None:
        super().__init__(
            status_code=403,
            error_code=ErrorCode.ACCOUNT_INACTIVE,
            message="Your account has been deactivated. Contact an administrator.",
        )


class EmailNotVerifiedError(AppException):
    """User has not verified their email address yet."""

    def __init__(self) -> None:
        super().__init__(
            status_code=403,
            error_code=ErrorCode.EMAIL_NOT_VERIFIED,
            message="Please verify your email address before logging in.",
        )


class InvalidCredentialsError(AppException):
    """Email/password combination is incorrect."""

    def __init__(self) -> None:
        # Deliberately vague to prevent user enumeration attacks
        super().__init__(
            status_code=401,
            error_code=ErrorCode.INVALID_CREDENTIALS,
            message="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ══════════════════════════════════════════════════════════════════════════════
#  User Domain
# ══════════════════════════════════════════════════════════════════════════════

class UserNotFoundError(AppException):
    """User does not exist."""

    def __init__(self, identifier: Any = None) -> None:
        msg = "User not found."
        details: dict[str, Any] = {}
        if identifier:
            details["identifier"] = str(identifier)
        super().__init__(
            status_code=404,
            error_code=ErrorCode.USER_NOT_FOUND,
            message=msg,
            details=details,
        )


class DuplicateEmailError(AppException):
    """Email address is already registered."""

    def __init__(self, email: str) -> None:
        super().__init__(
            status_code=409,
            error_code=ErrorCode.USER_ALREADY_EXISTS,
            message="An account with this email address already exists.",
            details={"email": email},
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Prediction & Model Serving
# ══════════════════════════════════════════════════════════════════════════════

class PredictionError(AppException):
    """Generic prediction pipeline failure."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            status_code=500,
            error_code=ErrorCode.PREDICTION_FAILED,
            message=message,
            details=details,
        )


class ModelNotFoundError(AppException):
    """Requested model is not registered in the model registry."""

    def __init__(self, model_name: str, version: str | None = None) -> None:
        ver_str = f" (version={version})" if version else ""
        super().__init__(
            status_code=404,
            error_code=ErrorCode.MODEL_NOT_FOUND,
            message=f"Model '{model_name}{ver_str}' is not registered.",
            details={"model_name": model_name, "version": version},
        )


class ModelLoadError(AppException):
    """Failed to load a model from storage into memory."""

    def __init__(self, model_name: str, reason: str | None = None) -> None:
        super().__init__(
            status_code=500,
            error_code=ErrorCode.MODEL_LOAD_FAILED,
            message=f"Failed to load model '{model_name}'.",
            details={"model_name": model_name, "reason": reason},
        )


class FeatureEngineeringError(AppException):
    """Feature engineering pipeline failed to transform input data."""

    def __init__(self, message: str, feature: str | None = None) -> None:
        super().__init__(
            status_code=422,
            error_code=ErrorCode.FEATURE_ENGINEERING_FAILED,
            message=message,
            details={"feature": feature},
        )


class InferenceTimeoutError(AppException):
    """Model inference did not complete within the allowed time budget."""

    def __init__(self, model_name: str, timeout_seconds: int) -> None:
        super().__init__(
            status_code=504,
            error_code=ErrorCode.INFERENCE_TIMEOUT,
            message=f"Inference timeout for model '{model_name}' after {timeout_seconds}s.",
            details={"model_name": model_name, "timeout_seconds": timeout_seconds},
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Agent Domain
# ══════════════════════════════════════════════════════════════════════════════

class AgentNotFoundError(AppException):
    """Requested agent is not registered in the agent registry."""

    def __init__(self, agent_name: str) -> None:
        super().__init__(
            status_code=404,
            error_code=ErrorCode.AGENT_NOT_FOUND,
            message=f"Agent '{agent_name}' is not registered.",
            details={"agent_name": agent_name},
        )


class AgentExecutionError(AppException):
    """Agent execution failed with an unexpected error."""

    def __init__(self, agent_name: str, reason: str | None = None) -> None:
        super().__init__(
            status_code=500,
            error_code=ErrorCode.AGENT_EXECUTION_FAILED,
            message=f"Agent '{agent_name}' execution failed.",
            details={"agent_name": agent_name, "reason": reason},
        )


class AgentTimeoutError(AppException):
    """Agent did not complete within its configured timeout."""

    def __init__(self, agent_name: str, timeout_seconds: int) -> None:
        super().__init__(
            status_code=504,
            error_code=ErrorCode.AGENT_TIMEOUT,
            message=f"Agent '{agent_name}' timed out after {timeout_seconds}s.",
            details={"agent_name": agent_name, "timeout_seconds": timeout_seconds},
        )


class AgentDisabledError(AppException):
    """Agent is explicitly disabled in configuration or feature flags."""

    def __init__(self, agent_name: str) -> None:
        super().__init__(
            status_code=503,
            error_code=ErrorCode.AGENT_DISABLED,
            message=f"Agent '{agent_name}' is currently disabled.",
            details={"agent_name": agent_name},
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Weather Domain
# ══════════════════════════════════════════════════════════════════════════════

class WeatherSourceUnavailableError(AppException):
    """A weather data source is currently unreachable or returning errors."""

    def __init__(self, source: str, reason: str | None = None) -> None:
        super().__init__(
            status_code=503,
            error_code=ErrorCode.WEATHER_SOURCE_UNAVAILABLE,
            message=f"Weather source '{source}' is unavailable.",
            details={"source": source, "reason": reason},
        )


class WeatherDataInvalidError(AppException):
    """Fetched weather data failed quality/validation checks."""

    def __init__(self, source: str, reason: str | None = None) -> None:
        super().__init__(
            status_code=422,
            error_code=ErrorCode.WEATHER_DATA_INVALID,
            message=f"Weather data from '{source}' is invalid or corrupt.",
            details={"source": source, "reason": reason},
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Digital Twin Domain
# ══════════════════════════════════════════════════════════════════════════════

class SimulationError(AppException):
    """Digital twin simulation failed."""

    def __init__(self, scenario: str | None = None, reason: str | None = None) -> None:
        super().__init__(
            status_code=500,
            error_code=ErrorCode.SIMULATION_FAILED,
            message="Digital twin simulation failed.",
            details={"scenario": scenario, "reason": reason},
        )


class StateSyncError(AppException):
    """Failed to synchronize digital twin state with latest observations."""

    def __init__(self, district: str | None = None, reason: str | None = None) -> None:
        super().__init__(
            status_code=500,
            error_code=ErrorCode.STATE_SYNC_FAILED,
            message="Digital twin state synchronization failed.",
            details={"district": district, "reason": reason},
        )
