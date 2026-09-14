"""
evaluation/compare_models.py
─────────────────────────────────────────────────────────────────────────────
Multi-model benchmark comparison CLI.

Reads trained model artifacts from the ModelRegistry (JSON file produced by
each model's train.py) and generates a ranked benchmark report in both human-
readable table and JSON format — the primary benchmark export artifact for
the research paper.

Works without ml_ready/ data (uses val/test metrics already stored in the
registry) OR can re-run evaluation on fresh data (--recompute flag).

Usage
─────
# Compare all registered models using stored metrics:
    python evaluation/compare_models.py \
        --registry machine_learning_module/artifacts/model_registry.json \
        --output reports/benchmark_results

# Re-compute metrics on a fresh test set and then compare:
    python evaluation/compare_models.py \
        --registry machine_learning_module/artifacts/model_registry.json \
        --recompute \
        --data-dir ml_ready \
        --target-column imd_rainfall_mm \
        --task-type regression \
        --output reports/benchmark_results
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Make machine_learning_module importable ──────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "machine_learning_module"))

import pandas as pd

from models.common.model_registry import ModelRegistry


# ── Metric ranking config ────────────────────────────────────────────────────

# metric → (higher_is_better, display_label)
_METRIC_CONFIG = {
    "rmse":           (False, "RMSE (mm)"),
    "mae":            (False, "MAE  (mm)"),
    "r2":             (True,  "R²"),
    "nse":            (True,  "NSE"),
    "kge":            (True,  "KGE"),
    "pbias":          (False, "PBIAS (%)"),  # closer to 0 is better — handled specially
    "mape":           (False, "MAPE (%)"),
    "accuracy":       (True,  "Accuracy"),
    "f1":             (True,  "F1"),
    "roc_auc":        (True,  "ROC-AUC"),
    "pr_auc":         (True,  "PR-AUC"),
    "mcc":            (True,  "MCC"),
    "macro_f1":       (True,  "Macro-F1"),
    "weighted_f1":    (True,  "Weighted-F1"),
    "skill_vs_persistence": (True, "Skill (vs pers.)"),
    "skill_vs_climatology": (True, "Skill (vs clim.)"),
}

_RANK_PRIMARY = {
    "regression":   "rmse",
    "binary":       "f1",
    "multiclass":   "macro_f1",
    "forecasting":  "skill_vs_persistence",
}


# ── Report builder ───────────────────────────────────────────────────────────

class BenchmarkReport:
    """
    Aggregate metrics from a ModelRegistry into a comparison report.
    """

    def __init__(self, registry: ModelRegistry, task_type: str = "regression") -> None:
        self.registry  = registry
        self.task_type = task_type.lower()

    # -- helpers --

    def _get_primary_metric(self) -> str:
        return _RANK_PRIMARY.get(self.task_type, "rmse")

    def _higher_is_better(self, metric: str) -> bool:
        cfg = _METRIC_CONFIG.get(metric)
        if cfg is None:
            return True  # unknown metric: assume higher = better
        return cfg[0]

    def _rank_entries(self, entries: list, metric: str) -> list:
        hib = self._higher_is_better(metric)
        # For pbias: rank by absolute value
        if metric == "pbias":
            return sorted(entries, key=lambda e: abs(e["metrics"].get(metric, float("inf"))))
        return sorted(entries, key=lambda e: e["metrics"].get(metric, float("-inf") if hib else float("inf")),
                      reverse=hib)

    # -- main --

    def build(self, model_names: list | None = None) -> dict:
        entries = self.registry.list_entries()
        if model_names:
            entries = [e for e in entries if e["model_name"] in model_names]

        if not entries:
            return {"error": "No models found in registry.", "entries": []}

        primary = self._get_primary_metric()
        ranked  = self._rank_entries(entries, primary)

        rows = []
        for rank, e in enumerate(ranked, start=1):
            row = {
                "rank":            rank,
                "model_name":      e["model_name"],
                "experiment_name": e["experiment_name"],
                "task_type":       e["task_type"],
                "artifact_path":   e["artifact_path"],
                "registered_at":   e.get("registered_at", ""),
            }
            row.update(e.get("metrics", {}))
            rows.append(row)

        df = pd.DataFrame(rows)

        return {
            "generated_at":     datetime.now(timezone.utc).isoformat(),
            "task_type":        self.task_type,
            "primary_metric":   primary,
            "n_models":         len(rows),
            "ranked_models":    rows,
            "best_model":       rows[0]["model_name"] if rows else None,
            "best_metrics":     rows[0] if rows else {},
        }

    def print_table(self, report: dict | None = None) -> None:
        if report is None:
            report = self.build()

        primary = report.get("primary_metric", "rmse")
        models  = report.get("ranked_models", [])

        if not models:
            print("[BenchmarkReport] No models to display.")
            return

        # Determine columns to show
        metric_cols = [k for k in models[0] if k in _METRIC_CONFIG]

        header_parts = [f"{'Rank':>4}", f"{'Model':30}", f"{'Experiment':25}"]
        for col in metric_cols:
            label = _METRIC_CONFIG.get(col, (None, col))[1]
            header_parts.append(f"{label:>14}")
        header = "  ".join(header_parts)

        sep = "─" * len(header)
        print()
        print("  MODEL BENCHMARK REPORT")
        print(f"  Task: {report['task_type']}   |   Primary metric: {primary}")
        print(f"  Generated: {report['generated_at']}")
        print(sep)
        print(header)
        print(sep)

        for row in models:
            row_parts = [
                f"{row['rank']:>4}",
                f"{row['model_name']:30}",
                f"{row['experiment_name']:25}",
            ]
            for col in metric_cols:
                val = row.get(col, "–")
                if isinstance(val, float):
                    row_parts.append(f"{val:>14.4f}")
                else:
                    row_parts.append(f"{str(val):>14}")
            print("  ".join(row_parts))

        print(sep)
        print(f"  🏆  Best model: {report['best_model']}  (ranked by {primary})")
        print()

    def save(self, output_prefix: str | Path, report: dict | None = None) -> None:
        if report is None:
            report = self.build()

        out = Path(output_prefix)
        out.parent.mkdir(parents=True, exist_ok=True)

        # JSON
        json_path = out.with_suffix(".json")
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"[BenchmarkReport] JSON saved → {json_path}")

        # CSV (flat, no nested dicts)
        rows = [
            {k: v for k, v in r.items() if not isinstance(v, (dict, list))}
            for r in report.get("ranked_models", [])
        ]
        if rows:
            csv_path = out.with_suffix(".csv")
            pd.DataFrame(rows).to_csv(csv_path, index=False)
            print(f"[BenchmarkReport] CSV  saved → {csv_path}")


# ── Recompute mode (loads artifacts & re-evaluates on fresh data) ─────────────

def _recompute_metrics(entries: list, data_dir: str, target_column: str, task_type: str) -> list:
    """
    For each registry entry, load the saved model and re-compute metrics on the
    test split. Adds/overwrites the 'metrics' field with fresh values.
    """
    from models.common.base_evaluator import BaseEvaluator
    from models.common.data_utils import load_dataset_bundle
    from models.common.config_schema import TaskType

    print(f"[recompute] Loading dataset from {data_dir} ...")
    bundle = load_dataset_bundle(data_dir=data_dir, target_column=target_column)

    updated = []
    for entry in entries:
        model_path = entry.get("artifact_path", "")
        model_name = entry.get("model_name", "")
        print(f"[recompute] Evaluating {model_name} from {model_path} ...")
        try:
            # Dynamic import based on model type
            if "deep_learning" in model_name or "lstm" in model_name or "gru" in model_name or "tcn" in model_name:
                from models.deep_learning.model import DeepLearningModel
                from models.deep_learning.config import DeepLearningConfig
                arch = "lstm" if "lstm" in model_name else ("gru" if "gru" in model_name else "tcn")
                cfg = DeepLearningConfig(
                    data_dir=data_dir,
                    target_column=target_column,
                    task_type=TaskType[task_type.upper()],
                    architecture=arch,
                )
                model = DeepLearningModel(cfg)
            elif "xgboost" in model_name or "xgb" in model_name:
                from models.machine_learning.xgboost.model import XGBoostModel
                from models.machine_learning.xgboost.config import XGBoostConfig
                cfg = XGBoostConfig(data_dir=data_dir, target_column=target_column, task_type=TaskType[task_type.upper()])
                model = XGBoostModel(cfg)
            elif "lightgbm" in model_name or "lgb" in model_name:
                from models.machine_learning.lightgbm.model import LightGBMModel
                from models.machine_learning.lightgbm.config import LightGBMConfig
                cfg = LightGBMConfig(data_dir=data_dir, target_column=target_column, task_type=TaskType[task_type.upper()])
                model = LightGBMModel(cfg)
            elif "transformer" in model_name or "tft" in model_name:
                from models.transformer.model import TFTLiteModel
                from models.transformer.config import TFTLiteConfig
                cfg = TFTLiteConfig(data_dir=data_dir, target_column=target_column, task_type=TaskType[task_type.upper()])
                model = TFTLiteModel(cfg)
            else:
                print(f"  [skip] Cannot auto-detect model class for {model_name}")
                updated.append(entry)
                continue

            model.load(model_path)
            evaluator = BaseEvaluator(model, cfg)
            metrics = evaluator.compute_metrics(bundle.X_test, bundle.y_test)
            entry["metrics"] = metrics
            print(f"  [ok] {model_name}: {metrics}")
        except Exception as exc:
            print(f"  [error] {model_name}: {exc}")

        updated.append(entry)

    return updated


# ── CLI ──────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare all registered models and produce a ranked benchmark report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--registry", default="machine_learning_module/artifacts/model_registry.json",
        help="Path to model_registry.json produced by train.py scripts.",
    )
    parser.add_argument(
        "--task-type", default="regression",
        choices=["regression", "binary", "multiclass", "forecasting"],
        help="Evaluation task type (controls primary ranking metric).",
    )
    parser.add_argument(
        "--models", default=None, nargs="+",
        help="Restrict comparison to specific model names (e.g. xgboost lightgbm).",
    )
    parser.add_argument(
        "--output", default="reports/benchmark_results",
        help="Output path prefix (without extension); .json and .csv will be written.",
    )
    parser.add_argument(
        "--recompute", action="store_true",
        help="Re-evaluate each model on fresh test data instead of using stored metrics.",
    )
    parser.add_argument("--data-dir",      default="ml_ready",       help="(--recompute) ml_ready/ directory.")
    parser.add_argument("--target-column", default="imd_rainfall_mm", help="(--recompute) Target column name.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    registry_path = Path(args.registry)
    if not registry_path.exists():
        print(f"[compare_models] Registry not found: {registry_path}")
        print("  Run training scripts first to populate the registry.")
        sys.exit(1)

    registry = ModelRegistry(registry_path=str(registry_path))
    entries  = registry.list_entries(model_name=None)

    if args.models:
        entries = [e for e in entries if e["model_name"] in args.models]

    if not entries:
        print("[compare_models] No matching models found in registry. Exiting.")
        sys.exit(1)

    if args.recompute:
        entries = _recompute_metrics(entries, args.data_dir, args.target_column, args.task_type)

    # Temporarily write updated entries to a fresh in-memory registry
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as tmp:
        json.dump({"entries": entries}, tmp, indent=2, default=str)
        tmp_path = tmp.name

    tmp_registry = ModelRegistry(registry_path=tmp_path)
    report_builder = BenchmarkReport(tmp_registry, task_type=args.task_type)
    report = report_builder.build(model_names=args.models)

    report_builder.print_table(report)
    report_builder.save(args.output, report)

    Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
