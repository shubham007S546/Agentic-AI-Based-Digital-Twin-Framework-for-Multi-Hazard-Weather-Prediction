"""
app/dependencies/auth.py
────────────────────────
FastAPI dependencies for authentication and authorization.

Design decisions:
  • `OAuth2PasswordBearer` is used for Swagger UI compatibility, but it just 
    extracts the token string. We validate it manually.
  • `get_current_user` decodes the token, checks the blacklist (Redis cache),
    and returns a lightweight Pydantic model (TokenData) to avoid a database 
    hit on every single request.
  • `get_current_active_user` does hit the database (via repo) if full user 
    details are needed.
  • The current user's ID is injected into the request state for the logging 
    middleware to pick up automatically.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis_client import get_cache_client
from app.core.config import get_settings
from app.core.constants import TOKEN_BLACKLIST_PREFIX
from app.exceptions.domain import (
    AuthenticationError,
    TokenInvalidError,
    TokenBlacklistedError,
    AuthorizationError,
)
from app.schemas.auth import TokenData
from app.security.authentication.jwt import decode_access_token
from app.database.session import get_async_db
from app.models.user import User

# The token URL points to the Swagger-compatible login endpoint (if we implement one)
# We mainly use this to tell FastAPI where to look for the "Authorization: Bearer <token>" header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_token_data(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    redis: Annotated[Redis, Depends(get_cache_client)],
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> TokenData:
    """
    Validates the JWT token and checks if it has been blacklisted.
    Does NOT hit the Postgres database.
    Injects user_id into request.state.
    """
    if not token:
        raise AuthenticationError()

    # Decode token (raises AuthException if expired/invalid)
    payload = decode_access_token(token)
    
    user_id = payload.get("sub")
    jti = payload.get("jti")

    if not user_id or not jti:
        raise TokenInvalidError()

    # Check if token is blacklisted (logged out)
    is_blacklisted = await redis.exists(f"{TOKEN_BLACKLIST_PREFIX}:{jti}")
    if is_blacklisted:
        raise TokenBlacklistedError()

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError as exc:
        raise TokenInvalidError() from exc
    result = await db.execute(
        select(User).where(
            User.id == user_uuid,
            User.is_deleted.is_(False),
            User.is_active.is_(True),
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthenticationError()

    # Inject into request state for logging middleware
    request.state.user_id = user_id

    return TokenData(user_id=user_id, role=user.role.value, jti=jti)


# Use this dependency in endpoints that only need the user ID or role
CurrentUserToken = Annotated[TokenData, Depends(get_current_token_data)]


async def get_optional_token_data(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    redis: Annotated[Redis, Depends(get_cache_client)],
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> TokenData | None:
    if not token:
        return None
    try:
        return await get_current_token_data(request, token, redis, db)
    except Exception:
        return None


OptionalCurrentUserToken = Annotated[TokenData | None, Depends(get_optional_token_data)]



# Helper factory for RBAC (Role-Based Access Control)
def require_role(allowed_roles: list[str]):
    """
    Dependency factory to enforce role-based access.
    
    Usage:
        @router.post("/config", dependencies=[Depends(require_role([UserRole.ADMIN]))])
    """
    async def role_checker(token_data: CurrentUserToken):
        if token_data.role not in allowed_roles:
            raise AuthorizationError()
        return token_data
    
    return role_checker


# Convenience shortcut for admin-only endpoints
require_admin = require_role(["admin", "super_admin"])
