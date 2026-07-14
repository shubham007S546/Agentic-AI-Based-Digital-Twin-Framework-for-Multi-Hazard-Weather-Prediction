"""
Data loading utilities shared by every model.

Reads the pre-split, pre-scaled dataset produced upstream and located in
`data_dir` (typically ml_ready/):

    X_train.csv, X_val.csv, X_test.csv
    y_train.csv, y_val.csv, y_test.csv
    sample_weights_train.csv        (optional, one column, same row order as X_train)
    class_weights.json              (optional, {"0": w0, "1": w1, ...})
    dataset_metadata.json           (optional, informational)
    split_report.txt                (optional, informational)
    scaler_params.csv                (optional, informational / for inverse-transform)

No path in this module is hardcoded: every path is derived from `data_dir`.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .exceptions import DataValidationError


def set_global_seed(seed: int) -> None:
    """Set every relevant RNG for reproducibility (python, numpy)."""
    random.seed(seed)
    np.random.seed(seed)


@dataclass
class DatasetBundle:
    """Container for everything a Trainer/Evaluator/Predictor needs."""

    X_train: pd.DataFrame
    X_val: pd.DataFrame
    X_test: pd.DataFrame
    y_train: pd.Series
    y_val: pd.Series
    y_test: pd.Series
    sample_weights_train: Optional[np.ndarray] = None
    class_weights: Optional[dict] = None
    metadata: Optional[dict] = None
    feature_names: Optional[list] = None

    def __post_init__(self) -> None:
        if self.feature_names is None:
            self.feature_names = list(self.X_train.columns)


def _read_csv(path: Path, required: bool) -> Optional[pd.DataFrame]:
    if not path.exists():
        if required:
            raise DataValidationError(f"Required file missing: {path}")
        return None
    return pd.read_csv(path)


def _read_y(path: Path, target_column: str) -> pd.Series:
    """
    Read a y-file and return the target as a named Series.

    Multi-hazard projects often store several targets in one file
    (e.g. rainfall_mm, cloudburst_flag, landslide_risk all in y_train.csv).
    If `target_column` exists as a column name, that column is used. If the
    file has exactly one column, that column is used regardless of its name
    (and renamed to `target_column`). Otherwise this is an error rather than
    silently grabbing the wrong hazard's labels.
    """
    df = pd.read_csv(path)

    if target_column in df.columns:
        series = df[target_column]
    elif df.shape[1] == 1:
        series = df.iloc[:, 0]
    else:
        raise DataValidationError(
            f"{path} has {df.shape[1]} columns ({list(df.columns)}) and none "
            f"match target_column={target_column!r}. Pass the exact column "
            f"name for the hazard/task you want via --target-column."
        )

    series = series.rename(target_column)
    return series


def load_dataset_bundle(
    data_dir: str,
    target_column: str = "target",
    use_sample_weights: bool = True,
    use_class_weights: bool = True,
    train_x_filename: str = "X_train.csv",
    train_y_filename: str = "y_train.csv",
    drop_columns: Optional[list] = None,
) -> DatasetBundle:
    """
    Load the full pre-split dataset from `data_dir`.

    Parameters
    ----------
    train_x_filename / train_y_filename:
        Override the TRAIN split filenames only (val/test are always
        X_val.csv/y_val.csv/X_test.csv/y_test.csv). Use this to point
        training at a class-balanced variant, e.g.
        train_x_filename="X_train_cloudburst_flag_balanced.csv",
        train_y_filename="y_train_cloudburst_flag_balanced.csv",
        while still validating/testing on the real, unbalanced distribution.
    drop_columns:
        Column names to drop from every X split before use (e.g. an id
        column like "block_id" that rides along in a balanced variant but
        is not a real feature).

    Raises
    ------
    DataValidationError
        If any required file is missing, or shapes are inconsistent
        between X and y for a given split.
    """
    base = Path(data_dir)
    drop_columns = drop_columns or []

    x_train = _read_csv(base / train_x_filename, required=True)
    x_val = _read_csv(base / "X_val.csv", required=True)
    x_test = _read_csv(base / "X_test.csv", required=True)

    if drop_columns:
        x_train = x_train.drop(columns=[c for c in drop_columns if c in x_train.columns])
        x_val = x_val.drop(columns=[c for c in drop_columns if c in x_val.columns])
        x_test = x_test.drop(columns=[c for c in drop_columns if c in x_test.columns])

    if set(x_train.columns) != set(x_val.columns):
        extra_in_train = set(x_train.columns) - set(x_val.columns)
        extra_in_val = set(x_val.columns) - set(x_train.columns)
        raise DataValidationError(
            f"Feature columns differ between {train_x_filename} and X_val.csv. "
            f"Only in train: {sorted(extra_in_train)}. Only in val: {sorted(extra_in_val)}. "
            f"If train has extra non-feature columns (e.g. an id column), pass them via drop_columns."
        )
    x_train = x_train[list(x_val.columns)]  # align column order to val/test

    y_train = _read_y(base / train_y_filename, target_column)
    y_val = _read_y(base / "y_val.csv", target_column)
    y_test = _read_y(base / "y_test.csv", target_column)

    for name, x, y in (("train", x_train, y_train), ("val", x_val, y_val), ("test", x_test, y_test)):
        if len(x) != len(y):
            raise DataValidationError(
                f"Row count mismatch on {name} split: X has {len(x)} rows, y has {len(y)} rows."
            )

    sample_weights_train = None
    if use_sample_weights:
        sw_path = base / "sample_weights_train.csv"
        if sw_path.exists():
            sw_df = pd.read_csv(sw_path)
            sample_weights_train = sw_df.iloc[:, 0].to_numpy()
            if len(sample_weights_train) != len(x_train):
                raise DataValidationError(
                    "sample_weights_train.csv row count does not match X_train.csv."
                )

    class_weights = None
    if use_class_weights:
        cw_path = base / "class_weights.json"
        if cw_path.exists():
            with open(cw_path, "r") as f:
                raw = json.load(f)
            # normalize keys to the dtype found in y so sklearn/xgboost/lightgbm
            # class_weight / scale_pos_weight lookups line up correctly.
            class_weights = {_coerce_label(k, y_train): float(v) for k, v in raw.items()}

    metadata = None
    meta_path = base / "dataset_metadata.json"
    if meta_path.exists():
        with open(meta_path, "r") as f:
            metadata = json.load(f)

    return DatasetBundle(
        X_train=x_train,
        X_val=x_val,
        X_test=x_test,
        y_train=y_train,
        y_val=y_val,
        y_test=y_test,
        sample_weights_train=sample_weights_train,
        class_weights=class_weights,
        metadata=metadata,
    )


def _coerce_label(key: str, y_reference: pd.Series):
    """Best-effort cast of a JSON string key back to the label dtype used in y."""
    dtype = y_reference.dtype
    try:
        if np.issubdtype(dtype, np.integer):
            return int(key)
        if np.issubdtype(dtype, np.floating):
            return float(key)
    except (ValueError, TypeError):
        pass
    return key
