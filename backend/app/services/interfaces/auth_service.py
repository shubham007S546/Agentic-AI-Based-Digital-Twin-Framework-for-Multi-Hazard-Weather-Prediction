"""
app/services/interfaces/auth_service.py
───────────────────────────────────────
Interface for the Auth service.
"""

from abc import ABC, abstractmethod

from app.schemas.auth import LoginRequest, RefreshRequest, Token


class IAuthService(ABC):
    """Abstract interface for Authentication business logic."""

    @abstractmethod
    async def login(self, request: LoginRequest, client_ip: str) -> Token:
        """Authenticate user and return JWT tokens."""
        pass

    @abstractmethod
    async def refresh_token(self, request: RefreshRequest, client_ip: str) -> Token:
        """Issue new tokens given a valid refresh token."""
        pass

    @abstractmethod
    async def logout(self, jti: str, expires_at: int) -> None:
        """Invalidate the current access token."""
        pass
