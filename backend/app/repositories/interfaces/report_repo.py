"""
app/repositories/interfaces/report_repo.py
──────────────────────────────────────────
Interface for the Report repository.
"""

from abc import ABC, abstractmethod
import uuid
from typing import Optional, Sequence

from app.core.enums import District
from app.models.report import Report


class IReportRepository(ABC):
    """Abstract interface for Report data access."""

    @abstractmethod
    async def get_by_id(self, report_id: uuid.UUID) -> Optional[Report]:
        pass

    @abstractmethod
    async def create(self, report: Report) -> Report:
        pass

    @abstractmethod
    async def get_all_paginated(
        self, limit: int = 50, offset: int = 0, district: Optional[District] = None
    ) -> Sequence[Report]:
        pass
