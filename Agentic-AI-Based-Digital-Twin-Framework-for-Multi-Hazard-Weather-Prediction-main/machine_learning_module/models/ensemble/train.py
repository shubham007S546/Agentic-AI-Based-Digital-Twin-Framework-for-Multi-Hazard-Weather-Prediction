"""
CLI entrypoint for training an ensemble (stacking / voting / weighted_average
over random_forest + xgboost + lightgbm, optionally + deep_learning).

Example
-------
python -m models.machine_learning.ensemble.train \\
    --task-type regression --data-dir ml_ready --target-column imd_rainfall_mm \\
    --base-algorithms random_forest,xgboost,lightgbm --ensemble-method stacking \\
    --cv-folds 5 --experiment-name ensemble_stack_v1
"""

from __future__ import annotations

import argparse
import json

from models.common.base_trainer import BaseTrainer
from models.common.data_utils import load_dataset_bundle
from models.common.logging_config import get_logger
from models.common.model_registry import ModelRegistry

from .config import EnsembleConfig
from .model import EnsembleModel
from .utils import add_common_cli_args, add_ensemble_cli_args, build_config_from_args

logger = get_logger(__name__, log_file="logs/ensemble_train.log")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train an ensemble of base ML models.")
    parser = add_common_cli_args(parser)
    parser = add_ensemble_cli_args(parser)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config: EnsembleConfig = build_config_from_args(args)

    logger.info("Loading dataset from %s", config.data_dir)
    drop_columns = [c.strip() for c in args.drop_columns.split(",") if c.strip()]
    bundle = load_dataset_bundle(
        data_dir=config.data_dir,
        target_column=config.target_column,
        use_sample_weights=config.use_sample_weights,
        use_class_weights=config.use_class_weights,
        train_x_filename=args.train_x_file,
        train_y_filename=args.train_y_file,
        drop_columns=drop_columns,
    )

    model = EnsembleModel(config)
    trainer = BaseTrainer(config, model)

    eval_set = [(bundle.X_val, bundle.y_val)]
    result = trainer.run(bundle, eval_set=eval_set, class_weights=bundle.class_weights)

    artifact_path = config.artifact_path("model.joblib")
    result["model"].save(str(artifact_path))

    metrics_path = config.artifact_path("val_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(result["val_metrics"], f, indent=2)

    weights = result["model"].get_weights()
    if weights:
        weights_path = config.artifact_path("ensemble_weights.json")
        with open(weights_path, "w") as f:
            json.dump(weights, f, indent=2)

    registry = ModelRegistry(registry_path=f"{config.artifacts_dir}/model_registry.json")
    registry.register(
        model_name=f"{config.model_name}_{config.ensemble_method}",
        experiment_name=config.experiment_name,
        artifact_path=str(artifact_path),
        task_type=config.task_type.value,
        metrics=result["val_metrics"],
        params={**config.__dict__, "base_algorithms": list(config.base_algorithms)},
    )

    logger.info("Training complete. Artifact: %s", artifact_path)
    logger.info("Validation metrics: %s", result["val_metrics"])


if __name__ == "__main__":
    main()
