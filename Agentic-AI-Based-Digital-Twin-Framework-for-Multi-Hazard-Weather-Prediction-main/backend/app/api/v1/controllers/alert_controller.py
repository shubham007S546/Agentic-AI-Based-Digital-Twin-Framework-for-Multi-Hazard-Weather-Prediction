"""
app/api/v1/controllers/alert_controller.py
──────────────────────────────────────────
Alert Controller.
"""

from typing import Annotated, Optional
import uuid

from fastapi import Depends

from app.core.enums import District
from app.dependencies.services import get_alert_service
from app.models.alert import Alert
from app.schemas.alert import AlertCreateRequest, AlertUpdateRequest
from app.services.interfaces.alert_service import IAlertService


class AlertController:
    """Controller for Alert endpoints."""

    def __init__(
        self,
        alert_service: Annotated[IAlertService, Depends(get_alert_service)],
    ):
        self.alert_service = alert_service

    async def get_active_alerts(self, district: Optional[District] = None) -> list[Alert]:
        return list(await self.alert_service.get_active_alerts(district))

    async def get_all_alerts(
        self, limit: int = 50, offset: int = 0, district: Optional[District] = None
    ) -> list[Alert]:
        return list(await self.alert_service.get_all_alerts(limit, offset, district))

    async def get_alert(self, alert_id: uuid.UUID) -> Alert:
        return await self.alert_service.get_alert(alert_id)

    async def create_alert(self, request: AlertCreateRequest) -> Alert:
        return await self.alert_service.create_alert(request)

    async def update_alert(self, alert_id: uuid.UUID, request: AlertUpdateRequest) -> Alert:
        return await self.alert_service.update_alert_status(alert_id, request)
