"""
app/models/report.py
────────────────────
Automated Reporting domain models.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ReportStatus, ReportType, District
from app.database.base import Base, TimestampMixin, UUIDMixin


class Report(Base, UUIDMixin, TimestampMixin):
    """
    Log of all generated reports (daily briefings, post-disaster analysis, etc.)
    Contains the MinIO object key/URL for retrieving the actual PDF/HTML file.
    """
    
    __tablename__ = "reports"

    report_type: Mapped[ReportType] = mapped_column(
        Enum(ReportType, name="report_type_enum", native_enum=True),
        index=True,
        nullable=False,
    )
    
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    
    district: Mapped[District | None] = mapped_column(
        Enum(District, name="report_district_enum", native_enum=True),
        index=True,
        nullable=True,
    )

    # MinIO object path or full URL
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    @property
    def file_url(self) -> str | None:
        return self.storage_path

    @file_url.setter
    def file_url(self, value: str | None) -> None:
        self.storage_path = value

    @property
    def generated_at(self) -> datetime:
        return self.created_at

    @property
    def created_by(self) -> uuid.UUID | None:
        return self.generated_by_id

    @created_by.setter
    def created_by(self, value: uuid.UUID | None) -> None:
        self.generated_by_id = value

    # The time range covered by the report
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="report_status_enum", native_enum=True),
        default=ReportStatus.PENDING,
        index=True,
        nullable=False,
    )
    
    generated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return f"<Report {self.title} ({self.status.name})>"
