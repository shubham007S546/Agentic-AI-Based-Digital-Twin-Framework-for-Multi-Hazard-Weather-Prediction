"""
training/benchmark.py
─────────────────────────────────────────────────────────────────────────────
Full benchmark runner — trains ALL models sequentially, evaluates each on
the test split, and produces the final comparison report.

This is the single command that generates the complete benchmark table
for the research paper, covering all 7 architectures:
  XGBoost, LightGBM, LSTM, GRU, TCN, TFT-Lite

Each model is:
  1. Trained on X_train / y_train (using val split for early stopping)
  2. Evaluated on X_test / y_test
  3. Registered in the model registry
  4. Individual metrics saved to reports/benchmark/<model>/

Finally, a ranked comparison report is printed and saved to:
  reports/benchmark_results.json
  reports/benchmark_results.csv
  reports/plots/benchmark_comparison.png
  reports/plots/benchmark_taylor.png

Usage
─────
  # Full benchmark (all models):
  python training/benchmark.py \\
      --data-dir ml_ready \\
      --target-column imd_rainfall_mm \\
      --task-type regression \\
      --output-dir reports

  # Quick benchmark (only ML models, fewer epochs for DL):
  python training/benchmark.py \\
      --data-dir ml_ready \\
      --target-column imd_rainfall_mm \\
      --task-type regression \\
      --models xgboost lightgbm lstm \\
      --epochs 20 \\
      --output-dir reports

  # Cloudburst detection benchmark:
  python training/benchmark.py \\
      --data-dir ml_ready \\
      --target-column cloudburst_flag \\
      --task-type binary \\
      --train-x-file X_train_cloudburst_flag_balanced.csv \\
      --train-y-file y_train_cloudburst_flag_balanced.csv \\
      --output-dir reports/cloudburst_benchmark
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ML_MODULE  = _REPO_ROOT / "machine_learning_module"
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_ML_MODULE))

from models.common.data_utils    import load_dataset_bundle
from models.common.logging_config import get_logger
from models.common.model_registry import ModelRegistry

logger = get_logger(__name__, log_file="logs/benchmark.log")

# ── Default model roster ──────────────────────────────────────────────────────

ALL_MODELS = ["xgboost", "lightgbm", "lstm", "gru", "tcn", "tft"]


# ── Per-model train + evaluate ────────────────────────────────────────────────

def _train_and_evaluate(
    model_key: str,
    bundle,
    args: argparse.Namespace,
    output_dir: Path,
    registry: ModelRegistry,
) -> Optional[dict]:
    """Train one model and return its test metrics dict, or None on failure."""

    from models.common.config_schema import TaskType
    from models.common.base_trainer  import BaseTrainer
    from models.common.base_evaluator import BaseEvaluator

    task_type_str = args.task_type.upper().replace(" ", "_").replace("-", "_")
    try:
        task_type = TaskType[task_type_str]
    except KeyError:
        task_type = TaskType.REGRESSION

    model_dir = output_dir / model_key
    model_dir.mkdir(parents=True, exist_ok=True)

    # -- Build model & config --
    try:
        if model_key in ("xgboost", "xgb"):
            from models.machine_learning.xgboost.config import XGBoostConfig
            from models.machine_learning.xgboost.model  import XGBoostModel
            cfg   = XGBoostConfig(data_dir=args.data_dir, target_column=args.target_column,
                                  task_type=task_type, experiment_name=f"{model_key}_benchmark",
                                  n_estimators=args.n_estimators, random_seed=args.seed,
                                  artifacts_dir=str(model_dir))
            model = XGBoostModel(cfg)

        elif model_key in ("lightgbm", "lgb"):
            from models.machine_learning.lightgbm.config import LightGBMConfig
            from models.machine_learning.lightgbm.model  import LightGBMModel
            cfg   = LightGBMConfig(data_dir=args.data_dir, target_column=args.target_column,
                                   task_type=task_type, experiment_name=f"{model_key}_benchmark",
                                   n_estimators=args.n_estimators, random_seed=args.seed,
                                   artifacts_dir=str(model_dir))
            model = LightGBMModel(cfg)

        elif model_key in ("lstm", "gru", "tcn"):
            from models.deep_learning.config import DeepLearningConfig
            from models.deep_learning.model  import DeepLearningModel
            cfg   = DeepLearningConfig(data_dir=args.data_dir, target_column=args.target_column,
                                       task_type=task_type, experiment_name=f"{model_key}_benchmark",
                                       architecture=model_key,
                                       epochs=args.epochs,
                                       early_stopping_patience=args.early_stopping,
                                       sequence_length=args.sequence_length,
                                       device=args.device, random_seed=args.seed,
                                       artifacts_dir=str(model_dir))
            model = DeepLearningModel(cfg)

        elif model_key in ("tft", "transformer"):
            from models.transformer.config import TFTLiteConfig
            from models.transformer.model  import TFTLiteModel
            cfg   = TFTLiteConfig(data_dir=args.data_dir, target_column=args.target_column,
                                  task_type=task_type, experiment_name=f"{model_key}_benchmark",
                                  epochs=args.epochs,
                                  early_stopping_patience=args.early_stopping,
                                  sequence_length=args.sequence_length,
                                  device=args.device, random_seed=args.seed,
                                  artifacts_dir=str(model_dir))
            model = TFTLiteModel(cfg)
        else:
            logger.warning("Unknown model key: %s — skipping", model_key)
            return None

    except Exception as exc:
        logger.error("[%s] Failed to build model: %s", model_key, exc)
        return None

    # -- Train --
    print(f"\n{'─'*60}")
    print(f"  Training: {model_key.upper()}  ...")
    print(f"{'─'*60}")
    t0 = time.perf_counter()
    try:
        trainer = BaseTrainer(cfg, model)
        result  = trainer.run(bundle, eval_set=[(bundle.X_val, bundle.y_val)],
                               class_weights=bundle.class_weights)
    except Exception as exc:
        logger.error("[%s] Training failed: %s", model_key, exc)
        print(f"  ✗ {model_key.upper()} training failed: {exc}")
        return None
    train_elapsed = time.perf_counter() - t0

    # -- Save artifact --
    artifact_path = cfg.artifact_path("model.joblib")
    result["model"].save(str(artifact_path))

    # -- Evaluate on test --
    print(f"  Evaluating on test split ...")
    evaluator = BaseEvaluator(result["model"], cfg)
    try:
        test_metrics = evaluator.compute_metrics(bundle.X_test, bundle.y_test)
    except Exception as exc:
        logger.error("[%s] Evaluation failed: %s", model_key, exc)
        test_metrics = result.get("val_metrics", {})

    # -- Enriched regression metrics --
    if args.task_type == "regression":
        try:
            from evaluation.regression_metrics import RegressionEvaluator
            y_pred = result["model"].predict(bundle.X_test)
            reg_ev = RegressionEvaluator(bundle.y_test, y_pred)
            reg_result = reg_ev.evaluate()
            test_metrics.update({
                "nse":   reg_result.nse,
                "kge":   reg_result.kge,
                "pbias": reg_result.pbias,
                "mape":  reg_result.mape,
                "bias":  reg_result.bias,
            })
        except Exception as exc:
            logger.warning("[%s] Extended regression metrics failed: %s", model_key, exc)

    # -- Save metrics --
    metrics_file = model_dir / "test_metrics.json"
    with open(metrics_file, "w") as f:
        json.dump(test_metrics, f, indent=2, default=str)

    # -- Register --
    registry.register(
        model_name=model_key,
        experiment_name=f"{model_key}_benchmark",
        artifact_path=str(artifact_path),
        task_type=args.task_type,
        metrics=test_metrics,
        params={"train_elapsed_s": round(train_elapsed, 1)},
    )

    # -- Summary --
    print(f"  ✓ {model_key.upper()} — trained in {train_elapsed:.1f}s")
    for k, v in test_metrics.items():
        if isinstance(v, float):
            print(f"    {k:20s} = {v:.4f}")

    return {"model": model_key, "elapsed_s": round(train_elapsed, 1), **test_metrics}


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Full benchmark: train + evaluate ALL models and produce comparison report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--data-dir",        default="ml_ready")
    parser.add_argument("--target-column",   default="imd_rainfall_mm")
    parser.add_argument("--task-type",       default="regression",
                        choices=["regression", "binary", "multiclass"])
    parser.add_argument("--models",          nargs="+", default=None,
                        help=f"Subset of models to benchmark (default: all = {ALL_MODELS})")
    parser.add_argument("--output-dir",      default="reports")
    parser.add_argument("--registry",        default="machine_learning_module/artifacts/model_registry.json")
    parser.add_argument("--seed",            type=int, default=42)

    # ML hyperparams
    parser.add_argument("--n-estimators",    type=int, default=500)

    # DL hyperparams
    parser.add_argument("--epochs",          type=int, default=100)
    parser.add_argument("--early-stopping",  type=int, default=10)
    parser.add_argument("--sequence-length", type=int, default=24)
    parser.add_argument("--device",          default="auto")

    # Data
    parser.add_argument("--train-x-file",    default="X_train.csv")
    parser.add_argument("--train-y-file",    default="y_train.csv")
    parser.add_argument("--drop-columns",    default="")

    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    models_to_run = args.models or ALL_MODELS

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    bench_dir = output_dir / "benchmark"
    bench_dir.mkdir(parents=True, exist_ok=True)
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 70)
    print("  FULL MODEL BENCHMARK")
    print(f"  Task      : {args.task_type}")
    print(f"  Target    : {args.target_column}")
    print(f"  Data dir  : {args.data_dir}")
    print(f"  Models    : {', '.join(models_to_run)}")
    print(f"  Output    : {output_dir}")
    print("=" * 70)

    # Load data once for all models
    drop_cols = [c.strip() for c in args.drop_columns.split(",") if c.strip()]
    print("\nLoading dataset ...")
    bundle = load_dataset_bundle(
        data_dir=args.data_dir,
        target_column=args.target_column,
        train_x_filename=args.train_x_file,
        train_y_filename=args.train_y_file,
        drop_columns=drop_cols,
    )
    print(f"  X_train={bundle.X_train.shape}  X_val={bundle.X_val.shape}  X_test={bundle.X_test.shape}")

    registry = ModelRegistry(registry_path=args.registry)

    all_results = []
    global_t0 = time.perf_counter()

    for model_key in models_to_run:
        metrics = _train_and_evaluate(model_key, bundle, args, bench_dir, registry)
        if metrics:
            all_results.append(metrics)

    total_elapsed = time.perf_counter() - global_t0

    # ── Comparison report ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  BENCHMARK COMPLETE — Generating comparison report ...")
    print("=" * 70)

    from evaluation.compare_models import BenchmarkReport
    report_builder = BenchmarkReport(registry, task_type=args.task_type)
    report = report_builder.build(model_names=models_to_run)
    report["total_elapsed_seconds"] = round(total_elapsed, 1)
    report["generated_at"] = datetime.now(timezone.utc).isoformat()

    report_builder.print_table(report)
    report_builder.save(str(output_dir / "benchmark_results"), report)

    # ── Comparison plot ────────────────────────────────────────────────────────
    primary_metric = report.get("primary_metric", "rmse")
    ranked = report.get("ranked_models", [])
    if ranked:
        try:
            from evaluation.plots import plot_model_comparison, plot_taylor_diagram
            model_names  = [r["model_name"] for r in ranked]
            metric_vals  = [r.get(primary_metric, 0) for r in ranked]
            higher_is_better = primary_metric in ("r2", "nse", "kge", "f1", "roc_auc", "accuracy", "macro_f1")
            plot_model_comparison(
                model_names, metric_vals,
                metric_label=primary_metric.upper(),
                higher_is_better=higher_is_better,
                title=f"Benchmark: {args.target_column} | Metric: {primary_metric}",
                output_path=str(plots_dir / "benchmark_comparison.png"),
            )
            # Taylor diagram for regression
            if args.task_type == "regression" and all_results:
                taylor_points = []
                for r in all_results:
                    std_ratio = r.get("std_ratio", 1.0)
                    corr_val  = r.get("r2", 0.5)
                    if corr_val > 0:
                        import math
                        corr_val = math.sqrt(corr_val)  # approximate correlation from R²
                    taylor_points.append({"name": r["model"], "std_ratio": std_ratio, "correlation": corr_val})
                plot_taylor_diagram(
                    obs_std=1.0,
                    model_points=taylor_points,
                    title=f"Taylor Diagram — {args.target_column}",
                    output_path=str(plots_dir / "benchmark_taylor.png"),
                )
        except Exception as exc:
            logger.warning("Plot generation failed: %s", exc)

    print(f"\n  ⏱  Total time: {total_elapsed/60:.1f} min")
    print(f"  🏆  Best model: {report.get('best_model', 'N/A')}")
    print(f"\n  Reports saved to: {output_dir}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
