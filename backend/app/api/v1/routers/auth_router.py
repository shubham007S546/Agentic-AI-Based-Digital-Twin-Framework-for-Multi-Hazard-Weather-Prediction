"""
app/api/v1/routers/auth_router.py
──────────────────────────────────
Authentication routing definitions.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.v1.controllers.auth_controller import AuthController
from app.dependencies.auth import CurrentUserToken
from app.schemas.auth import LoginRequest, Token
from app.schemas.common import ApiResponse, EmptyResponse

router = APIRouter()


@router.post(
    "/login",
    response_model=ApiResponse[Token],
    summary="Login and obtain access token",
)
async def login(
    request: Request,
    payload: LoginRequest,
    controller: Annotated[AuthController, Depends()],
) -> ApiResponse[Token]:
    """
    Authenticate a user via email/password and return JWT tokens.
    """
    token_data = await controller.login(request, payload)
    return ApiResponse(data=token_data, message="Successfully logged in.")


@router.post(
    "/logout",
    response_model=EmptyResponse,
    summary="Logout and revoke current token",
)
async def logout(
    token_data: CurrentUserToken,
    controller: Annotated[AuthController, Depends()],
) -> EmptyResponse:
    """
    Log out the current user by blacklisting their active JWT access token.
    """
    return await controller.logout(token_data)
