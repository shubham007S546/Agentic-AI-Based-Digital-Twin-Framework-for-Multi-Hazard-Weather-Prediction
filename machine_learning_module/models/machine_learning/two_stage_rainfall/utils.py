"""Two-stage-rainfall-specific helper functions."""

from __future__ import annotations

import argparse

from .config import TwoStageRainfallConfig


def build_config_from_args(args: argparse.Namespace) -> TwoStageRainfallConfig:
    config = TwoStageRainfallConfig(
        data_dir=args.data_dir,
        target_column=args.target_column,
        random_seed=args.random_seed,
        n_jobs=args.n_jobs,
        use_sample_weights=args.use_sample_weights,
        experiment_name=args.experiment_name,
        artifacts_dir=args.artifacts_dir,
        classifier_algorithm=args.classifier_algorithm,
        regressor_algorithm=args.regressor_algorithm,
        rain_threshold=args.rain_threshold,
        log_transform=args.log_transform,
        classification_threshold=args.classification_threshold,
    )
    config.validate()
    return config


def add_common_cli_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--data-dir", dest="data_dir", default="ml_ready")
    parser.add_argument("--target-column", dest="target_column", default="imd_rainfall_mm")
    parser.add_argument("--random-seed", dest="random_seed", type=int, default=42)
    parser.add_argument("--n-jobs", dest="n_jobs", type=int, default=-1)
    parser.add_argument("--use-sample-weights", dest="use_sample_weights", action="store_true", default=True)
    parser.add_argument("--no-sample-weights", dest="use_sample_weights", action="store_false")
    parser.add_argument("--experiment-name", dest="experiment_name", default="two_stage_rainfall_v1")
    parser.add_argument("--artifacts-dir", dest="artifacts_dir", default="artifacts")
    return parser


def add_two_stage_cli_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--classifier-algorithm", dest="classifier_algorithm", default="random_forest",
                         choices=["random_forest", "xgboost", "lightgbm"])
    parser.add_argument("--regressor-algorithm", dest="regressor_algorithm", default="random_forest",
                         choices=["random_forest", "xgboost", "lightgbm"])
    parser.add_argument("--rain-threshold", dest="rain_threshold", type=float, default=0.1,
                         help="mm; rows with target above this are treated as 'it rained' for stage 1.")
    parser.add_argument("--log-transform", dest="log_transform", action="store_true", default=True)
    parser.add_argument("--no-log-transform", dest="log_transform", action="store_false")
    parser.add_argument("--classification-threshold", dest="classification_threshold", type=float, default=0.5,
                         help="Probability cutoff for stage 1's 'did it rain' decision.")
    return parser
