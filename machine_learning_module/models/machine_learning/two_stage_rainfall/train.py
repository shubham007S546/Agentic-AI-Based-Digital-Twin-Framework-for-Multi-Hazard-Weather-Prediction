"""
CLI entrypoint for training the two-stage rainfall pipeline.

Example
-------
python -m models.machine_learning.two_stage_rainfall.train \
    --data-dir ml_ready --target-column imd_rainfall_mm \
    --classifier-algorithm random_forest --regressor-algorithm xgboost \
    --experiment-name two_stage_v1
"""

from __future__ import annotations

import argparse
import json

from models.common.data_utils import load_dataset_bundle, set_global_seed
from models.common.logging_config import get_logger
from models.common.model_registry import ModelRegistry

from .config import TwoStageRainfallConfig
from .pipeline import TwoStageRainfallModel
from .utils import add_common_cli_args, add_two_stage_cli_args, build_config_from_args
from .evaluate import compute_pipeline_metrics

logger = get_logger(__name__, log_file="logs/two_stage_rainfall_train.log")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the two-stage rainfall pipeline.")
    parser = add_common_cli_args(parser)
    parser = add_two_stage_cli_args(parser)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config: TwoStageRainfallConfig = build_config_from_args(args)
    set_global_seed(config.random_seed)

    logger.info("Loading dataset from %s (target=%s)", config.data_dir, config.target_column)
    bundle = load_dataset_bundle(
        data_dir=config.data_dir,
        target_column=config.target_column,
        use_sample_weights=config.use_sample_weights,
        use_class_weights=False,
    )

    model = TwoStageRainfallModel(config)
    model.fit(
        bundle.X_train,
        bundle.y_train,
        sample_weight=bundle.sample_weights_train,
        X_val=bundle.X_val,
        y_val=bundle.y_val,
    )

    val_metrics = compute_pipeline_metrics(model, config, bundle.X_val, bundle.y_val)
    logger.info("Validation metrics: %s", val_metrics)

    artifact_path = config.artifact_path("model.joblib")
    model.save(str(artifact_path))

    metrics_path = config.artifact_path("val_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(val_metrics, f, indent=2)

    registry = ModelRegistry(registry_path=f"{config.artifacts_dir}/model_registry.json")
    registry.register(
        model_name=config.model_name,
        experiment_name=config.experiment_name,
        artifact_path=str(artifact_path),
        task_type=config.task_type.value,
        metrics=val_metrics["combined"],
        params=config.__dict__,
    )

    logger.info("Training complete. Artifact: %s", artifact_path)


if __name__ == "__main__":
    main()
