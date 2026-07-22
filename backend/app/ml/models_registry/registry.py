"""
app/ml/models_registry/registry.py
─────────────────────────────────
Production Model Registry.

Design decisions:
  • Singleton registry loaded at startup — models are registered by name+version.
  • Lazy loading: models load on first use if not warm-loaded at startup.
  • Warm loading: configured models pre-load during application lifespan.
  • Thread-safe: asyncio.Lock prevents concurrent duplicate loads.
  • Registry is the single source of truth for active model versions.
    No code change is needed to swap a model version — update the config.
  • MinIO integration: model artifacts (.pkl, .onnx, .pt) are fetched from
    object storage, not bundled in the Docker image.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Dict, Optional

try:
    import structlog
    logger = structlog.get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)

from app.core.enums import HazardType
from app.ml.inference.base import IModelPredictor


@dataclass
class ModelEntry:
    """Metadata record for a registered model."""
    model_name: str
    version: str
    hazard_type: HazardType
    predictor: IModelPredictor
    is_loaded: bool = False
    loaded_at: Optional[datetime] = None
    load_error: Optional[str] = None


class ModelRegistry:
    """
    Singleton model registry.

    Manages loading, versioning, and health of all ML predictors.
    """

    _instance: Optional["ModelRegistry"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(self) -> None:
        self._registry: Dict[str, ModelEntry] = {}
        self._load_locks: Dict[str, asyncio.Lock] = {}
        self._active_versions: Dict[HazardType, str] = {}
        self._ab_configs: Dict[HazardType, dict] = {}

    @classmethod
    def get_instance(cls) -> "ModelRegistry":
        if cls._instance is None:
            cls._instance = ModelRegistry()
        return cls._instance

    def register(self, hazard_type: HazardType, predictor: IModelPredictor) -> None:
        """Register a predictor for a given hazard type."""
        key = f"{hazard_type.name}:{predictor.model_name}:{predictor.model_version}"
        self._registry[key] = ModelEntry(
            model_name=predictor.model_name,
            version=predictor.model_version,
            hazard_type=hazard_type,
            predictor=predictor,
        )
        self._load_locks[key] = asyncio.Lock()
        # Set default active version to the first registered model of the hazard type
        if hazard_type not in self._active_versions:
            self._active_versions[hazard_type] = key
        logger.info(
            "Model registered",
            hazard=hazard_type.name,
            model=predictor.model_name,
            version=predictor.model_version,
        )

    async def set_active_version(self, hazard_type: HazardType, model_name: str, version: str) -> bool:
        """Promote or rollback to a specific version for a hazard type."""
        key = f"{hazard_type.name}:{model_name}:{version}"
        if key not in self._registry:
            return False
        self._active_versions[hazard_type] = key
        logger.info("Active model promoted/rolled-back", hazard=hazard_type.name, key=key)
        return True

    def set_ab_config(self, hazard_type: HazardType, baseline_version: str, challenger_version: str, split: float) -> None:
        """Configure A/B testing config for a hazard type."""
        self._ab_configs[hazard_type] = {
            "baseline": baseline_version,
            "challenger": challenger_version,
            "split": split
        }

    async def get_predictor(self, hazard_type: HazardType, route_key: str | None = None) -> Optional[IModelPredictor]:
        """
        Get the active or A/B routed predictor for a hazard type.
        Lazily loads the model if not yet loaded.
        """
        import random
        # 1. Check A/B Testing split configuration
        ab_config = self._ab_configs.get(hazard_type)
        if ab_config and route_key:
            # Deterministic routing based on route_key hash if needed, or simple random route
            # For simplicity, route randomly based on the configured split percentage
            chosen_version = ab_config["baseline"]
            if random.random() < ab_config["split"]:
                chosen_version = ab_config["challenger"]
            
            # Find matching entry in registry
            for key, entry in self._registry.items():
                if entry.hazard_type == hazard_type and entry.version == chosen_version:
                    if not entry.is_loaded:
                        await self._load_model(key)
                    if entry.is_loaded:
                        return entry.predictor

        # 2. Fallback to active version
        active_key = self._active_versions.get(hazard_type)
        if active_key and active_key in self._registry:
            entry = self._registry[active_key]
            if not entry.is_loaded:
                await self._load_model(active_key)
            if entry.is_loaded:
                return entry.predictor

        # 3. Fallback to first matching registered entry
        for key, entry in self._registry.items():
            if entry.hazard_type == hazard_type:
                if not entry.is_loaded:
                    await self._load_model(key)
                if entry.is_loaded:
                    return entry.predictor
        return None

    async def _load_model(self, key: str) -> None:
        """Load a model safely with per-model locking to prevent duplicate loads."""
        lock = self._load_locks.get(key)
        if not lock:
            return

        async with lock:
            entry = self._registry[key]
            if entry.is_loaded:
                return  # Already loaded by another coroutine

            try:
                logger.info("Loading model", model=entry.model_name, version=entry.version)
                await entry.predictor.load()
                entry.is_loaded = True
                entry.loaded_at = datetime.now(UTC)
                logger.info("Model loaded successfully", model=entry.model_name)
            except Exception as exc:
                entry.load_error = str(exc)
                logger.error("Model load failed", model=entry.model_name, error=str(exc))

    async def warm_load_all(self) -> None:
        """Pre-load all registered models. Called during application startup."""
        tasks = [self._load_model(key) for key in self._registry]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Model warm-load complete", count=len(self._registry))

    def health_report(self) -> list[dict]:
        """Return health status of all registered models."""
        return [
            {
                "model_name": entry.model_name,
                "version": entry.version,
                "hazard_type": entry.hazard_type.name,
                "is_loaded": entry.is_loaded,
                "loaded_at": entry.loaded_at.isoformat() if entry.loaded_at else None,
                "load_error": entry.load_error,
            }
            for entry in self._registry.values()
        ]

    def get_all_entries(self) -> list[ModelEntry]:
        return list(self._registry.values())


def get_model_registry() -> ModelRegistry:
    """FastAPI dependency / service accessor for the registry singleton."""
    return ModelRegistry.get_instance()
