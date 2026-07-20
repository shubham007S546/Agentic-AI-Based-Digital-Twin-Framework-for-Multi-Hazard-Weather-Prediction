"""LightGBM model wrapper, task-aware (regression / binary / multiclass)."""

from __future__ import annotations

from typing import Any, Optional

import lightgbm as lgb
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor

from models.common.base_model import BaseModel
from models.common.config_schema import TaskType
from models.common.logging_config import get_logger

from .config import LightGBMConfig

logger = get_logger(__name__)


class LightGBMModel(BaseModel):
    """Wraps LGBMRegressor / LGBMClassifier behind BaseModel, with
    leaf-wise growth, categorical feature support, and early stopping via
    the `lightgbm.early_stopping` callback."""

    def __init__(self, config: LightGBMConfig):
        super().__init__(config)
        self.config: LightGBMConfig = config
        self._class_weight_lookup: Optional[dict] = None

    def _build_estimator(self, params: Optional[dict] = None) -> Any:
        cfg = self.config
        overrides = params or {}

        kwargs = dict(
            n_estimators=overrides.get("n_estimators", cfg.n_estimators),
            num_leaves=overrides.get("num_leaves", cfg.num_leaves),
            max_depth=overrides.get("max_depth", cfg.max_depth),
            learning_rate=overrides.get("learning_rate", cfg.learning_rate),
            subsample=overrides.get("subsample", cfg.subsample),
            subsample_freq=overrides.get("subsample_freq", cfg.subsample_freq),
            colsample_bytree=overrides.get("colsample_bytree", cfg.colsample_bytree),
            min_child_samples=overrides.get("min_child_samples", cfg.min_child_samples),
            reg_alpha=overrides.get("reg_alpha", cfg.reg_alpha),
            reg_lambda=overrides.get("reg_lambda", cfg.reg_lambda),
            device=cfg.device,
            random_state=cfg.random_seed,
            n_jobs=cfg.n_jobs,
            verbosity=-1,
        )

        if cfg.task_type == TaskType.REGRESSION:
            if cfg.tweedie_variance_power is not None:
                kwargs["objective"] = "tweedie"
                kwargs["tweedie_variance_power"] = overrides.get(
                    "tweedie_variance_power", cfg.tweedie_variance_power
                )
            return LGBMRegressor(**kwargs)

        if cfg.task_type == TaskType.BINARY_CLASSIFICATION:
            spw = overrides.get("scale_pos_weight", cfg.scale_pos_weight)
            if spw is None and self._class_weight_lookup and not cfg.is_unbalance:
                w0 = self._class_weight_lookup.get(0, 1.0)
                w1 = self._class_weight_lookup.get(1, 1.0)
                spw = w1 / w0 if w0 else 1.0
            if cfg.is_unbalance:
                kwargs["is_unbalance"] = True
            elif spw is not None:
                kwargs["scale_pos_weight"] = spw
            return LGBMClassifier(**kwargs)

        # multiclass
        return LGBMClassifier(**kwargs)

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        sample_weight: Optional[np.ndarray] = None,
        eval_set: Optional[list] = None,
        class_weights: Optional[dict] = None,
        **fit_kwargs: Any,
    ) -> "LightGBMModel":
        """
        Extends BaseModel.fit with:
          - `class_weights`: used to derive scale_pos_weight for binary
            classification if not explicitly set / not using is_unbalance.
          - native `eval_set` + `lightgbm.early_stopping` callback support.
          - `categorical_feature` passed through from config.
        """
        self._class_weight_lookup = class_weights
        if self._estimator is None:
            self.build()

        cfg = self.config
        y_fit = self._transform_target(y)
        eval_set_fit = [(ex, self._transform_target(ey)) for ex, ey in eval_set] if eval_set is not None else None

        fit_params: dict = dict(fit_kwargs)
        if sample_weight is not None:
            fit_params["sample_weight"] = sample_weight

        if cfg.categorical_features:
            fit_params["categorical_feature"] = cfg.categorical_features

        eval_metric = cfg.eval_metric or (
            "tweedie" if cfg.tweedie_variance_power is not None
            else "rmse" if cfg.task_type == TaskType.REGRESSION
            else "binary_logloss" if cfg.task_type == TaskType.BINARY_CLASSIFICATION
            else "multi_logloss"
        )
        fit_params["eval_metric"] = eval_metric

        callbacks = list(fit_kwargs.get("callbacks", []))
        if eval_set_fit is not None:
            fit_params["eval_set"] = eval_set_fit
            if cfg.early_stopping_rounds is not None and cfg.use_validation_for_early_stopping:
                callbacks.append(lgb.early_stopping(cfg.early_stopping_rounds, verbose=False))
        if callbacks:
            fit_params["callbacks"] = callbacks

        self._estimator.fit(X, y_fit, **fit_params)
        self._is_fitted = True
        return self

    def get_best_iteration(self) -> Optional[int]:
        self._check_fitted()
        return getattr(self._estimator, "best_iteration_", None)
