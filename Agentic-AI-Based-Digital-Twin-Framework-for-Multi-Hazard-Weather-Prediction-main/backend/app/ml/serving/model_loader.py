"""
app/ml/serving/model_loader.py
───────────────────────────────
Initializes and seeds the ModelRegistry at application startup with production ML predictors.
"""

from __future__ import annotations

import structlog

from app.core.enums import HazardType
from app.ml.inference.landslide_model import (
    CloudburstPredictor,
    FloodPredictor,
    LandslidePredictor,
)
from app.ml.inference.rainfall_model import RainfallPredictor
from app.ml.models_registry.registry import ModelRegistry

logger = structlog.get_logger(__name__)


def seed_model_registry(registry: ModelRegistry, warm_load: bool = False) -> None:
    """
    Register all known production ML predictors into the registry.
    """
    registry.register(HazardType.RAINFALL, RainfallPredictor())
    registry.register(HazardType.LANDSLIDE, LandslidePredictor())
    registry.register(HazardType.CLOUDBURST, CloudburstPredictor())
    registry.register(HazardType.FLASH_FLOOD, FloodPredictor())

    logger.info(
        "Production Model Registry seeded successfully",
        model_count=len(registry.get_all_entries()),
    )
