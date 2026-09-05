"""
Ensemble hyperparameter tuner: searches ensemble-level knobs (method,
meta-learner regularization, CV folds) via Optuna + grid/random fallbacks.
Note this does NOT re-tune the base models' own hyperparameters -- tune
random_forest/xgboost/lightgbm individually first (see their own
hyperparameter.py), then use their defaults/best params here. Each trial
retrains every base model + refits, so this is the slowest tuner in the
framework; keep --n-trials small.

Example
-------
python -m models.machine_learning.ensemble.hyperparameter \\
    --data-dir ml_ready --target-column imd_rainfall_mm --task-type regression \\
    --method optuna --n-trials 10
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from models.common.base_tuner import BaseHyperparameterTuner
from models.common.data_utils import load_dataset_bundle
from models.common.logging_config import get_logger

from .config import EnsembleConfig
from .model import EnsembleModel
from .utils import add_common_cli_args, add_ensemble_cli_args, build_config_from_args

logger = get_logger(__name__, log_file="logs/ensemble_tuning.log")


class EnsembleTuner(BaseHyperparameterTuner):
    def _extra_fit_kwargs(self) -> dict:
        return {
            "eval_set": [(self.bundle.X_val, self.bundle.y_val)],
            "class_weights": self.bundle.class_weights,
        }

    def search_space(self, trial: Any) -> dict:
        method = trial.suggest_categorical("ensemble_method", ["stacking", "weighted_average"])
        params = {"ensemble_method": method}
        if method == "stacking":
            params["cv_folds"] = trial.suggest_int("cv_folds", 3, 8)
            params["meta_learner_alpha"] = trial.suggest_float("meta_learner_alpha", 0.01, 100.0, log=True)
        return params

    def param_grid(self) -> dict:
        return {
            "ensemble_method": ["stacking", "weighted_average"],
            "meta_learner_alpha": [0.1, 1.0, 10.0],
        }

    def param_distributions(self) -> dict:
        return {
            "ensemble_method": ["stacking", "voting", "weighted_average"],
            "cv_folds": [3, 4, 5, 6, 8],
            "meta_learner_alpha": [0.01, 0.1, 1.0, 10.0, 100.0],
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tune ensemble-level hyperparameters.")
    parser = add_common_cli_args(parser)
    parser = add_ensemble_cli_args(parser)
    parser.add_argument("--method", choices=["optuna", "grid", "random"], default="optuna")
    parser.add_argument("--n-trials", dest="n_trials", type=int, default=10)
    parser.add_argument("--n-iter", dest="n_iter", type=int, default=8)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config: EnsembleConfig = build_config_from_args(args)

    drop_columns = [c.strip() for c in args.drop_columns.split(",") if c.strip()]
    bundle = load_dataset_bundle(
        data_dir=config.data_dir,
        target_column=config.target_column,
        use_sample_weights=config.use_sample_weights,
        use_class_weights=config.use_class_weights,
        train_x_filename=args.train_x_file,
        train_y_filename=args.train_y_file,
        drop_columns=drop_columns,
    )

    tuner = EnsembleTuner(config, EnsembleModel, bundle)

    if args.method == "optuna":
        result = tuner.tune_optuna(n_trials=args.n_trials)
    elif args.method == "grid":
        result = tuner.tune_grid_search()
    else:
        result = tuner.tune_random_search(n_iter=args.n_iter)

    best_model = result.pop("best_model")
    artifact_path = config.artifact_path("model_tuned.joblib")
    best_model.save(str(artifact_path))

    result_path = config.artifact_path("tuning_result.json")
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    logger.info("Best params: %s | best %s=%.5f", result["best_params"], result["metric"], result["best_score"])
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
