"""
CLI entrypoint for evaluating a trained TFT-Lite model on the test split.

Example
-------
python -m models.machine_learning.transformer.evaluate \\
    --data-dir ml_ready --target-column imd_rainfall_mm --task-type regression \\
    --sequence-length 24 --hidden-size 64 --num-attention-heads 4 \\
    --experiment-name tft_lite_v1 \\
    --model-path artifacts/transformer/tft_lite_v1/model.joblib
"""

from __future__ import annotations

import argparse
import json

from models.common.base_evaluator import BaseEvaluator
from models.common.data_utils import load_dataset_bundle
from models.common.logging_config import get_logger

from .config import TFTLiteConfig
from .model import TFTLiteModel
from .utils import add_common_cli_args, add_tft_cli_args, build_config_from_args

logger = get_logger(__name__, log_file="logs/transformer_evaluate.log")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a trained TFT-Lite model.")
    parser = add_common_cli_args(parser)
    parser = add_tft_cli_args(parser)
    parser.add_argument("--model-path", dest="model_path", required=True)
    parser.add_argument("--with-permutation-importance", dest="with_perm", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config: TFTLiteConfig = build_config_from_args(args)

    bundle = load_dataset_bundle(
        data_dir=config.data_dir,
        target_column=config.target_column,
        use_sample_weights=config.use_sample_weights,
        use_class_weights=config.use_class_weights,
    )

    model = TFTLiteModel(config)
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
