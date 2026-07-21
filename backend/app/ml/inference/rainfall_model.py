"""
app/ml/inference/rainfall_model.py
──────────────────────────────────
Stub implementation for the Rainfall Prediction Model.
"""

import asyncio
import random
from typing import Any

from app.ml.inference.base import IModelPredictor


class DummyRainfallPredictor(IModelPredictor):
    """
    A placeholder model for Phase 7.
    In later phases, this will load a real .pkl or .onnx model.
    """

    @property
    def model_name(self) -> str:
        return "random_forest_rainfall_stub"

    @property
    def model_version(self) -> str:
        return "0.1.0"

    async def load(self) -> None:
        # Simulate I/O overhead of loading a model from MinIO or disk
        await asyncio.sleep(0.5)

    async def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        # Simulate inference time
        await asyncio.sleep(0.1)
        
        # Naive dummy logic based on temperature/humidity to show variable outputs
        temp = float(features.get("temperature_2m", 25.0))
        humidity = float(features.get("relative_humidity_2m", 60.0))
        
        # If hot and humid, predict higher rainfall
        base_rain = (temp / 30.0) * (humidity / 100.0) * 50
        
        # Add some random noise
        predicted_mm = max(0.0, base_rain + random.uniform(-5.0, 15.0))
        
        return {
            "precipitation_mm": round(predicted_mm, 2),
            "risk_level": "HIGH" if predicted_mm > 50 else "MEDIUM" if predicted_mm > 20 else "LOW",
            "confidence": round(random.uniform(0.70, 0.95), 2),
            "feature_importance": {
                "relative_humidity_2m": 0.45,
                "temperature_2m": 0.35,
                "cloud_cover": 0.20,
            }
        }
