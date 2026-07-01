"""
final_preprocessing.py
==============================================================================
Stage B -- Final ML Preprocessing Pipeline
Mandi District Extreme Weather Prediction

Fixes in this version
---------------------
  FIX 1: imd_rainfall_mm removed from FEATURE_COLS
          -> was leaking as 'imd_rainfall_mm.1' into X splits (data leakage)
  FIX 2: Duplicate column removal happens FIRST (Step 2), before any other step
  FIX 3: No parquet -- CSV only, zero import errors
  FIX 4: Final validation step checks X splits for any leaked target columns
  FIX 5: train.dtypes[c] used instead of train[c].dtype (safe with any df)
  FIX 6: output named final_preprocessed.csv

Output files (in ml_ready/)
----------------------------
    final_preprocessed.csv      full clean dataset (36 cols)
    X_train.csv                 13,104 rows x 35 features
    X_val.csv                    4,416 rows x 35 features
    X_test.csv                   6,553 rows x 35 features
    y_train.csv                 13,104 rows x 4 targets
    y_val.csv                    4,416 rows x 4 targets
    y_test.csv                   6,553 rows x 4 targets
    scaler_params.csv           mean / std per scaled feature
    split_report.txt            full summary

Usage
-----
    python final_preprocessing.py
    python final_preprocessing.py --data path/to/final_dataset.csv
    python final_preprocessing.py --data path/to/final_dataset.csv --output ml_ready
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

# ==============================================================================
#  CONFIGURATION
# ==============================================================================

DEFAULT_INPUT  = Path("datasets/merged_dataset/final_dataset.csv")
DEFAULT_OUTPUT = Path("ml_ready")

TRAIN_END     = "2023-06-30 23:00:00"
VAL_END       = "2023-12-31 23:00:00"
CLOUDBURST_MM = 100.0

# Columns confirmed bad by EDA
DROP_COLS = [
    "precipitation_gpm",   # all zeros -- GPM merge failed
    "mslp",                # 88% missing, redundant with surface_pressure
]

# ==============================================================================
#  FEATURE COLUMNS  (X -- model inputs)
#
#  IMPORTANT: imd_rainfall_mm is NOT listed here.
#  It is a TARGET (y), not a feature. Including it here caused it to appear
#  as 'imd_rainfall_mm.1' in X splits -- classic data leakage.
# ==============================================================================

FEATURE_COLS = [
    # -- Raw atmospheric state --
    "temperature_2m",
    "dewpoint_2m",
    "relative_humidity",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "wind_u_10m",
    "wind_v_10m",
    "cloud_cover",
    "cape",
    # -- Rainfall observations (predictors, not targets) --
    "precipitation_openmeteo",
    "rain_openmeteo",
    "snowfall",
    # -- Rolling window features --
    "rolling_precip_3h",
    "rolling_precip_6h",
    "rolling_precip_24h",
    "rolling_precip_72h",
    # -- Lag features --
    "precip_lag_1h",
    "precip_lag_3h",
    "precip_lag_6h",
    # -- Engineered features (added in Step 9) --
    "temp_dewpoint_spread",    # temp - dewpoint -> near 0 = saturated air = rain
    "wind_gust_ratio",         # gusts / mean wind -> convective storm signal
    "precip_acceleration",     # lag1 - lag3 -> is rain intensifying?
    "humidity_cape_interact",  # RH * CAPE -> joint convection signal
    "rolling_ratio_3_24",      # 3h / 24h -> sudden burst vs background rain
    # -- Time cyclic features --
    "hour_sin",
    "hour_cos",
    "month_sin",
    "month_cos",
    # -- Time categorical features --
    "hour",
    "month",
    "day_of_year",
    "season",
    "is_monsoon",
]

# ==============================================================================
#  TARGET COLUMNS  (y -- what models predict)
# ==============================================================================

TARGET_COLS = [
    "imd_rainfall_mm",       # Task 1: Regression  -- how much rain?
    "rain_intensity_class",  # Task 2: Multi-class -- 0=No Rain .. 5=Extreme
    "cloudburst_flag",       # Task 3: Binary      -- >= 100mm/3h yes/no
    "landslide_risk",        # Task 4: Binary      -- landslide risk yes/no
]

# Columns that must NOT be scaled
DO_NOT_SCALE = [
    "hour_sin", "hour_cos", "month_sin", "month_cos",
    "hour", "month", "day_of_year", "season", "is_monsoon",
    "wind_direction_10m",
]

# ==============================================================================
#  STEP 1 -- LOAD
# ==============================================================================

def load(path: Path) -> pd.DataFrame:
    _header("STEP 1 -- Load Dataset")
    df = pd.read_csv(path, low_memory=False)
    print(f"  File   : {path}")
    print(f"  Shape  : {df.shape[0]:,} rows x {df.shape[1]} columns")
    print(f"  Cols   : {list(df.columns)}")
    return df


# ==============================================================================
#  STEP 2 -- DEDUPLICATE COLUMNS  (MUST be first -- fixes the .1 suffix bug)
# ==============================================================================

def deduplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    When pandas reads a CSV that has two columns with the same name,
    it silently renames the second one as 'colname.1'. This step removes
    ALL duplicates immediately after load, before any other processing.
    """
    _header("STEP 2 -- Deduplicate Column Names")
    dup = df.columns[df.columns.duplicated()].tolist()
    if dup:
        print(f"  WARNING: {len(dup)} duplicate column(s) -- removing:")
        for c in dup:
            print(f"    REMOVED: {c}")
        df = df.loc[:, ~df.columns.duplicated()]
    else:
        print(f"  No duplicates found.")

    # Also explicitly drop any '.1' suffix columns that pandas auto-generated
    dot1_cols = [c for c in df.columns if c.endswith(".1")]
    if dot1_cols:
        print(f"  WARNING: Auto-renamed '.1' columns found -- removing:")
        for c in dot1_cols:
            print(f"    REMOVED: {c}")
        df = df.drop(columns=dot1_cols)

    print(f"  Columns after clean: {df.shape[1]}")
    return df


# ==============================================================================
#  STEP 3 -- PARSE DATETIME + SORT
# ==============================================================================

def parse_sort(df: pd.DataFrame) -> pd.DataFrame:
    _header("STEP 3 -- Parse Datetime and Sort")
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
    n_bad = df["datetime"].isna().sum()
    if n_bad:
        print(f"  WARNING: {n_bad} unparseable datetime rows dropped")
        df = df.dropna(subset=["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    print(f"  Start  : {df['datetime'].min()}")
    print(f"  End    : {df['datetime'].max()}")
    pct = (df["datetime"].diff().dropna() == pd.Timedelta("1h")).mean() * 100
    print(f"  Hourly : {pct:.1f}% of gaps are exactly 1 hour")
    return df


# ==============================================================================
#  STEP 4 -- DROP BAD COLUMNS
# ==============================================================================

def drop_bad(df: pd.DataFrame) -> pd.DataFrame:
    _header("STEP 4 -- Drop Bad Columns")
    reasons = {
        "precipitation_gpm": "all zeros -- GPM merge failed",
        "mslp":              "88% missing, redundant with surface_pressure",
    }
    dropped = []
    for col in DROP_COLS:
        if col in df.columns:
            df = df.drop(columns=[col])
            dropped.append(col)
            print(f"  DROPPED : {col}  [{reasons.get(col, '')}]")
    if not dropped:
        print(f"  Nothing to drop (already clean).")
    print(f"  Columns remaining : {df.shape[1]}")
    return df


# ==============================================================================
#  STEP 5 -- FIX rain_intensity_class (IMD official thresholds)
# ==============================================================================

def fix_intensity_class(df: pd.DataFrame) -> pd.DataFrame:
    """
    Original column was miscalculated (class 0 had rows with 140mm).
    Recalculate using official IMD thresholds:
      0 = No Rain      < 2.5 mm
      1 = Light        2.5 - 15.5 mm
      2 = Moderate     15.6 - 64.4 mm
      3 = Heavy        64.5 - 115.5 mm
      4 = Very Heavy   115.6 - 204.4 mm
      5 = Extreme      >= 204.5 mm
    """
    _header("STEP 5 -- Fix rain_intensity_class (IMD thresholds)")
    print("  Before:")
    _print_dist(df["rain_intensity_class"], "    ")

    r = df["imd_rainfall_mm"]
    df["rain_intensity_class"] = np.select(
        [r < 2.5,
         (r >= 2.5)   & (r < 15.6),
         (r >= 15.6)  & (r < 64.5),
         (r >= 64.5)  & (r < 115.6),
         (r >= 115.6) & (r < 204.5),
         r >= 204.5],
        [0, 1, 2, 3, 4, 5],
        default=0
    )
    names = {0:"No Rain", 1:"Light", 2:"Moderate", 3:"Heavy", 4:"Very Heavy", 5:"Extreme"}
    print("  After (corrected):")
    for cls, cnt in df["rain_intensity_class"].value_counts().sort_index().items():
        print(f"    Class {cls} ({names.get(cls,'?'):<12}): {cnt:>6,}  ({cnt/len(df)*100:.2f}%)")
    return df


# ==============================================================================
#  STEP 6 -- FIX cloudburst_flag (was all zeros)
# ==============================================================================

def fix_cloudburst(df: pd.DataFrame) -> pd.DataFrame:
    """
    India standard: >= 100mm rainfall in <= 3 hours = cloudburst.
    Original column was all zeros (broken). Recalculate from rolling_precip_3h.
    """
    _header("STEP 6 -- Fix cloudburst_flag (was all zeros)")
    print(f"  Before: {df['cloudburst_flag'].sum():,} events")

    if "rolling_precip_3h" in df.columns and (df["rolling_precip_3h"] >= CLOUDBURST_MM).any():
        df["cloudburst_flag"] = (df["rolling_precip_3h"] >= CLOUDBURST_MM).astype(int)
        src = "rolling_precip_3h >= 100mm"
    else:
        df["cloudburst_flag"] = (df["imd_rainfall_mm"] >= CLOUDBURST_MM).astype(int)
        src = "imd_rainfall_mm >= 100mm (fallback -- no 3h rolling data)"

    n = df["cloudburst_flag"].sum()
    print(f"  After : {n:,} events ({n/len(df)*100:.3f}%)  [{src}]")
    return df


# ==============================================================================
#  STEP 7 -- IMPUTE CAPE (88% missing -> seasonal median)
# ==============================================================================

def impute_cape(df: pd.DataFrame) -> pd.DataFrame:
    """
    CAPE is critical for convective rainfall prediction but 88% missing.
    Global mean is wrong -- CAPE is near 0 in winter and high in monsoon.
    Use seasonal median per season group.
    """
    _header("STEP 7 -- Impute CAPE (seasonal median)")
    n_miss = df["cape"].isna().sum()
    print(f"  Missing before : {n_miss:,} ({n_miss/len(df)*100:.1f}%)")

    season_map = {0: "Winter", 1: "Pre-Monsoon", 2: "Monsoon", 3: "Post-Monsoon"}
    medians = df.groupby("season")["cape"].median()

    print("  Seasonal medians used for imputation:")
    for s, med in medians.items():
        val = float(med) if not pd.isna(med) else 0.0
        print(f"    {season_map.get(int(s), str(s)):<15}: {val:.2f} J/kg")
        mask = df["cape"].isna() & (df["season"] == s)
        df.loc[mask, "cape"] = val

    df["cape"] = df["cape"].fillna(0.0)  # catch any remaining NaN
    print(f"  Missing after  : {df['cape'].isna().sum():,}")
    print(f"  CAPE mean      : {df['cape'].mean():.2f} J/kg")
    return df


# ==============================================================================
#  STEP 8 -- FIX LAG NaNs (edge effect from shift operation)
# ==============================================================================

def fix_lag_nans(df: pd.DataFrame) -> pd.DataFrame:
    """
    precip_lag_1h/3h/6h have NaN in the first few rows -- edge effect
    from the shift() operation. Fill with 0 (no prior rainfall assumed).
    """
    _header("STEP 8 -- Fix Lag NaN Edge Values")
    fixed = False
    for col in ["precip_lag_1h", "precip_lag_3h", "precip_lag_6h"]:
        if col in df.columns:
            n = df[col].isna().sum()
            if n > 0:
                df[col] = df[col].fillna(0.0)
                print(f"  {col:<20}: filled {n} NaN(s) with 0")
                fixed = True
    if not fixed:
        print(f"  No lag NaNs found.")
    return df


# ==============================================================================
#  STEP 9 -- ENGINEER 5 EXTRA FEATURES (boost accuracy)
# ==============================================================================

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Five physics-informed features that give models stronger signals:

    1. temp_dewpoint_spread    : T - Td  --> near 0 = air near saturation = rain
    2. wind_gust_ratio         : gusts/wind --> high = convective instability
    3. precip_acceleration     : lag1 - lag3 --> is rainfall intensifying?
    4. humidity_cape_interact  : (RH/100) * CAPE --> joint convection index
    5. rolling_ratio_3_24      : 3h/24h rainfall --> sudden burst detection
    """
    _header("STEP 9 -- Engineer Extra Features")

    if "temperature_2m" in df.columns and "dewpoint_2m" in df.columns:
        df["temp_dewpoint_spread"] = (df["temperature_2m"] - df["dewpoint_2m"]).clip(lower=0)
        print(f"  + temp_dewpoint_spread   mean={df['temp_dewpoint_spread'].mean():.3f}")

    if "wind_gusts_10m" in df.columns and "wind_speed_10m" in df.columns:
        df["wind_gust_ratio"] = (df["wind_gusts_10m"] / (df["wind_speed_10m"] + 0.1)).clip(upper=20)
        print(f"  + wind_gust_ratio        mean={df['wind_gust_ratio'].mean():.3f}")

    if "precip_lag_1h" in df.columns and "precip_lag_3h" in df.columns:
        df["precip_acceleration"] = df["precip_lag_1h"] - df["precip_lag_3h"]
        print(f"  + precip_acceleration    mean={df['precip_acceleration'].mean():.3f}")

    if "relative_humidity" in df.columns and "cape" in df.columns:
        df["humidity_cape_interact"] = (df["relative_humidity"] / 100.0) * df["cape"]
        print(f"  + humidity_cape_interact mean={df['humidity_cape_interact'].mean():.3f}")

    if "rolling_precip_3h" in df.columns and "rolling_precip_24h" in df.columns:
        df["rolling_ratio_3_24"] = (df["rolling_precip_3h"] / (df["rolling_precip_24h"] + 0.1)).clip(upper=10)
        print(f"  + rolling_ratio_3_24     mean={df['rolling_ratio_3_24'].mean():.3f}")

    return df


# ==============================================================================
#  STEP 10 -- REORDER COLUMNS
# ==============================================================================

def reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Final column order: datetime | features | targets
    Any unrecognised columns are listed but not dropped.
    """
    _header("STEP 10 -- Reorder Columns")

    avail_feats = [c for c in FEATURE_COLS if c in df.columns]
    avail_tgts  = [c for c in TARGET_COLS  if c in df.columns]
    all_known   = set(avail_feats) | set(avail_tgts) | {"datetime"}
    extras      = [c for c in df.columns if c not in all_known]

    if extras:
        print(f"  WARNING: {len(extras)} unrecognised column(s) -- will be dropped:")
        for c in extras:
            print(f"    DROPPED: {c}")
        # Drop extras so they never appear in output
        df = df.drop(columns=extras)

    final_order = ["datetime"] + avail_feats + avail_tgts
    df = df[final_order]

    print(f"  datetime : 1  |  features : {len(avail_feats)}  |  targets : {len(avail_tgts)}")
    print(f"  Total columns : {df.shape[1]}")
    return df


# ==============================================================================
#  STEP 11 -- TIME-BASED SPLIT
# ==============================================================================

def time_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Temporal split -- NO random shuffle (that would leak future into past).
      Train : 2022-01-01 -> 2023-06-30   ~18 months
      Val   : 2023-07-01 -> 2023-12-31   ~6 months (includes 2023 monsoon)
      Test  : 2024-01-01 -> 2024-09-30   ~9 months (includes 2024 monsoon)
    """
    _header("STEP 11 -- Time-Based Train / Val / Test Split")

    train_end = pd.Timestamp(TRAIN_END, tz="UTC")
    val_end   = pd.Timestamp(VAL_END,   tz="UTC")

    train = df[df["datetime"] <= train_end].copy()
    val   = df[(df["datetime"] > train_end) & (df["datetime"] <= val_end)].copy()
    test  = df[df["datetime"] > val_end].copy()

    n = len(df)
    for name, sp in [("Train", train), ("Val", val), ("Test", test)]:
        s = sp["datetime"].min().strftime("%Y-%m-%d")
        e = sp["datetime"].max().strftime("%Y-%m-%d")
        print(f"  {name:<6} : {len(sp):>6,} rows ({len(sp)/n*100:.1f}%)  {s} -> {e}")

    print("\n  rain_intensity_class per split:")
    names = {0:"NoRain", 1:"Light", 2:"Moderate", 3:"Heavy", 4:"VHeavy", 5:"Extreme"}
    for name, sp in [("Train", train), ("Val", val), ("Test", test)]:
        vc = sp["rain_intensity_class"].value_counts().sort_index()
        s  = "  ".join([f"cls{k}={v:,}" for k, v in vc.items()])
        print(f"  {name:<6}: {s}")

    print("\n  cloudburst_flag per split:")
    for name, sp in [("Train", train), ("Val", val), ("Test", test)]:
        n_cb = sp["cloudburst_flag"].sum()
        print(f"  {name:<6}: {n_cb:,} events ({n_cb/len(sp)*100:.3f}%)")

    print("\n  landslide_risk per split:")
    for name, sp in [("Train", train), ("Val", val), ("Test", test)]:
        n_ls = sp["landslide_risk"].sum()
        print(f"  {name:<6}: {n_ls:,} events ({n_ls/len(sp)*100:.3f}%)")

    return train, val, test


# ==============================================================================
#  STEP 12 -- FEATURE SCALING (StandardScaler, fit on train only)
# ==============================================================================

def scale(
    train: pd.DataFrame,
    val:   pd.DataFrame,
    test:  pd.DataFrame,
    output_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, StandardScaler]:
    """
    Scale continuous features using StandardScaler fit on TRAIN ONLY.
    Val and test are transformed (not fit) to prevent data leakage.

    Uses train.dtypes[c].kind (not train[c].dtype) -- safe against
    any edge case where train[c] might return a DataFrame instead of Series.
    """
    _header("STEP 12 -- Feature Scaling (fit on train only)")

    # Safety dedup on all three splits
    for split_name, split_df in [("train", train), ("val", val), ("test", test)]:
        dup = split_df.columns[split_df.columns.duplicated()].tolist()
        if dup:
            print(f"  WARNING: duplicate cols in {split_name} split: {dup} -- removing")
    train = train.loc[:, ~train.columns.duplicated()].copy()
    val   = val.loc[:,   ~val.columns.duplicated()].copy()
    test  = test.loc[:,  ~test.columns.duplicated()].copy()

    avail_feats = [c for c in FEATURE_COLS if c in train.columns]

    # Use train.dtypes[c] -- always returns a scalar dtype, never a DataFrame
    scale_cols    = [c for c in avail_feats
                     if c not in DO_NOT_SCALE and train.dtypes[c].kind == 'f']
    no_scale_cols = [c for c in avail_feats if c not in scale_cols]

    print(f"  Scaled     : {len(scale_cols)} continuous float columns")
    print(f"  Not scaled : {len(no_scale_cols)} columns  {no_scale_cols}")

    scaler = StandardScaler()

    def _apply(df: pd.DataFrame, fit: bool = False) -> pd.DataFrame:
        df = df.copy()
        if fit:
            df[scale_cols] = scaler.fit_transform(df[scale_cols])
        else:
            df[scale_cols] = scaler.transform(df[scale_cols])
        return df

    train_sc = _apply(train, fit=True)
    val_sc   = _apply(val)
    test_sc  = _apply(test)

    print(f"  Fit on train ({len(train_sc):,} rows) -- applied to val+test")

    pd.DataFrame({
        "feature": scale_cols,
        "mean":    scaler.mean_.round(6),
        "std":     scaler.scale_.round(6),
    }).to_csv(output_dir / "scaler_params.csv", index=False)
    print(f"  Saved: scaler_params.csv")

    return train_sc, val_sc, test_sc, scaler


# ==============================================================================
#  STEP 13 -- EXTRACT X / y
# ==============================================================================

def extract_xy(
    train: pd.DataFrame,
    val:   pd.DataFrame,
    test:  pd.DataFrame,
) -> tuple[pd.DataFrame, ...]:
    _header("STEP 13 -- Extract X / y for All Splits")

    avail_feats = [c for c in FEATURE_COLS if c in train.columns]
    avail_tgts  = [c for c in TARGET_COLS  if c in train.columns]

    X_train = train[avail_feats].reset_index(drop=True)
    X_val   = val[avail_feats].reset_index(drop=True)
    X_test  = test[avail_feats].reset_index(drop=True)
    y_train = train[avail_tgts].reset_index(drop=True)
    y_val   = val[avail_tgts].reset_index(drop=True)
    y_test  = test[avail_tgts].reset_index(drop=True)

    print(f"  X_train : {X_train.shape[0]:,} rows x {X_train.shape[1]} features")
    print(f"  X_val   : {X_val.shape[0]:,} rows x {X_val.shape[1]} features")
    print(f"  X_test  : {X_test.shape[0]:,} rows x {X_test.shape[1]} features")
    print(f"  y cols  : {list(y_train.columns)}")

    return X_train, X_val, X_test, y_train, y_val, y_test


# ==============================================================================
#  STEP 14 -- VALIDATE  (catches any remaining leakage before saving)
# ==============================================================================

def validate(
    X_train: pd.DataFrame,
    X_val:   pd.DataFrame,
    X_test:  pd.DataFrame,
    y_train: pd.DataFrame,
) -> None:
    _header("STEP 14 -- Final Validation")

    errors = []

    # 1. No target column should appear in X
    for tgt in TARGET_COLS:
        for name, X in [("X_train", X_train), ("X_val", X_val), ("X_test", X_test)]:
            if tgt in X.columns:
                errors.append(f"  DATA LEAKAGE: target '{tgt}' found in {name}!")
            # Also catch '.1' variant
            if f"{tgt}.1" in X.columns:
                errors.append(f"  DATA LEAKAGE: leaked column '{tgt}.1' found in {name}!")

    # 2. No '.1' suffix columns anywhere in X
    for name, X in [("X_train", X_train), ("X_val", X_val), ("X_test", X_test)]:
        dot1 = [c for c in X.columns if c.endswith(".1")]
        if dot1:
            errors.append(f"  BAD COLUMNS: '.1' suffix cols in {name}: {dot1}")

    # 3. No missing values in X
    for name, X in [("X_train", X_train), ("X_val", X_val), ("X_test", X_test)]:
        n_miss = X.isna().sum().sum()
        if n_miss > 0:
            top = X.isna().sum().nlargest(3).to_dict()
            errors.append(f"  MISSING VALUES: {n_miss} NaNs in {name}  top cols: {top}")

    # 4. No missing values in y
    n_miss_y = y_train.isna().sum().sum()
    if n_miss_y > 0:
        errors.append(f"  MISSING VALUES: {n_miss_y} NaNs in y_train")

    # 5. Shapes consistent
    if not (len(X_train) == len(y_train)):
        errors.append(f"  SHAPE MISMATCH: X_train {len(X_train)} != y_train {len(y_train)}")

    if errors:
        print("\n  *** VALIDATION FAILED ***")
        for e in errors:
            print(e)
        raise ValueError("Preprocessing validation failed -- see errors above.")
    else:
        print(f"  PASSED -- no leakage, no missing values, shapes consistent")
        print(f"  X features : {X_train.shape[1]}")
        print(f"  X cols     : {list(X_train.columns)}")


# ==============================================================================
#  STEP 15 -- SAVE (CSV only -- no parquet dependency)
# ==============================================================================

def save_all(
    df_master: pd.DataFrame,
    X_train:   pd.DataFrame,
    X_val:     pd.DataFrame,
    X_test:    pd.DataFrame,
    y_train:   pd.DataFrame,
    y_val:     pd.DataFrame,
    y_test:    pd.DataFrame,
    train:     pd.DataFrame,
    val:       pd.DataFrame,
    test:      pd.DataFrame,
    output_dir: Path,
) -> None:
    _header("STEP 15 -- Save All Outputs (CSV only)")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Main dataset
    master_path = output_dir / "final_preprocessed.csv"
    df_master.to_csv(master_path, index=False)
    sz = master_path.stat().st_size / 1e6
    print(f"  final_preprocessed.csv   {len(df_master):>6,} rows x {df_master.shape[1]} cols  ({sz:.1f} MB)")

    # X / y splits
    for name, df in {
        "X_train": X_train, "X_val": X_val, "X_test": X_test,
        "y_train": y_train, "y_val": y_val, "y_test": y_test,
    }.items():
        df.to_csv(output_dir / f"{name}.csv", index=False)
        print(f"  {name:<10}  {len(df):>6,} rows x {df.shape[1]:>2} cols")

    # Report
    report = _build_report(df_master, X_train, X_val, X_test,
                           y_train, y_val, y_test, train, val, test)
    (output_dir / "split_report.txt").write_text("\n".join(report), encoding="utf-8")
    print(f"\n  split_report.txt  saved")
    print(f"  All files -> {output_dir.resolve()}")


# ==============================================================================
#  REPORT BUILDER
# ==============================================================================

def _build_report(
    df_master, X_train, X_val, X_test,
    y_train, y_val, y_test, train, val, test,
) -> list[str]:
    L = []
    L.append("=" * 65)
    L.append("  MANDI DISTRICT -- FINAL PREPROCESSING REPORT")
    L.append("=" * 65)
    L.append(f"\nDataset  : {len(df_master):,} rows x {df_master.shape[1]} columns")
    L.append(f"Features : {X_train.shape[1]}  |  Targets : {y_train.shape[1]}")

    L.append(f"\n{'-'*65}")
    L.append("  SPLITS")
    L.append(f"{'-'*65}")
    for name, sp in [("Train", train), ("Val", val), ("Test", test)]:
        s = sp["datetime"].min().strftime("%Y-%m-%d")
        e = sp["datetime"].max().strftime("%Y-%m-%d")
        L.append(f"  {name:<6}: {len(sp):>6,} rows  {s} -> {e}")

    L.append(f"\n{'-'*65}")
    L.append("  CLASS DISTRIBUTION -- rain_intensity_class")
    L.append(f"{'-'*65}")
    names = {0:"No Rain",1:"Light",2:"Moderate",3:"Heavy",4:"Very Heavy",5:"Extreme"}
    for label, y in [("Train", y_train), ("Val", y_val), ("Test", y_test)]:
        L.append(f"\n  {label}:")
        vc = y["rain_intensity_class"].value_counts().sort_index()
        for cls, cnt in vc.items():
            bar = "#" * int(cnt / len(y) * 40)
            L.append(f"    {cls} ({names.get(cls,'?'):<12}): {cnt:>6,} ({cnt/len(y)*100:.1f}%)  {bar}")

    L.append(f"\n{'-'*65}")
    L.append("  FEATURE COLUMNS IN X (no target leakage)")
    L.append(f"{'-'*65}")
    new_feats = {"temp_dewpoint_spread","wind_gust_ratio","precip_acceleration",
                 "humidity_cape_interact","rolling_ratio_3_24"}
    for i, col in enumerate(X_train.columns, 1):
        tag = "  <-- engineered" if col in new_feats else ""
        L.append(f"  {i:>3}. {col}{tag}")

    L.append(f"\n{'-'*65}")
    L.append("  HOW TO USE IN TRAINING")
    L.append(f"{'-'*65}")
    L.append("""
  import pandas as pd
  X_train = pd.read_csv("ml_ready/X_train.csv")
  X_val   = pd.read_csv("ml_ready/X_val.csv")
  X_test  = pd.read_csv("ml_ready/X_test.csv")
  y_train = pd.read_csv("ml_ready/y_train.csv")
  y_val   = pd.read_csv("ml_ready/y_val.csv")
  y_test  = pd.read_csv("ml_ready/y_test.csv")

  Task 1 -- Regression
    y = y_train["imd_rainfall_mm"]
    XGBRegressor()  |  metrics: MAE, RMSE, R2

  Task 2 -- Intensity Classification (0-5)
    y = y_train["rain_intensity_class"]
    XGBClassifier(use_label_encoder=False, eval_metric="mlogloss")
    + scale_pos_weight per class  |  metric: F1-macro

  Task 3 -- Cloudburst Detection (0.5% positive)
    y = y_train["cloudburst_flag"]
    XGBClassifier(scale_pos_weight=200)  |  metric: F1, AUC-PR

  Task 4 -- Landslide Risk (0.66% positive)
    y = y_train["landslide_risk"]
    XGBClassifier(scale_pos_weight=151)  |  metric: F1, AUC-PR

  DO NOT use accuracy for Tasks 3 & 4 -- imbalanced datasets.
  Use: F1, Precision-Recall AUC, ROC-AUC
""")
    L.append("=" * 65)
    L.append("  END")
    L.append("=" * 65)
    return L


# ==============================================================================
#  HELPERS
# ==============================================================================

def _header(title: str) -> None:
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")

def _print_dist(series: pd.Series, indent: str = "") -> None:
    for k, v in series.value_counts().sort_index().items():
        print(f"{indent}  {k}: {v:,}")


# ==============================================================================
#  MAIN
# ==============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Mandi District -- Final ML Preprocessing")
    parser.add_argument("--data",   type=str, default=None, help="Path to final_dataset.csv")
    parser.add_argument("--output", type=str, default=None, help="Output directory (default: ml_ready)")
    args = parser.parse_args()

    input_path = Path(args.data)   if args.data   else DEFAULT_INPUT
    output_dir = Path(args.output) if args.output else DEFAULT_OUTPUT

    print("\n" + "="*65)
    print("  MANDI DISTRICT -- FINAL ML PREPROCESSING")
    print("="*65)

    output_dir.mkdir(parents=True, exist_ok=True)

    # ---- Pipeline ----
    df = load(input_path)
    df = deduplicate_columns(df)   # Step 2: MUST be first
    df = parse_sort(df)            # Step 3
    df = drop_bad(df)              # Step 4
    df = fix_intensity_class(df)   # Step 5
    df = fix_cloudburst(df)        # Step 6
    df = impute_cape(df)           # Step 7
    df = fix_lag_nans(df)          # Step 8
    df = engineer_features(df)     # Step 9: +5 accuracy features
    df = reorder_columns(df)       # Step 10

    train, val, test = time_split(df)                          # Step 11
    train_sc, val_sc, test_sc, _ = scale(train, val, test,    # Step 12
                                          output_dir)
    X_train, X_val, X_test, \
    y_train, y_val, y_test = extract_xy(train_sc, val_sc,     # Step 13
                                         test_sc)

    validate(X_train, X_val, X_test, y_train)                 # Step 14

    save_all(df, X_train, X_val, X_test,                      # Step 15
             y_train, y_val, y_test,
             train, val, test, output_dir)

    # ---- Summary ----
    print("\n" + "="*65)
    print("  PREPROCESSING COMPLETE")
    print("="*65)
    print(f"\n  Input rows       : {len(df):,}")
    print(f"  Features (X)     : {X_train.shape[1]}")
    print(f"  X_train          : {X_train.shape[0]:,} rows")
    print(f"  X_val            : {X_val.shape[0]:,} rows")
    print(f"  X_test           : {X_test.shape[0]:,} rows")
    print(f"  y columns        : {list(y_train.columns)}")
    print(f"  Output dir       : {output_dir.resolve()}")
    print(f"\n  Ready for XGBoost model training.")


if __name__ == "__main__":
    main()