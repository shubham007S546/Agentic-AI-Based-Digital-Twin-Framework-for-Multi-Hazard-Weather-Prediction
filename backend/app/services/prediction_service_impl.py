"""
app/services/prediction_service_impl.py
───────────────────────────────────────
Implementation of IPredictionService.
"""

import time
import structlog

from app.core.enums import HazardType, PredictionStatus, District
from app.exceptions.base import AppException
from app.ml.models_registry.registry import ModelRegistry
from app.models.prediction import PredictionRequest
from app.repositories.interfaces.prediction_repo import IPredictionRepository
from app.services.interfaces.prediction_service import IPredictionService
from app.services.interfaces.weather_service import IWeatherService
from app.schemas.prediction import PredictionRunRequest, BatchPredictionRunRequest

logger = structlog.get_logger(__name__)


class PredictionServiceImpl(IPredictionService):
    def __init__(
        self,
        prediction_repo: IPredictionRepository,
        weather_service: IWeatherService,
        model_registry: ModelRegistry,
    ):
        self.prediction_repo = prediction_repo
        self.weather_service = weather_service
        self.model_registry = model_registry

    async def run_prediction(self, request: PredictionRunRequest, triggered_by: str) -> PredictionRequest:
        model = await self.model_registry.get_predictor(request.hazard_type)
        if not model:
            raise AppException(f"No ML model configured for hazard type: {request.hazard_type.name}")

        # 1. Fetch features if not provided manually
        features = request.features
        if not features:
            latest_weather = await self.weather_service.get_latest_observation(request.district)
            features = {
                "temperature_2m": latest_weather.temperature_2m,
                "relative_humidity_2m": latest_weather.relative_humidity_2m,
                "precipitation": latest_weather.precipitation,
                "cloud_cover": latest_weather.cloud_cover,
                "soil_moisture": latest_weather.soil_moisture,
            }

        # 2. Create the initial prediction record (PENDING)
        record = PredictionRequest(
            triggered_by=triggered_by,
            model_name=model.model_name,
            model_version=model.model_version,
            district=request.district,
            hazard_type=request.hazard_type,
            prediction_type=request.prediction_type,
            input_features=features,
            status=PredictionStatus.PENDING,
        )
        record = await self.prediction_repo.create(record)

        # 3. Execute inference
        start_time = time.perf_counter()
        try:
            result = await model.predict(features)
            
            record.prediction_result = result
            record.confidence = result.get("confidence")
            record.status = PredictionStatus.COMPLETED
            
        except Exception as exc:
            logger.error("Inference failed", model=model.model_name, error=str(exc))
            record.status = PredictionStatus.FAILED
            record.error_message = str(exc)
        finally:
            record.inference_time_ms = (time.perf_counter() - start_time) * 1000
            
            # The session will flush this update when the dependency yields
            # In a fully decoupled repo, we might call update(record) here.
            
        return record

    async def run_batch_prediction(
        self, request: BatchPredictionRunRequest, triggered_by: str
    ) -> list[PredictionRequest]:
        results = []
        for req in request.requests:
            result = await self.run_prediction(req, triggered_by)
            results.append(result)
        return results

    async def get_prediction_history(
        self, district: District, hazard: HazardType, limit: int = 10
    ) -> list[PredictionRequest]:
        return await self.prediction_repo.get_recent_by_district_and_hazard(
            district=district, hazard=hazard, limit=limit
        )
