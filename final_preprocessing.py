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
  FIX 7 (NEW): Robust datetime column detection in Step 3. Previously the
          script assumed a column literally named 'datetime' existed and
          crashed with KeyError: 'datetime' the moment the source CSV used
          a different name/case (Date, Timestamp, DateTime) or the datetime
          came back as an unnamed index column ('Unnamed: 0') from an
          upstream to_csv() that didn't set index=False. Step 3 now searches
          for it and renames it instead of assuming.

NEW in this version
--------------------
  STEP 5B: Log1p target transform  -- imd_rainfall_mm is heavily right-skewed
                                      (mostly near-zero hours, rare huge
                                      values during cloudbursts). Adds
                                      imd_rainfall_mm_log1p = log1p(mm) as an
                                      EXTRA target column alongside the raw
                                      mm column (raw is kept -- thresholds in
                                      Step 5/6 and reporting all use it).
                                      Regression models can train on the
                                      log1p column instead, which usually
                                      gives a much better-conditioned loss
                                      surface for skewed rainfall regression;
                                      just remember to np.expm1() predictions
                                      back to mm before computing MAE/RMSE.
  STEP 9B: Isolation Forest outlier flagging -- flags statistically
                                      anomalous sensor rows (temp, wind,
                                      CAPE, etc.) and writes them to
                                      outlier_report.csv for manual review.
                                      Never drops or alters rows: doing so
                                      would break rolling/lag continuity for
                                      neighbouring hours and risks deleting
                                      genuine extreme-weather signal along
                                      with real sensor glitches.
  STEP 16: Class weighting        -- balanced weights for rain_intensity_class,
                                      data-driven scale_pos_weight for
                                      cloudburst_flag / landslide_risk
                                      (computed from real counts, not hardcoded)
  STEP 17: Weighted temporal CV   -- blocked/expanding-window CV folds
                                      (never shuffled -- this is a time series),
                                      with per-fold class-weight table since the
                                      positive rate drifts across the year
  STEP 18: Time-block undersampling -- fixes rare-event imbalance for
                                      cloudburst_flag / landslide_risk by
                                      dropping whole negative-only time blocks
                                      (never individual rows, which would break
                                      rolling/lag features)
  STEP 19: Hyperparameter recommendations -- data-driven search spaces +
                                      scale_pos_weight values saved to JSON
  STEP 8B (NEW): Humidity trend        -- relative_humidity_change_1h/3h,
                                      the missing counterpart to the
                                      existing pressure/temp/dewpoint trend
                                      features. Computed defensively (only
                                      fills what's missing; never overwrites
                                      real upstream values).
  STEP 9C (NEW): Spatial / terrain features -- latitude, longitude,
                                      elevation, slope, aspect, terrain
                                      ruggedness index, distance to river,
                                      land cover. Constant for this single-
                                      station dataset (documented caveat in
                                      the function docstring); wired in so
                                      the pipeline is multi-station/gridded
                                      -data ready without further code
                                      changes, and excluded from scaling to
                                      avoid a zero-std divide-by-zero.

Output files (in ml_ready/)
----------------------------
    final_preprocessed.csv          full clean dataset (37 cols incl. log1p target)
    X_train.csv / X_val.csv / X_test.csv
    y_train.csv / y_val.csv / y_test.csv    (includes imd_rainfall_mm_log1p)
    scaler_params.csv               mean / std per scaled feature
    sample_weights_train.csv        per-row weights for all 3 classification tasks
    class_weights.json              balanced class weights + scale_pos_weight
    temporal_cv_folds.csv           row_index -> fold (blocked, expanding window)
    temporal_cv_fold_weights.csv    per-fold pos counts + scale_pos_weight
    X_train_cloudburst_flag_balanced.csv / y_train_cloudburst_flag_balanced.csv
    X_train_landslide_risk_balanced.csv  / y_train_landslide_risk_balanced.csv
    hyperparam_recommendations.json search spaces per task
    train_ready_master.csv          *** SINGLE FILE FOR TRAINING ***
                                     X_train + y_train + all 3 sample-weight
                                     cols + cv_fold, one row per hour.
                                     Use for Task 1 & 2. For Task 3/4 use the
                                     *_balanced.csv pair instead (different
                                     row count by design -- see Step 20 docstring)
    split_report.txt                full summary

Usage
-----
    python final_preprocessing.py
    python final_preprocessing.py --data path/to/final_dataset.csv
    python final_preprocessing.py --data path/to/final_dataset.csv --output ml_ready
"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_class_weight

warnings.filterwarnings("ignore")

# ==============================================================================
#  CONFIGURATION
# ==============================================================================

DEFAULT_INPUT  = Path("datasets/merged_dataset/final_dataset.csv")
DEFAULT_OUTPUT = Path("ml_ready")

TRAIN_END     = "2023-06-30 23:00:00"
VAL_END       = "2023-12-31 23:00:00"
CLOUDBURST_MM = 100.0

CV_N_SPLITS               = 5      # temporal CV folds
UNDERSAMPLE_BLOCK_HOURS   = 24     # size of a time block for undersampling
UNDERSAMPLE_TARGET_RATIO  = 10     # neg:pos ratio to aim for after undersampling
RANDOM_STATE              = 42

# Candidate names/aliases used to auto-detect the datetime column in Step 3
# (case/spacing/underscore-insensitive match against this list).
DATETIME_ALIASES = ["datetime", "date", "timestamp", "time", "datetimeutc"]

# Columns checked for statistical outliers (Step 9B). Only raw sensor-derived
# atmospheric/rainfall readings -- never targets, never already-engineered
# ratios (those would just re-flag the same signal twice).
OUTLIER_DETECTION_COLS = [
    "temperature_2m", "dewpoint_2m", "relative_humidity", "surface_pressure",
    "wind_speed_10m", "wind_gusts_10m", "cloud_cover", "cape",
    "precipitation_openmeteo", "rain_openmeteo",
]
OUTLIER_CONTAMINATION = 0.01   # expected fraction of rows that are sensor anomalies

# Features that overlap with how cloudburst_flag / landslide_risk are DEFINED
# (cloudburst_flag = rolling_precip_3h >= 100mm), so rolling_precip_24h/72h
# contain that exact 3h window inside their own sum -- a validation report
# flagged these with AUC 0.90-0.99 predicting the rare-event targets alone.
# That's not future leakage (all past/current data), but it IS circular:
# the model would mostly be re-detecting a component of its own label.
# Dropped ONLY from the rare-event balanced sets below -- kept for Task 1/2,
# where they are legitimate predictors of continuous rainfall / intensity.
RARE_EVENT_DROP_COLS = ["rolling_precip_24h", "rolling_precip_72h"]

# Columns confirmed bad by EDA
DROP_COLS = [
    "precipitation_gpm",   # all zeros -- GPM merge failed
    "mslp",                # 88% missing, redundant with surface_pressure
]

# ------------------------------------------------------------------------
# STATIC SPATIAL / TERRAIN METADATA (Step 9D)
# ------------------------------------------------------------------------
# This dataset is a SINGLE weather-station record for Mandi district, HP,
# so latitude/longitude/elevation/terrain descriptors are constants -- they
# do not vary row-to-row the way a multi-station dataset would. They are
# still added as columns (per your request) because:
#   - They make the feature set self-documenting and station-portable: if
#     you later merge in a second station (or a gridded product covering
#     several points across Mandi district), each row's real coordinates
#     replace these constants and the model can then actually learn
#     terrain-driven spatial effects.
#   - A tree-based model (XGBoost etc.) simply ignores a zero-variance
#     column (no valid split can improve impurity on a constant), so
#     including it is harmless for a single-station model -- it's a no-op
#     placeholder rather than something that hurts current performance.
# If your source CSV already carries real per-row values for any of these
# (e.g. because you've since merged multiple stations/grid points), Step 9D
# below will detect and KEEP those real values instead of overwriting them.
#
# Values below are approximate for Mandi town, Himachal Pradesh -- replace
# with your station's exact surveyed coordinates/DEM-derived values if known.
MANDI_STATION_METADATA = {
    "latitude":                 31.7076,   # deg N
    "longitude":                76.9319,   # deg E
    "elevation":                761.0,     # metres above sea level
    "slope":                    18.5,      # deg, local terrain slope (DEM-derived estimate)
    "aspect":                   225.0,     # deg (0-360, compass direction terrain faces; SW here)
    "terrain_ruggedness_index": 145.0,     # TRI (metres), moderate-to-high Himalayan foothill terrain
    "distance_to_river_km":     1.2,       # approx. distance to nearest major river (Beas)
    "land_cover":                2,        # categorical code: 0=water,1=urban,2=forest,3=cropland,4=barren/rock
}

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
    "precip_lag_12h",   # NEW -- longer lag windows for hazard/forecast horizon
    "precip_lag_24h",   # NEW
    "precip_lag_48h",   # NEW
    "precip_lag_72h",   # NEW
    # -- Trend / change features (NEW) --
    "pressure_change_1h",   # rapid pressure drop often precedes storms
    "pressure_change_3h",
    "pressure_change_6h",
    "temp_change_1h",
    "temp_change_3h",
    "temp_change_6h",
    "dewpoint_change_1h",
    "dewpoint_change_3h",
    "relative_humidity_change_1h",   # NEW -- humidity trend (rising RH often precedes rain)
    "relative_humidity_change_3h",   # NEW
    # -- Antecedent-condition features (NEW, built from precip_lag_1h only --
    #    i.e. based on PRIOR hours, never the current hour's rain status, to
    #    avoid leaking the very thing these tasks are trying to predict) --
    "consecutive_rain_hours",   # how many prior hours were consecutively wet
    "dry_spell_hours",          # how many prior hours since it last rained
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
    "week_of_year",   # NEW
    "day_of_week",    # NEW
    "is_weekend",     # NEW -- low predictive value for weather but nearly free;
                       # kept since some anthropogenic/reporting patterns can
                       # correlate with day-of-week (station staffing gaps etc.)
    # -- Spatial / terrain features (NEW, Step 9D) --
    # Constant for this single-station dataset today; wired in so the
    # pipeline is ready for multi-station/gridded data without code changes.
    # See MANDI_STATION_METADATA docstring above for details/caveats.
    "latitude",
    "longitude",
    "elevation",
    "slope",
    "aspect",
    "terrain_ruggedness_index",
    "distance_to_river_km",
    "land_cover",
]

# ==============================================================================
#  TARGET COLUMNS  (y -- what models predict)
# ==============================================================================

TARGET_COLS = [
    "imd_rainfall_mm",          # Task 1: Regression  -- how much rain?
    "imd_rainfall_mm_log1p",    # Task 1 (alt): Regression on log1p(mm) -- less skewed
    "rain_intensity_class",     # Task 2: Multi-class -- 0=No Rain .. 5=Extreme
    "cloudburst_flag",          # Task 3: Binary      -- >= 100mm/3h yes/no
    "landslide_risk",           # Task 4: Binary      -- landslide risk yes/no
    # -- Alternate simplified binary targets (NEW) -- these are coarser
    # re-thresholds of imd_rainfall_mm / rain_intensity_class, so they are
    # TARGETS, never features: using them as X would be direct label leakage.
    "heavy_rain_flag",          # Task 2b: Binary -- rain_intensity_class >= 3
    "very_heavy_rain_flag",     # Task 2c: Binary -- rain_intensity_class >= 4
    "extreme_rain_flag",        # Task 2d: Binary -- rain_intensity_class == 5
]

# Columns that must NOT be scaled
DO_NOT_SCALE = [
    "hour_sin", "hour_cos", "month_sin", "month_cos",
    "hour", "month", "day_of_year", "season", "is_monsoon",
    "wind_direction_10m",
    "week_of_year", "day_of_week", "is_weekend",   # NEW -- categorical/ordinal calendar
    # NEW -- spatial/terrain fields. land_cover is a categorical code and
    # aspect is a circular compass bearing (0-360, like wind_direction_10m),
    # neither of which StandardScaler should touch. latitude/longitude/
    # elevation/slope/terrain_ruggedness_index/distance_to_river_km are
    # CONSTANT for this single-station dataset -- StandardScaler would
    # divide by a std of 0 and produce NaN/inf, so they're excluded here
    # too. Remove them from this list once real per-row multi-station
    # values with genuine variance are present.
    "latitude", "longitude", "elevation", "slope", "aspect",
    "terrain_ruggedness_index", "distance_to_river_km", "land_cover",
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
    # NOTE: this only removes true '<name>.1' duplicates -- it never touches
    # the primary 'datetime' column itself, so it can't be the cause of a
    # missing 'datetime' column downstream (that's a naming mismatch, see
    # the robust detection added in Step 3 below).
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

def _find_datetime_column(df: pd.DataFrame) -> str:
    """
    Robustly locate the datetime column instead of assuming it is literally
    named 'datetime'. Handles:
      - different case/spacing/underscores ('Date', 'Time Stamp', 'DateTime')
      - the datetime having been saved as an unnamed index column upstream,
        which pandas reads back in as 'Unnamed: 0'
    Raises a clear error (with the real column list) if nothing matches,
    instead of a bare KeyError.
    """
    if "datetime" in df.columns:
        return "datetime"

    norm = lambda s: str(s).lower().replace(" ", "").replace("_", "").replace("-", "")
    for col in df.columns:
        if norm(col) in DATETIME_ALIASES:
            return col

    unnamed = [c for c in df.columns if str(c).startswith("Unnamed:")]
    if unnamed:
        return unnamed[0]

    raise KeyError(
        "No datetime-like column found in the input file. "
        f"Available columns: {list(df.columns)}"
    )


def parse_sort(df: pd.DataFrame) -> pd.DataFrame:
    _header("STEP 3 -- Parse Datetime and Sort")

    dt_col = _find_datetime_column(df)
    if dt_col != "datetime":
        print(f"  NOTE: datetime column found as '{dt_col}' -- renaming to 'datetime'")
        df = df.rename(columns={dt_col: "datetime"})

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
#  STEP 4B -- DROP ROWS WITH MISSING REGRESSION TARGET (imd_rainfall_mm)
# ==============================================================================

def drop_missing_target(df: pd.DataFrame) -> pd.DataFrame:
    """
    Some hours in a 20+ year station record simply have no rainfall reading
    (sensor/reporting gap). imd_rainfall_mm is the ground truth for Task 1
    AND the raw value that Step 5/6 threshold into rain_intensity_class and
    cloudburst_flag -- so a missing reading here poisons all three targets
    at once, not just one column.

    This MUST run before Step 5, because the old code's np.select(...,
    default=0) silently mapped every NaN-rainfall hour to class 0
    ('No Rain') -- fabricating a label for an hour where we have no idea
    what actually happened, rather than admitting the ground truth is
    unknown. Statistically imputing a rainfall AMOUNT (unlike CAPE or
    dewpoint, which have physical/seasonal proxies) would be inventing
    ground truth for a supervised target, which is worse than just
    dropping the row.
    """
    _header("STEP 4B -- Drop Rows with Missing Rainfall Target")
    n_before = len(df)
    n_missing = int(df["imd_rainfall_mm"].isna().sum())
    if n_missing:
        df = df.dropna(subset=["imd_rainfall_mm"]).reset_index(drop=True)
        print(f"  DROPPED : {n_missing:,} rows ({n_missing/n_before*100:.2f}%) "
              f"with missing imd_rainfall_mm (target unknown -- not imputed)")
    else:
        print(f"  No missing rainfall readings found.")
    print(f"  Rows remaining : {len(df):,}")
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

    NOTE: by the time this runs, Step 4B has already dropped every row with
    a missing imd_rainfall_mm, so `default=0` below only ever fires as an
    unreachable safety net -- it can no longer silently mislabel an unknown
    reading as 'No Rain' the way the original script did.
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
#  STEP 5B -- LOG1P TARGET TRANSFORM (skew correction for regression)
# ==============================================================================

def add_log_target(df: pd.DataFrame) -> pd.DataFrame:
    """
    imd_rainfall_mm is extremely right-skewed: the vast majority of hours are
    0 or near-0 mm, with a long thin tail of large values during storms and
    cloudbursts. Training a regressor directly on raw mm lets those rare
    large values dominate the squared-error loss and pulls predictions
    toward over-forecasting typical hours.

    log1p(x) = log(1 + x) compresses that tail while leaving 0 -> 0, so it:
      - keeps the transform valid for the many exact-zero rainfall hours
        (plain log(x) would be -inf there)
      - is monotonic and exactly invertible: mm = expm1(log1p(mm))

    This ADDS a new target column -- it does NOT replace imd_rainfall_mm.
    Every downstream step that thresholds on real millimetres (Step 5's IMD
    classes, Step 6's cloudburst flag, reporting, EDA) keeps using the raw
    mm column untouched. Use imd_rainfall_mm_log1p only as an alternative
    training target for the Task 1 regressor, and remember to np.expm1()
    the model's predictions back to mm before computing MAE/RMSE or
    comparing against the raw-mm baseline.
    """
    _header("STEP 5B -- Log1p Target Transform (imd_rainfall_mm)")

    raw = df["imd_rainfall_mm"]
    print(f"  Raw imd_rainfall_mm       : skew={raw.skew():.2f}  "
          f"mean={raw.mean():.2f}  max={raw.max():.2f}")

    df["imd_rainfall_mm_log1p"] = np.log1p(raw.clip(lower=0))
    logged = df["imd_rainfall_mm_log1p"]
    print(f"  imd_rainfall_mm_log1p     : skew={logged.skew():.2f}  "
          f"mean={logged.mean():.3f}  max={logged.max():.3f}")
    print(f"  Added as an EXTRA target column (raw imd_rainfall_mm kept as-is)")
    print(f"  Inverse transform for predictions: np.expm1(pred)")
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
#  STEP 7B -- PHYSICALLY DERIVE MISSING dewpoint_2m / wind_u_10m / wind_v_10m
# ==============================================================================

def derive_missing_met_vars(df: pd.DataFrame) -> pd.DataFrame:
    """
    dewpoint_2m and the wind_u_10m/wind_v_10m components are NOT independent
    measurements -- they are exact mathematical functions of columns that
    are already fully populated in this dataset:

      dewpoint_2m  <- temperature_2m, relative_humidity   (Magnus formula)
      wind_u_10m   <- wind_speed_10m, wind_direction_10m  (trigonometry)
      wind_v_10m   <- wind_speed_10m, wind_direction_10m  (trigonometry)

    So when ~80% of these three columns are missing, the correct fix is to
    RECOMPUTE the true physical value, not statistically impute a
    seasonal/climatological filler the way Step 7 does for CAPE. A seasonal
    median for dewpoint would replace a hard-derivable, hour-specific
    physical quantity with a constant that ignores that hour's actual
    temperature and humidity -- much worse than just calculating it.

    Only fills where missing; any value already present is left untouched.
    Falls back to leaving NaN (caught by Step 14's validation) only if the
    required inputs are themselves missing for that row.
    """
    _header("STEP 7B -- Derive Missing dewpoint_2m / wind_u_10m / wind_v_10m")

    # ---- Dewpoint via Magnus-Tetens formula (T in deg C, RH in %) ----
    if "dewpoint_2m" in df.columns:
        n_miss = int(df["dewpoint_2m"].isna().sum())
        if n_miss and {"temperature_2m", "relative_humidity"}.issubset(df.columns):
            T = df["temperature_2m"]
            RH = df["relative_humidity"].clip(lower=0.1, upper=100)  # avoid log(0)
            a, b = 17.27, 237.7
            gamma = (a * T) / (b + T) + np.log(RH / 100.0)
            td_derived = (b * gamma) / (a - gamma)
            mask = df["dewpoint_2m"].isna()
            df.loc[mask, "dewpoint_2m"] = td_derived[mask]
            print(f"  dewpoint_2m  : derived {mask.sum():,} of {n_miss:,} missing "
                  f"values from temperature_2m + relative_humidity")
        n_left = int(df["dewpoint_2m"].isna().sum())
        if n_left:
            print(f"  dewpoint_2m  : {n_left:,} still missing (inputs also missing)")

    # ---- Wind u/v components via trigonometry ----
    if {"wind_u_10m", "wind_v_10m"}.issubset(df.columns):
        n_miss_u = int(df["wind_u_10m"].isna().sum())
        n_miss_v = int(df["wind_v_10m"].isna().sum())
        if (n_miss_u or n_miss_v) and {"wind_speed_10m", "wind_direction_10m"}.issubset(df.columns):
            speed = df["wind_speed_10m"]
            direction_rad = np.deg2rad(df["wind_direction_10m"])
            u_derived = -speed * np.sin(direction_rad)
            v_derived = -speed * np.cos(direction_rad)

            mask_u = df["wind_u_10m"].isna()
            mask_v = df["wind_v_10m"].isna()
            df.loc[mask_u, "wind_u_10m"] = u_derived[mask_u]
            df.loc[mask_v, "wind_v_10m"] = v_derived[mask_v]
            print(f"  wind_u_10m   : derived {mask_u.sum():,} of {n_miss_u:,} missing "
                  f"values from wind_speed_10m + wind_direction_10m")
            print(f"  wind_v_10m   : derived {mask_v.sum():,} of {n_miss_v:,} missing "
                  f"values from wind_speed_10m + wind_direction_10m")
        n_left_u = int(df["wind_u_10m"].isna().sum())
        n_left_v = int(df["wind_v_10m"].isna().sum())
        if n_left_u or n_left_v:
            print(f"  wind_u/v_10m : {n_left_u:,}/{n_left_v:,} still missing (inputs also missing)")

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
    # FIX (bug found during testing): the original list here only covered
    # 1h/3h/6h, but FEATURE_COLS also includes the longer 12h/24h/48h/72h
    # lag windows added for the extended forecast horizon. Those longer
    # lags have edge-effect NaNs in the first up to 72 rows of the whole
    # series, same reason as the short lags -- left unfilled, they slipped
    # through as real NaNs into X_train and failed Step 14's validation.
    for col in ["precip_lag_1h", "precip_lag_3h", "precip_lag_6h",
                "precip_lag_12h", "precip_lag_24h", "precip_lag_48h", "precip_lag_72h"]:
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
#  STEP 8B -- HUMIDITY TREND FEATURES (relative_humidity_change_1h/3h)
# ==============================================================================

def add_humidity_trend(df: pd.DataFrame) -> pd.DataFrame:
    """
    pressure_change_*, temp_change_*, and dewpoint_change_* are assumed to
    already exist in the source CSV (built upstream in Stage A), but the
    upstream pipeline had no equivalent humidity-trend feature. Rising
    relative humidity over the last 1-3 hours is itself a useful precursor
    signal for rain (moistening boundary layer ahead of convection), so it
    belongs alongside the other *_change_* trend features.

    Computed here (not assumed pre-built) as a simple hourly diff:
      relative_humidity_change_Nh = RH(t) - RH(t - N hours)

    If the source CSV already provides these columns (e.g. a future Stage A
    update adds them upstream), this step leaves the existing values alone
    and only fills in genuinely missing ones -- it never overwrites real
    upstream data.
    """
    _header("STEP 8B -- Humidity Trend Features (relative_humidity_change_1h/3h)")

    if "relative_humidity" not in df.columns:
        print("  relative_humidity column not found -- skipping (nothing to derive from).")
        return df

    for hrs, col in [(1, "relative_humidity_change_1h"), (3, "relative_humidity_change_3h")]:
        if col in df.columns:
            n_miss = int(df[col].isna().sum())
            if n_miss:
                computed = df["relative_humidity"].diff(hrs)
                mask = df[col].isna()
                df.loc[mask, col] = computed[mask]
                print(f"  {col:<28}: already present -- filled {n_miss} missing value(s)")
            else:
                print(f"  {col:<28}: already present, no missing values -- left untouched")
        else:
            df[col] = df["relative_humidity"].diff(hrs)
            print(f"  {col:<28}: derived (RH(t) - RH(t-{hrs}h))  mean={df[col].mean():.3f}")

    # Same edge-effect NaNs as the other lag/diff features (first N rows of
    # the whole series have no prior hour to diff against) -- fill with 0,
    # i.e. assume no humidity change at the very start of the record.
    for col in ["relative_humidity_change_1h", "relative_humidity_change_3h"]:
        n = df[col].isna().sum()
        if n:
            df[col] = df[col].fillna(0.0)
            print(f"  {col:<28}: filled {n} edge-effect NaN(s) with 0")

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
#  STEP 9B -- ISOLATION FOREST OUTLIER DETECTION (flag + report, never drop)
# ==============================================================================

def detect_outliers(df: pd.DataFrame, output_dir: Path) -> pd.DataFrame:
    """
    Flags statistically anomalous rows (likely sensor glitches) using
    IsolationForest over the raw atmospheric/rainfall readings.

    Deliberately does NOT drop or modify any row. This is an hourly time
    series with rolling/lag features -- silently removing a row would blow a
    hole in every neighbouring row's rolling window and lag features (the
    exact same reason Step 18's undersampling drops whole time BLOCKS
    instead of individual rows). An outlier here might also be a genuine
    extreme weather reading, which is precisely what Tasks 3/4 are trying to
    predict -- auto-dropping it would remove real signal, not noise.

    Writes outlier_report.csv (datetime + flagged sensor values) so you can
    review candidates manually and decide case-by-case whether any are
    confirmed sensor errors worth hand-correcting upstream in Stage A.
    """
    _header("STEP 9B -- Isolation Forest Outlier Detection (flag only)")

    cols = [c for c in OUTLIER_DETECTION_COLS if c in df.columns]
    if not cols:
        print("  No outlier-detection columns present -- skipping.")
        return df

    X = df[cols].fillna(df[cols].median())
    iso = IsolationForest(
        n_estimators=200,
        contamination=OUTLIER_CONTAMINATION,
        random_state=RANDOM_STATE,
    )
    flags = iso.fit_predict(X)          # -1 = outlier, 1 = inlier
    is_outlier = (flags == -1)
    n_out = int(is_outlier.sum())

    print(f"  Columns checked : {cols}")
    print(f"  Flagged         : {n_out:,} rows ({n_out/len(df)*100:.2f}%) as statistical anomalies")
    print(f"  NOT dropped -- see docstring: would break rolling/lag continuity")
    print(f"  and may remove genuine extreme-weather signal, not just noise.")

    report_cols = ["datetime"] + cols
    df.loc[is_outlier, report_cols].to_csv(output_dir / "outlier_report.csv", index=False)
    print(f"  Saved: outlier_report.csv ({n_out:,} flagged rows, for manual review)")
    return df


# ==============================================================================
#  STEP 9C -- SPATIAL / TERRAIN FEATURES
#  (latitude, longitude, elevation, slope, aspect, TRI, dist-to-river, land cover)
# ==============================================================================

def add_spatial_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds the 8 spatial/terrain columns recommended for a Himachal Pradesh
    rainfall/multi-hazard model: latitude, longitude, elevation, slope,
    aspect, terrain_ruggedness_index, distance_to_river_km, land_cover.
    Terrain strongly shapes orographic rainfall and landslide risk in HP,
    so these are worth carrying even in a single-station setup.

    IMPORTANT CAVEAT (single-station dataset): this source file is one
    station's hourly time series, so these values are the SAME constant on
    every row here. A tree-based model can't learn anything from a
    zero-variance column, so today they act as documentation/placeholders
    rather than active predictors -- they earn their keep once you add a
    second station or a gridded terrain product with real row-to-row
    variation (each grid cell/station gets its own true lat/lon/elevation/
    slope/aspect/TRI/river-distance/land-cover instead of the Mandi
    constant). DO_NOT_SCALE already excludes them so a zero standard
    deviation doesn't blow up StandardScaler.

    If the input CSV already has real per-row values for any of these
    columns (e.g. you've since merged additional stations), this function
    detects that and KEEPS the existing values -- it only fills in columns
    that are completely absent.
    """
    _header("STEP 9C -- Spatial / Terrain Features")

    added, kept = [], []
    for col, val in MANDI_STATION_METADATA.items():
        if col in df.columns:
            n_miss = int(df[col].isna().sum())
            if n_miss:
                df[col] = df[col].fillna(val)
                print(f"  {col:<26}: already present -- filled {n_miss} missing value(s) "
                      f"with Mandi default ({val})")
            kept.append(col)
        else:
            df[col] = val
            added.append(col)

    if added:
        print(f"  Added as constants (Mandi station default): {added}")
    if kept:
        print(f"  Already present in source data -- left as-is (only NaNs backfilled): {kept}")
    print("  NOTE: these are constant for this single-station dataset -- see docstring.")
    print("  They become genuinely predictive once multi-station/gridded terrain data is used.")
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
#  STEP 16 -- CLASS WEIGHTS & SAMPLE WEIGHTS  (data-driven, not hardcoded)
# ==============================================================================

def compute_weights(y_train: pd.DataFrame, output_dir: Path) -> dict:
    """
    - rain_intensity_class (multiclass, 0-5): sklearn 'balanced' class weights
      -> a per-row sample_weight column, since XGBClassifier's multiclass mode
      has no native class_weight argument (only binary scale_pos_weight does).
    - cloudburst_flag / landslide_risk (binary, rare-event): scale_pos_weight
      = neg/pos, computed from the ACTUAL train counts (the old script had
      these hardcoded as 200 / 151 -- guesses that go stale the moment the
      dataset changes).

    Saves sample_weights_train.csv (row-aligned with X_train/y_train) and
    class_weights.json (for reference / for the tuning script).
    """
    _header("STEP 16 -- Class Weights & Sample Weights")

    weights_summary: dict = {}

    # ---- Multiclass: rain_intensity_class ----
    classes = np.sort(y_train["rain_intensity_class"].unique())
    cw = compute_class_weight("balanced", classes=classes, y=y_train["rain_intensity_class"])
    class_weight_map = {int(c): float(w) for c, w in zip(classes, cw)}
    weights_summary["rain_intensity_class"] = {"class_weight": class_weight_map}
    sw_intensity = y_train["rain_intensity_class"].map(class_weight_map).values
    print(f"  rain_intensity_class class_weight: {class_weight_map}")

    sample_weights = pd.DataFrame({"sw_rain_intensity_class": sw_intensity})

    # ---- Binary rare-event tasks ----
    for col in ["cloudburst_flag", "landslide_risk"]:
        pos = int(y_train[col].sum())
        neg = int(len(y_train) - pos)
        spw = round(neg / max(pos, 1), 3)
        weights_summary[col] = {
            "scale_pos_weight": spw, "pos": pos, "neg": neg,
            "pos_pct": round(pos / len(y_train) * 100, 4),
        }
        sample_weights[f"sw_{col}"] = np.where(y_train[col] == 1, spw, 1.0)
        print(f"  {col:<18}: pos={pos:,}  neg={neg:,}  scale_pos_weight={spw}"
              f"  ({pos/len(y_train)*100:.3f}% positive)")

    sample_weights.to_csv(output_dir / "sample_weights_train.csv", index=False)
    with open(output_dir / "class_weights.json", "w") as f:
        json.dump(weights_summary, f, indent=2)

    print(f"  Saved: sample_weights_train.csv (row-aligned with X_train/y_train)")
    print(f"  Saved: class_weights.json")
    return weights_summary


# ==============================================================================
#  STEP 17 -- WEIGHTED TEMPORAL CROSS-VALIDATION FOLDS
# ==============================================================================

def make_temporal_cv_folds(
    dates_train: pd.Series,
    y_train: pd.DataFrame,
    output_dir: Path,
    n_splits: int = CV_N_SPLITS,
) -> pd.DataFrame:
    """
    Blocked / expanding-window CV -- NEVER shuffled, because this is a time
    series. Fold i trains on everything chronologically BEFORE its validation
    block and validates on the block right after it (sklearn's TimeSeriesSplit).
    Plain KFold or a random shuffle-split would leak future rows into past
    training folds and give badly over-optimistic CV scores.

    It is 'weighted' because each fold also gets its own scale_pos_weight
    for cloudburst_flag/landslide_risk: the positive rate for these rare
    events drifts across the year (monsoon-heavy folds vs winter-heavy
    folds), so a single global weight would under- or over-correct
    depending which fold you're on. Use temporal_cv_fold_weights.csv during
    hyperparameter search to re-weight scale_pos_weight per fold.
    """
    _header("STEP 17 -- Weighted Temporal Cross-Validation Folds")

    n = len(dates_train)
    tscv = TimeSeriesSplit(n_splits=n_splits)

    fold_assignment = np.full(n, -1, dtype=int)
    fold_report = []

    for fold_id, (tr_idx, va_idx) in enumerate(tscv.split(np.arange(n))):
        fold_assignment[va_idx] = fold_id

        tr_start, tr_end = dates_train.iloc[tr_idx[0]], dates_train.iloc[tr_idx[-1]]
        va_start, va_end = dates_train.iloc[va_idx[0]], dates_train.iloc[va_idx[-1]]

        row = {
            "fold": fold_id,
            "train_rows": len(tr_idx), "val_rows": len(va_idx),
            "train_start": str(tr_start), "train_end": str(tr_end),
            "val_start": str(va_start), "val_end": str(va_end),
        }

        for col in ["cloudburst_flag", "landslide_risk"]:
            pos = int(y_train[col].iloc[va_idx].sum())
            neg = len(va_idx) - pos
            row[f"{col}_val_pos"] = pos
            row[f"{col}_val_scale_pos_weight"] = round(neg / max(pos, 1), 3)

        fold_report.append(row)
        print(f"  Fold {fold_id}: train={len(tr_idx):>6,} rows [{tr_start.date()} -> {tr_end.date()}]"
              f"  val={len(va_idx):>6,} rows [{va_start.date()} -> {va_end.date()}]")

    cv_df = pd.DataFrame({"row_index": np.arange(n), "fold": fold_assignment})
    cv_df.to_csv(output_dir / "temporal_cv_folds.csv", index=False)

    fold_report_df = pd.DataFrame(fold_report)
    fold_report_df.to_csv(output_dir / "temporal_cv_fold_weights.csv", index=False)

    n_unused = int((fold_assignment == -1).sum())
    print(f"  Rows before fold 0's validation window (fold=-1, used only as training context): {n_unused:,}")
    print(f"  Saved: temporal_cv_folds.csv, temporal_cv_fold_weights.csv")
    return fold_report_df


# ==============================================================================
#  STEP 18 -- TIME-BLOCK UNDERSAMPLING (rare-event tasks)
# ==============================================================================

def time_block_undersample(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    dates_train: pd.Series,
    target_col: str,
    output_dir: Path,
    block_hours: int = UNDERSAMPLE_BLOCK_HOURS,
    target_ratio: float = UNDERSAMPLE_TARGET_RATIO,
    random_state: int = RANDOM_STATE,
) -> None:
    """
    Random row-level undersampling would rip individual hours out of the
    sequence, which destroys the meaning of rolling/lag features for their
    neighbours. Instead this undersamples by whole CONTIGUOUS time blocks:

      1. Bucket every row into a block of `block_hours` hours.
      2. Any block containing >= 1 positive event is always kept whole
         (full context around every real event is preserved).
      3. Blocks with zero positives ('negative-only') are randomly dropped
         WHOLE until the remaining neg:pos ratio reaches `target_ratio`.

    Output is a separate, smaller, class-balanced training set -- use it
    for the rare-event tasks (cloudburst_flag, landslide_risk) instead of
    the full X_train/y_train, on top of scale_pos_weight.

    Also drops RARE_EVENT_DROP_COLS (rolling_precip_24h/72h) here ONLY --
    these wide rolling windows contain the exact same hours used to define
    cloudburst_flag (rolling_precip_3h >= 100mm), so keeping them would let
    the model mostly re-detect a component of its own label rather than
    learn genuine precursor signals. Task 1/2 datasets keep these columns,
    since they're legitimate predictors there.
    """
    block_id = ((dates_train - dates_train.min()) / pd.Timedelta(hours=block_hours)).astype(int)

    pos_mask = y_train[target_col] == 1
    pos_blocks = set(block_id[pos_mask].unique())
    keep_mask = block_id.isin(pos_blocks).values  # always keep event blocks

    neg_only_blocks = sorted(set(block_id.unique()) - pos_blocks)
    n_pos = int(pos_mask.sum())
    target_neg = int(n_pos * target_ratio)

    rng = np.random.default_rng(random_state)
    rng.shuffle(neg_only_blocks)

    kept_neg_rows = 0
    chosen_neg_blocks = set()
    for b in neg_only_blocks:
        if kept_neg_rows >= target_neg:
            break
        chosen_neg_blocks.add(b)
        kept_neg_rows += int((block_id == b).sum())

    final_mask = keep_mask | block_id.isin(chosen_neg_blocks).values

    X_bal = X_train.loc[final_mask].reset_index(drop=True)
    y_bal = y_train.loc[final_mask].reset_index(drop=True)
    # Carried through so downstream CV can split by whole BLOCK instead of
    # raw row position. A plain row-position time-series split can slice
    # straight through the middle of one storm's block -- neighbouring
    # hours of the SAME event are nearly identical, so a model 'validates'
    # on what's essentially a copy of its own training data, producing an
    # artificially perfect CV score that collapses on real validation data.
    y_bal["block_id"] = block_id.loc[final_mask].reset_index(drop=True).values

    drop_now = [c for c in RARE_EVENT_DROP_COLS if c in X_bal.columns]
    if drop_now:
        X_bal = X_bal.drop(columns=drop_now)
        print(f"    Dropped (label-overlap risk): {drop_now}")

    n_pos_final = int(y_bal[target_col].sum())
    n_neg_final = len(y_bal) - n_pos_final
    spw_final = round(n_neg_final / max(n_pos_final, 1), 3)

    X_bal.to_csv(output_dir / f"X_train_{target_col}_balanced.csv", index=False)
    y_bal.to_csv(output_dir / f"y_train_{target_col}_balanced.csv", index=False)

    print(f"  {target_col:<18}: {len(X_train):,} -> {len(X_bal):,} rows "
          f"(pos={n_pos_final:,}, neg={n_neg_final:,}, neg:pos = {spw_final}:1, "
          f"{X_bal.shape[1]} features)")
    print(f"    Saved: X_train_{target_col}_balanced.csv, y_train_{target_col}_balanced.csv")


def run_time_block_undersampling(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    dates_train: pd.Series,
    output_dir: Path,
) -> None:
    _header("STEP 18 -- Time-Block Undersampling (cloudburst_flag, landslide_risk)")
    for col in ["cloudburst_flag", "landslide_risk"]:
        if col in y_train.columns:
            time_block_undersample(X_train, y_train, dates_train, col, output_dir)


# ==============================================================================
#  STEP 19 -- HYPERPARAMETER RECOMMENDATIONS  (data-driven, not hardcoded)
# ==============================================================================

def save_hyperparam_recommendations(weights_summary: dict, output_dir: Path) -> None:
    _header("STEP 19 -- Hyperparameter Recommendations")

    # Derive num_class from the ACTUAL classes seen in train, not a hardcoded 6.
    # If a rare class (e.g. class 5 "Extreme") never occurs in train, XGBoost
    # must still be told the true number of classes or label alignment breaks.
    observed_classes = sorted(int(c) for c in weights_summary["rain_intensity_class"]["class_weight"].keys())
    num_class = max(observed_classes) + 1  # classes are 0-indexed (0..5)
    if len(observed_classes) != num_class:
        print(f"  WARNING: classes observed in train = {observed_classes} "
              f"-- some intensity classes never occurred in this train split.")
    print(f"  num_class (derived from data) = {num_class}")

    recs = {
        "task1_regression_imd_rainfall_mm": {
            "model": "XGBRegressor",
            "target_options": {
                "raw_mm": "imd_rainfall_mm -- train/evaluate directly in mm",
                "log1p_mm": "imd_rainfall_mm_log1p -- train on this, then "
                            "np.expm1(pred) before computing MAE/RMSE in mm. "
                            "Usually a better-conditioned loss for this "
                            "heavily right-skewed target.",
            },
            "search_space": {
                "n_estimators": [300, 500, 800, 1200],
                "max_depth": [3, 4, 5, 6, 8],
                "learning_rate": [0.01, 0.03, 0.05, 0.1],
                "subsample": [0.6, 0.8, 1.0],
                "colsample_bytree": [0.6, 0.8, 1.0],
                "min_child_weight": [1, 3, 5, 7],
                "reg_alpha": [0, 0.1, 1.0],
                "reg_lambda": [1.0, 2.0, 5.0],
            },
            "metric": "RMSE / MAE / R2 (computed in mm, after expm1 if log1p target used)",
            "cv": "temporal_cv_folds.csv (blocked, expanding window)",
        },
        "task2_classification_rain_intensity_class": {
            "model": "XGBClassifier",
            "objective": "multi:softprob",
            "num_class": num_class,
            "sample_weight": "sample_weights_train.csv -> sw_rain_intensity_class",
            "class_weight": weights_summary["rain_intensity_class"]["class_weight"],
            "search_space": {
                "n_estimators": [300, 500, 800],
                "max_depth": [4, 5, 6, 8],
                "learning_rate": [0.01, 0.03, 0.05, 0.1],
                "subsample": [0.6, 0.8, 1.0],
                "colsample_bytree": [0.6, 0.8, 1.0],
            },
            "metric": "F1-macro",
            "cv": "temporal_cv_folds.csv",
        },
        "task3_cloudburst_flag": {
            "model": "XGBClassifier",
            "objective": "binary:logistic",
            "scale_pos_weight_full_train": weights_summary["cloudburst_flag"]["scale_pos_weight"],
            "balanced_dataset": "X_train_cloudburst_flag_balanced.csv / y_train_cloudburst_flag_balanced.csv",
            "note": "Train on the time-block-balanced set with a SMALLER scale_pos_weight "
                    "(re-derived from the balanced set's own pos/neg counts, printed in the "
                    "Step 18 log) rather than the raw full-train value above.",
            "search_space": {
                "n_estimators": [300, 500, 800],
                "max_depth": [3, 4, 5, 6],
                "learning_rate": [0.01, 0.03, 0.05, 0.1],
                "subsample": [0.6, 0.8, 1.0],
                "min_child_weight": [1, 3, 5],
            },
            "metric": "F1 / AUC-PR (never accuracy on a rare-event task)",
            "cv": "temporal_cv_folds.csv (use temporal_cv_fold_weights.csv for per-fold scale_pos_weight)",
        },
        "task4_landslide_risk": {
            "model": "XGBClassifier",
            "objective": "binary:logistic",
            "scale_pos_weight_full_train": weights_summary["landslide_risk"]["scale_pos_weight"],
            "balanced_dataset": "X_train_landslide_risk_balanced.csv / y_train_landslide_risk_balanced.csv",
            "search_space": {
                "n_estimators": [300, 500, 800],
                "max_depth": [3, 4, 5, 6],
                "learning_rate": [0.01, 0.03, 0.05, 0.1],
                "subsample": [0.6, 0.8, 1.0],
                "min_child_weight": [1, 3, 5],
            },
            "metric": "F1 / AUC-PR (never accuracy on a rare-event task)",
            "cv": "temporal_cv_folds.csv",
        },
    }

    with open(output_dir / "hyperparam_recommendations.json", "w") as f:
        json.dump(recs, f, indent=2)
    print("  Saved: hyperparam_recommendations.json")


# ==============================================================================
#  STEP 20 -- SINGLE MERGED TRAINING FILE
#  (X_train + y_train + sample weights + temporal CV fold, one row per hour)
# ==============================================================================

def build_master_training_file(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    dates_train: pd.Series,
    output_dir: Path,
) -> pd.DataFrame:
    """
    One CSV with everything needed to train Tasks 1 & 2 (regression +
    intensity classification) in a single read:
      datetime | <35 features> | <5 targets incl. log1p> | sw_rain_intensity_class |
      sw_cloudburst_flag | sw_landslide_risk | cv_fold

    This does NOT include the time-block-undersampled rows for Tasks 3/4
    (cloudburst_flag, landslide_risk) -- those are a different, shorter set
    of rows by design (whole negative blocks removed) and can't share a row
    count with the full X_train, so they stay in their own
    X_train_<target>_balanced.csv / y_train_<target>_balanced.csv files.
    For Tasks 3/4, load those two files instead of this one.
    """
    _header("STEP 20 -- Build Single Merged Training File")

    sw = pd.read_csv(output_dir / "sample_weights_train.csv")
    cv = pd.read_csv(output_dir / "temporal_cv_folds.csv")

    master = pd.concat(
        [dates_train.reset_index(drop=True).rename("datetime"),
         X_train.reset_index(drop=True),
         y_train.reset_index(drop=True),
         sw.reset_index(drop=True),
         cv["fold"].rename("cv_fold").reset_index(drop=True)],
        axis=1,
    )

    out_path = output_dir / "train_ready_master.csv"
    master.to_csv(out_path, index=False)
    sz = out_path.stat().st_size / 1e6
    print(f"  train_ready_master.csv  {len(master):,} rows x {master.shape[1]} cols  ({sz:.1f} MB)")
    print(f"  Columns: datetime | {X_train.shape[1]} features | {y_train.shape[1]} targets | "
          f"3 sample-weight cols | cv_fold")
    print(f"  Use this ONE file for Task 1 (regression) and Task 2 (intensity class).")
    print(f"  For Task 3/4 (cloudburst_flag, landslide_risk), use the *_balanced.csv files instead.")
    return master


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
    _header("STEP 15 -- Save Core Outputs (CSV only)")
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
    L.append("  REGRESSION TARGET SKEW -- imd_rainfall_mm vs imd_rainfall_mm_log1p")
    L.append(f"{'-'*65}")
    for label, y in [("Train", y_train), ("Val", y_val), ("Test", y_test)]:
        raw_skew = y["imd_rainfall_mm"].skew()
        log_skew = y["imd_rainfall_mm_log1p"].skew()
        L.append(f"  {label:<6}: raw skew={raw_skew:.2f}   log1p skew={log_skew:.2f}")

    L.append(f"\n{'-'*65}")
    L.append("  FEATURE COLUMNS IN X (no target leakage)")
    L.append(f"{'-'*65}")
    new_feats = {"temp_dewpoint_spread","wind_gust_ratio","precip_acceleration",
                 "humidity_cape_interact","rolling_ratio_3_24"}
    for i, col in enumerate(X_train.columns, 1):
        tag = "  <-- engineered" if col in new_feats else ""
        L.append(f"  {i:>3}. {col}{tag}")

    L.append(f"\n{'-'*65}")
    L.append("  IMBALANCE HANDLING (new)")
    L.append(f"{'-'*65}")
    L.append("""
  1. Class weighting        -- class_weights.json + sample_weights_train.csv
                                (balanced weights for rain_intensity_class,
                                data-driven scale_pos_weight for the two
                                binary rare-event tasks)
  2. Weighted temporal CV   -- temporal_cv_folds.csv (blocked, expanding
                                window, never shuffled) + per-fold
                                scale_pos_weight in temporal_cv_fold_weights.csv
  3. Time-block undersampling -- X_train_<target>_balanced.csv /
                                y_train_<target>_balanced.csv for
                                cloudburst_flag and landslide_risk (whole
                                negative-only time blocks dropped, event
                                blocks always kept intact)
  4. hyperparam_recommendations.json -- data-driven search spaces + weights
                                for all 4 tasks, ready for RandomizedSearchCV
                                / Optuna using the temporal CV folds above
  5. Log1p target transform -- imd_rainfall_mm_log1p alongside raw mm, for
                                a less skewed Task 1 regression target
""")

    L.append(f"{'-'*65}")
    L.append("  HOW TO USE IN TRAINING")
    L.append(f"{'-'*65}")
    L.append("""
  import pandas as pd
  import numpy as np
  X_train = pd.read_csv("ml_ready/X_train.csv")
  X_val   = pd.read_csv("ml_ready/X_val.csv")
  X_test  = pd.read_csv("ml_ready/X_test.csv")
  y_train = pd.read_csv("ml_ready/y_train.csv")
  y_val   = pd.read_csv("ml_ready/y_val.csv")
  y_test  = pd.read_csv("ml_ready/y_test.csv")
  sw      = pd.read_csv("ml_ready/sample_weights_train.csv")

  Task 1 -- Regression (two target options)
    # Option A: raw mm
    y = y_train["imd_rainfall_mm"]
    # Option B: log1p mm (usually better-conditioned for this skew)
    y = y_train["imd_rainfall_mm_log1p"]
    ... model.fit(X_train, y) ...
    preds_mm = np.expm1(model.predict(X_val))   # ONLY if trained on log1p
    XGBRegressor()  |  metrics: MAE, RMSE, R2 (always computed in mm)
    tune with temporal_cv_folds.csv (see train_xgboost_tuned.py)

  Task 2 -- Intensity Classification (0-5)
    y = y_train["rain_intensity_class"]
    XGBClassifier(objective="multi:softprob", num_class=6)
    .fit(X_train, y, sample_weight=sw["sw_rain_intensity_class"])
    metric: F1-macro

  Task 3 -- Cloudburst Detection (rare event)
    X = pd.read_csv("ml_ready/X_train_cloudburst_flag_balanced.csv")
    y = pd.read_csv("ml_ready/y_train_cloudburst_flag_balanced.csv")["cloudburst_flag"]
    XGBClassifier(scale_pos_weight=<see class_weights.json, recomputed on
                  the BALANCED set -- printed in Step 18 log>)
    metric: F1, AUC-PR

  Task 4 -- Landslide Risk (rare event)
    same pattern as Task 3, with *_landslide_risk_balanced.csv

  DO NOT use accuracy for Tasks 3 & 4 -- imbalanced datasets.
  Use: F1, Precision-Recall AUC, ROC-AUC

  See train_xgboost_tuned.py for a full RandomizedSearchCV example wired
  up to temporal_cv_folds.csv + sample_weights_train.csv.
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
    df = parse_sort(df)            # Step 3 (now with robust datetime detection)
    df = drop_bad(df)              # Step 4
    df = drop_missing_target(df)   # Step 4B: drop rows with no rainfall reading (NEW)
    df = fix_intensity_class(df)   # Step 5
    df = add_log_target(df)        # Step 5B: log1p regression target (NEW)
    df = fix_cloudburst(df)        # Step 6
    df = impute_cape(df)           # Step 7
    df = derive_missing_met_vars(df)  # Step 7B: physically derive dewpoint/wind u,v (NEW)
    df = fix_lag_nans(df)          # Step 8
    df = add_humidity_trend(df)    # Step 8B: humidity trend feature (NEW)
    df = engineer_features(df)     # Step 9: +5 accuracy features
    df = detect_outliers(df, output_dir)  # Step 9B: Isolation Forest (NEW, flag only)
    df = add_spatial_features(df)  # Step 9C: spatial/terrain features (NEW)
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

    # ---- Imbalance handling & tuning prep (new) ----
    weights_summary = compute_weights(y_train, output_dir)                 # Step 16
    dates_train = train_sc["datetime"].reset_index(drop=True)
    make_temporal_cv_folds(dates_train, y_train, output_dir)               # Step 17
    run_time_block_undersampling(X_train, y_train, dates_train, output_dir)  # Step 18
    save_hyperparam_recommendations(weights_summary, output_dir)           # Step 19
    build_master_training_file(X_train, y_train, dates_train, output_dir)  # Step 20

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
    print(f"\n  Class weights, temporal CV folds, time-block-balanced sets,")
    print(f"  log1p regression target, and hyperparameter search spaces are")
    print(f"  ready in the output dir. Ready for XGBoost model training --")
    print(f"  see train_xgboost_tuned.py")


if __name__ == "__main__":
    main()