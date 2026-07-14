"""XGBoost model wrapper, task-aware (regression / binary / multiclass)."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd
from xgboost import XGBClassifier, XGBRegressor

from models.common.base_model import BaseModel
from models.common.config_schema import TaskType
from models.common.logging_config import get_logger

from .config import XGBoostConfig

logger = get_logger(__name__)


class XGBoostModel(BaseModel):
    """Wraps XGBRegressor / XGBClassifier behind BaseModel, with early
    stopping on a validation eval_set and native NaN handling."""

    def __init__(self, config: XGBoostConfig):
        super().__init__(config)
        self.config: XGBoostConfig = config
        self._class_weight_lookup: Optional[dict] = None

    def _build_estimator(self, params: Optional[dict] = None) -> Any:
        cfg = self.config
        overrides = params or {}

        kwargs = dict(
            n_estimators=overrides.get("n_estimators", cfg.n_estimators),
            max_depth=overrides.get("max_depth", cfg.max_depth),
            learning_rate=overrides.get("learning_rate", cfg.learning_rate),
            subsample=overrides.get("subsample", cfg.subsample),
            colsample_bytree=overrides.get("colsample_bytree", cfg.colsample_bytree),
            min_child_weight=overrides.get("min_child_weight", cfg.min_child_weight),
            reg_alpha=overrides.get("reg_alpha", cfg.reg_alpha),
            reg_lambda=overrides.get("reg_lambda", cfg.reg_lambda),
            gamma=overrides.get("gamma", cfg.gamma),
            tree_method=overrides.get("tree_method", cfg.tree_method),
            device=cfg.device,
            missing=cfg.missing_value,
            random_state=cfg.random_seed,
            n_jobs=cfg.n_jobs,
        )

        if cfg.early_stopping_rounds is not None and cfg.use_validation_for_early_stopping:
            kwargs["early_stopping_rounds"] = overrides.get(
                "early_stopping_rounds", cfg.early_stopping_rounds
            )

        if cfg.task_type == TaskType.REGRESSION:
            if cfg.tweedie_variance_power is not None:
                kwargs["objective"] = "reg:tweedie"
                kwargs["tweedie_variance_power"] = overrides.get(
                    "tweedie_variance_power", cfg.tweedie_variance_power
                )
                kwargs["eval_metric"] = overrides.get("eval_metric", cfg.eval_metric or "tweedie-nloglik@1.5")
            else:
                kwargs["eval_metric"] = overrides.get("eval_metric", cfg.eval_metric or "rmse")
            return XGBRegressor(**kwargs)

        if cfg.task_type == TaskType.BINARY_CLASSIFICATION:
            kwargs["eval_metric"] = overrides.get("eval_metric", cfg.eval_metric or "logloss")
            spw = overrides.get("scale_pos_weight", cfg.scale_pos_weight)
            if spw is None and self._class_weight_lookup:
                w0 = self._class_weight_lookup.get(0, 1.0)
                w1 = self._class_weight_lookup.get(1, 1.0)
                spw = w1 / w0 if w0 else 1.0
            if spw is not None:
                kwargs["scale_pos_weight"] = spw
            return XGBClassifier(**kwargs)

        # multiclass
        kwargs["eval_metric"] = overrides.get("eval_metric", cfg.eval_metric or "mlogloss")
        return XGBClassifier(**kwargs)

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        sample_weight: Optional[np.ndarray] = None,
        eval_set: Optional[list] = None,
        class_weights: Optional[dict] = None,
        **fit_kwargs: Any,
    ) -> "XGBoostModel":
        """
        Extends BaseModel.fit with:
          - `class_weights`: {label: weight} used to derive scale_pos_weight
            for binary classification if not explicitly set in config.
          - native `eval_set` support for early stopping.
        """
        self._class_weight_lookup = class_weights
        if self._estimator is None:
            self.build()

        y_fit = self._transform_target(y)
        eval_set_fit = [(ex, self._transform_target(ey)) for ex, ey in eval_set] if eval_set is not None else None

        fit_params: dict = dict(fit_kwargs)
        if sample_weight is not None:
            fit_params["sample_weight"] = sample_weight
        if eval_set_fit is not None:
            fit_params["eval_set"] = eval_set_fit
            fit_params["verbose"] = fit_kwargs.get("verbose", False)

        self._estimator.fit(X, y_fit, **fit_params)
        self._is_fitted = True
        return self

    def get_best_iteration(self) -> Optional[int]:
        self._check_fitted()
        return getattr(self._estimator, "best_iteration", None)
