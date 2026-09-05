"""
app/repositories/report_repo_impl.py
────────────────────────────────────
SQLAlchemy implementation of the Report repository.
"""

import uuid
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import District
from app.models.report import Report
from app.repositories.interfaces.report_repo import IReportRepository


class ReportRepositoryImpl(IReportRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, report_id: uuid.UUID, owner_id: uuid.UUID | None = None) -> Optional[Report]:
        stmt = select(Report).where(Report.id == report_id)
        if owner_id is not None:
            stmt = stmt.where(Report.generated_by_id == owner_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, report: Report) -> Report:
        self.session.add(report)
        await self.session.flush()
        return report

    async def get_all_paginated(
        self, limit: int = 50, offset: int = 0, district: Optional[District] = None,
        owner_id: uuid.UUID | None = None,
    ) -> Sequence[Report]:
        stmt = select(Report).order_by(Report.created_at.desc()).limit(limit).offset(offset)
        
        if district:
            stmt = stmt.where(Report.district == district)
        if owner_id is not None:
            stmt = stmt.where(Report.generated_by_id == owner_id)
            
        result = await self.session.execute(stmt)
        return result.scalars().all()
