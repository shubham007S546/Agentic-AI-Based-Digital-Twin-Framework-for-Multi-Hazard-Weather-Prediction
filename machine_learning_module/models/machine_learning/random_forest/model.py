"""Random Forest model wrapper, task-aware (regression / binary / multiclass)."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

from models.common.base_model import BaseModel
from models.common.config_schema import TaskType
from models.common.exceptions import TrainingError
from models.common.logging_config import get_logger

from .config import RandomForestConfig

logger = get_logger(__name__)


class RandomForestModel(BaseModel):
    """Wraps RandomForestRegressor / RandomForestClassifier behind BaseModel."""

    def __init__(self, config: RandomForestConfig):
        super().__init__(config)
        self.config: RandomForestConfig = config

    def _build_estimator(self, params: Optional[dict] = None) -> Any:
        cfg = self.config
        overrides = params or {}

        kwargs = dict(
            n_estimators=overrides.get("n_estimators", cfg.n_estimators),
            max_depth=overrides.get("max_depth", cfg.max_depth),
            min_samples_split=overrides.get("min_samples_split", cfg.min_samples_split),
            min_samples_leaf=overrides.get("min_samples_leaf", cfg.min_samples_leaf),
            max_features=overrides.get("max_features", cfg.max_features),
            bootstrap=overrides.get("bootstrap", cfg.bootstrap),
            oob_score=overrides.get("oob_score", cfg.oob_score) and cfg.bootstrap,
            random_state=cfg.random_seed,
            n_jobs=cfg.n_jobs,
        )

        if cfg.task_type == TaskType.REGRESSION:
            kwargs["criterion"] = overrides.get("criterion", cfg.criterion or "squared_error")
            return RandomForestRegressor(**kwargs)

        # classification (binary or multiclass)
        kwargs["criterion"] = overrides.get("criterion", cfg.criterion or "gini")
        class_weight_mode = overrides.get("class_weight_mode", cfg.class_weight_mode)
        if class_weight_mode != "none":
            kwargs["class_weight"] = class_weight_mode
        return RandomForestClassifier(**kwargs)

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        sample_weight: Optional[np.ndarray] = None,
        eval_set: Optional[list] = None,
        **fit_kwargs: Any,
    ) -> "RandomForestModel":
        # RandomForest has no native eval_set / early stopping, so it is
        # deliberately dropped here rather than raising, keeping train.py
        # identical across all three algorithms.
        if eval_set is not None:
            logger.debug("RandomForest ignores eval_set (no early stopping support).")
        return super().fit(X, y, sample_weight=sample_weight, eval_set=None, **fit_kwargs)

    def get_oob_score(self) -> Optional[float]:
        self._check_fitted()
        return getattr(self._estimator, "oob_score_", None)
