"""
CLI entrypoint for evaluating a trained ensemble on the test split.

Example
-------
python -m models.machine_learning.ensemble.evaluate \\
    --data-dir ml_ready --target-column imd_rainfall_mm --task-type regression \\
    --base-algorithms random_forest,xgboost,lightgbm --ensemble-method stacking \\
    --experiment-name ensemble_stack_v1 \\
    --model-path artifacts/ensemble/ensemble_stack_v1/model.joblib
"""

from __future__ import annotations

import argparse
import json

from models.common.base_evaluator import BaseEvaluator
from models.common.data_utils import load_dataset_bundle
from models.common.logging_config import get_logger

from .config import EnsembleConfig
from .model import EnsembleModel
from .utils import add_common_cli_args, add_ensemble_cli_args, build_config_from_args

logger = get_logger(__name__, log_file="logs/ensemble_evaluate.log")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a trained ensemble.")
    parser = add_common_cli_args(parser)
    parser = add_ensemble_cli_args(parser)
    parser.add_argument("--model-path", dest="model_path", required=True)
    parser.add_argument("--with-feature-importance", dest="with_fi", action="store_true", default=True)
    parser.add_argument("--no-feature-importance", dest="with_fi", action="store_false")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config: EnsembleConfig = build_config_from_args(args)

    bundle = load_dataset_bundle(
        data_dir=config.data_dir,
        target_column=config.target_column,
        use_sample_weights=config.use_sample_weights,
        use_class_weights=config.use_class_weights,
    )

    model = EnsembleModel(config)
    model.load(args.model_path)

    evaluator = BaseEvaluator(model, config)
    test_metrics = evaluator.compute_metrics(bundle.X_test, bundle.y_test)
    logger.info("Test metrics: %s", test_metrics)

    metrics_path = config.artifact_path("test_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(test_metrics, f, indent=2)

    if args.with_fi:
        try:
            importance = model.get_feature_importance(bundle.feature_names)
            importance.to_csv(config.artifact_path("feature_importance.csv"), header=["importance"])
        except Exception as exc:  # e.g. a pure deep_learning ensemble has no feature_importances_
            logger.warning("Skipping feature importance: %s", exc)

    print(json.dumps(test_metrics, indent=2))


if __name__ == "__main__":
    main()
