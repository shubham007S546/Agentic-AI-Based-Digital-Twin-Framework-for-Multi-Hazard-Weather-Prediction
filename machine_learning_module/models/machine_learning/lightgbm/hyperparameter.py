"""
LightGBM hyperparameter tuner: Optuna search space + grid/random search
fallbacks. Early stopping is preserved during tuning via the validation
eval_set (see `_extra_fit_kwargs`).

Example
-------
python -m models.machine_learning.lightgbm.hyperparameter \
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

from .config import LightGBMConfig
from .model import LightGBMModel
from .utils import add_common_cli_args, add_lgbm_cli_args, build_config_from_args

logger = get_logger(__name__, log_file="logs/lightgbm_tuning.log")


class LightGBMTuner(BaseHyperparameterTuner):
    def _extra_fit_kwargs(self) -> dict:
        kwargs: dict = {"class_weights": self.bundle.class_weights}
        if self.config.early_stopping_rounds is not None and self.config.use_validation_for_early_stopping:
            kwargs["eval_set"] = [(self.bundle.X_val, self.bundle.y_val)]
        return kwargs

    def search_space(self, trial: Any) -> dict:
        return {
            "n_estimators": trial.suggest_int("n_estimators", 100, 1000, step=50),
            "num_leaves": trial.suggest_int("num_leaves", 15, 255, log=True),
            "max_depth": trial.suggest_categorical("max_depth", [-1, 5, 10, 15, 20]),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
        }

    def param_grid(self) -> dict:
        return {
            "n_estimators": [200, 500],
            "num_leaves": [15, 31, 63],
            "learning_rate": [0.01, 0.05, 0.1],
            "subsample": [0.7, 1.0],
        }

    def param_distributions(self) -> dict:
        return {
            "n_estimators": [100, 200, 300, 500, 700, 1000],
            "num_leaves": [15, 31, 63, 127, 255],
            "max_depth": [-1, 5, 10, 15, 20],
            "learning_rate": [0.005, 0.01, 0.03, 0.05, 0.1, 0.2, 0.3],
            "subsample": [0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            "colsample_bytree": [0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            "min_child_samples": [5, 10, 20, 30, 50, 100],
            "reg_alpha": [0.0001, 0.001, 0.01, 0.1, 1.0, 10.0],
            "reg_lambda": [0.0001, 0.001, 0.01, 0.1, 1.0, 10.0],
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tune LightGBM hyperparameters.")
    parser = add_common_cli_args(parser)
    parser = add_lgbm_cli_args(parser)
    parser.add_argument("--method", choices=["optuna", "grid", "random"], default="optuna")
    parser.add_argument("--n-trials", dest="n_trials", type=int, default=50)
    parser.add_argument("--n-iter", dest="n_iter", type=int, default=25)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config: LightGBMConfig = build_config_from_args(args)

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

    tuner = LightGBMTuner(config, LightGBMModel, bundle)

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
