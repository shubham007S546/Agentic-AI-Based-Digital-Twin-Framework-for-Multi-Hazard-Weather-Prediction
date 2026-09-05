"""
app/services/auth_service_impl.py
─────────────────────────────────
Implementation of IAuthService.
"""

import uuid
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.constants import TOKEN_BLACKLIST_PREFIX
from app.exceptions.domain import AuthenticationError, AccountLockedError
from app.repositories.interfaces.user_repo import IUserRepository
from app.schemas.auth import LoginRequest, RefreshRequest, Token
from app.security.authentication.jwt import create_access_token, create_refresh_token
from app.security.authentication.passwords import verify_password
from app.services.interfaces.auth_service import IAuthService


class AuthServiceImpl(IAuthService):
    def __init__(self, user_repo: IUserRepository, redis: Redis):
        self.user_repo = user_repo
        self.redis = redis
        self.settings = get_settings()

    async def login(self, request: LoginRequest, client_ip: str) -> Token:
        user = await self.user_repo.get_by_email(request.email)
        if not user or not user.is_active:
            raise AuthenticationError()

        if user.is_locked:
            raise AccountLockedError()

        if not verify_password(request.password, user.hashed_password):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.now(UTC) + timedelta(minutes=15)
            await self.user_repo.update(user)
            raise AuthenticationError()

        # Success - reset attempts
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login = datetime.now(UTC)
        await self.user_repo.update(user)

        # Generate tokens
        access_token = create_access_token(user.id, role=user.role.name)
        refresh_token = create_refresh_token(user.id, role=user.role.name)
        
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=self.settings.jwt.access_token_expire_minutes * 60,
        )

    async def refresh_token(self, request: RefreshRequest, client_ip: str) -> Token:
        # Full implementation would validate the refresh_token against DB
        raise NotImplementedError("Refresh token logic pending")

    async def logout(self, jti: str, expires_at: int) -> None:
        """
        Blacklist the JTI in Redis. The key will automatically expire when the
        token itself was supposed to expire, keeping Redis memory clean.
        """
        now = int(datetime.now(UTC).timestamp())
        ttl = max(0, expires_at - now)
        if ttl > 0:
            await self.redis.setex(f"{TOKEN_BLACKLIST_PREFIX}:{jti}", ttl, "1")
