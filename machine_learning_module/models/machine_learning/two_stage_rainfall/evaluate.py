"""
Evaluation for the two-stage rainfall pipeline: stage-1 classification
metrics, stage-2-on-true-rain-subset regression metrics, and the combined
end-to-end regression metrics (the number that actually matters).

CLI example
-----------
python -m models.machine_learning.two_stage_rainfall.evaluate \
    --data-dir ml_ready --target-column imd_rainfall_mm \
    --experiment-name two_stage_v1 \
    --model-path artifacts/two_stage_rainfall/two_stage_v1/model.joblib
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score, f1_score, mean_absolute_error,
    mean_squared_error, precision_score, r2_score, recall_score, roc_auc_score,
)

from models.common.data_utils import load_dataset_bundle
from models.common.logging_config import get_logger

from .config import TwoStageRainfallConfig
from .pipeline import TwoStageRainfallModel
from .utils import add_common_cli_args, add_two_stage_cli_args, build_config_from_args

logger = get_logger(__name__, log_file="logs/two_stage_rainfall_evaluate.log")


def compute_pipeline_metrics(
    model: TwoStageRainfallModel,
    config: TwoStageRainfallConfig,
    X: pd.DataFrame,
    y: pd.Series,
) -> dict:
    """Returns {"stage1_classification": {...}, "stage2_on_rainy_subset": {...}, "combined": {...}}."""
    rain_actual = (y > config.rain_threshold).astype(int)

    # ---- stage 1: did it rain? ----
    rain_proba = model.predict_rain_probability(X)
    rain_pred = (rain_proba >= config.classification_threshold).astype(int)
    stage1_metrics = {
        "accuracy": float(accuracy_score(rain_actual, rain_pred)),
        "precision": float(precision_score(rain_actual, rain_pred, zero_division=0)),
        "recall": float(recall_score(rain_actual, rain_pred, zero_division=0)),
        "f1": float(f1_score(rain_actual, rain_pred, zero_division=0)),
    }
    if rain_actual.nunique() > 1:
        stage1_metrics["roc_auc"] = float(roc_auc_score(rain_actual, rain_proba))

    # ---- stage 2: how much, on rows that TRULY rained (regressor evaluated
    # in isolation -- NOT gated by stage 1's classification, so stage 1's
    # false negatives don't contaminate this number) ----
    true_rain_mask = rain_actual == 1
    stage2_metrics = {}
    if true_rain_mask.sum() > 0:
        X_true_rain = X.loc[true_rain_mask]
        reg_pred = model._regressor.predict(X_true_rain)
        if config.log_transform:
            reg_pred = np.expm1(reg_pred)
        reg_pred = np.clip(reg_pred, a_min=0, a_max=None)
        y_rain = y.loc[true_rain_mask]
        stage2_metrics = {
            "rmse": float(np.sqrt(mean_squared_error(y_rain, reg_pred))),
            "mae": float(mean_absolute_error(y_rain, reg_pred)),
            "r2": float(r2_score(y_rain, reg_pred)),
            "n_samples": int(true_rain_mask.sum()),
        }

    combined_pred = model.predict(X)

    # ---- combined: the end-to-end number that matters ----
    combined_metrics = {
        "rmse": float(np.sqrt(mean_squared_error(y, combined_pred))),
        "mae": float(mean_absolute_error(y, combined_pred)),
        "r2": float(r2_score(y, combined_pred)),
        "n_samples": int(len(y)),
    }

    return {
        "stage1_classification": stage1_metrics,
        "stage2_on_rainy_subset": stage2_metrics,
        "combined": combined_metrics,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the two-stage rainfall pipeline.")
    parser = add_common_cli_args(parser)
    parser = add_two_stage_cli_args(parser)
    parser.add_argument("--model-path", dest="model_path", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config: TwoStageRainfallConfig = build_config_from_args(args)

    bundle = load_dataset_bundle(
        data_dir=config.data_dir,
        target_column=config.target_column,
        use_sample_weights=config.use_sample_weights,
        use_class_weights=False,
    )

    model = TwoStageRainfallModel(config)
    model.load(args.model_path)

    test_metrics = compute_pipeline_metrics(model, config, bundle.X_test, bundle.y_test)
    logger.info("Test metrics: %s", json.dumps(test_metrics, indent=2))

    metrics_path = config.artifact_path("test_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(test_metrics, f, indent=2)

    print(json.dumps(test_metrics, indent=2))


if __name__ == "__main__":
    main()
