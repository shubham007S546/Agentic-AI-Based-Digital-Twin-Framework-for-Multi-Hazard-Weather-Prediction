"""
CLI entrypoint for evaluating a trained deep-learning model on the test split.

Note: feature-importance / SHAP are not available for these architectures
(no native feature_importances_, and shap.TreeExplainer only supports tree
ensembles) -- use --with-permutation-importance for a model-agnostic
alternative instead.

Example
-------
python -m models.machine_learning.deep_learning.evaluate \\
    --data-dir ml_ready --target-column imd_rainfall_mm --task-type regression \\
    --architecture lstm --sequence-length 24 --experiment-name dl_lstm_v1 \\
    --model-path artifacts/deep_learning/dl_lstm_v1/model.joblib
"""

from __future__ import annotations

import argparse
import json

from models.common.base_evaluator import BaseEvaluator
from models.common.data_utils import load_dataset_bundle
from models.common.logging_config import get_logger

from .config import DeepLearningConfig
from .model import DeepLearningModel
from .utils import add_common_cli_args, add_dl_cli_args, build_config_from_args

logger = get_logger(__name__, log_file="logs/deep_learning_evaluate.log")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a trained deep-learning model.")
    parser = add_common_cli_args(parser)
    parser = add_dl_cli_args(parser)
    parser.add_argument("--model-path", dest="model_path", required=True)
    parser.add_argument("--with-permutation-importance", dest="with_perm", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config: DeepLearningConfig = build_config_from_args(args)

    bundle = load_dataset_bundle(
        data_dir=config.data_dir,
        target_column=config.target_column,
        use_sample_weights=config.use_sample_weights,
        use_class_weights=config.use_class_weights,
    )

    model = DeepLearningModel(config)
    model.load(args.model_path)

    evaluator = BaseEvaluator(model, config)
    test_metrics = evaluator.compute_metrics(bundle.X_test, bundle.y_test)
    logger.info("Test metrics: %s", test_metrics)

    metrics_path = config.artifact_path("test_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(test_metrics, f, indent=2)

    if args.with_perm:
        perm_df = evaluator.permutation_importance(bundle.X_test, bundle.y_test)
        perm_path = config.artifact_path("permutation_importance.csv")
        perm_df.to_csv(perm_path, index=False)
        logger.info("Permutation importance saved to %s", perm_path)

    print(json.dumps(test_metrics, indent=2))


if __name__ == "__main__":
    main()
