"""
app/repositories/alert_repo_impl.py
───────────────────────────────────
SQLAlchemy implementation of the Alert repository.
"""

import uuid
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AlertStatus, District
from app.models.alert import Alert
from app.repositories.interfaces.alert_repo import IAlertRepository


class AlertRepositoryImpl(IAlertRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, alert_id: uuid.UUID) -> Optional[Alert]:
        stmt = select(Alert).where(Alert.id == alert_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, alert: Alert) -> Alert:
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def update(self, alert: Alert) -> Alert:
        await self.session.flush()
        return alert

    async def get_active_alerts(self, district: Optional[District] = None) -> Sequence[Alert]:
        active_statuses = [AlertStatus.ACTIVE, AlertStatus.ESCALATED]
        stmt = select(Alert).where(Alert.status.in_(active_statuses))
        
        if district:
            stmt = stmt.where(Alert.district == district)
            
        stmt = stmt.order_by(Alert.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_all_paginated(
        self, limit: int = 50, offset: int = 0, district: Optional[District] = None
    ) -> Sequence[Alert]:
        stmt = select(Alert).order_by(Alert.created_at.desc()).limit(limit).offset(offset)
        
        if district:
            stmt = stmt.where(Alert.district == district)
            
        result = await self.session.execute(stmt)
        return result.scalars().all()
