"""Deep-learning-specific helper functions (CLI arg parsing / config building)."""

from __future__ import annotations

import argparse

from models.common.config_schema import TaskType

from .config import DeepLearningConfig


def build_config_from_args(args: argparse.Namespace) -> DeepLearningConfig:
    tcn_channels = [int(c.strip()) for c in args.tcn_channels.split(",") if c.strip()]
    config = DeepLearningConfig(
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
        architecture=args.architecture,
        sequence_length=args.sequence_length,
        group_column=args.group_column,
        hidden_size=args.hidden_size,
        num_layers=args.num_layers,
        dropout=args.dropout,
        tcn_channels=tcn_channels,
        tcn_kernel_size=args.tcn_kernel_size,
        num_classes=args.num_classes,
        batch_size=args.batch_size,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        early_stopping_patience=args.early_stopping_patience,
        grad_clip_norm=args.grad_clip_norm,
        device=args.device,
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
                         help="Comma-separated non-feature columns to drop from X (in addition to --group-column, which is handled automatically).")
    parser.add_argument("--experiment-name", dest="experiment_name", default="dl_experiment")
    parser.add_argument("--artifacts-dir", dest="artifacts_dir", default="artifacts")
    parser.add_argument("--target-transform", dest="target_transform", default="none",
                         choices=["none", "log1p"],
                         help="Regression only: fit on log1p(target), inverse-transform predictions with expm1.")
    return parser


def add_dl_cli_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--architecture", dest="architecture", default="lstm", choices=["lstm", "gru", "tcn"])
    parser.add_argument("--sequence-length", dest="sequence_length", type=int, default=24,
                         help="Rows of history per prediction window (zero-padded at the start of each group/series).")
    parser.add_argument("--group-column", dest="group_column", default=None,
                         help="Column name (must be present in X_*.csv) that identifies separate time series "
                              "(e.g. a district/station id), so windows never bleed across them. Handled "
                              "automatically -- do not also pass it via --drop-columns.")
    parser.add_argument("--hidden-size", dest="hidden_size", type=int, default=64)
    parser.add_argument("--num-layers", dest="num_layers", type=int, default=2)
    parser.add_argument("--dropout", dest="dropout", type=float, default=0.2)
    parser.add_argument("--tcn-channels", dest="tcn_channels", default="64,64,64",
                         help="Comma-separated channel sizes per TCN residual block.")
    parser.add_argument("--tcn-kernel-size", dest="tcn_kernel_size", type=int, default=3)
    parser.add_argument("--num-classes", dest="num_classes", type=int, default=2,
                         help="Only used when --task-type is multiclass_classification.")
    parser.add_argument("--batch-size", dest="batch_size", type=int, default=64)
    parser.add_argument("--epochs", dest="epochs", type=int, default=100)
    parser.add_argument("--learning-rate", dest="learning_rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", dest="weight_decay", type=float, default=1e-5)
    parser.add_argument("--early-stopping-patience", dest="early_stopping_patience", type=int, default=10)
    parser.add_argument("--grad-clip-norm", dest="grad_clip_norm", type=float, default=1.0)
    parser.add_argument("--device", dest="device", default="cpu", choices=["cpu", "cuda", "auto"])
    return parser
