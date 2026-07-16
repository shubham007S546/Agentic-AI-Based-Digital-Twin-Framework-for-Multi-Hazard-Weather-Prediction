"""Configuration for the ensemble package (stacking / voting / weighted-average
over random_forest + xgboost + lightgbm, and optionally deep_learning)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from models.common.config_schema import BaseModelConfig
from models.common.exceptions import ConfigValidationError

_VALID_ALGORITHMS = ("random_forest", "xgboost", "lightgbm", "deep_learning")
_VALID_METHODS = ("stacking", "voting", "weighted_average")
_VALID_META_LEARNERS = ("ridge", "logistic")


@dataclass
class EnsembleConfig(BaseModelConfig):
    """
    Ensemble-specific hyperparameters, on top of the shared fields in
    BaseModelConfig.

    method="stacking" (recommended, usually the most accurate):
        Each base algorithm's out-of-fold predictions on the TRAIN split
        become features for a meta-learner (Ridge for regression, Logistic
        Regression for classification), which learns how to best combine
        them. Base models are then refit on the full train split for use
        at inference time. Out-of-fold (rather than in-sample) predictions
        are what prevent the meta-learner from just learning to trust
        whichever base model overfit train the hardest.

    method="voting":
        Plain unweighted average (regression) / majority vote or averaged
        probabilities (classification) across base models. No meta-learner,
        no CV -- fastest and hardest to overfit, but leaves accuracy on the
        table versus stacking.

    method="weighted_average":
        Like voting, but each base model is weighted. If `weights` is not
        given explicitly, weights are auto-derived from each base model's
        validation performance (inverse RMSE for regression, accuracy for
        classification) -- so a base model that validates poorly counts for
        less.
    """

    model_name: str = "ensemble"

    base_algorithms: List[str] = field(default_factory=lambda: ["random_forest", "xgboost", "lightgbm"])
    ensemble_method: str = "stacking"          # "stacking" | "voting" | "weighted_average"
    meta_learner: str = "ridge"                # "ridge" | "logistic" -- stacking only
    meta_learner_alpha: float = 1.0            # ridge regularization strength
    cv_folds: int = 5                          # out-of-fold splits for stacking
    weights: Optional[List[float]] = None      # weighted_average only; same order as base_algorithms
    use_proba_for_classification_stacking: bool = True

    def validate(self) -> None:
        super().validate()

        if not self.base_algorithms:
            raise ConfigValidationError("base_algorithms must not be empty.")
        if len(self.base_algorithms) < 2:
            raise ConfigValidationError("Ensembles need at least 2 base_algorithms.")
        for algo in self.base_algorithms:
            if algo not in _VALID_ALGORITHMS:
                raise ConfigValidationError(
                    f"Unknown base algorithm {algo!r}. Must be one of {_VALID_ALGORITHMS}."
                )
        if len(set(self.base_algorithms)) != len(self.base_algorithms):
            raise ConfigValidationError("base_algorithms must not contain duplicates.")
        if self.ensemble_method not in _VALID_METHODS:
            raise ConfigValidationError(f"ensemble_method must be one of {_VALID_METHODS}.")
        if self.meta_learner not in _VALID_META_LEARNERS:
            raise ConfigValidationError(f"meta_learner must be one of {_VALID_META_LEARNERS}.")
        # meta_learner is really determined by task_type (Ridge only makes sense for a
        # continuous target, Logistic only for a class label) -- auto-correct rather
        # than hard-fail, same pattern as target_transform/use_class_weights above.
        correct_meta_learner = "logistic" if self.is_classification else "ridge"
        if self.meta_learner != correct_meta_learner:
            self.meta_learner = correct_meta_learner

        if self.cv_folds < 2:
            raise ConfigValidationError("cv_folds must be >= 2.")
        if self.weights is not None:
            if len(self.weights) != len(self.base_algorithms):
                raise ConfigValidationError("weights must have the same length as base_algorithms.")
            if any(w < 0 for w in self.weights):
                raise ConfigValidationError("weights must be >= 0.")
            if sum(self.weights) <= 0:
                raise ConfigValidationError("weights must sum to > 0.")
