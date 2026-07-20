"""
Shared configuration schema.

Every per-algorithm config.py (random_forest/config.py, xgboost/config.py,
lightgbm/config.py) defines a dataclass that SUBCLASSES BaseModelConfig and
adds algorithm-specific hyperparameters. This file only defines the fields
that are common across all algorithms and all task types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from .exceptions import ConfigValidationError


class TaskType(str, Enum):
    REGRESSION = "regression"
    BINARY_CLASSIFICATION = "binary_classification"
    MULTICLASS_CLASSIFICATION = "multiclass_classification"


@dataclass
class BaseModelConfig:
    """
    Fields shared by every model config in the framework.

    Attributes
    ----------
    task_type: which of the three supported tasks this run is for.
    data_dir: path to the ml_ready/ folder containing the pre-split CSVs.
    target_column: name of the target column in y_train.csv/y_val.csv/y_test.csv.
    random_seed: seed used everywhere (model, splits, tuner) for reproducibility.
    n_jobs: parallelism passed to the underlying estimator / tuner.
    use_sample_weights: whether to load and apply sample_weights_train.csv.
    use_class_weights: whether to load and apply class_weights.json
        (only meaningful for classification tasks).
    experiment_name: used for logging, registry keys, and artifact naming.
    artifacts_dir: where trained models / reports / plots are written.
    model_name: short identifier for the algorithm, set by subclasses
        (e.g. "random_forest", "xgboost", "lightgbm").
    """

    task_type: TaskType = TaskType.REGRESSION
    data_dir: str = "ml_ready"
    target_column: str = "target"
    random_seed: int = 42
    n_jobs: int = -1
    use_sample_weights: bool = True
    use_class_weights: bool = True
    experiment_name: str = "experiment"
    artifacts_dir: str = "artifacts"
    model_name: str = "base"
    target_transform: str = "none"  # "none" | "log1p" -- regression only; fit on
                                     # log1p(y), inverse-transform predictions with expm1

    def validate(self) -> None:
        """Validate shared fields. Subclasses should call super().validate()
        first, then validate their own algorithm-specific fields."""
        if not isinstance(self.task_type, TaskType):
            try:
                self.task_type = TaskType(self.task_type)
            except ValueError as exc:
                raise ConfigValidationError(
                    f"Invalid task_type={self.task_type!r}. "
                    f"Must be one of {[t.value for t in TaskType]}"
                ) from exc

        if not self.data_dir:
            raise ConfigValidationError("data_dir must not be empty.")

        if not self.target_column:
            raise ConfigValidationError("target_column must not be empty.")

        if self.random_seed < 0:
            raise ConfigValidationError("random_seed must be >= 0.")

        if self.use_class_weights and self.task_type == TaskType.REGRESSION:
            # class weighting is meaningless for regression; auto-disable
            # rather than hard-failing, since CLIs default this flag to True.
            self.use_class_weights = False

        if self.target_transform not in ("none", "log1p"):
            raise ConfigValidationError('target_transform must be "none" or "log1p".')
        if self.target_transform == "log1p" and self.task_type != TaskType.REGRESSION:
            # meaningless for classification; auto-disable rather than hard-fail
            self.target_transform = "none"

    @property
    def is_classification(self) -> bool:
        return self.task_type in (
            TaskType.BINARY_CLASSIFICATION,
            TaskType.MULTICLASS_CLASSIFICATION,
        )

    def artifact_path(self, filename: str) -> Path:
        p = Path(self.artifacts_dir) / self.model_name / self.experiment_name
        p.mkdir(parents=True, exist_ok=True)
        return p / filename
