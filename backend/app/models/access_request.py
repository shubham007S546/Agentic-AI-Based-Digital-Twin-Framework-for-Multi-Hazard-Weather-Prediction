"""
app/models/access_request.py
─────────────────────────────
Pending platform-access applications (the "Request Access" flow).

Design decisions:
  • Submitting this form does NOT create a User row — only an admin
    approval action (in the Admin Panel, not built here) creates the
    actual User + sends credentials/invite.
  • Kept separate from User so unapproved applicants never appear in
    the users table, never get a password_hash, and can't authenticate
    even accidentally before being approved.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AccessRequestStatus
from app.database.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class AccessRequest(Base, UUIDMixin, TimestampMixin):
    """An applicant's request for a VARUNA account, pending admin review."""

    __tablename__ = "access_requests"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)

    institution: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    research_area: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[AccessRequestStatus] = mapped_column(
        default=AccessRequestStatus.PENDING,
        nullable=False,
    )

    # Populated only once an admin acts on the request.
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Set once approval creates the real User row, so we never lose the
    # link between an application and the account it produced.
    created_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    reviewed_by: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by_id])
    created_user: Mapped["User | None"] = relationship("User", foreign_keys=[created_user_id])

    def __repr__(self) -> str:
        return f"<AccessRequest {self.email} ({self.status})>"
