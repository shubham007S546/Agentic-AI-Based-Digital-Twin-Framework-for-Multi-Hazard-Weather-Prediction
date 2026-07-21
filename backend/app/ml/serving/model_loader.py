"""
app/ml/serving/model_loader.py
───────────────────────────────
Initializes and seeds the ModelRegistry at application startup.

Called from main.py lifespan — must be fast and fault-tolerant.
"""

from __future__ import annotations

import structlog

from app.core.enums import HazardType
from app.ml.inference.landslide_model import (
    DummyCloudburstPredictor,
    DummyFloodPredictor,
    DummyLandslidePredictor,
)
from app.ml.inference.rainfall_model import DummyRainfallPredictor
from app.ml.models_registry.registry import ModelRegistry

logger = structlog.get_logger(__name__)


def seed_model_registry(registry: ModelRegistry, warm_load: bool = False) -> None:
    """
    Register all known models into the registry.

    Args:
        registry:   The singleton ModelRegistry instance.
        warm_load:  If True, trigger async warm-loading (done in lifespan).
    """
    # Register all hazard → predictor mappings
    registry.register(HazardType.RAINFALL, DummyRainfallPredictor())
    registry.register(HazardType.LANDSLIDE, DummyLandslidePredictor())
    registry.register(HazardType.CLOUDBURST, DummyCloudburstPredictor())
    registry.register(HazardType.FLASH_FLOOD, DummyFloodPredictor())

    logger.info(
        "Model registry seeded",
        model_count=len(registry.get_all_entries()),
    )
