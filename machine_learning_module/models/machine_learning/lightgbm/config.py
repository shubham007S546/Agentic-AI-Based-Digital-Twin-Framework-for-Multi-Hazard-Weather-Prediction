"""Configuration for the LightGBM model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from models.common.config_schema import BaseModelConfig, TaskType
from models.common.exceptions import ConfigValidationError


@dataclass
class LightGBMConfig(BaseModelConfig):
    """
    LightGBM specific hyperparameters, on top of the shared fields in
    BaseModelConfig.
    """

    model_name: str = "lightgbm"

    n_estimators: int = 500
    num_leaves: int = 31
    max_depth: int = -1                  # -1 = no limit (leaf-wise growth)
    learning_rate: float = 0.05
    subsample: float = 0.8               # bagging_fraction
    subsample_freq: int = 1              # bagging_freq
    colsample_bytree: float = 0.8        # feature_fraction
    min_child_samples: int = 20          # min_data_in_leaf
    reg_alpha: float = 0.0
    reg_lambda: float = 0.0

    device: str = "cpu"                  # "cpu" or "gpu"

    categorical_features: List[str] = field(default_factory=list)

    early_stopping_rounds: Optional[int] = 30
    use_validation_for_early_stopping: bool = True

    scale_pos_weight: Optional[float] = None  # binary classification only
    eval_metric: Optional[str] = None          # None -> pick a sensible default per task
    is_unbalance: bool = False                 # alternative to scale_pos_weight

    tweedie_variance_power: Optional[float] = None  # regression only; e.g. 1.5. Sets
                                                      # objective="tweedie", built for
                                                      # zero-inflated, right-skewed targets.
                                                      # Mutually exclusive with target_transform="log1p".

    def validate(self) -> None:
        super().validate()

        if self.n_estimators <= 0:
            raise ConfigValidationError("n_estimators must be > 0.")
        if self.num_leaves <= 1:
            raise ConfigValidationError("num_leaves must be > 1.")
        if not (0.0 < self.learning_rate <= 1.0):
            raise ConfigValidationError("learning_rate must be in (0, 1].")
        if not (0.0 < self.subsample <= 1.0):
            raise ConfigValidationError("subsample must be in (0, 1].")
        if not (0.0 < self.colsample_bytree <= 1.0):
            raise ConfigValidationError("colsample_bytree must be in (0, 1].")
        if self.device not in ("cpu", "gpu"):
            raise ConfigValidationError("device must be one of: cpu, gpu.")
        if self.early_stopping_rounds is not None and self.early_stopping_rounds <= 0:
            raise ConfigValidationError("early_stopping_rounds must be > 0 or None.")
        if self.scale_pos_weight is not None and self.is_unbalance:
            raise ConfigValidationError(
                "scale_pos_weight and is_unbalance are mutually exclusive in LightGBM."
            )
        if self.tweedie_variance_power is not None:
            if self.task_type != TaskType.REGRESSION:
                raise ConfigValidationError("tweedie_variance_power is only valid for regression.")
            if not (1.0 <= self.tweedie_variance_power < 2.0):
                raise ConfigValidationError("tweedie_variance_power must be in [1.0, 2.0).")
            if self.target_transform == "log1p":
                raise ConfigValidationError(
                    "tweedie_variance_power and target_transform='log1p' are mutually exclusive: "
                    "Tweedie models the raw-scale distribution directly."
                )
