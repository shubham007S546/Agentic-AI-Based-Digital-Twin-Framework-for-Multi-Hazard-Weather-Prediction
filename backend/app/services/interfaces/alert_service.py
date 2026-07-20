"""
app/services/interfaces/alert_service.py
────────────────────────────────────────
Interface for the Alert service.
"""

from abc import ABC, abstractmethod
import uuid
from typing import Optional, Sequence

from app.core.enums import District
from app.models.alert import Alert
from app.schemas.alert import AlertCreateRequest, AlertUpdateRequest


class IAlertService(ABC):
    """Abstract interface for Alert business logic."""

    @abstractmethod
    async def create_alert(self, request: AlertCreateRequest) -> Alert:
        pass

    @abstractmethod
    async def get_alert(self, alert_id: uuid.UUID) -> Alert:
        pass

    @abstractmethod
    async def update_alert_status(
        self, alert_id: uuid.UUID, request: AlertUpdateRequest
    ) -> Alert:
        pass

    @abstractmethod
    async def get_active_alerts(self, district: Optional[District] = None) -> Sequence[Alert]:
        pass

    @abstractmethod
    async def get_all_alerts(
        self, limit: int = 50, offset: int = 0, district: Optional[District] = None
    ) -> Sequence[Alert]:
        pass
