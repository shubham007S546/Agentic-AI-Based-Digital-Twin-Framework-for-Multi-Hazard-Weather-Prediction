"""
models.common
=============
Shared framework used by every model implementation under
models/machine_learning/<algorithm>/.

NOTE: This package was not supplied by the user. It is generated here,
explicitly, so that every downstream model folder (random_forest,
xgboost, lightgbm) has a real, consistent, importable contract to code
against. If a real models/common/ already exists in the user's repo,
this file's public API (class/function names + signatures) is what the
downstream code depends on -- diff against that before dropping this in.
"""

from .exceptions import (
    FrameworkError,
    ConfigValidationError,
    DataValidationError,
    ModelNotFittedError,
    SerializationError,
    TrainingError,
    TuningError,
)
from .config_schema import TaskType, BaseModelConfig
from .logging_config import get_logger
from .data_utils import DatasetBundle, load_dataset_bundle, set_global_seed
from .serialization import save_artifact, load_artifact
from .base_model import BaseModel, BasePredictor
from .base_trainer import BaseTrainer
from .base_evaluator import BaseEvaluator
from .base_tuner import BaseHyperparameterTuner
from .model_registry import ModelRegistry
from .model_comparator import ModelComparator

__all__ = [
    "FrameworkError",
    "ConfigValidationError",
    "DataValidationError",
    "ModelNotFittedError",
    "SerializationError",
    "TrainingError",
    "TuningError",
    "TaskType",
    "BaseModelConfig",
    "get_logger",
    "DatasetBundle",
    "load_dataset_bundle",
    "set_global_seed",
    "save_artifact",
    "load_artifact",
    "BaseModel",
    "BasePredictor",
    "BaseTrainer",
    "BaseEvaluator",
    "BaseHyperparameterTuner",
    "ModelRegistry",
    "ModelComparator",
]
