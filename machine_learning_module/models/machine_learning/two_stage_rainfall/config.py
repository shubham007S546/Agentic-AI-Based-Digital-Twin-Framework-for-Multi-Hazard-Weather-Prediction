"""
Configuration for the two-stage rainfall pipeline.

Rainfall (imd_rainfall_mm) is zero-inflated: most rows are 0 (no rain), and
the rest are right-skewed with rare large spikes. A single regressor tends
to be mediocre everywhere rather than good anywhere. This pipeline splits
the problem in two:

  Stage 1 (classifier): "did it rain at all?" -- binary_classification on
      (imd_rainfall_mm > rain_threshold).
  Stage 2 (regressor):  "how much, given that it rained?" -- trained ONLY
      on the rainy subset of the training data, optionally on log1p(rainfall)
      to tame the right-skew.

Final prediction = 0 where stage 1 says "no rain", else stage 2's (inverse-
transformed) prediction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.common.config_schema import BaseModelConfig, TaskType
from models.common.exceptions import ConfigValidationError

_VALID_ALGORITHMS = ("random_forest", "xgboost", "lightgbm")


@dataclass
class TwoStageRainfallConfig(BaseModelConfig):
    model_name: str = "two_stage_rainfall"
    task_type: TaskType = TaskType.REGRESSION  # the pipeline's overall output is a regression

    classifier_algorithm: str = "random_forest"   # "random_forest" | "xgboost" | "lightgbm"
    regressor_algorithm: str = "random_forest"    # "random_forest" | "xgboost" | "lightgbm"

    rain_threshold: float = 0.1        # mm; rows with target > this are "it rained"
    log_transform: bool = True         # fit stage 2 on log1p(target), expm1 back at predict time
    classification_threshold: float = 0.5  # probability cutoff for stage 1's "did it rain" decision

    def validate(self) -> None:
        super().validate()
        if self.classifier_algorithm not in _VALID_ALGORITHMS:
            raise ConfigValidationError(
                f"classifier_algorithm must be one of {_VALID_ALGORITHMS}, got {self.classifier_algorithm!r}."
            )
        if self.regressor_algorithm not in _VALID_ALGORITHMS:
            raise ConfigValidationError(
                f"regressor_algorithm must be one of {_VALID_ALGORITHMS}, got {self.regressor_algorithm!r}."
            )
        if self.rain_threshold < 0:
            raise ConfigValidationError("rain_threshold must be >= 0.")
        if not (0.0 < self.classification_threshold < 1.0):
            raise ConfigValidationError("classification_threshold must be in (0, 1).")
