"""
app/api/v1/routers/auth_router.py
──────────────────────────────────
Authentication routing definitions.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.v1.controllers.auth_controller import AuthController
from app.dependencies.auth import CurrentUserToken
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
    """Authenticate a user via email/password and return JWT tokens."""
    token_data = await controller.login(request, payload)
    return ApiResponse(data=token_data, message="Successfully logged in.")


@router.post(
    "/refresh",
    response_model=ApiResponse[Token],
    summary="Exchange a refresh token for a new token pair",
)
async def refresh(
    request: Request,
    payload: RefreshRequest,
    controller: Annotated[AuthController, Depends()],
) -> ApiResponse[Token]:
    """Rotate refresh token and issue a new access+refresh pair."""
    token_data = await controller.refresh(request, payload)
    return ApiResponse(data=token_data, message="Token refreshed.")


@router.post(
    "/logout",
    response_model=EmptyResponse,
    summary="Logout and revoke current token",
)
async def logout(
    request: Request,
    token_data: CurrentUserToken,
    controller: Annotated[AuthController, Depends()],
) -> EmptyResponse:
    """Log out the current user by blacklisting their active JWT access token."""
    return await controller.logout(request, token_data)


@router.get(
    "/me",
    response_model=ApiResponse[MeResponse],
    summary="Get the current authenticated user's profile",
)
async def me(
    token_data: CurrentUserToken,
    controller: Annotated[AuthController, Depends()],
) -> ApiResponse[MeResponse]:
    profile = await controller.me(token_data)
    return ApiResponse(data=profile)


@router.post(
    "/request-access",
    response_model=ApiResponse[AccessRequestResponse],
    summary="Submit a platform-access application for admin review",
)
async def request_access(
    payload: RequestAccessCreate,
    controller: Annotated[AuthController, Depends()],
) -> ApiResponse[AccessRequestResponse]:
    """Does NOT create a user account — only an admin approval does that."""
    result = await controller.request_access(payload)
    return ApiResponse(data=result, message="Your application has been submitted for review.")


@router.post(
    "/forgot-password",
    response_model=EmptyResponse,
    summary="Request a password reset email",
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    controller: Annotated[AuthController, Depends()],
) -> EmptyResponse:
    return await controller.forgot_password(payload)


@router.post(
    "/reset-password",
    response_model=EmptyResponse,
    summary="Reset password using a reset token",
)
async def reset_password(
    payload: ResetPasswordRequest,
    controller: Annotated[AuthController, Depends()],
) -> EmptyResponse:
    return await controller.reset_password(payload)