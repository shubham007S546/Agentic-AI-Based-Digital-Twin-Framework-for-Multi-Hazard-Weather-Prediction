"""
app/services/interfaces/auth_service.py
─────────────────────────────────────────
Interface for the Auth service.
"""

from abc import ABC, abstractmethod

from app.schemas.auth import (
    AccessRequestResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RequestAccessCreate,
    ResetPasswordRequest,
    Token,
)


class IAuthService(ABC):
    """Abstract interface for Authentication business logic."""

    @abstractmethod
    async def login(self, request: LoginRequest, client_ip: str) -> Token:
        """Authenticate user and return JWT tokens."""
        pass

    @abstractmethod
    async def refresh_token(self, request: RefreshRequest, client_ip: str) -> Token:
        """Issue new tokens given a valid refresh token (rotates the refresh token)."""
        pass

    @abstractmethod
    async def logout(self, jti: str, expires_at: int) -> None:
        """Invalidate the current access token (and its refresh token, if provided)."""
        pass

    @abstractmethod
    async def get_current_user_profile(self, user_id: str) -> MeResponse:
        """Return the authenticated user's own profile."""
        pass

    @abstractmethod
    async def request_access(self, request: RequestAccessCreate) -> AccessRequestResponse:
        """Submit a platform-access application for admin review."""
        pass

    @abstractmethod
    async def forgot_password(self, request: ForgotPasswordRequest) -> None:
        """Issue a password-reset token and (in production) email it. Always succeeds
        silently even for unknown emails, to avoid leaking which emails are registered."""
        pass

    @abstractmethod
    async def reset_password(self, request: ResetPasswordRequest) -> None:
        """Consume a password-reset token and set a new password."""
        pass