"""
Random Forest hyperparameter tuner: Optuna search space + grid/random search
fallbacks, all sharing BaseHyperparameterTuner's tune_optuna / tune_grid_search
/ tune_random_search loops.

Example
-------
python -m models.machine_learning.random_forest.hyperparameter \
    --data-dir ml_ready --target-column imd_rainfall_mm \
    --task-type regression --method optuna --n-trials 50
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from models.common.base_tuner import BaseHyperparameterTuner
from models.common.data_utils import load_dataset_bundle
from models.common.logging_config import get_logger

from .config import RandomForestConfig
from .model import RandomForestModel
from .utils import add_common_cli_args, add_rf_cli_args, build_config_from_args

logger = get_logger(__name__, log_file="logs/random_forest_tuning.log")


class RandomForestTuner(BaseHyperparameterTuner):
    def search_space(self, trial: Any) -> dict:
        return {
            "n_estimators": trial.suggest_int("n_estimators", 100, 800, step=50),
            "max_depth": trial.suggest_categorical("max_depth", [None, 5, 10, 15, 20, 30]),
            "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 10),
            "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2", 0.5, 0.7, None]),
        }

    def param_grid(self) -> dict:
        return {
            "n_estimators": [100, 300, 500],
            "max_depth": [None, 10, 20],
            "min_samples_split": [2, 5, 10],
            "min_samples_leaf": [1, 2, 4],
        }

    def param_distributions(self) -> dict:
        return {
            "n_estimators": [100, 200, 300, 400, 500, 600, 800],
            "max_depth": [None, 5, 10, 15, 20, 30],
            "min_samples_split": [2, 5, 10, 15, 20],
            "min_samples_leaf": [1, 2, 4, 6, 10],
            "max_features": ["sqrt", "log2", 0.5, 0.7, None],
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tune Random Forest hyperparameters.")
    parser = add_common_cli_args(parser)
    parser = add_rf_cli_args(parser)
    parser.add_argument("--method", choices=["optuna", "grid", "random"], default="optuna")
    parser.add_argument("--n-trials", dest="n_trials", type=int, default=50)
    parser.add_argument("--n-iter", dest="n_iter", type=int, default=25)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config: RandomForestConfig = build_config_from_args(args)

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

    tuner = RandomForestTuner(config, RandomForestModel, bundle)

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
