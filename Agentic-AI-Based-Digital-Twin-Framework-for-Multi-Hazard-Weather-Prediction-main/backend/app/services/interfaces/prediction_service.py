"""
app/services/interfaces/prediction_service.py
─────────────────────────────────────────────
Interface for the Prediction service.
"""

from abc import ABC, abstractmethod

from app.core.enums import District, HazardType
from app.models.prediction import PredictionRequest
from app.schemas.prediction import PredictionRunRequest, BatchPredictionRunRequest


class IPredictionService(ABC):
    """Abstract interface for Prediction business logic."""

    @abstractmethod
    async def run_prediction(self, request: PredictionRunRequest, triggered_by: str) -> PredictionRequest:
        """
        Execute an ML prediction for a specific district and hazard type.
        Logs the input and output to the database.
        """
        pass

    @abstractmethod
    async def run_batch_prediction(
        self, request: BatchPredictionRunRequest, triggered_by: str
    ) -> list[PredictionRequest]:
        """
        Execute multiple predictions in a batch.
        """
        pass

    @abstractmethod
    async def get_prediction_history(
        self, district: District, hazard: HazardType, limit: int = 10
    ) -> list[PredictionRequest]:
        """
        Fetch recent prediction logs for monitoring/performance audit.
        """
        pass
