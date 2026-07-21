"""
app/services/alert_service_impl.py
──────────────────────────────────
Alert Service Implementation.
Coordinates alert creation, notification triggers, and status updates.
"""

import uuid
from datetime import UTC, datetime
from typing import Optional, Sequence

import structlog

from app.core.enums import AlertStatus, District
from app.exceptions.base import AppException
from app.models.alert import Alert
from app.repositories.interfaces.alert_repo import IAlertRepository
from app.services.interfaces.alert_service import IAlertService
from app.schemas.alert import AlertCreateRequest, AlertUpdateRequest

logger = structlog.get_logger(__name__)


class AlertServiceImpl(IAlertService):
    def __init__(self, alert_repo: IAlertRepository):
        self.alert_repo = alert_repo

    async def create_alert(self, request: AlertCreateRequest) -> Alert:
        alert = Alert(
            district=request.district,
            hazard_type=request.hazard_type,
            severity=request.severity,
            status=AlertStatus.ACTIVE,
            title=request.title,
            description=request.description,
            source_context=request.source_context,
            recommended_actions=request.recommended_actions,
            issued_at=datetime.now(UTC),
        )

        created_alert = await self.alert_repo.create(alert)
        
        logger.info(
            "Alert created",
            alert_id=str(created_alert.id),
            district=created_alert.district.name,
            hazard=created_alert.hazard_type.name,
            severity=created_alert.severity.name,
        )
        
        # In a real implementation, this is where we would trigger the AgentManager
        # to fire off the NotificationAgent with this newly created alert data.
        
        return created_alert

    async def get_alert(self, alert_id: uuid.UUID) -> Alert:
        alert = await self.alert_repo.get_by_id(alert_id)
        if not alert:
            raise AppException(f"Alert not found: {alert_id}")
        return alert

    async def update_alert_status(
        self, alert_id: uuid.UUID, request: AlertUpdateRequest
    ) -> Alert:
        alert = await self.get_alert(alert_id)
        
        # Prevent invalid transitions (e.g., resolved back to active)
        if alert.status in [AlertStatus.RESOLVED, AlertStatus.FALSE_ALARM] and request.status not in [AlertStatus.RESOLVED, AlertStatus.FALSE_ALARM]:
            raise AppException(f"Cannot reopen a closed alert ({alert.status.name})")

        alert.status = request.status
        if request.resolution_notes:
            alert.resolution_notes = request.resolution_notes
            
        if request.status in [AlertStatus.RESOLVED, AlertStatus.FALSE_ALARM] and not alert.resolved_at:
            alert.resolved_at = datetime.now(UTC)
            
        updated = await self.alert_repo.update(alert)
        
        logger.info("Alert status updated", alert_id=str(alert.id), status=alert.status.name)
        return updated

    async def get_active_alerts(self, district: Optional[District] = None) -> Sequence[Alert]:
        return await self.alert_repo.get_active_alerts(district=district)

    async def get_all_alerts(
        self, limit: int = 50, offset: int = 0, district: Optional[District] = None
    ) -> Sequence[Alert]:
        return await self.alert_repo.get_all_paginated(
            limit=limit, offset=offset, district=district
        )
