"""
training/evaluate.py
─────────────────────────────────────────────────────────────────────────────
Evaluate a single trained model artifact on the test split.

Loads the saved model, runs it on X_test / y_test, computes the full suite
of evaluation metrics (regression + IMD threshold scores, or classification),
and prints + saves the result.

Usage
─────
  # Regression model (XGBoost):
  python training/evaluate.py \\
      --model xgboost \\
      --model-path machine_learning_module/artifacts/machine_learning/xgb_v1/model.joblib \\
      --data-dir ml_ready \\
      --target-column imd_rainfall_mm \\
      --task-type regression \\
      --output reports/xgb_test_metrics.json

  # Classification model (binary cloudburst):
  python training/evaluate.py \\
      --model lstm \\
      --model-path machine_learning_module/artifacts/deep_learning/lstm_v1/model.joblib \\
      --data-dir ml_ready \\
      --target-column cloudburst_flag \\
      --task-type binary \\
      --output reports/lstm_cloudburst_test_metrics.json \\
      --save-plots reports/plots/lstm_cloudburst
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ML_MODULE  = _REPO_ROOT / "machine_learning_module"
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_ML_MODULE))

from models.common.data_utils   import load_dataset_bundle
from models.common.logging_config import get_logger

logger = get_logger(__name__, log_file="logs/training_evaluate.log")


# ── Load model by type ────────────────────────────────────────────────────────

def _load_model(model_key: str, model_path: str, data_dir: str, target_column: str, task_type_str: str):
    from models.common.config_schema import TaskType
    try:
        task_type = TaskType[task_type_str.upper()]
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
    logger.info("Loaded model from %s", model_path)
    return model, cfg


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a trained model on the test split.")
    parser.add_argument("--model",          required=True)
    parser.add_argument("--model-path",     required=True)
    parser.add_argument("--data-dir",       default="ml_ready")
    parser.add_argument("--target-column",  default="imd_rainfall_mm")
    parser.add_argument("--task-type",      default="regression",
                        choices=["regression", "binary", "multiclass", "binary_classification", "multiclass_classification"])
    parser.add_argument("--output",         default=None,  help="Path to save JSON metrics")
    parser.add_argument("--save-plots",     default=None,  help="Prefix path for evaluation plots (optional)")
    parser.add_argument("--with-perm-importance", action="store_true",
                        help="Compute permutation importance (slow for large test sets)")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # Normalise task type string
    task_type = args.task_type.replace("_classification", "")

    logger.info("Evaluating %s from %s", args.model, args.model_path)

    # Load data
    bundle = load_dataset_bundle(data_dir=args.data_dir, target_column=args.target_column)
    X_test, y_test = bundle.X_test, bundle.y_test
    logger.info("Test set: %s rows, %s features", len(X_test), X_test.shape[1])

    # Load model
    model, config = _load_model(args.model, args.model_path, args.data_dir, args.target_column, args.task_type)

    # Predict
    y_pred = model.predict(X_test)

    # ── Regression metrics ────────────────────────────────────────────────────
    metrics: dict = {}
    if task_type == "regression":
        from evaluation.regression_metrics import RegressionEvaluator
        ev = RegressionEvaluator(y_test, y_pred)
        result = ev.summary(verbose=True)
        metrics = result.to_dict()

        if args.save_plots:
            from evaluation.plots import plot_residuals, plot_imd_category_rates
            plot_residuals(y_test, y_pred, model_name=args.model,
                           output_path=f"{args.save_plots}_residuals.png")
            if result.threshold_scores:
                plot_imd_category_rates(result.threshold_scores, model_name=args.model,
                                        output_path=f"{args.save_plots}_imd_rates.png")

    # ── Binary classification metrics ─────────────────────────────────────────
    elif task_type == "binary":
        from evaluation.classification_metrics import ClassificationEvaluator
        probas = None
        if hasattr(model, "predict_proba"):
            try:
                probas = model.predict_proba(X_test)
            except Exception:
                pass
        ev = ClassificationEvaluator(y_test, y_pred, probas=probas, task="binary")
        result = ev.summary(verbose=True)
        metrics = result.to_dict()

        if args.save_plots and probas is not None:
            from evaluation.plots import plot_roc_curve, plot_confusion_matrix
            plot_roc_curve(y_test, probas[:, 1], model_name=args.model,
                           output_path=f"{args.save_plots}_roc.png")
            plot_confusion_matrix(result.confusion_matrix, model_name=args.model,
                                  output_path=f"{args.save_plots}_cm.png")

    # ── Multiclass classification metrics ─────────────────────────────────────
    elif task_type == "multiclass":
        from evaluation.classification_metrics import ClassificationEvaluator
        probas = None
        if hasattr(model, "predict_proba"):
            try:
                probas = model.predict_proba(X_test)
            except Exception:
                pass
        ev = ClassificationEvaluator(y_test, y_pred, probas=probas, task="multiclass")
        result = ev.summary(verbose=True)
        metrics = result.to_dict()

        if args.save_plots:
            from evaluation.plots import plot_confusion_matrix
            plot_confusion_matrix(result.confusion_matrix, model_name=args.model,
                                  output_path=f"{args.save_plots}_cm.png")

    # ── Permutation importance ────────────────────────────────────────────────
    if args.with_perm_importance:
        from models.common.base_evaluator import BaseEvaluator
        evaluator = BaseEvaluator(model, config)
        try:
            perm_df = evaluator.permutation_importance(X_test, y_test)
            perm_path = Path(args.output).parent / f"{args.model}_perm_importance.csv" if args.output else Path(f"{args.model}_perm_importance.csv")
            perm_df.to_csv(perm_path, index=False)
            print(f"\nPermutation importance → {perm_path}")
        except Exception as exc:
            logger.warning("Permutation importance failed: %s", exc)

    # ── Save metrics ──────────────────────────────────────────────────────────
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(metrics, f, indent=2, default=str)
        print(f"\nTest metrics saved → {out}")
    else:
        print("\n" + json.dumps(metrics, indent=2, default=str))


if __name__ == "__main__":
    main()
