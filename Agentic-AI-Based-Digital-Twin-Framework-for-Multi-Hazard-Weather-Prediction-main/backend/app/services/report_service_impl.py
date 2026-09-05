"""
app/services/report_service_impl.py
───────────────────────────────────
Report Service Implementation.
Coordinates report requests and persistence.
"""

import uuid
from typing import Optional, Sequence

import structlog

from app.core.enums import District
from app.exceptions.base import AppException
from app.models.report import Report
from app.repositories.interfaces.report_repo import IReportRepository
from app.services.interfaces.report_service import IReportService
from app.schemas.report import ReportCreateRequest

logger = structlog.get_logger(__name__)


class ReportServiceImpl(IReportService):
    def __init__(self, report_repo: IReportRepository):
        self.report_repo = report_repo

    async def request_report(self, request: ReportCreateRequest, requested_by: Optional[uuid.UUID] = None) -> Report:
        # In a real implementation, this would publish a message to the AgentManager 
        # to trigger the ReportAgent. We'll simulate immediate creation of the DB record
        report_filename = f"{request.report_type.lower()}_{uuid.uuid4().hex[:8]}.pdf"
        real_url = f"/api/v1/reports/download/{report_filename}"
        
        report = Report(
            title=request.title,
            report_type=request.report_type,
            district=request.district,
            file_url=real_url,
            created_by=requested_by
        )

        created_report = await self.report_repo.create(report)
        
        logger.info(
            "Report generation requested",
            report_id=str(created_report.id),
            type=request.report_type,
        )
        
        return created_report

    async def get_report(self, report_id: uuid.UUID, owner_id: uuid.UUID | None = None) -> Report:
        report = await self.report_repo.get_by_id(report_id, owner_id=owner_id)
        if not report:
            raise AppException(f"Report not found: {report_id}")
        return report

    async def get_all_reports(
        self, limit: int = 50, offset: int = 0, district: Optional[District] = None,
        owner_id: uuid.UUID | None = None,
    ) -> Sequence[Report]:
        return await self.report_repo.get_all_paginated(
            limit=limit, offset=offset, district=district, owner_id=owner_id
        )
