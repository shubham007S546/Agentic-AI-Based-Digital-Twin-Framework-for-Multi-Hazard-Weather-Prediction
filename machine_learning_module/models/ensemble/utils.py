"""Ensemble-specific helper functions (CLI arg parsing / config building)."""

from __future__ import annotations

import argparse

from models.common.config_schema import TaskType

from .config import EnsembleConfig


def build_config_from_args(args: argparse.Namespace) -> EnsembleConfig:
    base_algorithms = [a.strip() for a in args.base_algorithms.split(",") if a.strip()]
    weights = None
    if args.weights:
        weights = [float(w.strip()) for w in args.weights.split(",") if w.strip()]

    config = EnsembleConfig(
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
        base_algorithms=base_algorithms,
        ensemble_method=args.ensemble_method,
        meta_learner=args.meta_learner,
        meta_learner_alpha=args.meta_learner_alpha,
        cv_folds=args.cv_folds,
        weights=weights,
        use_proba_for_classification_stacking=args.use_proba_for_stacking,
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
                         help="Filename (relative to data-dir) to use for TRAIN features. val/test always use X_val.csv/X_test.csv.")
    parser.add_argument("--train-y-file", dest="train_y_file", default="y_train.csv",
                         help="Filename (relative to data-dir) to use for TRAIN targets. val/test always use y_val.csv/y_test.csv.")
    parser.add_argument("--drop-columns", dest="drop_columns", default="",
                         help="Comma-separated non-feature columns to drop from X.")
    parser.add_argument("--experiment-name", dest="experiment_name", default="ensemble_experiment")
    parser.add_argument("--artifacts-dir", dest="artifacts_dir", default="artifacts")
    parser.add_argument("--target-transform", dest="target_transform", default="none",
                         choices=["none", "log1p"],
                         help="Regression only: fit every base model + the meta-learner on log1p(target), "
                              "inverse-transform the final ensemble prediction with expm1.")
    return parser


def add_ensemble_cli_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--base-algorithms", dest="base_algorithms", default="random_forest,xgboost,lightgbm",
                         help="Comma-separated list from {random_forest, xgboost, lightgbm, deep_learning}.")
    parser.add_argument("--ensemble-method", dest="ensemble_method", default="stacking",
                         choices=["stacking", "voting", "weighted_average"])
    parser.add_argument("--meta-learner", dest="meta_learner", default="ridge", choices=["ridge", "logistic"],
                         help="Stacking only. Ridge for regression targets, Logistic for classification "
                              "(auto-appropriate for the chosen --task-type either way).")
    parser.add_argument("--meta-learner-alpha", dest="meta_learner_alpha", type=float, default=1.0,
                         help="Ridge regularization strength (stacking, regression only).")
    parser.add_argument("--cv-folds", dest="cv_folds", type=int, default=5,
                         help="Out-of-fold splits used to build stacking meta-features (leakage-safe).")
    parser.add_argument("--weights", dest="weights", default=None,
                         help="Comma-separated weights, same order as --base-algorithms (weighted_average only). "
                              "If omitted, weights are auto-derived from validation performance.")
    parser.add_argument("--use-proba-for-stacking", dest="use_proba_for_stacking", action="store_true", default=True)
    parser.add_argument("--no-proba-for-stacking", dest="use_proba_for_stacking", action="store_false")
    return parser
