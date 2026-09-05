"""
app/models/alert.py
───────────────────
Disaster Early Warning Alert models.

Aligned with AlertService, AlertSchema, and AlertRepositoryImpl:
  • title, description      — human-readable summary
  • source_context          — triggering entity (prediction_id, agent, thresholds)
  • recommended_actions     — SDMA protocol actions for this event
  • resolution_notes        — post-resolution notes (set when RESOLVED / FALSE_ALARM)
  • issued_at / expires_at / resolved_at — lifecycle timestamps
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    AlertSeverity,
    AlertStatus,
    District,
    HazardType,
    NotificationChannel,
    NotificationStatus,
)
from app.database.base import Base, TimestampMixin, UUIDMixin


class Alert(Base, UUIDMixin, TimestampMixin):
    """
    Early warning alert issued by the AlertAgent or manually by an admin.
    Contains hazard type, severity, geographic scope, and SDMA action guidance.
    """

    __tablename__ = "alerts"

    # ── Core classification ───────────────────────────────────────────────────

    hazard_type: Mapped[HazardType] = mapped_column(
        Enum(HazardType, name="alert_hazard_type_enum", native_enum=True),
        index=True,
        nullable=False,
    )

    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity, name="alert_severity_enum", native_enum=True),
        index=True,
        nullable=False,
    )

    district: Mapped[District] = mapped_column(
        Enum(District, name="alert_district_enum", native_enum=True),
        index=True,
        nullable=False,
    )

    # ── Human-readable content ────────────────────────────────────────────────

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)

    # ── Structured context ────────────────────────────────────────────────────

    # What triggered this alert (prediction_id, agent name, threshold value)
    source_context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # SDMA-recommended actions (evacuation routes, emergency contacts, etc.)
    recommended_actions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Optional reference to the ML prediction that triggered this alert
    prediction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prediction_requests.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    # ── Status & lifecycle ────────────────────────────────────────────────────

    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus, name="alert_status_enum", native_enum=True),
        default=AlertStatus.ACTIVE,
        index=True,
        nullable=False,
    )

    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Post-resolution notes (set when status → RESOLVED or FALSE_ALARM)
    resolution_notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────

    notifications: Mapped[List["AlertNotification"]] = relationship(
        "AlertNotification", back_populates="alert", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Alert {self.hazard_type.name} {self.severity.name} @ {self.district.name}>"


class AlertNotification(Base, UUIDMixin):
    """
    Tracks the delivery of an alert to a specific user via a specific channel.
    One row per (alert, user, channel) combination.
    """

    __tablename__ = "alert_notifications"

    alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel_enum", native_enum=True),
        nullable=False,
    )

    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status_enum", native_enum=True),
        default=NotificationStatus.PENDING,
        index=True,
        nullable=False,
    )

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    alert: Mapped["Alert"] = relationship("Alert", back_populates="notifications")

    def __repr__(self) -> str:
        return f"<AlertNotification alert={self.alert_id} channel={self.channel.name}>"
