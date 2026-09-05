"""
app/api/v1/controllers/auth_controller.py
──────────────────────────────────────────
Auth Controller class.

Design decisions:
  • Separates HTTP routing from request handling logic.
  • Injected with IAuthService.
"""

from typing import Annotated

from fastapi import Depends, Request

from app.dependencies.auth import CurrentUserToken, oauth2_scheme
from app.dependencies.services import get_auth_service
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
from app.schemas.common import EmptyResponse
from app.security.authentication.jwt import decode_access_token
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

    async def refresh(self, request: Request, payload: RefreshRequest) -> Token:
        client_ip = self._get_client_ip(request)
        return await self.auth_service.refresh_token(payload, client_ip)

    async def logout(
        self,
        request: Request,
        token_data: CurrentUserToken,
        raw_token: Annotated[str | None, Depends(oauth2_scheme)],
    ) -> EmptyResponse:
        # FIX: previously hardcoded expires_at=9999999999, which meant every
        # blacklist entry lived in Redis forever. Decode the real token to
        # get its actual `exp` claim so the blacklist entry expires exactly
        # when the token itself would have.
        expires_at = 0
        if raw_token:
            payload = decode_access_token(raw_token)
            expires_at = int(payload.get("exp", 0))

        await self.auth_service.logout(user_id=token_data.user_id, jti=token_data.jti, expires_at=expires_at)
        return EmptyResponse(message="Successfully logged out.")

    async def me(self, token_data: CurrentUserToken) -> MeResponse:
        return await self.auth_service.get_current_user_profile(token_data.user_id)

    async def request_access(self, payload: RequestAccessCreate) -> AccessRequestResponse:
        return await self.auth_service.request_access(payload)

    async def forgot_password(self, payload: ForgotPasswordRequest) -> EmptyResponse:
        await self.auth_service.forgot_password(payload)
        # Identical response regardless of whether the email exists — see
        # forgot_password()'s docstring for why.
        return EmptyResponse(message="If that email is registered, a reset link has been sent.")

    async def reset_password(self, payload: ResetPasswordRequest) -> EmptyResponse:
        await self.auth_service.reset_password(payload)
        return EmptyResponse(message="Password has been reset. Please log in again.")

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"