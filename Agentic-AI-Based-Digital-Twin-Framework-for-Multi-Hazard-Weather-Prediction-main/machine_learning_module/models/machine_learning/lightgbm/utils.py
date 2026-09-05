"""LightGBM-specific helper functions."""

from __future__ import annotations

import argparse

from models.common.config_schema import TaskType

from .config import LightGBMConfig


def build_config_from_args(args: argparse.Namespace) -> LightGBMConfig:
    categorical_features = (
        [c.strip() for c in args.categorical_features.split(",") if c.strip()]
        if args.categorical_features else []
    )
    config = LightGBMConfig(
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
        num_leaves=args.num_leaves,
        max_depth=args.max_depth,
        learning_rate=args.learning_rate,
        subsample=args.subsample,
        subsample_freq=args.subsample_freq,
        colsample_bytree=args.colsample_bytree,
        min_child_samples=args.min_child_samples,
        reg_alpha=args.reg_alpha,
        reg_lambda=args.reg_lambda,
        device=args.device,
        categorical_features=categorical_features,
        early_stopping_rounds=args.early_stopping_rounds,
        is_unbalance=args.is_unbalance,
        tweedie_variance_power=args.tweedie_variance_power,
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
    parser.add_argument("--experiment-name", dest="experiment_name", default="lgbm_experiment")
    parser.add_argument("--artifacts-dir", dest="artifacts_dir", default="artifacts")
    parser.add_argument("--target-transform", dest="target_transform", default="none",
                         choices=["none", "log1p"],
                         help="Regression only: fit on log1p(target), inverse-transform predictions with expm1.")
    return parser


def add_lgbm_cli_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--n-estimators", dest="n_estimators", type=int, default=500)
    parser.add_argument("--num-leaves", dest="num_leaves", type=int, default=31)
    parser.add_argument("--max-depth", dest="max_depth", type=int, default=-1)
    parser.add_argument("--learning-rate", dest="learning_rate", type=float, default=0.05)
    parser.add_argument("--subsample", dest="subsample", type=float, default=0.8)
    parser.add_argument("--subsample-freq", dest="subsample_freq", type=int, default=1)
    parser.add_argument("--colsample-bytree", dest="colsample_bytree", type=float, default=0.8)
    parser.add_argument("--min-child-samples", dest="min_child_samples", type=int, default=20)
    parser.add_argument("--reg-alpha", dest="reg_alpha", type=float, default=0.0)
    parser.add_argument("--reg-lambda", dest="reg_lambda", type=float, default=0.0)
    parser.add_argument("--device", dest="device", default="cpu", choices=["cpu", "gpu"])
    parser.add_argument("--categorical-features", dest="categorical_features", default="",
                         help="Comma-separated column names to treat as categorical.")
    parser.add_argument("--early-stopping-rounds", dest="early_stopping_rounds", type=int, default=30)
    parser.add_argument("--tweedie-variance-power", dest="tweedie_variance_power", type=float, default=None,
                         help="Regression only: set to enable a Tweedie loss (e.g. 1.5) for zero-inflated targets like rainfall. Range [1.0, 2.0).")
    parser.add_argument("--is-unbalance", dest="is_unbalance", action="store_true", default=False)
    return parser
