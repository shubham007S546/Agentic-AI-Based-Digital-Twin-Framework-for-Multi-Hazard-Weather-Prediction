"""Configuration for the Random Forest model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.common.config_schema import BaseModelConfig
from models.common.exceptions import ConfigValidationError


@dataclass
class RandomForestConfig(BaseModelConfig):
    """
    Random Forest specific hyperparameters, on top of the shared fields in
    BaseModelConfig (task_type, data_dir, target_column, random_seed, n_jobs,
    use_sample_weights, use_class_weights, experiment_name, artifacts_dir).
    """

    model_name: str = "random_forest"

    n_estimators: int = 300
    max_depth: Optional[int] = None
    min_samples_split: int = 2
    min_samples_leaf: int = 1
    max_features: str = "sqrt"          # "sqrt", "log2", float, int, or None
    bootstrap: bool = True
    oob_score: bool = True              # only valid when bootstrap=True
    criterion: Optional[str] = None      # None -> pick a sensible default per task
    class_weight_mode: str = "balanced"  # "balanced", "balanced_subsample", or "none"

    def validate(self) -> None:
        super().validate()

        if self.n_estimators <= 0:
            raise ConfigValidationError("n_estimators must be > 0.")
        if self.max_depth is not None and self.max_depth <= 0:
            raise ConfigValidationError("max_depth must be > 0 or None.")
        if self.min_samples_split < 2:
            raise ConfigValidationError("min_samples_split must be >= 2.")
        if self.min_samples_leaf < 1:
            raise ConfigValidationError("min_samples_leaf must be >= 1.")
        if self.oob_score and not self.bootstrap:
            raise ConfigValidationError("oob_score=True requires bootstrap=True.")
        if self.class_weight_mode not in ("balanced", "balanced_subsample", "none"):
            raise ConfigValidationError(
                "class_weight_mode must be one of: balanced, balanced_subsample, none."
            )
