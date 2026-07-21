"""
app/security/authentication/jwt.py
──────────────────────────────────
JWT access token generation and validation.

Design decisions:
  • Uses pyjwt for token handling.
  • Tokens include standard claims (exp, sub, iat, jti) and custom claims (role).
  • A unique JTI (JWT ID) is added to every token to allow blacklisting of 
    specific access tokens before they expire (e.g., during logout).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import get_settings
from app.exceptions.domain import TokenExpiredError, TokenInvalidError


def create_access_token(
    subject: str | uuid.UUID,
    role: str,
    expires_delta: timedelta | None = None
) -> str:
    """
    Create a JWT access token.
    
    Args:
        subject: The user ID (sub).
        role: The user's role (for RBAC checks without DB hits).
        expires_delta: Optional custom expiry time.
    """
    settings = get_settings()
    
    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.jwt.access_token_expire_minutes)
        
    jti = str(uuid.uuid4())
    
    to_encode: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "exp": expire,
        "iat": now,
        "jti": jti,
    }
    
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.jwt.secret_key.get_secret_value(), 
        algorithm=settings.jwt.algorithm
    )
    
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT access token.
    
    Raises:
        TokenExpiredError: If token is expired.
        TokenInvalidError: If token is invalid or malformed.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt.secret_key.get_secret_value(),
            algorithms=[settings.jwt.algorithm],
        )
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError() from exc
    except jwt.InvalidTokenError as exc:
        raise TokenInvalidError() from exc
