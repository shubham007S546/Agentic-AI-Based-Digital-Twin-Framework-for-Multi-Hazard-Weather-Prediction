"""
train_xgboost_tuned.py
==============================================================================
Companion training script for the ml_ready/ output of final_preprocessing.py.

Demonstrates all 4 techniques wired together, end to end:

  1. WEIGHTED TEMPORAL CROSS-VALIDATION
       CV splits are rebuilt from temporal_cv_folds.csv (Step 17 of
       preprocessing) -- a blocked, expanding-window split that is NEVER
       shuffled. Fold i's train set is every row chronologically BEFORE
       fold i's validation block. Passed directly into RandomizedSearchCV's
       cv= argument, so every hyperparameter trial is scored with proper
       time-series validation instead of leaking future rows into past
       training folds (which a plain KFold/shuffle-split would do).

  2. CLASS WEIGHTING
       - rain_intensity_class (multiclass): per-row sample_weight column
         (sw_rain_intensity_class, from class_weights.json) passed straight
         into .fit(sample_weight=...). RandomizedSearchCV slices this
         array identically to X/y for every CV fold automatically.
       - cloudburst_flag / landslide_risk (binary): scale_pos_weight is
         RE-DERIVED from the balanced dataset's own pos/neg counts (not
         the raw full-train value) and passed as a fixed XGBClassifier
         param, since these targets are trained on technique #3 below.

  3. TIME-BLOCK UNDERSAMPLING
       cloudburst_flag / landslide_risk are trained on
       X_train_<target>_balanced.csv (Step 18 of preprocessing) instead of
       the full X_train -- whole negative-only time blocks were removed,
       never individual rows, so temporal structure is preserved.
       Evaluation always happens on the REAL, untouched X_val/y_val --
       never evaluate a rare-event model on a rebalanced set, that gives
       a falsely optimistic picture.

  4. HYPERPARAMETER TUNING
       RandomizedSearchCV per task, search spaces loaded from
       hyperparam_recommendations.json (Step 19), scored with the metric
       appropriate to each task (RMSE for regression, F1-macro for
       multiclass, AUC-PR for the two rare-event binary tasks -- never
       accuracy on an imbalanced target).

Usage
-----
    python train_xgboost_tuned.py --ml-ready ml_ready
    python train_xgboost_tuned.py --ml-ready ml_ready --task cloudburst
    python train_xgboost_tuned.py --ml-ready ml_ready --n-iter 50
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit
from xgboost import XGBClassifier, XGBRegressor

RANDOM_STATE = 42
DEFAULT_N_ITER = 25   # RandomizedSearchCV trials per task -- raise for a deeper search


# ==============================================================================
#  TEMPORAL CV -- rebuild the exact blocked/expanding-window folds from
#  preprocessing Step 17, so tuning uses the same time-respecting splits.
# ==============================================================================

def load_temporal_cv_splits(ml_ready: Path, n_splits: int = 5) -> list[tuple[np.ndarray, np.ndarray]]:
    """
    Reads temporal_cv_folds.csv and reconstructs (train_idx, val_idx) pairs
    matching sklearn's TimeSeriesSplit behaviour used in preprocessing:
    train_idx = every row chronologically BEFORE this fold's validation
    block. This is what "weighted temporal cross-validation" means here --
    temporal because it's blocked/expanding and never shuffled, weighted
    because the sample_weight / scale_pos_weight from Step 16 are applied
    on top, inside every fold.
    """
    cv = pd.read_csv(ml_ready / "temporal_cv_folds.csv")
    splits = []
    for fold in range(n_splits):
        val_idx = cv.loc[cv["fold"] == fold, "row_index"].to_numpy()
        train_idx = cv.loc[cv["row_index"] < val_idx.min(), "row_index"].to_numpy()
        splits.append((train_idx, val_idx))
    return splits


def _feature_cols_from_master(master: pd.DataFrame) -> list[str]:
    exclude = {
        "datetime", "imd_rainfall_mm", "rain_intensity_class", "cloudburst_flag",
        "landslide_risk", "sw_rain_intensity_class", "sw_cloudburst_flag",
        "sw_landslide_risk", "cv_fold",
    }
    return [c for c in master.columns if c not in exclude]


# ==============================================================================
#  TASK 1 -- REGRESSION (imd_rainfall_mm)
# ==============================================================================

def task1_regression(ml_ready: Path, feature_cols: list[str], recs: dict, n_iter: int):
    _header("TASK 1 -- Regression (imd_rainfall_mm)")

    master = pd.read_csv(ml_ready / "train_ready_master.csv")
    X, y = master[feature_cols], master["imd_rainfall_mm"]

    splits = load_temporal_cv_splits(ml_ready)
    space = recs["task1_regression_imd_rainfall_mm"]["search_space"]

    model = XGBRegressor(random_state=RANDOM_STATE, tree_method="hist")
    search = RandomizedSearchCV(
        model, param_distributions=space, n_iter=n_iter, cv=splits,
        scoring="neg_root_mean_squared_error", random_state=RANDOM_STATE,
        n_jobs=-1, verbose=1,
    )
    search.fit(X, y)

    print(f"\n  Best CV RMSE : {-search.best_score_:.4f}")
    print(f"  Best params  : {search.best_params_}")

    X_val = pd.read_csv(ml_ready / "X_val.csv")[feature_cols]
    y_val = pd.read_csv(ml_ready / "y_val.csv")["imd_rainfall_mm"]
    pred = search.best_estimator_.predict(X_val)
    print(f"  VAL  RMSE : {np.sqrt(mean_squared_error(y_val, pred)):.4f}")
    print(f"  VAL  MAE  : {mean_absolute_error(y_val, pred):.4f}")
    print(f"  VAL  R2   : {r2_score(y_val, pred):.4f}")

    return search.best_estimator_

def _filter_multiclass_splits(splits, y: pd.Series, num_class: int):
    """
    XGBClassifier's multiclass mode requires every class 0..num_class-1 to be
    present in whatever y_train slice it's fit on. With expanding-window
    temporal CV, the earliest fold's training window can be too short to
    have seen a rare class yet (e.g. no 'Extreme' rain event occurred in the
    first few months) -- fitting on that fold then raises a hard error and
    silently corrupts the whole hyperparameter search (every candidate
    scores nan). Drop only the folds where the train slice is missing a
    class; keep every fold where it isn't, no shuffling or resampling
    involved -- this is a validity filter, not a rebalancing step.
    """
    kept = []
    for train_idx, val_idx in splits:
        n_train_classes = y.iloc[train_idx].nunique()
        if n_train_classes == num_class:
            kept.append((train_idx, val_idx))
        else:
            print(f"    Skipping a CV fold: train window only has {n_train_classes}/{num_class} "
                  f"classes so far (too early in the timeline for a rare class to have occurred)")
    if len(kept) < 2:
        raise ValueError(
            "Fewer than 2 valid temporal CV folds have all classes present in their "
            "training window -- widen CV_N_SPLITS's training window in preprocessing "
            "(fewer, larger folds) or collect more data covering rare classes."
        )
    return kept


# ==============================================================================
#  TASK 2 -- INTENSITY CLASSIFICATION (rain_intensity_class, 0-5)
# ==============================================================================

def task2_intensity(ml_ready: Path, feature_cols: list[str], recs: dict, n_iter: int):
    _header("TASK 2 -- Rain Intensity Classification")

    master = pd.read_csv(ml_ready / "train_ready_master.csv")
    X = master[feature_cols]
    y = master["rain_intensity_class"]
    sw = master["sw_rain_intensity_class"]   # class weighting (Step 16), per-row

    splits = load_temporal_cv_splits(ml_ready)
    task_recs = recs["task2_classification_rain_intensity_class"]
    num_class = task_recs["num_class"]
    splits = _filter_multiclass_splits(splits, y, num_class)
    space = task_recs["search_space"]

    model = XGBClassifier(
        objective="multi:softprob", num_class=num_class,
        random_state=RANDOM_STATE, tree_method="hist", eval_metric="mlogloss",
    )
    search = RandomizedSearchCV(
        model, param_distributions=space, n_iter=n_iter, cv=splits,
        scoring="f1_macro", random_state=RANDOM_STATE, n_jobs=-1, verbose=1,
    )
    # sample_weight is sliced by RandomizedSearchCV the same way as X/y for
    # every fold -- this is how class weighting actually reaches training,
    # not just something computed and left unused in a CSV.
    search.fit(X, y, sample_weight=sw)

    print(f"\n  Best CV F1-macro : {search.best_score_:.4f}")
    print(f"  Best params      : {search.best_params_}")

    X_val = pd.read_csv(ml_ready / "X_val.csv")[feature_cols]
    y_val = pd.read_csv(ml_ready / "y_val.csv")["rain_intensity_class"]
    pred = search.best_estimator_.predict(X_val)
    print(f"  VAL  F1-macro : {f1_score(y_val, pred, average='macro'):.4f}")

    return search.best_estimator_


def _filter_binary_splits(splits, y: pd.Series, min_pos: int = 1):
    """
    average_precision_score / roc_auc_score raise a hard ValueError on any
    fold whose VALIDATION slice has zero positive events -- easy to hit here
    since these rare-event tasks only have 24-100 total positives spread
    across a small balanced set. Keep only folds where both train and val
    contain at least one positive.
    """
    return [(tr, va) for tr, va in splits
            if y.iloc[tr].sum() >= min_pos and y.iloc[va].sum() >= min_pos]


def _build_valid_binary_splits(X: pd.DataFrame, y: pd.Series, max_splits: int):
    """
    Tries TimeSeriesSplit with max_splits folds; if too many folds end up
    with zero positives in their validation slice (common with this few
    total events), automatically retries with fewer, larger folds instead
    of crashing the search. Falls back down to 2 folds minimum.
    """
    for n in range(max_splits, 1, -1):
        splits = list(TimeSeriesSplit(n_splits=n).split(X))
        splits = _filter_binary_splits(splits, y)
        if len(splits) >= 2:
            print(f"  Using {len(splits)} valid temporal CV fold(s) (tried n_splits={n})")
            return splits
    raise ValueError(
        "Could not build 2+ CV folds with positive events in both train and val -- "
        "too few total events for this target to cross-validate reliably. "
        "Consider training a single fit on all balanced data without CV-based tuning."
    )


# ==============================================================================
#  TASK 3 / 4 -- RARE-EVENT BINARY (cloudburst_flag, landslide_risk)
# ==============================================================================

def task_rare_event(ml_ready: Path, target_col: str, recs: dict, n_iter: int, n_splits: int = 3):
    _header(f"TASK -- {target_col} (rare-event binary)")

    X = pd.read_csv(ml_ready / f"X_train_{target_col}_balanced.csv")
    y = pd.read_csv(ml_ready / f"y_train_{target_col}_balanced.csv")[target_col]
    feature_cols = list(X.columns)   # already excludes rolling_precip_24h/72h

    # Time-block undersampling (Step 18) shrinks row count and drops rows by
    # whole blocks, not individually -- chronological order is preserved,
    # but positions no longer line up with temporal_cv_folds.csv row_index.
    # CV is rebuilt directly on this balanced set with TimeSeriesSplit --
    # still blocked/expanding-window, never shuffled, same principle as
    # Step 17 -- with folds lacking a positive event in train OR val dropped,
    # falling back to fewer/larger folds automatically if needed.
    splits = _build_valid_binary_splits(X, y, max_splits=n_splits)

    pos, neg = int(y.sum()), int(len(y) - y.sum())
    scale_pos_weight = round(neg / max(pos, 1), 3)
    print(f"  Balanced train set : {len(X):,} rows (pos={pos}, neg={neg})")
    print(f"  scale_pos_weight   : {scale_pos_weight}  (re-derived from the BALANCED set, "
          f"not the raw full-train value)")

    task_key = "task3_cloudburst_flag" if target_col == "cloudburst_flag" else "task4_landslide_risk"
    space = recs[task_key]["search_space"]

    model = XGBClassifier(
        objective="binary:logistic", scale_pos_weight=scale_pos_weight,
        random_state=RANDOM_STATE, tree_method="hist", eval_metric="aucpr",
    )
    search = RandomizedSearchCV(
        model, param_distributions=space, n_iter=min(n_iter, 15), cv=splits,
        scoring="average_precision", random_state=RANDOM_STATE, n_jobs=-1, verbose=1,
    )
    search.fit(X, y)

    print(f"\n  Best CV AUC-PR : {search.best_score_:.4f}")
    print(f"  Best params    : {search.best_params_}")

    # Evaluate on the REAL, untouched val set -- never the balanced set.
    X_val = pd.read_csv(ml_ready / "X_val.csv")[feature_cols]
    y_val = pd.read_csv(ml_ready / "y_val.csv")[target_col]
    proba = search.best_estimator_.predict_proba(X_val)[:, 1]
    pred = (proba >= 0.5).astype(int)

    print(f"  VAL  positives : {int(y_val.sum())} / {len(y_val)}")
    print(f"  VAL  F1        : {f1_score(y_val, pred, zero_division=0):.4f}")
    print(f"  VAL  AUC-PR    : {average_precision_score(y_val, proba):.4f}")
    if y_val.nunique() > 1:
        print(f"  VAL  ROC-AUC   : {roc_auc_score(y_val, proba):.4f}")
    else:
        print(f"  VAL  ROC-AUC   : undefined (only one class present in this val split)")

    return search.best_estimator_


# ==============================================================================
#  HELPERS / MAIN
# ==============================================================================

def _header(title: str) -> None:
    print(f"\n{'='*70}\n  {title}\n{'='*70}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train + tune XGBoost models on ml_ready/ output")
    parser.add_argument("--ml-ready", type=str, default="ml_ready", help="Path to ml_ready/ folder")
    parser.add_argument("--task", type=str, default="all",
                         choices=["all", "regression", "intensity", "cloudburst", "landslide"])
    parser.add_argument("--n-iter", type=int, default=DEFAULT_N_ITER,
                         help="RandomizedSearchCV trials per task (default 25)")
    args = parser.parse_args()

    ml_ready = Path(args.ml_ready)

    with open(ml_ready / "hyperparam_recommendations.json") as f:
        recs = json.load(f)

    master_head = pd.read_csv(ml_ready / "train_ready_master.csv", nrows=1)
    feature_cols = _feature_cols_from_master(master_head)

    print("\n" + "=" * 70)
    print("  XGBOOST TRAINING + TUNING")
    print("=" * 70)
    print(f"  ml_ready dir : {ml_ready.resolve()}")
    print(f"  features     : {len(feature_cols)}")
    print(f"  n_iter/task  : {args.n_iter}")

    results = {}
    if args.task in ("all", "regression"):
        results["regression"] = task1_regression(ml_ready, feature_cols, recs, args.n_iter)
    if args.task in ("all", "intensity"):
        results["intensity"] = task2_intensity(ml_ready, feature_cols, recs, args.n_iter)
    if args.task in ("all", "cloudburst"):
        results["cloudburst"] = task_rare_event(ml_ready, "cloudburst_flag", recs, args.n_iter)
    if args.task in ("all", "landslide"):
        results["landslide"] = task_rare_event(ml_ready, "landslide_risk", recs, args.n_iter)

    _header("ALL TASKS COMPLETE")
    for name in results:
        print(f"  {name}: trained + tuned OK")


if __name__ == "__main__":
    main()