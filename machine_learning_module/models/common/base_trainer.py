"""
BaseTrainer: orchestrates loading data, fitting a BaseModel, evaluating on
the validation split, and persisting the artifact. Each algorithm's
train.py builds a concrete BaseModel subclass and a BaseModelConfig
subclass, then calls BaseTrainer(config, model).run(bundle).
"""

from __future__ import annotations

from typing import Any, Optional

from .base_evaluator import BaseEvaluator
from .base_model import BaseModel
from .config_schema import BaseModelConfig
from .data_utils import DatasetBundle, set_global_seed
from .exceptions import TrainingError
from .logging_config import get_logger

logger = get_logger(__name__)


class BaseTrainer:
    """Generic training loop shared by every algorithm."""

    def __init__(self, config: BaseModelConfig, model: BaseModel):
        self.config = config
        self.model = model

    def run(
        self,
        bundle: DatasetBundle,
        params: Optional[dict] = None,
        eval_set: Optional[list] = None,
        **fit_kwargs: Any,
    ) -> dict:
        """
        Full train pass:
          1. seed everything
          2. build the estimator (optionally with overridden `params`,
             used by the tuner)
          3. fit on X_train/y_train, applying sample_weight / class_weight
             per config
          4. evaluate on the validation split
          5. return a result dict with the fitted model + val metrics

        Does NOT save to disk -- callers (train.py) decide when/whether to
        persist, so a tuner can call this repeatedly without writing
        artifacts for every trial.
        """
        set_global_seed(self.config.random_seed)
        logger.info(
            "Starting training | model=%s | task=%s | seed=%d",
            self.config.model_name,
            self.config.task_type.value,
            self.config.random_seed,
        )

        self.model.build(params)

        sample_weight = None
        if self.config.use_sample_weights and bundle.sample_weights_train is not None:
            sample_weight = bundle.sample_weights_train
            logger.info("Applying %d sample weights.", len(sample_weight))

        try:
            self.model.fit(
                bundle.X_train,
                bundle.y_train,
                sample_weight=sample_weight,
                eval_set=eval_set,
                **fit_kwargs,
            )
        except Exception as exc:
            raise TrainingError(f"Training run failed: {exc}") from exc

        evaluator = BaseEvaluator(self.model, self.config)
        val_metrics = evaluator.compute_metrics(bundle.X_val, bundle.y_val)
        logger.info("Validation metrics: %s", val_metrics)

        return {
            "model": self.model,
            "val_metrics": val_metrics,
        }
