"""
BaseEvaluator: computes metrics, feature importance, permutation importance,
and SHAP values for a fitted BaseModel. Shared by every algorithm's
evaluate.py.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)

from .base_model import BaseModel
from .config_schema import BaseModelConfig, TaskType
from .exceptions import ModelNotFittedError
from .logging_config import get_logger

logger = get_logger(__name__)


class BaseEvaluator:
    """Task-aware evaluation utilities: regression or classification metrics,
    feature importance, permutation importance, and SHAP -- all algorithm
    agnostic since they operate on the fitted estimator through BaseModel."""

    def __init__(self, model: BaseModel, config: BaseModelConfig):
        self.model = model
        self.config = config

    # ------------------------------------------------------------------ #
    def compute_metrics(self, X: pd.DataFrame, y: pd.Series) -> dict:
        if not self.model.is_fitted:
            raise ModelNotFittedError("Cannot evaluate an unfitted model.")

        y_pred = self.model.predict(X)

        if self.config.task_type == TaskType.REGRESSION:
            return {
                "rmse": float(np.sqrt(mean_squared_error(y, y_pred))),
                "mae": float(mean_absolute_error(y, y_pred)),
                "r2": float(r2_score(y, y_pred)),
                "n_samples": int(len(y)),
            }

        # classification (binary or multiclass)
        average = "binary" if self.config.task_type == TaskType.BINARY_CLASSIFICATION else "macro"
        metrics = {
            "accuracy": float(accuracy_score(y, y_pred)),
            "precision": float(precision_score(y, y_pred, average=average, zero_division=0)),
            "recall": float(recall_score(y, y_pred, average=average, zero_division=0)),
            "f1": float(f1_score(y, y_pred, average=average, zero_division=0)),
            "n_samples": int(len(y)),
        }

        if hasattr(self.model.estimator, "predict_proba"):
            try:
                proba = self.model.predict_proba(X)
                if self.config.task_type == TaskType.BINARY_CLASSIFICATION:
                    metrics["roc_auc"] = float(roc_auc_score(y, proba[:, 1]))
                else:
                    metrics["roc_auc_ovr"] = float(
                        roc_auc_score(y, proba, multi_class="ovr", average="macro")
                    )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Could not compute ROC-AUC: %s", exc)

        return metrics

    # ------------------------------------------------------------------ #
    def feature_importance(self, feature_names: Optional[list] = None) -> pd.Series:
        return self.model.get_feature_importance(feature_names)

    def permutation_importance(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        n_repeats: int = 10,
        n_jobs: Optional[int] = None,
    ) -> pd.DataFrame:
        if not self.model.is_fitted:
            raise ModelNotFittedError("Cannot compute permutation importance on an unfitted model.")

        scoring = "r2" if self.config.task_type == TaskType.REGRESSION else "f1_weighted"
        result = permutation_importance(
            self.model.estimator,
            X,
            y,
            n_repeats=n_repeats,
            random_state=self.config.random_seed,
            n_jobs=n_jobs if n_jobs is not None else self.config.n_jobs,
            scoring=scoring,
        )
        return pd.DataFrame(
            {
                "feature": X.columns,
                "importance_mean": result.importances_mean,
                "importance_std": result.importances_std,
            }
        ).sort_values("importance_mean", ascending=False).reset_index(drop=True)

    # ------------------------------------------------------------------ #
    def shap_values(self, X: pd.DataFrame, max_samples: int = 500) -> Any:
        """
        Compute SHAP values using shap.TreeExplainer (valid for RandomForest,
        XGBoost, and LightGBM alike, since they are all tree ensembles).
        Returns the raw shap.Explanation object; the caller (evaluate.py)
        decides how to plot/save it.
        """
        if not self.model.is_fitted:
            raise ModelNotFittedError("Cannot compute SHAP values on an unfitted model.")

        try:
            import shap
        except ImportError as exc:
            raise ImportError(
                "The 'shap' package is required for SHAP explainability. "
                "Install it with: pip install shap"
            ) from exc

        X_sample = X.sample(n=min(max_samples, len(X)), random_state=self.config.random_seed)
        explainer = shap.TreeExplainer(self.model.estimator)
        return explainer(X_sample)
