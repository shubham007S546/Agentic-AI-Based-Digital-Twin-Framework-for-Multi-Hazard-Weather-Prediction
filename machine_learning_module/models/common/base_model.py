"""
BaseModel / BasePredictor contracts.

Every algorithm's model.py (random_forest/model.py, xgboost/model.py,
lightgbm/model.py) defines a concrete class that subclasses BaseModel and
implements `_build_estimator`. Everything else (fit/predict/save/load/
feature_importance plumbing) is handled here so behaviour stays identical
across algorithms.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

import numpy as np
import pandas as pd

from .config_schema import BaseModelConfig, TaskType
from .exceptions import ModelNotFittedError, TrainingError
from .logging_config import get_logger
from .serialization import load_artifact, save_artifact

logger = get_logger(__name__)


class BaseModel(ABC):
    """
    Wraps a single underlying estimator (sklearn / xgboost / lightgbm) behind
    a uniform interface so Trainer/Evaluator/Predictor/Tuner code never has
    to branch on which algorithm is being used.
    """

    def __init__(self, config: BaseModelConfig):
        self.config = config
        self._estimator: Any = None
        self._is_fitted: bool = False

    # ------------------------------------------------------------------ #
    # Subclasses MUST implement this.
    # ------------------------------------------------------------------ #
    @abstractmethod
    def _build_estimator(self, params: Optional[dict] = None) -> Any:
        """
        Construct and return the underlying estimator instance
        (e.g. RandomForestRegressor, XGBClassifier, LGBMRegressor)
        using `self.config` and, if given, an override `params` dict
        (used by the hyperparameter tuner to try new hyperparameter sets
        without mutating self.config).
        """
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # Shared behaviour.
    # ------------------------------------------------------------------ #
    def build(self, params: Optional[dict] = None) -> "BaseModel":
        """(Re)build the underlying estimator. Does not fit."""
        self._estimator = self._build_estimator(params)
        self._is_fitted = False
        return self

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        sample_weight: Optional[np.ndarray] = None,
        eval_set: Optional[list] = None,
        **fit_kwargs: Any,
    ) -> "BaseModel":
        """
        Fit the underlying estimator. `eval_set` (list of (X, y) tuples) and
        extra `fit_kwargs` are passed through as-is, which lets xgboost/
        lightgbm subclasses use early_stopping_rounds etc. Estimators that
        don't accept these (e.g. RandomForest) should have their model.py
        strip unsupported kwargs before calling super().fit(...).

        If `config.target_transform == "log1p"`, y (and each eval_set y) is
        transformed with log1p before fitting; predict() inverse-transforms
        with expm1 automatically.
        """
        if self._estimator is None:
            self.build()

        y_fit = self._transform_target(y)
        eval_set_fit = None
        if eval_set is not None:
            eval_set_fit = [(ex, self._transform_target(ey)) for ex, ey in eval_set]

        fit_params: dict = dict(fit_kwargs)
        if sample_weight is not None:
            fit_params["sample_weight"] = sample_weight
        if eval_set_fit is not None:
            fit_params["eval_set"] = eval_set_fit

        try:
            self._estimator.fit(X, y_fit, **fit_params)
        except TypeError:
            # estimator doesn't accept one of the extra kwargs (e.g. plain
            # RandomForest has no eval_set) -- retry with just sample_weight.
            fallback_params = {}
            if sample_weight is not None:
                fallback_params["sample_weight"] = sample_weight
            self._estimator.fit(X, y_fit, **fallback_params)
        except Exception as exc:
            raise TrainingError(f"Failed to fit {self.__class__.__name__}: {exc}") from exc

        self._is_fitted = True
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        self._check_fitted()
        raw = self._estimator.predict(X)
        return self._inverse_transform_target(raw)

    def _transform_target(self, y: pd.Series) -> pd.Series:
        if self.config.task_type == TaskType.REGRESSION and self.config.target_transform == "log1p":
            return np.log1p(y)
        return y

    def _inverse_transform_target(self, pred: np.ndarray) -> np.ndarray:
        if self.config.task_type == TaskType.REGRESSION and self.config.target_transform == "log1p":
            return np.expm1(pred)
        return pred

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        self._check_fitted()
        if not self.config.is_classification:
            raise TrainingError("predict_proba is only valid for classification tasks.")
        if not hasattr(self._estimator, "predict_proba"):
            raise TrainingError(
                f"Underlying estimator {type(self._estimator).__name__} has no predict_proba."
            )
        return self._estimator.predict_proba(X)

    def get_feature_importance(self, feature_names: Optional[list] = None) -> pd.Series:
        """Return native feature_importances_ as a sorted pandas Series."""
        self._check_fitted()
        if not hasattr(self._estimator, "feature_importances_"):
            raise TrainingError(
                f"{type(self._estimator).__name__} does not expose feature_importances_."
            )
        importances = self._estimator.feature_importances_
        names = feature_names or [f"f{i}" for i in range(len(importances))]
        return pd.Series(importances, index=names).sort_values(ascending=False)

    def save(self, path: str) -> None:
        self._check_fitted()
        save_artifact(
            self._estimator,
            path,
            metadata={
                "model_class": self.__class__.__name__,
                "task_type": self.config.task_type.value,
                "config": self.config.__dict__,
            },
        )
        logger.info("Saved fitted %s to %s", self.__class__.__name__, path)

    def load(self, path: str) -> "BaseModel":
        self._estimator = load_artifact(path)
        self._is_fitted = True
        logger.info("Loaded %s from %s", self.__class__.__name__, path)
        return self

    @property
    def estimator(self) -> Any:
        return self._estimator

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def _check_fitted(self) -> None:
        if not self._is_fitted or self._estimator is None:
            raise ModelNotFittedError(
                f"{self.__class__.__name__} must be fit (or loaded) before this operation."
            )


class BasePredictor:
    """
    Thin inference-only wrapper around a saved BaseModel artifact. Used by
    predict.py in each algorithm folder so batch/production inference does
    not need training-time dependencies (Trainer, Tuner, etc.).
    """

    def __init__(self, model: BaseModel):
        self.model = model

    @classmethod
    def from_artifact(cls, model_cls: type, config: BaseModelConfig, path: str) -> "BasePredictor":
        instance = model_cls(config)
        instance.load(path)
        return cls(instance)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict(X)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(X)

    def predict_dataframe(self, X: pd.DataFrame, output_column: str = "prediction") -> pd.DataFrame:
        """Return a copy of X with an added prediction column (and, for
        classification, one probability column per class)."""
        result = X.copy()
        result[output_column] = self.predict(X)
        if self.model.config.is_classification and hasattr(self.model.estimator, "predict_proba"):
            proba = self.predict_proba(X)
            for i in range(proba.shape[1]):
                result[f"{output_column}_proba_class_{i}"] = proba[:, i]
        return result
