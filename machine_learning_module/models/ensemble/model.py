"""
Ensemble model wrapper: composes random_forest / xgboost / lightgbm (and
optionally deep_learning) base models behind a single BaseModel, the same
way TwoStageRainfallModel composes a classifier + regressor -- except here
all base models share the same task_type and are combined via stacking,
voting, or weighted averaging rather than being sequential stages.

Design note
-----------
Like DeepLearningModel, this only implements `_build_estimator`; BaseModel.
fit/predict (unmodified) handle log1p target-transform / sample_weight
plumbing generically by forwarding to `self._estimator.fit/.predict`. So
--target-transform log1p on the ensemble CLI transforms y once, in the
same log-space every base model and the meta-learner then train in --
there's no risk of double-transforming since base sub-configs are built
with target_transform="none" (see `_build_sub_config`).
"""

from __future__ import annotations

from typing import Any, Optional, Tuple, Type

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, mean_squared_error
from sklearn.model_selection import KFold, StratifiedKFold

from models.common.base_model import BaseModel
from models.common.config_schema import BaseModelConfig, TaskType
from models.common.exceptions import TrainingError
from models.common.logging_config import get_logger

from .config import EnsembleConfig

logger = get_logger(__name__)


def _get_algorithm(name: str) -> Tuple[Type[BaseModelConfig], Type[BaseModel]]:
    """Return (ConfigClass, ModelClass) for a base algorithm name."""
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
    if name == "deep_learning":
        from models.deep_learning.config import DeepLearningConfig
        from models.deep_learning.model import DeepLearningModel
        return DeepLearningConfig, DeepLearningModel
    raise ValueError(f"Unknown base algorithm: {name!r}")


def _build_sub_config(base: EnsembleConfig, algorithm: str, enable_early_stopping: bool = True) -> BaseModelConfig:
    """Build a fully-formed sub-model config inheriting shared fields from the
    ensemble config. target_transform is deliberately left at 'none' -- the
    ensemble applies it once, at the BaseModel level (see module docstring).

    enable_early_stopping=False turns off xgboost/lightgbm's native early
    stopping (which otherwise defaults on and requires an eval_set) -- needed
    during stacking's CV folds, where no held-out validation split exists.
    """
    config_cls, _ = _get_algorithm(algorithm)
    sub_config = config_cls(
        task_type=base.task_type,
        data_dir=base.data_dir,
        target_column=base.target_column,
        random_seed=base.random_seed,
        n_jobs=base.n_jobs,
        use_sample_weights=base.use_sample_weights,
        use_class_weights=False,
        experiment_name=base.experiment_name,
        artifacts_dir=base.artifacts_dir,
    )
    if not enable_early_stopping and hasattr(sub_config, "early_stopping_rounds"):
        sub_config.early_stopping_rounds = None
    return sub_config


class EnsembleEstimator:
    """Duck-typed sklearn-style estimator combining several BaseModel
    instances via stacking / voting / weighted_average."""

    def __init__(self, config: EnsembleConfig):
        self.cfg = config
        self.base_models_: dict = {}
        self.meta_learner_ = None
        self.weights_: Optional[dict] = None
        self._stacking_use_proba = False
        self.is_fitted_ = False

    # -- base model fitting -------------------------------------------- #
    def _fit_one_base(self, algo: str, X: pd.DataFrame, y: pd.Series,
                       sample_weight: Optional[np.ndarray], eval_set: Optional[list]) -> BaseModel:
        _, model_cls = _get_algorithm(algo)
        sub_config = _build_sub_config(self.cfg, algo, enable_early_stopping=eval_set is not None)
        sub_config.validate()
        model = model_cls(sub_config)
        if algo == "random_forest":
            model.fit(X, y, sample_weight=sample_weight)
        else:
            model.fit(X, y, sample_weight=sample_weight, eval_set=eval_set)
        return model

    def _score_base(self, model: BaseModel, X_val: pd.DataFrame, y_val: pd.Series) -> float:
        pred = model.predict(X_val)
        if self.cfg.is_classification:
            return float(accuracy_score(y_val, pred))
        return float(np.sqrt(mean_squared_error(y_val, pred)))

    # -- fit -------------------------------------------------------------- #
    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        sample_weight: Optional[np.ndarray] = None,
        eval_set: Optional[list] = None,
        class_weights: Optional[dict] = None,
        **kwargs: Any,
    ) -> "EnsembleEstimator":
        cfg = self.cfg
        X = X.reset_index(drop=True)
        y = y.reset_index(drop=True)

        X_val, y_val = (None, None)
        if eval_set:
            X_val, y_val = eval_set[0]

        if cfg.ensemble_method == "stacking":
            self._fit_stacking(X, y, sample_weight, X_val, y_val)
        else:
            self._fit_simple(X, y, sample_weight, X_val, y_val)

        self.is_fitted_ = True
        return self

    def _fit_simple(self, X, y, sample_weight, X_val, y_val) -> None:
        """voting / weighted_average: fit each base model once on the full train split."""
        cfg = self.cfg
        eval_set = [(X_val, y_val)] if X_val is not None else None
        self.base_models_ = {}
        val_scores = {}
        for algo in cfg.base_algorithms:
            logger.info("Fitting base model: %s", algo)
            model = self._fit_one_base(algo, X, y, sample_weight, eval_set)
            self.base_models_[algo] = model
            if X_val is not None:
                val_scores[algo] = self._score_base(model, X_val, y_val)

        n = len(cfg.base_algorithms)
        if cfg.ensemble_method == "weighted_average":
            if cfg.weights is not None:
                self.weights_ = dict(zip(cfg.base_algorithms, cfg.weights))
            elif val_scores:
                if cfg.is_classification:
                    raw = val_scores  # higher accuracy -> higher weight
                else:
                    raw = {k: 1.0 / max(v, 1e-6) for k, v in val_scores.items()}  # inverse RMSE
                total = sum(raw.values()) or 1.0
                self.weights_ = {k: v / total for k, v in raw.items()}
                logger.info("Auto-derived weighted_average weights from validation performance: %s", self.weights_)
            else:
                self.weights_ = {a: 1.0 / n for a in cfg.base_algorithms}
        else:  # voting = uniform weights
            self.weights_ = {a: 1.0 / n for a in cfg.base_algorithms}

    def _fit_stacking(self, X, y, sample_weight, X_val, y_val) -> None:
        cfg = self.cfg
        n = len(X)

        use_proba = (
            cfg.is_classification
            and cfg.use_proba_for_classification_stacking
            and cfg.task_type == TaskType.BINARY_CLASSIFICATION
        )
        self._stacking_use_proba = use_proba

        if cfg.is_classification:
            splitter = StratifiedKFold(n_splits=cfg.cv_folds, shuffle=True, random_state=cfg.random_seed)
            split_iter = splitter.split(X, y)
        else:
            splitter = KFold(n_splits=cfg.cv_folds, shuffle=True, random_state=cfg.random_seed)
            split_iter = splitter.split(X)

        meta_features = {algo: np.zeros(n, dtype=np.float64) for algo in cfg.base_algorithms}

        for fold_idx, (tr_idx, ho_idx) in enumerate(split_iter):
            X_tr, X_ho = X.iloc[tr_idx], X.iloc[ho_idx]
            y_tr = y.iloc[tr_idx]
            sw_tr = sample_weight[tr_idx] if sample_weight is not None else None
            logger.info("Stacking fold %d/%d", fold_idx + 1, cfg.cv_folds)
            for algo in cfg.base_algorithms:
                model = self._fit_one_base(algo, X_tr, y_tr, sw_tr, eval_set=None)
                if use_proba and hasattr(model.estimator, "predict_proba"):
                    meta_features[algo][ho_idx] = model.predict_proba(X_ho)[:, 1]
                else:
                    meta_features[algo][ho_idx] = model.predict(X_ho)

        meta_X = np.column_stack([meta_features[a] for a in cfg.base_algorithms])

        if cfg.is_classification:
            self.meta_learner_ = LogisticRegression(max_iter=1000, random_state=cfg.random_seed)
            self.meta_learner_.fit(meta_X, y)
        else:
            self.meta_learner_ = Ridge(alpha=cfg.meta_learner_alpha, random_state=cfg.random_seed)
            self.meta_learner_.fit(meta_X, y, sample_weight=sample_weight)

        logger.info("Refitting base models on the full training split for inference.")
        eval_set = [(X_val, y_val)] if X_val is not None else None
        self.base_models_ = {
            algo: self._fit_one_base(algo, X, y, sample_weight, eval_set) for algo in cfg.base_algorithms
        }

    # -- inference --------------------------------------------------------- #
    def _base_predictions_matrix(self, X: pd.DataFrame) -> np.ndarray:
        cfg = self.cfg
        cols = []
        for algo in cfg.base_algorithms:
            model = self.base_models_[algo]
            if self._stacking_use_proba and hasattr(model.estimator, "predict_proba"):
                cols.append(model.predict_proba(X)[:, 1])
            else:
                cols.append(model.predict(X))
        return np.column_stack(cols)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        cfg = self.cfg
        if cfg.ensemble_method == "stacking":
            meta_X = self._base_predictions_matrix(X)
            return self.meta_learner_.predict(meta_X)

        preds = {algo: self.base_models_[algo].predict(X) for algo in cfg.base_algorithms}
        weights = np.array([self.weights_[a] for a in cfg.base_algorithms])

        if cfg.is_classification:
            stacked = np.column_stack([preds[a] for a in cfg.base_algorithms])
            n_samples = stacked.shape[0]
            out = np.zeros(n_samples, dtype=stacked.dtype)
            for i in range(n_samples):
                vals, inv = np.unique(stacked[i], return_inverse=True)
                w = np.zeros(len(vals))
                np.add.at(w, inv, weights)
                out[i] = vals[np.argmax(w)]
            return out

        stacked = np.column_stack([preds[a] for a in cfg.base_algorithms])
        return (stacked * weights).sum(axis=1) / weights.sum()

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        cfg = self.cfg
        if not cfg.is_classification:
            raise TrainingError("predict_proba is only valid for classification tasks.")

        if cfg.ensemble_method == "stacking":
            meta_X = self._base_predictions_matrix(X)
            return self.meta_learner_.predict_proba(meta_X)

        proba_list, weights = [], []
        for algo in cfg.base_algorithms:
            model = self.base_models_[algo]
            if hasattr(model.estimator, "predict_proba"):
                proba_list.append(model.predict_proba(X))
                weights.append(self.weights_[algo])
        if not proba_list:
            raise TrainingError("No base model in this ensemble exposes predict_proba.")
        weights_arr = np.array(weights)
        weights_arr = weights_arr / weights_arr.sum()
        stacked = np.stack(proba_list, axis=0)  # (n_models, n_samples, n_classes)
        return np.tensordot(weights_arr, stacked, axes=(0, 0))


class EnsembleModel(BaseModel):
    """Stacking / voting / weighted-average ensemble behind the standard
    BaseModel contract. Only `_build_estimator` is implemented; BaseModel.
    fit/predict handle log1p target-transform + sample_weight plumbing."""

    def __init__(self, config: EnsembleConfig):
        super().__init__(config)
        self.config: EnsembleConfig = config

    def _build_estimator(self, params: Optional[dict] = None) -> Any:
        cfg = self.config
        if params:
            from dataclasses import replace
            cfg = replace(cfg, **{k: v for k, v in params.items() if hasattr(cfg, k)})
        return EnsembleEstimator(cfg)

    def get_feature_importance(self, feature_names: Optional[list] = None) -> pd.Series:
        """Average feature_importances_ across whichever base models expose it
        (tree-based algorithms); raises if none do (e.g. a pure deep_learning ensemble)."""
        self._check_fitted()
        series_list = []
        for model in self._estimator.base_models_.values():
            if hasattr(model.estimator, "feature_importances_"):
                idx = feature_names or [f"f{i}" for i in range(len(model.estimator.feature_importances_))]
                series_list.append(pd.Series(model.estimator.feature_importances_, index=idx))
        if not series_list:
            raise TrainingError("None of the base models in this ensemble expose feature_importances_.")
        combined = pd.concat(series_list, axis=1).mean(axis=1)
        return combined.sort_values(ascending=False)

    def get_base_models(self) -> dict:
        self._check_fitted()
        return self._estimator.base_models_

    def get_weights(self) -> Optional[dict]:
        self._check_fitted()
        return self._estimator.weights_
