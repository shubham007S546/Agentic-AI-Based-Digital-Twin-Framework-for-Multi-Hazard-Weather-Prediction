"""Configuration for the XGBoost model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.common.config_schema import BaseModelConfig, TaskType
from models.common.exceptions import ConfigValidationError


@dataclass
class XGBoostConfig(BaseModelConfig):
    """
    XGBoost specific hyperparameters, on top of the shared fields in
    BaseModelConfig.
    """

    model_name: str = "xgboost"

    n_estimators: int = 500
    max_depth: int = 6
    learning_rate: float = 0.05
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    min_child_weight: float = 1.0
    reg_alpha: float = 0.0
    reg_lambda: float = 1.0
    gamma: float = 0.0

    tree_method: str = "hist"                # "hist", "approx", "exact"
    use_gpu: bool = False                     # if True, device="cuda"
    missing_value: float = float("nan")       # native NaN handling

    early_stopping_rounds: Optional[int] = 30
    use_validation_for_early_stopping: bool = True

    scale_pos_weight: Optional[float] = None  # binary classification only; None -> auto from class_weights
    eval_metric: Optional[str] = None         # None -> pick a sensible default per task

    tweedie_variance_power: Optional[float] = None  # regression only; e.g. 1.5. Sets
                                                      # objective="reg:tweedie", built for
                                                      # zero-inflated, right-skewed targets
                                                      # like rainfall. Mutually exclusive
                                                      # with target_transform="log1p".

    def validate(self) -> None:
        super().validate()

        if self.n_estimators <= 0:
            raise ConfigValidationError("n_estimators must be > 0.")
        if self.max_depth <= 0:
            raise ConfigValidationError("max_depth must be > 0.")
        if not (0.0 < self.learning_rate <= 1.0):
            raise ConfigValidationError("learning_rate must be in (0, 1].")
        if not (0.0 < self.subsample <= 1.0):
            raise ConfigValidationError("subsample must be in (0, 1].")
        if not (0.0 < self.colsample_bytree <= 1.0):
            raise ConfigValidationError("colsample_bytree must be in (0, 1].")
        if self.tree_method not in ("hist", "approx", "exact"):
            raise ConfigValidationError("tree_method must be one of: hist, approx, exact.")
        if self.early_stopping_rounds is not None and self.early_stopping_rounds <= 0:
            raise ConfigValidationError("early_stopping_rounds must be > 0 or None.")
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

    @property
    def device(self) -> str:
        return "cuda" if self.use_gpu else "cpu"
