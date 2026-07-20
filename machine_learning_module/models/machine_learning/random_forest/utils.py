"""Random-forest-specific helper functions."""

from __future__ import annotations

import argparse

from models.common.config_schema import TaskType

from .config import RandomForestConfig


def build_config_from_args(args: argparse.Namespace) -> RandomForestConfig:
    """Build a RandomForestConfig from parsed CLI args (see train.py)."""
    config = RandomForestConfig(
        task_type=TaskType(args.task_type),
        data_dir=args.data_dir,
        target_column=args.target_column,
        random_seed=args.random_seed,
        n_jobs=args.n_jobs,
        use_sample_weights=args.use_sample_weights,
        use_class_weights=args.use_class_weights,
        experiment_name=args.experiment_name,
        artifacts_dir=args.artifacts_dir,
        target_transform=args.target_transform,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        min_samples_split=args.min_samples_split,
        min_samples_leaf=args.min_samples_leaf,
        max_features=args.max_features,
        bootstrap=args.bootstrap,
        oob_score=args.oob_score,
        class_weight_mode=args.class_weight_mode,
    )
    config.validate()
    return config


def add_common_cli_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--task-type", dest="task_type", default="regression",
                         choices=["regression", "binary_classification", "multiclass_classification"])
    parser.add_argument("--data-dir", dest="data_dir", default="ml_ready")
    parser.add_argument("--target-column", dest="target_column", default="target")
    parser.add_argument("--random-seed", dest="random_seed", type=int, default=42)
    parser.add_argument("--n-jobs", dest="n_jobs", type=int, default=-1)
    parser.add_argument("--use-sample-weights", dest="use_sample_weights", action="store_true", default=True)
    parser.add_argument("--no-sample-weights", dest="use_sample_weights", action="store_false")
    parser.add_argument("--use-class-weights", dest="use_class_weights", action="store_true", default=True)
    parser.add_argument("--no-class-weights", dest="use_class_weights", action="store_false")
    parser.add_argument("--train-x-file", dest="train_x_file", default="X_train.csv",
                         help="Filename (relative to data-dir) to use for TRAIN features. Point this at a class-balanced variant if desired; val/test always use X_val.csv/X_test.csv.")
    parser.add_argument("--train-y-file", dest="train_y_file", default="y_train.csv",
                         help="Filename (relative to data-dir) to use for TRAIN targets. val/test always use y_val.csv/y_test.csv.")
    parser.add_argument("--drop-columns", dest="drop_columns", default="",
                         help="Comma-separated non-feature columns to drop from X (e.g. an id column present only in a balanced train variant).")
    parser.add_argument("--experiment-name", dest="experiment_name", default="rf_experiment")
    parser.add_argument("--artifacts-dir", dest="artifacts_dir", default="artifacts")
    parser.add_argument("--target-transform", dest="target_transform", default="none",
                         choices=["none", "log1p"],
                         help="Regression only: fit on log1p(target), inverse-transform predictions with expm1.")
    return parser


def add_rf_cli_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--n-estimators", dest="n_estimators", type=int, default=300)
    parser.add_argument("--max-depth", dest="max_depth", type=int, default=None)
    parser.add_argument("--min-samples-split", dest="min_samples_split", type=int, default=2)
    parser.add_argument("--min-samples-leaf", dest="min_samples_leaf", type=int, default=1)
    parser.add_argument("--max-features", dest="max_features", default="sqrt")
    parser.add_argument("--bootstrap", dest="bootstrap", action="store_true", default=True)
    parser.add_argument("--no-bootstrap", dest="bootstrap", action="store_false")
    parser.add_argument("--oob-score", dest="oob_score", action="store_true", default=True)
    parser.add_argument("--no-oob-score", dest="oob_score", action="store_false")
    parser.add_argument("--class-weight-mode", dest="class_weight_mode", default="balanced",
                         choices=["balanced", "balanced_subsample", "none"])
    return parser
