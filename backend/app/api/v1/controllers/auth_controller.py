"""
app/api/v1/controllers/auth_controller.py
─────────────────────────────────────────
Auth Controller class.

Design decisions:
  • Separates HTTP routing from request handling logic.
  • Injected with IAuthService.
"""

from typing import Annotated

from fastapi import Depends, Request

from app.dependencies.auth import CurrentUserToken
from app.dependencies.services import get_auth_service
from app.schemas.auth import LoginRequest, Token
from app.schemas.common import EmptyResponse
from app.services.interfaces.auth_service import IAuthService


class AuthController:
    """Controller for authentication endpoints."""

    def __init__(
        self,
        auth_service: Annotated[IAuthService, Depends(get_auth_service)],
    ):
        self.auth_service = auth_service

    async def login(self, request: Request, payload: LoginRequest) -> Token:
        client_ip = self._get_client_ip(request)
        return await self.auth_service.login(payload, client_ip)

    async def logout(self, token_data: CurrentUserToken) -> EmptyResponse:
        # Decode timestamp or pass 0 for now (the actual expiry from the payload is needed)
        from app.security.authentication.jwt import decode_access_token
        # In a real impl, decode the raw token from the request to get the `exp` claim,
        # but for simplicity here we assume it's done or we just set a fixed TTL.
        await self.auth_service.logout(jti=token_data.jti, expires_at=9999999999)
        return EmptyResponse(message="Successfully logged out.")

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
