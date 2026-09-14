"""
Loads your actual trained model artifacts (rainfall / cloudburst / landslide)
using the same BasePredictor / BaseModel classes from machine_learning_module
-- this is the real inference path, not a stub, as long as you point
RAINFALL_MODEL_PATH (etc.) at a real `model.joblib`.

Adds ML_MODULE_PATH to sys.path so `from models.machine_learning.lightgbm...`
imports resolve, exactly like running from inside machine_learning_module
yourself.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional, Tuple

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)

_ml_module_added = False


def _ensure_ml_module_on_path() -> None:
    global _ml_module_added
    if _ml_module_added:
        return
    ml_path = str(Path(settings.ml_module_path).resolve())
    if ml_path not in sys.path:
        sys.path.insert(0, ml_path)
        logger.info("Added ML_MODULE_PATH to sys.path: %s", ml_path)
    _ml_module_added = True


def _get_algorithm(algo: str) -> Tuple[Any, Any]:
    """Mirrors ensemble/model.py's _get_algorithm -- returns (ConfigClass, ModelClass)."""
    _ensure_ml_module_on_path()

    if algo == "random_forest":
        from models.machine_learning.random_forest.config import RandomForestConfig
        from models.machine_learning.random_forest.model import RandomForestModel
        return RandomForestConfig, RandomForestModel
    if algo == "xgboost":
        from models.machine_learning.xgboost.config import XGBoostConfig
        from models.machine_learning.xgboost.model import XGBoostModel
        return XGBoostConfig, XGBoostModel
    if algo == "lightgbm":
        from models.machine_learning.lightgbm.config import LightGBMConfig
        from models.machine_learning.lightgbm.model import LightGBMModel
        return LightGBMConfig, LightGBMModel
    if algo == "ensemble":
        from models.ensemble.config import EnsembleConfig
        from models.ensemble.model import EnsembleModel
        return EnsembleConfig, EnsembleModel
    if algo == "deep_learning":
        from models.deep_learning.config import DeepLearningConfig
        from models.deep_learning.model import DeepLearningModel
        return DeepLearningConfig, DeepLearningModel
    if algo == "transformer":
        from models.transformer.config import TFTLiteConfig
        from models.transformer.model import TFTLiteModel
        return TFTLiteConfig, TFTLiteModel
    raise ValueError(f"Unknown algorithm: {algo!r}")


class LoadedModel:
    def __init__(self, predictor: Any, algo: str, artifact_path: str, target_transform: str, task_type: str):
        self.predictor = predictor
        self.algo = algo
        self.artifact_path = artifact_path
        self.target_transform = target_transform
        self.task_type = task_type

    def info(self) -> dict:
        return {
            "name": self.algo,
            "artifact_path": self.artifact_path,
            "target_transform": self.target_transform,
            "task_type": self.task_type,
        }


_cache: dict = {}


def load_model(
    artifact_path: str, algo: str, task_type: str = "regression", target_transform: str = "none"
) -> Optional[LoadedModel]:
    if not artifact_path:
        return None

    cache_key = (artifact_path, algo, task_type, target_transform)
    if cache_key in _cache:
        return _cache[cache_key]

    try:
        _ensure_ml_module_on_path()
        from models.common.base_model import BasePredictor

        config_cls, model_cls = _get_algorithm(algo)
        config = config_cls(task_type=task_type, target_transform=target_transform)
        predictor = BasePredictor.from_artifact(model_cls, config, artifact_path)
        loaded = LoadedModel(predictor, algo, artifact_path, target_transform, task_type)
        _cache[cache_key] = loaded
        logger.info("Loaded model: algo=%s path=%s", algo, artifact_path)
        return loaded
    except Exception as exc:
        logger.error("Failed to load model (algo=%s, path=%s): %s", algo, artifact_path, exc)
        return None


def get_rainfall_model() -> Optional[LoadedModel]:
    if not settings.has_rainfall_model:
        return None
    return load_model(
        settings.rainfall_model_path, settings.rainfall_model_algo,
        task_type="regression", target_transform=settings.rainfall_target_transform,
    )


def get_cloudburst_model() -> Optional[LoadedModel]:
    if not settings.has_cloudburst_model:
        return None
    return load_model(settings.cloudburst_model_path, settings.cloudburst_model_algo,
                       task_type="binary_classification")


def get_landslide_model() -> Optional[LoadedModel]:
    if not settings.has_landslide_model:
        return None
    return load_model(settings.landslide_model_path, settings.landslide_model_algo,
                       task_type="binary_classification")
