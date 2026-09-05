"""
app/repositories/interfaces/prediction_repo.py
──────────────────────────────────────────────
Interface for the Prediction repository.
"""

from abc import ABC, abstractmethod
from typing import Optional
import uuid

from app.core.enums import District, HazardType
from app.models.prediction import PredictionRequest


class IPredictionRepository(ABC):
    """Abstract interface for Prediction data access."""

    @abstractmethod
    async def create(self, request: PredictionRequest) -> PredictionRequest:
        """Save a new prediction record."""
        pass

    @abstractmethod
    async def get_by_id(self, request_id: uuid.UUID) -> Optional[PredictionRequest]:
        """Fetch a specific prediction by UUID."""
        pass

    @abstractmethod
    async def get_recent_by_district_and_hazard(
        self, district: District, hazard: HazardType, limit: int = 10
    ) -> list[PredictionRequest]:
        """Fetch recent predictions for a district and hazard type."""
        pass
