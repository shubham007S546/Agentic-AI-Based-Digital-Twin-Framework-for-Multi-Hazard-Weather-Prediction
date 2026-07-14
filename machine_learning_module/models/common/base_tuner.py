"""
BaseHyperparameterTuner: Optuna-based tuning shared by every algorithm, with
plain random-search and grid-search fallbacks for environments without
Optuna or for quick sanity checks. Each algorithm's hyperparameter.py
subclasses this and implements `search_space` (Optuna) / `param_grid`
(grid search) / `param_distributions` (random search).
"""

from __future__ import annotations

import itertools
import random
from abc import ABC, abstractmethod
from typing import Any, Optional

import numpy as np
import pandas as pd

from .base_evaluator import BaseEvaluator
from .base_model import BaseModel
from .base_trainer import BaseTrainer
from .config_schema import BaseModelConfig, TaskType
from .data_utils import DatasetBundle
from .exceptions import TuningError
from .logging_config import get_logger

logger = get_logger(__name__)

_METRIC_BY_TASK = {
    TaskType.REGRESSION: ("rmse", False),          # (metric name, higher_is_better)
    TaskType.BINARY_CLASSIFICATION: ("f1", True),
    TaskType.MULTICLASS_CLASSIFICATION: ("f1", True),
}


class BaseHyperparameterTuner(ABC):
    """
    Generic tuning loop. Subclasses (one per algorithm) must implement:
      - search_space(trial): optuna trial -> params dict
      - param_grid(): dict[str, list] for grid search
      - param_distributions(): dict[str, list] for random search
    """

    def __init__(
        self,
        config: BaseModelConfig,
        model_cls: type,
        bundle: DatasetBundle,
    ):
        self.config = config
        self.model_cls = model_cls
        self.bundle = bundle
        self.metric_name, self.higher_is_better = _METRIC_BY_TASK[config.task_type]
        self.best_params_: Optional[dict] = None
        self.best_score_: Optional[float] = None
        self.best_model_: Optional[BaseModel] = None

    # ------------------------------------------------------------------ #
    # Subclasses implement these.
    # ------------------------------------------------------------------ #
    @abstractmethod
    def search_space(self, trial: Any) -> dict:
        """Given an optuna.Trial, return a hyperparameter dict."""
        raise NotImplementedError

    @abstractmethod
    def param_grid(self) -> dict:
        """Return {param_name: [values...]} for exhaustive grid search."""
        raise NotImplementedError

    @abstractmethod
    def param_distributions(self) -> dict:
        """Return {param_name: [candidate values...]} for random search
        sampling (uniform choice over the list, per param, per trial)."""
        raise NotImplementedError

    def _extra_fit_kwargs(self) -> dict:
        """
        Hook for subclasses that need extra fit-time arguments during tuning
        (e.g. XGBoostTuner passes eval_set/class_weights so early stopping
        still works while trying different hyperparameter sets). Default:
        no extra kwargs.
        """
        return {}

    # ------------------------------------------------------------------ #
    def _score(self, params: dict) -> tuple:
        """Train once with `params`, return (score, fitted_model)."""
        model = self.model_cls(self.config)
        trainer = BaseTrainer(self.config, model)
        result = trainer.run(self.bundle, params=params, **self._extra_fit_kwargs())
        metrics = result["val_metrics"]
        if self.metric_name not in metrics:
            raise TuningError(
                f"Metric '{self.metric_name}' not found in validation metrics: {metrics}"
            )
        return metrics[self.metric_name], result["model"]

    def _is_better(self, candidate: float, current_best: Optional[float]) -> bool:
        if current_best is None:
            return True
        return candidate > current_best if self.higher_is_better else candidate < current_best

    # ------------------------------------------------------------------ #
    def tune_optuna(self, n_trials: int = 50, timeout: Optional[int] = None) -> dict:
        try:
            import optuna
            from optuna.samplers import TPESampler
        except ImportError as exc:
            raise ImportError(
                "The 'optuna' package is required for tune_optuna(). "
                "Install it with: pip install optuna"
            ) from exc

        optuna.logging.set_verbosity(optuna.logging.WARNING)
        direction = "maximize" if self.higher_is_better else "minimize"
        sampler = TPESampler(seed=self.config.random_seed)
        study = optuna.create_study(direction=direction, sampler=sampler)

        def objective(trial: "optuna.Trial") -> float:
            params = self.search_space(trial)
            score, _ = self._score(params)
            return score

        study.optimize(objective, n_trials=n_trials, timeout=timeout)

        self.best_params_ = study.best_params
        self.best_score_ = study.best_value
        logger.info(
            "Optuna tuning finished | best %s=%.5f | params=%s",
            self.metric_name, self.best_score_, self.best_params_,
        )
        return self._finalize()

    def tune_grid_search(self) -> dict:
        grid = self.param_grid()
        keys = list(grid.keys())
        combos = list(itertools.product(*[grid[k] for k in keys]))
        logger.info("Grid search over %d combinations.", len(combos))

        best_score, best_params = None, None
        for combo in combos:
            params = dict(zip(keys, combo))
            score, _ = self._score(params)
            if self._is_better(score, best_score):
                best_score, best_params = score, params

        self.best_params_, self.best_score_ = best_params, best_score
        logger.info(
            "Grid search finished | best %s=%.5f | params=%s",
            self.metric_name, self.best_score_, self.best_params_,
        )
        return self._finalize()

    def tune_random_search(self, n_iter: int = 25) -> dict:
        rng = random.Random(self.config.random_seed)
        distributions = self.param_distributions()
        keys = list(distributions.keys())

        best_score, best_params = None, None
        for _ in range(n_iter):
            params = {k: rng.choice(distributions[k]) for k in keys}
            score, _ = self._score(params)
            if self._is_better(score, best_score):
                best_score, best_params = score, params

        self.best_params_, self.best_score_ = best_params, best_score
        logger.info(
            "Random search finished | best %s=%.5f | params=%s",
            self.metric_name, self.best_score_, self.best_params_,
        )
        return self._finalize()

    # ------------------------------------------------------------------ #
    def _finalize(self) -> dict:
        """Refit a fresh model on best_params_ so best_model_ is populated,
        then return a summary dict."""
        if self.best_params_ is None:
            raise TuningError("Tuning did not produce any valid trial.")
        _, model = self._score(self.best_params_)
        self.best_model_ = model
        return {
            "best_params": self.best_params_,
            "best_score": self.best_score_,
            "metric": self.metric_name,
            "best_model": self.best_model_,
        }
