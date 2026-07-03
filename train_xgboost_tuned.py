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
from sklearn.linear_model import RidgeCV
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

# ==============================================================================
#  TASK 1 -- REGRESSION (imd_rainfall_mm)
# ==============================================================================

RAIN_THRESHOLD_MM = 0.1   # anything at or below this counts as "no rain" for stage A

# Search space for the stage-A rain/no-rain classifier (two-stage strategy).
# Not in hyperparam_recommendations.json since that file predates this task --
# reuses the same shape as the other binary tasks' spaces.
_RAIN_DETECT_SEARCH_SPACE = {
    "n_estimators": [300, 500, 800],
    "max_depth": [4, 5, 6, 8],
    "learning_rate": [0.01, 0.03, 0.05, 0.1],
    "subsample": [0.6, 0.8, 1.0],
    "colsample_bytree": [0.6, 0.8, 1.0],
}


def _slice_splits_to_mask(splits, mask: np.ndarray, min_train: int = 20, min_val: int = 10):
    """
    Restricts a list of (train_idx, val_idx) row-position splits to only the
    positions where `mask` is True (e.g. only rainy rows), remapped to the
    smaller array's own indexing. Drops any fold left too small to be useful.
    Used to reuse the same temporal CV folds for stage B (amount regression,
    rain-only rows) without leaking non-rain rows' positions into it.
    """
    keep_positions = np.where(mask)[0]
    remap = {old: new for new, old in enumerate(keep_positions)}
    out = []
    for tr, va in splits:
        tr_r = np.array([remap[i] for i in tr if i in remap])
        va_r = np.array([remap[i] for i in va if i in remap])
        if len(tr_r) >= min_train and len(va_r) >= min_val:
            out.append((tr_r, va_r))
    return out


def task1_regression(ml_ready: Path, feature_cols: list[str], recs: dict, n_iter: int,
                      strategy: str = "two-stage"):
    """
    strategy="single":    one XGBRegressor on log1p(imd_rainfall_mm) directly.
    strategy="two-stage": Stage A classifies rain/no-rain; Stage B regresses
                           log1p(amount) using ONLY the rows Stage A calls
                           "rain". Final prediction = 0 where Stage A says no
                           rain, else Stage B's (inverse-transformed) amount.
                           This exists because R2 on the raw target is hurt by
                           the model having to simultaneously learn "usually
                           predict 0" and "predict the right nonzero amount"
                           -- splitting those into two models each learning
                           one job tends to help both.
    Both strategies log-transform the target (log1p) before fitting and
    invert with expm1 before scoring -- rainfall is heavily right-skewed
    (mostly 0, occasionally huge), and RMSE/R2 on the raw scale is dominated
    by a handful of extreme values without this.
    """
    _header(f"TASK 1 -- Regression (imd_rainfall_mm)  [strategy={strategy}]")

    master = pd.read_csv(ml_ready / "train_ready_master.csv")
    X = master[feature_cols]
    y_raw = master["imd_rainfall_mm"]
    y_log = np.log1p(y_raw)

    splits = load_temporal_cv_splits(ml_ready)
    space = recs["task1_regression_imd_rainfall_mm"]["search_space"]

    X_val = pd.read_csv(ml_ready / "X_val.csv")[feature_cols]
    y_val_raw = pd.read_csv(ml_ready / "y_val.csv")["imd_rainfall_mm"]

    if strategy == "single":
        model = XGBRegressor(random_state=RANDOM_STATE, tree_method="hist")
        search = RandomizedSearchCV(
            model, param_distributions=space, n_iter=n_iter, cv=splits,
            scoring="neg_root_mean_squared_error", random_state=RANDOM_STATE,
            n_jobs=-1, verbose=1,
        )
        search.fit(X, y_log)
        print(f"\n  Best CV RMSE (log-space) : {-search.best_score_:.4f}")
        print(f"  Best params              : {search.best_params_}")

        pred = np.clip(np.expm1(search.best_estimator_.predict(X_val)), 0, None)
        result_model = search.best_estimator_

    elif strategy == "two-stage":
        # ---- Stage A: rain vs no-rain ----
        y_rain = (y_raw > RAIN_THRESHOLD_MM).astype(int)
        pos, neg = int(y_rain.sum()), int(len(y_rain) - y_rain.sum())
        spw = round(neg / max(pos, 1), 3)
        print(f"  Stage A (rain/no-rain): {pos:,} rain rows, {neg:,} no-rain rows, "
              f"scale_pos_weight={spw}")

        splits_A = _filter_binary_splits(splits, y_rain)
        modelA = XGBClassifier(
            objective="binary:logistic", scale_pos_weight=spw,
            random_state=RANDOM_STATE, tree_method="hist", eval_metric="logloss",
        )
        searchA = RandomizedSearchCV(
            modelA, param_distributions=_RAIN_DETECT_SEARCH_SPACE, n_iter=n_iter,
            cv=splits_A, scoring="f1", random_state=RANDOM_STATE, n_jobs=-1, verbose=1,
        )
        searchA.fit(X, y_rain)
        bestA = searchA.best_estimator_
        print(f"  Stage A best CV F1 : {searchA.best_score_:.4f}")

        # ---- Stage B: amount, rain rows only, log-target ----
        rain_mask = y_rain.values.astype(bool)
        X_rain = X.loc[rain_mask].reset_index(drop=True)
        y_rain_log = y_log.loc[rain_mask].reset_index(drop=True)
        splits_B = _slice_splits_to_mask(splits, rain_mask)

        if len(splits_B) >= 2:
            modelB = XGBRegressor(random_state=RANDOM_STATE, tree_method="hist")
            searchB = RandomizedSearchCV(
                modelB, param_distributions=space, n_iter=n_iter, cv=splits_B,
                scoring="neg_root_mean_squared_error", random_state=RANDOM_STATE,
                n_jobs=-1, verbose=1,
            )
            searchB.fit(X_rain, y_rain_log)
            bestB = searchB.best_estimator_
            print(f"  Stage B best CV RMSE (log-space, rain rows only) : {-searchB.best_score_:.4f}")
        else:
            print(f"  Too few valid CV folds on rain-only rows ({len(X_rain):,} rows) -- "
                  f"fitting Stage B once with fixed reasonable hyperparameters.")
            bestB = XGBRegressor(random_state=RANDOM_STATE, tree_method="hist", **FALLBACK_PARAMS)
            bestB.fit(X_rain, y_rain_log)

        # ---- Combine for final prediction ----
        rain_pred_flag = bestA.predict(X_val).astype(bool)
        pred = np.zeros(len(X_val))
        if rain_pred_flag.any():
            pred[rain_pred_flag] = np.expm1(bestB.predict(X_val.loc[rain_pred_flag]))
        pred = np.clip(pred, 0, None)
        result_model = (bestA, bestB)

    else:
        raise ValueError(f"Unknown strategy: {strategy!r} (use 'single' or 'two-stage')")

    print(f"\n  VAL  RMSE (original mm scale) : {np.sqrt(mean_squared_error(y_val_raw, pred)):.4f}")
    print(f"  VAL  MAE  (original mm scale) : {mean_absolute_error(y_val_raw, pred):.4f}")
    print(f"  VAL  R2   (original mm scale) : {r2_score(y_val_raw, pred):.4f}")

    _print_regression_baselines(X, y_log, X_val, y_val_raw)

    return result_model


def _print_regression_baselines(X: pd.DataFrame, y_log: pd.Series, X_val: pd.DataFrame, y_val_raw: pd.Series):
    """
    Cheap sanity-check baselines run alongside the tuned model so a modest
    R2 can be judged in context.

    IMPORTANT CAVEAT ON THE PERSISTENCE BASELINE: "predict this hour = last
    hour" tends to score a deceptively high R2/RMSE here because most
    validation hours are dry, and persisting 'no rain' when it was already
    dry is nearly free accuracy. That's not forecasting skill -- it has
    ZERO lead time and can never anticipate a new event starting. It's
    included for honesty, but the fairer comparison for an early-warning
    system is the ONSET-ONLY score printed below: how each model does
    specifically at the hours where rain just started or just stopped,
    which is where persistence has no information advantage at all.
    """
    print("\n  --- Baseline comparison (same val set, same metric) ---")

    y_val_sorted = y_val_raw.reset_index(drop=True)
    pred_persist = y_val_sorted.shift(1).fillna(0.0).values
    print(f"  Persistence (predict = last hour's actual):")
    print(f"    RMSE : {np.sqrt(mean_squared_error(y_val_sorted, pred_persist)):.4f}")
    print(f"    R2   : {r2_score(y_val_sorted, pred_persist):.4f}")
    print(f"    NOTE : inflated by dry-hour-to-dry-hour matches -- has ZERO lead time, "
          f"cannot warn of anything. See onset-only comparison below for a fairer read.")

    # RidgeCV (cross-validated L2 regularization strength) instead of a
    # fixed alpha -- your feature set has strong collinearity
    # (rolling_precip_3h/6h/24h/72h, precip_lag_1h/3h/6h all correlate),
    # and alpha=10 wasn't nearly strong enough to control it (still
    # exploded). Let CV pick from a wide range, AND hard-clip the
    # log-space prediction to what's actually been observed in training --
    # a linear model can still extrapolate to nonsense values on an unusual
    # feature combination even when well-regularized, and this is a safety
    # net against that, not a fix for the underlying collinearity.
    ridge = RidgeCV(alphas=[1, 10, 50, 100, 500, 1000, 5000])
    ridge.fit(X, y_log)
    max_log_y = float(y_log.max())
    pred_log_ridge = np.clip(ridge.predict(X_val), 0, max_log_y * 1.2)
    pred_ridge = np.clip(np.expm1(pred_log_ridge), 0, None)
    print(f"  Ridge Regression (log-target, same features, alpha={ridge.alpha_:.0f} via CV):")
    print(f"    RMSE : {np.sqrt(mean_squared_error(y_val_sorted, pred_ridge)):.4f}")
    print(f"    R2   : {r2_score(y_val_sorted, pred_ridge):.4f}")

    # Onset-only comparison: hours where rain STARTED or STOPPED relative
    # to the previous hour. Persistence is defined to be wrong here by
    # construction (it always predicts 'no change'), so this isolates each
    # model's actual predictive skill from the dry-hour inflation above.
    prev = y_val_sorted.shift(1).fillna(0.0)
    changed = ((y_val_sorted > RAIN_THRESHOLD_MM) != (prev > RAIN_THRESHOLD_MM))
    n_changed = int(changed.sum())
    if n_changed >= 5:
        print(f"\n  --- Onset-only comparison ({n_changed} hours where rain started/stopped) ---")
        print(f"  Persistence R2 on onset hours only : "
              f"{r2_score(y_val_sorted[changed], pred_persist[changed.values]):.4f}  "
              f"(structurally near-worst-possible here, as expected)")
    else:
        print(f"\n  (Too few rain-onset hours ({n_changed}) in this val split for a "
              f"reliable onset-only comparison)")


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


def _build_block_aware_splits(y: pd.Series, block_ids: pd.Series, max_splits: int):
    """
    Splits by whole time BLOCK (the same blocks time-block undersampling in
    preprocessing was built from), never by raw row position. A row-position
    TimeSeriesSplit can cut straight through the middle of one storm's
    block -- neighbouring hours of the SAME event are nearly identical, so
    the model would 'validate' on a near-duplicate of its own training data,
    producing an artificially perfect CV score (e.g. AUC-PR = 1.0) that then
    collapses on real, independent validation data. Blocks are kept whole on
    one side of the split or the other, always.

    Uses an expanding-window scheme over blocks (same spirit as Step 17):
    fold i validates on one contiguous group of blocks, trains on every
    block chronologically before it.
    """
    unique_blocks = np.sort(block_ids.unique())
    for n in range(max_splits, 1, -1):
        if len(unique_blocks) < n + 1:
            continue
        block_groups = np.array_split(unique_blocks, n)
        splits = []
        for i in range(1, len(block_groups)):  # first group has no prior blocks to train on
            train_blocks = np.concatenate(block_groups[:i])
            val_blocks = block_groups[i]
            train_idx = np.where(block_ids.isin(train_blocks))[0]
            val_idx = np.where(block_ids.isin(val_blocks))[0]
            splits.append((train_idx, val_idx))
        splits = _filter_binary_splits(splits, y)
        if len(splits) >= 2:
            print(f"  Using {len(splits)} block-aware CV fold(s) (tried n_splits={n}, "
                  f"{len(unique_blocks)} total blocks)")
            return splits
    return None


# Reasonable fixed defaults used only when there are too few events/blocks
# to cross-validate at all (see fallback path in task_rare_event below).
FALLBACK_PARAMS = dict(
    n_estimators=300, max_depth=4, learning_rate=0.05,
    subsample=0.8, colsample_bytree=0.8, min_child_weight=3,
)


# ==============================================================================
#  TASK 3 / 4 -- RARE-EVENT BINARY (cloudburst_flag, landslide_risk)
# ==============================================================================

def task_rare_event(ml_ready: Path, target_col: str, recs: dict, n_iter: int, n_splits: int = 5):
    _header(f"TASK -- {target_col} (rare-event binary)")

    X = pd.read_csv(ml_ready / f"X_train_{target_col}_balanced.csv")
    y_full = pd.read_csv(ml_ready / f"y_train_{target_col}_balanced.csv")
    y = y_full[target_col]
    feature_cols = list(X.columns)   # already excludes rolling_precip_24h/72h

    pos, neg = int(y.sum()), int(len(y) - y.sum())
    scale_pos_weight = round(neg / max(pos, 1), 3)
    print(f"  Balanced train set : {len(X):,} rows (pos={pos}, neg={neg})")
    print(f"  scale_pos_weight   : {scale_pos_weight}  (re-derived from the BALANCED set, "
          f"not the raw full-train value)")

    task_key = "task3_cloudburst_flag" if target_col == "cloudburst_flag" else "task4_landslide_risk"
    space = recs[task_key]["search_space"]

    X_val = pd.read_csv(ml_ready / "X_val.csv")[feature_cols]
    y_val = pd.read_csv(ml_ready / "y_val.csv")[target_col]

    if "block_id" not in y_full.columns:
        print("  WARNING: 'block_id' not found in the balanced y file -- re-run the updated "
              "final_preprocessing.py to regenerate it. Falling back to a single un-tuned fit "
              "for now (row-position CV would risk leaking one storm's hours across train/val).")
        splits = None
    else:
        # Splits by whole time BLOCK, never by raw row position -- see
        # _build_block_aware_splits docstring for why this matters.
        splits = _build_block_aware_splits(y, y_full["block_id"], max_splits=n_splits)

    if splits is None:
        print("  Not enough distinct blocks/events to build 2+ valid CV folds -- "
              "training a single fit on all balanced data with fixed reasonable "
              "hyperparameters (no tuning search performed for this task).")
        model = XGBClassifier(
            objective="binary:logistic", scale_pos_weight=scale_pos_weight,
            random_state=RANDOM_STATE, tree_method="hist", eval_metric="aucpr",
            **FALLBACK_PARAMS,
        )
        model.fit(X, y)
        best_model, best_params, best_cv_score = model, FALLBACK_PARAMS, None
    else:
        model = XGBClassifier(
            objective="binary:logistic", scale_pos_weight=scale_pos_weight,
            random_state=RANDOM_STATE, tree_method="hist", eval_metric="aucpr",
        )
        search = RandomizedSearchCV(
            model, param_distributions=space, n_iter=min(n_iter, 15), cv=splits,
            scoring="average_precision", random_state=RANDOM_STATE, n_jobs=-1, verbose=1,
        )
        search.fit(X, y)
        best_model = search.best_estimator_
        best_params, best_cv_score = search.best_params_, search.best_score_
        print(f"\n  Best CV AUC-PR : {best_cv_score:.4f}")
        print(f"  Best params    : {best_params}")

    # Evaluate on the REAL, untouched val set -- never the balanced set.
    proba = best_model.predict_proba(X_val)[:, 1]
    pred = (proba >= 0.5).astype(int)

    print(f"  VAL  positives : {int(y_val.sum())} / {len(y_val)}")
    print(f"  VAL  F1        : {f1_score(y_val, pred, zero_division=0):.4f}")
    print(f"  VAL  AUC-PR    : {average_precision_score(y_val, proba):.4f}")
    if y_val.nunique() > 1:
        print(f"  VAL  ROC-AUC   : {roc_auc_score(y_val, proba):.4f}")
    else:
        print(f"  VAL  ROC-AUC   : undefined (only one class present in this val split)")

    return best_model


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
    parser.add_argument("--strategy", type=str, default="two-stage",
                         choices=["single", "two-stage"],
                         help="Task 1 regression strategy: 'two-stage' (rain/no-rain -> "
                              "amount, default) or 'single' (one model, log-transformed target)")
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
        results["regression"] = task1_regression(ml_ready, feature_cols, recs, args.n_iter,
                                                   strategy=args.strategy)
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