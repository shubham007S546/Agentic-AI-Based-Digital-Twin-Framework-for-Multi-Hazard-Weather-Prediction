"""TwoStageRainfallModel: composes a "did it rain" classifier with a
"how much" regressor, reusing the existing RandomForest/XGBoost/LightGBM
BaseModel implementations rather than duplicating them."""

from __future__ import annotations

from typing import Any, Optional, Tuple, Type

import numpy as np
import pandas as pd

from models.common.base_model import BaseModel
from models.common.config_schema import BaseModelConfig, TaskType
from models.common.exceptions import ModelNotFittedError, TrainingError
from models.common.logging_config import get_logger
from models.common.serialization import load_artifact, save_artifact

from .config import TwoStageRainfallConfig

logger = get_logger(__name__)


def _get_algorithm(name: str) -> Tuple[Type[BaseModelConfig], Type[BaseModel]]:
    """Return (ConfigClass, ModelClass) for 'random_forest' | 'xgboost' | 'lightgbm'."""
    if name == "random_forest":
        from models.machine_learning.random_forest.config import RandomForestConfig
        from models.machine_learning.random_forest.model import RandomForestModel
        return RandomForestConfig, RandomForestModel
    if name == "xgboost":
        from models.machine_learning.xgboost.config import XGBoostConfig
        from models.machine_learning.xgboost.model import XGBoostModel
        return XGBoostConfig, XGBoostModel
    if name == "lightgbm":
        from models.machine_learning.lightgbm.config import LightGBMConfig
        from models.machine_learning.lightgbm.model import LightGBMModel
        return LightGBMConfig, LightGBMModel
    raise ValueError(f"Unknown algorithm: {name!r}")


def _build_sub_config(base: TwoStageRainfallConfig, algorithm: str, task_type: TaskType) -> BaseModelConfig:
    """Build a fully-formed sub-model config (RandomForestConfig / XGBoostConfig /
    LightGBMConfig) inheriting the shared fields from the two-stage config."""
    config_cls, _ = _get_algorithm(algorithm)
    sub_config = config_cls(
        task_type=task_type,
        data_dir=base.data_dir,
        target_column=base.target_column,
        random_seed=base.random_seed,
        n_jobs=base.n_jobs,
        use_sample_weights=base.use_sample_weights,
        use_class_weights=False,  # stage 1/2 sub-models don't read class_weights.json directly
        experiment_name=base.experiment_name,
        artifacts_dir=base.artifacts_dir,
    )
    return sub_config


class TwoStageRainfallModel:
    """
    Not a BaseModel subclass -- it composes two of them (a classifier and a
    regressor), which have different task types and different fit/predict
    contracts, so it exposes its own fit/predict/save/load instead.
    """

    def __init__(self, config: TwoStageRainfallConfig):
        self.config = config
        self._classifier: Optional[BaseModel] = None
        self._regressor: Optional[BaseModel] = None
        self._is_fitted = False

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        sample_weight: Optional[np.ndarray] = None,
        X_val: Optional[pd.DataFrame] = None,
        y_val: Optional[pd.Series] = None,
    ) -> "TwoStageRainfallModel":
        cfg = self.config
        rain_occurred = (y > cfg.rain_threshold).astype(int)

        if rain_occurred.nunique() < 2:
            raise TrainingError(
                f"rain_threshold={cfg.rain_threshold} produces a single class in the "
                f"training target ({rain_occurred.unique().tolist()}). Lower the threshold "
                "or check that the target column really is imd_rainfall_mm."
            )

        # ---- Stage 1: did it rain? ----
        clf_config_cls, clf_model_cls = _get_algorithm(cfg.classifier_algorithm)
        clf_config = _build_sub_config(cfg, cfg.classifier_algorithm, TaskType.BINARY_CLASSIFICATION)
        clf_config.validate()
        self._classifier = clf_model_cls(clf_config)

        clf_eval_set = None
        if X_val is not None and y_val is not None:
            clf_eval_set = [(X_val, (y_val > cfg.rain_threshold).astype(int))]

        logger.info(
            "Stage 1 (%s classifier): %d/%d rows rain > %.3f",
            cfg.classifier_algorithm, int(rain_occurred.sum()), len(rain_occurred), cfg.rain_threshold,
        )
        if cfg.classifier_algorithm == "random_forest":
            self._classifier.fit(X, rain_occurred, sample_weight=sample_weight)
        else:
            self._classifier.fit(X, rain_occurred, sample_weight=sample_weight, eval_set=clf_eval_set)

        # ---- Stage 2: how much, given it rained? ----
        mask = rain_occurred == 1
        X_rain = X.loc[mask]
        y_rain = y.loc[mask]
        y_rain_transformed = np.log1p(y_rain) if cfg.log_transform else y_rain
        sw_rain = sample_weight[mask.to_numpy()] if sample_weight is not None else None

        reg_config = _build_sub_config(cfg, cfg.regressor_algorithm, TaskType.REGRESSION)
        reg_config.validate()
        self._regressor = _get_algorithm(cfg.regressor_algorithm)[1](reg_config)

        reg_eval_set = None
        if X_val is not None and y_val is not None:
            val_mask = y_val > cfg.rain_threshold
            if val_mask.sum() > 0:
                y_val_t = np.log1p(y_val.loc[val_mask]) if cfg.log_transform else y_val.loc[val_mask]
                reg_eval_set = [(X_val.loc[val_mask], y_val_t)]

        logger.info("Stage 2 (%s regressor): fitting on %d rainy rows.", cfg.regressor_algorithm, len(X_rain))
        if cfg.regressor_algorithm == "random_forest":
            self._regressor.fit(X_rain, y_rain_transformed, sample_weight=sw_rain)
        else:
            self._regressor.fit(X_rain, y_rain_transformed, sample_weight=sw_rain, eval_set=reg_eval_set)

        self._is_fitted = True
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Final combined prediction: 0 where stage 1 says 'no rain', else
        stage 2's (inverse-transformed) amount."""
        self._check_fitted()
        cfg = self.config

        if hasattr(self._classifier.estimator, "predict_proba"):
            proba_rain = self._classifier.predict_proba(X)[:, 1]
            rain_pred = (proba_rain >= cfg.classification_threshold).astype(int)
        else:
            rain_pred = self._classifier.predict(X)

        output = np.zeros(len(X), dtype=float)
        rain_idx = np.where(rain_pred == 1)[0]
        if len(rain_idx) > 0:
            X_rain = X.iloc[rain_idx]
            reg_pred = self._regressor.predict(X_rain)
            if cfg.log_transform:
                reg_pred = np.expm1(reg_pred)
            reg_pred = np.clip(reg_pred, a_min=0, a_max=None)
            output[rain_idx] = reg_pred
        return output

    def predict_rain_probability(self, X: pd.DataFrame) -> np.ndarray:
        """Stage 1's raw probability of rain, useful for early-warning thresholds
        separate from the point-estimate amount."""
        self._check_fitted()
        if not hasattr(self._classifier.estimator, "predict_proba"):
            raise TrainingError(f"{self.config.classifier_algorithm} classifier has no predict_proba.")
        return self._classifier.predict_proba(X)[:, 1]

    def save(self, path: str) -> None:
        self._check_fitted()
        save_artifact(
            {"classifier": self._classifier.estimator, "regressor": self._regressor.estimator},
            path,
            metadata={
                "model_class": self.__class__.__name__,
                "config": {k: v for k, v in self.config.__dict__.items()},
            },
        )
        logger.info("Saved two-stage rainfall pipeline to %s", path)

    def load(self, path: str) -> "TwoStageRainfallModel":
        cfg = self.config
        payload = load_artifact(path)

        clf_config = _build_sub_config(cfg, cfg.classifier_algorithm, TaskType.BINARY_CLASSIFICATION)
        reg_config = _build_sub_config(cfg, cfg.regressor_algorithm, TaskType.REGRESSION)

        self._classifier = _get_algorithm(cfg.classifier_algorithm)[1](clf_config)
        self._classifier._estimator = payload["classifier"]
        self._classifier._is_fitted = True

        self._regressor = _get_algorithm(cfg.regressor_algorithm)[1](reg_config)
        self._regressor._estimator = payload["regressor"]
        self._regressor._is_fitted = True

        self._is_fitted = True
        logger.info("Loaded two-stage rainfall pipeline from %s", path)
        return self

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def _check_fitted(self) -> None:
        if not self._is_fitted:
            raise ModelNotFittedError("TwoStageRainfallModel must be fit (or loaded) before this operation.")
