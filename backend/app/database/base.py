"""
app/database/base.py
────────────────────
SQLAlchemy Declarative Base and Mixins.

Design decisions:
  • Uses SQLAlchemy 2.0 type-annotated mappings (`Mapped[type]`).
  • Provides TimestampMixin (created_at, updated_at).
  • Provides SoftDeleteMixin (is_deleted, deleted_at) so records are never
    truly destroyed, preserving referential integrity for audits.
  • Base class defines schema conventions (e.g. naming conventions for constraints).
"""

from __future__ import annotations

import uuid
from datetime import timezone, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Naming conventions for predictable constraint names (important for Alembic auto-migrations)
POSTGRES_INDEXES_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=POSTGRES_INDEXES_NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy 2.0 models."""
    metadata = metadata


class TimestampMixin:
    """Provides created_at and updated_at timestamps."""
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc)
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc)
    )


class SoftDeleteMixin:
    """Provides soft-delete capabilities."""
    
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UUIDMixin:
    """Provides a UUID primary key."""
    
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, 
        default=uuid.uuid4, 
        index=True
    )
