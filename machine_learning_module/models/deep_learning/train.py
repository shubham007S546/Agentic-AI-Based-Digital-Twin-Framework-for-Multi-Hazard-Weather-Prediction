"""
CLI entrypoint for training a deep-learning (LSTM / GRU / TCN) model.

Example
-------
python -m models.machine_learning.deep_learning.train \\
    --task-type regression --data-dir ml_ready --target-column imd_rainfall_mm \\
    --architecture lstm --sequence-length 24 --experiment-name dl_lstm_v1 \\
    --epochs 100 --early-stopping-patience 10
"""

from __future__ import annotations

import argparse
import json

from models.common.base_trainer import BaseTrainer
from models.common.data_utils import load_dataset_bundle
from models.common.logging_config import get_logger
from models.common.model_registry import ModelRegistry

from .config import DeepLearningConfig
from .model import DeepLearningModel
from .utils import add_common_cli_args, add_dl_cli_args, build_config_from_args

logger = get_logger(__name__, log_file="logs/deep_learning_train.log")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a deep-learning (LSTM/GRU/TCN) model.")
    parser = add_common_cli_args(parser)
    parser = add_dl_cli_args(parser)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config: DeepLearningConfig = build_config_from_args(args)

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

    model = DeepLearningModel(config)
    trainer = BaseTrainer(config, model)

    eval_set = [(bundle.X_val, bundle.y_val)]
    result = trainer.run(bundle, eval_set=eval_set, class_weights=bundle.class_weights)

    artifact_path = config.artifact_path("model.joblib")
    result["model"].save(str(artifact_path))

    metrics_path = config.artifact_path("val_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(result["val_metrics"], f, indent=2)

    history_path = config.artifact_path("training_history.json")
    with open(history_path, "w") as f:
        json.dump(result["model"].get_training_history(), f, indent=2)

    registry = ModelRegistry(registry_path=f"{config.artifacts_dir}/model_registry.json")
    registry.register(
        model_name=f"{config.model_name}_{config.architecture}",
        experiment_name=config.experiment_name,
        artifact_path=str(artifact_path),
        task_type=config.task_type.value,
        metrics=result["val_metrics"],
        params=config.__dict__,
    )

    logger.info("Training complete. Artifact: %s", artifact_path)
    logger.info("Validation metrics: %s", result["val_metrics"])


if __name__ == "__main__":
    main()
