"""
app/models/user.py
───────────────────
User domain models.

Design decisions:
  • SQLAlchemy 2.0 typed mapped columns.
  • Passwords are not stored here (managed by Auth repo) but hashed_password is on the model.
  • Uses TimestampMixin, SoftDeleteMixin, and UUIDMixin from the base class.
  • organization/department added to support the VARUNA Request-Access flow —
    populated from the approved AccessRequest at account-creation time.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import UserRole
from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.auth import RefreshToken


class User(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Core user account model."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Native Postgres Enum type
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum", native_enum=True),
        default=UserRole.PUBLIC,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))

    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Security tracking for brute force prevention
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"