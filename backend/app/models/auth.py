"""
app/models/auth.py
──────────────────
Authentication-related models (refresh tokens, blacklists).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(Base, UUIDMixin, TimestampMixin):
    """
    Long-lived refresh tokens for maintaining sessions.
    The actual token sent to the client is a JWT containing this row's ID.
    The token string itself is hashed in the DB so database dumps can't be used
    to hijack active sessions.
    """
    
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    
    # Stores bcrypt hash of the random token string
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    
    # Audit info
    device_info: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Revocation status (e.g. user logs out, or changes password)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")


class BlacklistedToken(Base, UUIDMixin):
    """
    Blacklist for JWT access tokens that were logged out before they expired.
    Only the JTI (JWT ID) claim is stored, not the whole token.
    This table can be periodically pruned of expired tokens to save space.
    """
    
    __tablename__ = "blacklisted_tokens"

    jti: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    blacklisted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PasswordResetToken(Base, UUIDMixin, TimestampMixin):
    """Temporary tokens used for password reset flows."""
    
    __tablename__ = "password_reset_tokens"
    
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailVerificationToken(Base, UUIDMixin, TimestampMixin):
    """Temporary tokens used for email verification flows."""
    
    __tablename__ = "email_verification_tokens"
    
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
