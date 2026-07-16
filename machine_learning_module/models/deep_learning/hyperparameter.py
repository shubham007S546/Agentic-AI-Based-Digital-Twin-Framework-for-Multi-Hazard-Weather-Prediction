"""
Deep-learning hyperparameter tuner: Optuna search space + grid/random search
fallbacks, reusing BaseHyperparameterTuner exactly like the tree-based
algorithms. Each trial fully retrains the network, so keep --n-trials modest
(these runs are much slower than a tree model fit).

Example
-------
python -m models.machine_learning.deep_learning.hyperparameter \\
    --data-dir ml_ready --target-column imd_rainfall_mm --task-type regression \\
    --architecture lstm --method optuna --n-trials 15
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from models.common.base_tuner import BaseHyperparameterTuner
from models.common.data_utils import load_dataset_bundle
from models.common.logging_config import get_logger

from .config import DeepLearningConfig
from .model import DeepLearningModel
from .utils import add_common_cli_args, add_dl_cli_args, build_config_from_args

logger = get_logger(__name__, log_file="logs/deep_learning_tuning.log")


class DeepLearningTuner(BaseHyperparameterTuner):
    def _extra_fit_kwargs(self) -> dict:
        return {
            "eval_set": [(self.bundle.X_val, self.bundle.y_val)],
            "class_weights": self.bundle.class_weights,
        }

    def search_space(self, trial: Any) -> dict:
        return {
            "hidden_size": trial.suggest_categorical("hidden_size", [32, 64, 128]),
            "num_layers": trial.suggest_int("num_layers", 1, 3),
            "dropout": trial.suggest_float("dropout", 0.0, 0.5),
            "learning_rate": trial.suggest_float("learning_rate", 1e-4, 1e-2, log=True),
            "batch_size": trial.suggest_categorical("batch_size", [32, 64, 128]),
            "sequence_length": trial.suggest_categorical("sequence_length", [12, 24, 48]),
        }

    def param_grid(self) -> dict:
        return {
            "hidden_size": [32, 64],
            "num_layers": [1, 2],
            "learning_rate": [1e-3, 5e-4],
        }

    def param_distributions(self) -> dict:
        return {
            "hidden_size": [32, 64, 128],
            "num_layers": [1, 2, 3],
            "dropout": [0.0, 0.1, 0.2, 0.3, 0.5],
            "learning_rate": [1e-4, 5e-4, 1e-3, 5e-3, 1e-2],
            "batch_size": [32, 64, 128],
            "sequence_length": [12, 24, 48],
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tune deep-learning hyperparameters.")
    parser = add_common_cli_args(parser)
    parser = add_dl_cli_args(parser)
    parser.add_argument("--method", choices=["optuna", "grid", "random"], default="optuna")
    parser.add_argument("--n-trials", dest="n_trials", type=int, default=15)
    parser.add_argument("--n-iter", dest="n_iter", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config: DeepLearningConfig = build_config_from_args(args)

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

    tuner = DeepLearningTuner(config, DeepLearningModel, bundle)

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
