"""
app/repositories/interfaces/alert_repo.py
─────────────────────────────────────────
Interface for the Alert repository.
"""

from abc import ABC, abstractmethod
import uuid
from typing import Optional, Sequence

from app.core.enums import AlertStatus, District
from app.models.alert import Alert


class IAlertRepository(ABC):
    """Abstract interface for Alert data access."""

    @abstractmethod
    async def get_by_id(self, alert_id: uuid.UUID) -> Optional[Alert]:
        pass

    @abstractmethod
    async def create(self, alert: Alert) -> Alert:
        pass

    @abstractmethod
    async def update(self, alert: Alert) -> Alert:
        pass

    @abstractmethod
    async def get_active_alerts(self, district: Optional[District] = None) -> Sequence[Alert]:
        """Fetch all alerts that are ACTIVE or ESCALATED."""
        pass

    @abstractmethod
    async def get_all_paginated(
        self, limit: int = 50, offset: int = 0, district: Optional[District] = None
    ) -> Sequence[Alert]:
        pass
