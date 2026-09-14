"""
training/predict.py
─────────────────────────────────────────────────────────────────────────────
Batch inference: run a trained model on new/unseen data and save predictions.

Loads a saved model artifact and applies it to a CSV file of features,
outputting a CSV with predictions (and optionally probabilities for
classification tasks).

Usage
─────
  # Regression prediction:
  python training/predict.py \\
      --model xgboost \\
      --model-path machine_learning_module/artifacts/machine_learning/xgb_v1/model.joblib \\
      --input data/new_features.csv \\
      --output predictions/xgb_predictions.csv \\
      --target-column rainfall_mm_pred

  # Binary classification with probabilities:
  python training/predict.py \\
      --model lstm \\
      --model-path machine_learning_module/artifacts/deep_learning/lstm_v1/model.joblib \\
      --input data/new_features.csv \\
      --output predictions/lstm_cloudburst.csv \\
      --with-probas \\
      --task-type binary
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ML_MODULE  = _REPO_ROOT / "machine_learning_module"
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_ML_MODULE))

from models.common.logging_config import get_logger

logger = get_logger(__name__, log_file="logs/training_predict.log")


# ── Load model ────────────────────────────────────────────────────────────────

def _load_model(model_key: str, model_path: str, task_type_str: str, data_dir: str = "ml_ready", target_column: str = "imd_rainfall_mm"):
    from models.common.config_schema import TaskType
    try:
        task_type = TaskType[task_type_str.upper().replace(" ", "_").replace("-", "_")]
    except KeyError:
        task_type = TaskType.REGRESSION

    model_key = model_key.lower()

    if model_key in ("xgboost", "xgb"):
        from models.machine_learning.xgboost.config import XGBoostConfig
        from models.machine_learning.xgboost.model  import XGBoostModel
        cfg   = XGBoostConfig(data_dir=data_dir, target_column=target_column, task_type=task_type)
        model = XGBoostModel(cfg)
    elif model_key in ("lightgbm", "lgb", "lgbm"):
        from models.machine_learning.lightgbm.config import LightGBMConfig
        from models.machine_learning.lightgbm.model  import LightGBMModel
        cfg   = LightGBMConfig(data_dir=data_dir, target_column=target_column, task_type=task_type)
        model = LightGBMModel(cfg)
    elif model_key in ("lstm", "gru", "tcn"):
        from models.deep_learning.config import DeepLearningConfig
        from models.deep_learning.model  import DeepLearningModel
        cfg   = DeepLearningConfig(data_dir=data_dir, target_column=target_column, task_type=task_type, architecture=model_key)
        model = DeepLearningModel(cfg)
    elif model_key in ("tft", "transformer"):
        from models.transformer.config import TFTLiteConfig
        from models.transformer.model  import TFTLiteModel
        cfg   = TFTLiteConfig(data_dir=data_dir, target_column=target_column, task_type=task_type)
        model = TFTLiteModel(cfg)
    else:
        raise ValueError(f"Unknown model: {model_key!r}")

    model.load(model_path)
    logger.info("Loaded model [%s] from %s", model_key, model_path)
    return model


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run batch inference with a trained model artifact.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--model",          required=True,  help="Model type (xgboost | lightgbm | lstm | gru | tcn | tft)")
    parser.add_argument("--model-path",     required=True,  help="Path to saved model.joblib artifact")
    parser.add_argument("--input",          required=True,  help="CSV file with input features")
    parser.add_argument("--output",         required=True,  help="Path to write predictions CSV")
    parser.add_argument("--target-column",  default="prediction",  help="Column name for predictions in output CSV")
    parser.add_argument("--task-type",      default="regression",
                        choices=["regression", "binary", "multiclass",
                                 "binary_classification", "multiclass_classification"])
    parser.add_argument("--with-probas",    action="store_true",
                        help="Include class probabilities in output (classification only)")
    parser.add_argument("--drop-columns",   default="",  help="Comma-separated list of columns to drop from input before inference")
    parser.add_argument("--data-dir",       default="ml_ready",       help="Data dir used during training (for config)")
    parser.add_argument("--training-target", default="imd_rainfall_mm", help="Target column used during training (for config)")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[predict] Input file not found: {input_path}")
        sys.exit(1)

    logger.info("Loading features from %s", input_path)
    X = pd.read_csv(input_path)
    logger.info("Input shape: %s", X.shape)

    # Drop columns if requested
    drop_cols = [c.strip() for c in args.drop_columns.split(",") if c.strip()]
    if drop_cols:
        X = X.drop(columns=[c for c in drop_cols if c in X.columns])
        logger.info("Dropped columns: %s", drop_cols)

    # Load model
    model = _load_model(
        args.model, args.model_path,
        task_type_str=args.task_type,
        data_dir=args.data_dir,
        target_column=args.training_target,
    )

    # Predict
    y_pred = model.predict(X)
    logger.info("Predictions computed: %d rows", len(y_pred))

    # Build output dataframe
    out_df = X.copy()
    out_df[args.target_column] = y_pred

    # Probabilities (classification only)
    if args.with_probas:
        try:
            probas = model.predict_proba(X)
            if probas.ndim == 1:
                out_df["proba_pos"] = probas
            else:
                for i in range(probas.shape[1]):
                    out_df[f"proba_class_{i}"] = probas[:, i]
            logger.info("Probability columns added.")
        except Exception as exc:
            logger.warning("Could not compute probabilities: %s", exc)

    # Save
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)

    print(f"\n[predict] Done.")
    print(f"  Input rows       : {len(X):,}")
    print(f"  Predictions saved: {out_path}")
    print(f"  Prediction stats :")
    print(f"    min  = {y_pred.min():.4f}")
    print(f"    mean = {y_pred.mean():.4f}")
    print(f"    max  = {y_pred.max():.4f}")
    print(f"    std  = {y_pred.std():.4f}")


if __name__ == "__main__":
    main()
