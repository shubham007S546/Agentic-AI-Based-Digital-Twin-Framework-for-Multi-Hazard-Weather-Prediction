"""
app/api/v1/controllers/report_controller.py
───────────────────────────────────────────
Report Controller.
"""

from typing import Annotated, Optional
import uuid

from fastapi import Depends

from app.core.enums import District
from app.dependencies.services import get_report_service
from app.models.report import Report
from app.schemas.report import ReportCreateRequest
from app.services.interfaces.report_service import IReportService


class ReportController:
    """Controller for Report endpoints."""

    def __init__(
        self,
        report_service: Annotated[IReportService, Depends(get_report_service)],
    ):
        self.report_service = report_service

    async def get_all_reports(
        self, limit: int = 50, offset: int = 0, district: Optional[District] = None,
        owner_id: uuid.UUID | None = None,
    ) -> list[Report]:
        return list(await self.report_service.get_all_reports(limit, offset, district, owner_id))

    async def get_report(self, report_id: uuid.UUID, owner_id: uuid.UUID | None = None) -> Report:
        return await self.report_service.get_report(report_id, owner_id)

    async def request_report(self, request: ReportCreateRequest, requested_by: uuid.UUID) -> Report:
        return await self.report_service.request_report(request, requested_by)
