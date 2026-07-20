"""
CLI entrypoint for evaluating a trained LightGBM model on the test split.

Example
-------
python -m models.machine_learning.lightgbm.evaluate \
    --data-dir ml_ready --target-column imd_rainfall_mm --task-type regression \
    --experiment-name lgbm_rainfall_v1 \
    --model-path artifacts/lightgbm/lgbm_rainfall_v1/model.joblib \
    --with-shap
"""

from __future__ import annotations

import argparse
import json

from models.common.base_evaluator import BaseEvaluator
from models.common.data_utils import load_dataset_bundle
from models.common.logging_config import get_logger

from .config import LightGBMConfig
from .model import LightGBMModel
from .utils import add_common_cli_args, add_lgbm_cli_args, build_config_from_args

logger = get_logger(__name__, log_file="logs/lightgbm_evaluate.log")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a trained LightGBM model.")
    parser = add_common_cli_args(parser)
    parser = add_lgbm_cli_args(parser)
    parser.add_argument("--model-path", dest="model_path", required=True)
    parser.add_argument("--with-permutation-importance", dest="with_perm", action="store_true")
    parser.add_argument("--with-shap", dest="with_shap", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config: LightGBMConfig = build_config_from_args(args)

    bundle = load_dataset_bundle(
        data_dir=config.data_dir,
        target_column=config.target_column,
        use_sample_weights=config.use_sample_weights,
        use_class_weights=config.use_class_weights,
    )

    model = LightGBMModel(config)
    model.load(args.model_path)

    evaluator = BaseEvaluator(model, config)
    test_metrics = evaluator.compute_metrics(bundle.X_test, bundle.y_test)
    logger.info("Test metrics: %s", test_metrics)

    metrics_path = config.artifact_path("test_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(test_metrics, f, indent=2)

    importance = evaluator.feature_importance(bundle.feature_names)
    importance_path = config.artifact_path("feature_importance.csv")
    importance.to_csv(importance_path, header=["importance"])

    if args.with_perm:
        perm_df = evaluator.permutation_importance(bundle.X_test, bundle.y_test)
        perm_path = config.artifact_path("permutation_importance.csv")
        perm_df.to_csv(perm_path, index=False)
        logger.info("Permutation importance saved to %s", perm_path)

    if args.with_shap:
        shap_values = evaluator.shap_values(bundle.X_test)
        import joblib
        shap_path = config.artifact_path("shap_values.joblib")
        joblib.dump(shap_values, shap_path)
        logger.info("SHAP values saved to %s", shap_path)

    print(json.dumps(test_metrics, indent=2))


if __name__ == "__main__":
    main()
