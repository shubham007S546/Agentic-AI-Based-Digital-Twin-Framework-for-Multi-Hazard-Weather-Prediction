"""
training/train.py
─────────────────────────────────────────────────────────────────────────────
Unified training entrypoint for ALL model architectures.

Delegates to the appropriate algorithm sub-package inside
machine_learning_module/models/ based on the --model flag.

Supported models
────────────────
  Machine learning:
    xgboost  (or xgb)
    lightgbm (or lgb)

  Deep learning:
    lstm
    gru
    tcn

  Transformer:
    tft  (Temporal Fusion Transformer — Lite)

Usage
─────
  cd <repo_root>

  # Train XGBoost on rainfall regression
  python training/train.py \\
      --model xgboost \\
      --data-dir ml_ready \\
      --target-column imd_rainfall_mm \\
      --task-type regression \\
      --experiment-name xgb_rainfall_v1

  # Train LSTM
  python training/train.py \\
      --model lstm \\
      --data-dir ml_ready \\
      --target-column imd_rainfall_mm \\
      --task-type regression \\
      --experiment-name lstm_rainfall_v1 \\
      --epochs 80 --early-stopping 10 --sequence-length 24

  # Train TFT
  python training/train.py \\
      --model tft \\
      --data-dir ml_ready \\
      --target-column imd_rainfall_mm \\
      --task-type regression \\
      --experiment-name tft_rainfall_v1 \\
      --epochs 100
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ── Path setup ───────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
_ML_MODULE  = _REPO_ROOT / "machine_learning_module"
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_ML_MODULE))

from models.common.logging_config import get_logger
from models.common.model_registry import ModelRegistry

logger = get_logger(__name__, log_file="logs/training_train.log")


# ── Model factory ─────────────────────────────────────────────────────────────

def _build_model_and_config(args: argparse.Namespace):
    """Return (model_instance, config_instance) for the requested architecture."""
    from models.common.config_schema import TaskType

    try:
        task_type = TaskType[args.task_type.upper()]
    except KeyError:
        task_type = TaskType.REGRESSION

    model_key = args.model.lower().strip()

    # ── XGBoost ──────────────────────────────────────────────────────────────
    if model_key in ("xgboost", "xgb"):
        from models.machine_learning.xgboost.config import XGBoostConfig
        from models.machine_learning.xgboost.model  import XGBoostModel
        cfg = XGBoostConfig(
            data_dir=args.data_dir,
            target_column=args.target_column,
            task_type=task_type,
            experiment_name=args.experiment_name,
            n_estimators=args.n_estimators,
            random_seed=args.seed,
        )
        return XGBoostModel(cfg), cfg

    # ── LightGBM ─────────────────────────────────────────────────────────────
    if model_key in ("lightgbm", "lgb", "lgbm"):
        from models.machine_learning.lightgbm.config import LightGBMConfig
        from models.machine_learning.lightgbm.model  import LightGBMModel
        cfg = LightGBMConfig(
            data_dir=args.data_dir,
            target_column=args.target_column,
            task_type=task_type,
            experiment_name=args.experiment_name,
            n_estimators=args.n_estimators,
            random_seed=args.seed,
        )
        return LightGBMModel(cfg), cfg

    # ── LSTM / GRU / TCN ──────────────────────────────────────────────────────
    if model_key in ("lstm", "gru", "tcn"):
        from models.deep_learning.config import DeepLearningConfig
        from models.deep_learning.model  import DeepLearningModel
        cfg = DeepLearningConfig(
            data_dir=args.data_dir,
            target_column=args.target_column,
            task_type=task_type,
            experiment_name=args.experiment_name,
            architecture=model_key,
            epochs=args.epochs,
            early_stopping_patience=args.early_stopping,
            sequence_length=args.sequence_length,
            hidden_size=args.hidden_size,
            num_layers=args.num_layers,
            dropout=args.dropout,
            batch_size=args.batch_size,
            learning_rate=args.lr,
            device=args.device,
            random_seed=args.seed,
        )
        return DeepLearningModel(cfg), cfg

    # ── TFT-Lite ──────────────────────────────────────────────────────────────
    if model_key in ("tft", "transformer"):
        from models.transformer.config import TFTLiteConfig
        from models.transformer.model  import TFTLiteModel
        cfg = TFTLiteConfig(
            data_dir=args.data_dir,
            target_column=args.target_column,
            task_type=task_type,
            experiment_name=args.experiment_name,
            epochs=args.epochs,
            early_stopping_patience=args.early_stopping,
            sequence_length=args.sequence_length,
            batch_size=args.batch_size,
            learning_rate=args.lr,
            device=args.device,
            random_seed=args.seed,
        )
        return TFTLiteModel(cfg), cfg

    raise ValueError(
        f"Unknown model: {args.model!r}. "
        "Choose from: xgboost, lightgbm, lstm, gru, tcn, tft"
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train any model in the framework with a single command.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Core
    parser.add_argument("--model",           required=True, help="Model architecture (xgboost | lightgbm | lstm | gru | tcn | tft)")
    parser.add_argument("--data-dir",        default="ml_ready",        help="Path to ml_ready/ data directory")
    parser.add_argument("--target-column",   default="imd_rainfall_mm", help="Name of target column in y_*.csv")
    parser.add_argument("--task-type",       default="regression",
                        choices=["regression", "binary_classification", "multiclass_classification"],
                        help="Task type")
    parser.add_argument("--experiment-name", default=None,              help="Experiment name (default: model_<timestamp>)")
    parser.add_argument("--seed",            type=int, default=42)
    parser.add_argument("--registry",        default="machine_learning_module/artifacts/model_registry.json",
                        help="Path to the model registry JSON file")

    # ML hyperparams
    parser.add_argument("--n-estimators",    type=int, default=500)

    # DL hyperparams
    parser.add_argument("--epochs",          type=int, default=100)
    parser.add_argument("--early-stopping",  type=int, default=10)
    parser.add_argument("--sequence-length", type=int, default=24)
    parser.add_argument("--hidden-size",     type=int, default=64)
    parser.add_argument("--num-layers",      type=int, default=2)
    parser.add_argument("--dropout",         type=float, default=0.2)
    parser.add_argument("--batch-size",      type=int, default=64)
    parser.add_argument("--lr",              type=float, default=1e-3)
    parser.add_argument("--device",          default="auto", choices=["cpu", "cuda", "auto"])

    # Data
    parser.add_argument("--train-x-file",    default="X_train.csv")
    parser.add_argument("--train-y-file",    default="y_train.csv")
    parser.add_argument("--drop-columns",    default="")

    return parser.parse_args()


def main() -> None:
    import time
    from datetime import datetime

    args = _parse_args()

    if args.experiment_name is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.experiment_name = f"{args.model.lower()}_{ts}"

    logger.info("=== Training %s  experiment=%s ===", args.model, args.experiment_name)
    logger.info("Data dir: %s | Target: %s | Task: %s", args.data_dir, args.target_column, args.task_type)

    # Load data
    from models.common.data_utils import load_dataset_bundle
    drop_columns = [c.strip() for c in args.drop_columns.split(",") if c.strip()]
    bundle = load_dataset_bundle(
        data_dir=args.data_dir,
        target_column=args.target_column,
        train_x_filename=args.train_x_file,
        train_y_filename=args.train_y_file,
        drop_columns=drop_columns,
    )
    logger.info("Dataset loaded: X_train=%s  X_val=%s  X_test=%s",
                bundle.X_train.shape, bundle.X_val.shape, bundle.X_test.shape)

    # Build model
    model, config = _build_model_and_config(args)

    # Train
    from models.common.base_trainer import BaseTrainer
    trainer = BaseTrainer(config, model)
    eval_set = [(bundle.X_val, bundle.y_val)]

    t0 = time.perf_counter()
    result = trainer.run(bundle, eval_set=eval_set, class_weights=bundle.class_weights)
    elapsed = time.perf_counter() - t0

    # Save artifact
    artifact_path = config.artifact_path("model.joblib")
    result["model"].save(str(artifact_path))
    logger.info("Model saved → %s", artifact_path)

    # Save val metrics
    metrics_path = config.artifact_path("val_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(result["val_metrics"], f, indent=2)
    logger.info("Val metrics → %s", metrics_path)

    # Register
    registry = ModelRegistry(registry_path=args.registry)
    registry.register(
        model_name=f"{args.model.lower()}",
        experiment_name=args.experiment_name,
        artifact_path=str(artifact_path),
        task_type=args.task_type,
        metrics=result["val_metrics"],
        params={k: v for k, v in vars(args).items()},
    )
    logger.info("Registered in model registry: %s", args.registry)

    # Summary
    print("\n" + "=" * 60)
    print(f"  Training complete: {args.model.upper()}  ({elapsed:.1f}s)")
    print(f"  Experiment : {args.experiment_name}")
    print(f"  Artifact   : {artifact_path}")
    print(f"  Val metrics:")
    for k, v in result["val_metrics"].items():
        print(f"    {k:20s} = {v}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
