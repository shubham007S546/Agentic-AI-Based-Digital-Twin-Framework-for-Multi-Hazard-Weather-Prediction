"""
app/api/v1/controllers/prediction_controller.py
───────────────────────────────────────────────
Prediction Controller class.
"""

from typing import Annotated

from fastapi import Depends

from app.core.enums import District, HazardType
from app.dependencies.services import get_prediction_service
from app.models.prediction import PredictionRequest
from app.schemas.prediction import PredictionRunRequest, BatchPredictionRunRequest
from app.services.interfaces.prediction_service import IPredictionService


class PredictionController:
    """Controller for ML prediction endpoints."""

    def __init__(
        self,
        prediction_service: Annotated[IPredictionService, Depends(get_prediction_service)],
    ):
        self.prediction_service = prediction_service

    async def run_prediction(
        self, payload: PredictionRunRequest, triggered_by: str
    ) -> PredictionRequest:
        return await self.prediction_service.run_prediction(payload, triggered_by=triggered_by)

    async def run_batch_prediction(
        self, payload: BatchPredictionRunRequest, triggered_by: str
    ) -> list[PredictionRequest]:
        return await self.prediction_service.run_batch_prediction(payload, triggered_by=triggered_by)

    async def get_prediction_history(
        self, district: District, hazard: HazardType, limit: int = 10
    ) -> list[PredictionRequest]:
        return await self.prediction_service.get_prediction_history(district, hazard, limit)
