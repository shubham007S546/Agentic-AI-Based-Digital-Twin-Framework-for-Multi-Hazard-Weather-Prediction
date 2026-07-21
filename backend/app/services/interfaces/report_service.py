"""
app/services/interfaces/report_service.py
─────────────────────────────────────────
Interface for the Report service.
"""

from abc import ABC, abstractmethod
import uuid
from typing import Optional, Sequence

from app.core.enums import District
from app.models.report import Report
from app.schemas.report import ReportCreateRequest


class IReportService(ABC):
    """Abstract interface for Report generation and retrieval."""

    @abstractmethod
    async def request_report(self, request: ReportCreateRequest, requested_by: Optional[uuid.UUID] = None) -> Report:
        """Queue a report for generation."""
        pass

    @abstractmethod
    async def get_report(self, report_id: uuid.UUID) -> Report:
        """Fetch a generated report by ID."""
        pass

    @abstractmethod
    async def get_all_reports(
        self, limit: int = 50, offset: int = 0, district: Optional[District] = None
    ) -> Sequence[Report]:
        """Fetch all reports, optionally filtered by district."""
        pass
