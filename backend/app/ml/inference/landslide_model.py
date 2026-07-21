"""
app/ml/inference/landslide_model.py
────────────────────────────────────
Stub implementation for the Landslide Risk Prediction Model.
"""

import asyncio
import random
from typing import Any

from app.ml.inference.base import IModelPredictor


class DummyLandslidePredictor(IModelPredictor):
    """
    Placeholder landslide risk predictor.
    Will be replaced with a real XGBoost/Random Forest model in Phase 8 serving.
    """

    @property
    def model_name(self) -> str:
        return "xgboost_landslide_stub"

    @property
    def model_version(self) -> str:
        return "0.1.0"

    async def load(self) -> None:
        await asyncio.sleep(0.3)

    async def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.1)

        soil_moisture = float(features.get("soil_moisture", 0.3))
        precipitation = float(features.get("precipitation", 0.0))

        # Simplified: high moisture + heavy rain = high landslide risk
        risk_score = min(1.0, (soil_moisture * 0.6) + (min(precipitation, 100) / 100 * 0.4))
        risk_score += random.uniform(-0.05, 0.05)
        risk_score = max(0.0, min(1.0, risk_score))

        return {
            "risk_score": round(risk_score, 3),
            "risk_level": "CRITICAL" if risk_score > 0.8 else "HIGH" if risk_score > 0.6 else "MEDIUM" if risk_score > 0.3 else "LOW",
            "confidence": round(random.uniform(0.70, 0.92), 2),
            "contributing_factors": {
                "soil_saturation": round(soil_moisture, 3),
                "antecedent_rainfall": round(precipitation, 2),
            },
        }


class DummyCloudburstPredictor(IModelPredictor):
    """Placeholder cloudburst predictor."""

    @property
    def model_name(self) -> str:
        return "lstm_cloudburst_stub"

    @property
    def model_version(self) -> str:
        return "0.1.0"

    async def load(self) -> None:
        await asyncio.sleep(0.4)

    async def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.15)

        humidity = float(features.get("relative_humidity_2m", 60.0))
        cloud_cover = float(features.get("cloud_cover", 40.0))

        probability = min(1.0, (humidity / 100 * 0.5) + (cloud_cover / 100 * 0.5))
        probability += random.uniform(-0.05, 0.1)
        probability = max(0.0, min(1.0, probability))

        return {
            "cloudburst_probability": round(probability, 3),
            "risk_level": "HIGH" if probability > 0.7 else "MEDIUM" if probability > 0.4 else "LOW",
            "confidence": round(random.uniform(0.65, 0.90), 2),
            "forecast_window_hours": 6,
        }


class DummyFloodPredictor(IModelPredictor):
    """Placeholder flash flood predictor."""

    @property
    def model_name(self) -> str:
        return "random_forest_flood_stub"

    @property
    def model_version(self) -> str:
        return "0.1.0"

    async def load(self) -> None:
        await asyncio.sleep(0.3)

    async def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.1)

        precipitation = float(features.get("precipitation", 0.0))
        soil_moisture = float(features.get("soil_moisture", 0.3))

        flood_index = min(1.0, (precipitation / 150 * 0.7) + (soil_moisture * 0.3))
        flood_index += random.uniform(-0.03, 0.08)
        flood_index = max(0.0, min(1.0, flood_index))

        return {
            "flood_risk_index": round(flood_index, 3),
            "risk_level": "EXTREME" if flood_index > 0.85 else "HIGH" if flood_index > 0.6 else "MEDIUM" if flood_index > 0.3 else "LOW",
            "confidence": round(random.uniform(0.72, 0.93), 2),
            "estimated_peak_hours": random.randint(2, 12),
        }
