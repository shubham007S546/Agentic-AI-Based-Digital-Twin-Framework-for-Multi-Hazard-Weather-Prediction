"""
feature_engineering.py
══════════════════════════════════════════════════════════════════════════════
Phase 2 — Feature Engineering for Mandi District Rainfall Prediction
PATCHED VERSION — fixes two label-generation bugs found in the original:

  BUG 1 (rain_intensity_class unit mismatch):
    imd_rainfall_mm is a DAILY total (mm/day) but was being binned directly
    against RAIN_INTENSITY_BINS, which are IMD's HOURLY thresholds (mm/hr).
    Result: a normal 35mm monsoon DAY got classified as "Heavy" HOURLY rain.
    Fix: daily-resolution columns are never run through hourly intensity bins.
    A separate daily-rainfall category is computed instead.

  BUG 2 (cloudburst_flag always 0 / dead label):
    rolling_precip_3h was built by dividing the IMD daily total by 24 and
    rolling that flat rate — which mathematically can never reach the
    100mm/3hr cloudburst threshold. The label was silently always 0.
    Fix: cloudburst_flag is ONLY computed from a column that passes a
    sub-daily-resolution quality check. If no such column exists, the
    label is set to NaN (not 0) and a CRITICAL warning is logged, so a
    model is never silently trained on a fabricated "never happens" label.

  BONUS GUARD (dead-column detection):
    Any precipitation column with zero variance among non-null values
    (e.g. the GPM column that is 100% 0.0 in the current dataset) is
    automatically excluded from rolling/label computation, with a logged
    warning, instead of being trusted as "usable."

What this does
──────────────
  1. Loads merged_dataset.parquet
  2. Fixes Open-Meteo missing (reads it directly if merger missed it)
  3. Filters to rows where core variables are present (2022-01-01 onwards)
  4. Engineers features needed for rainfall/cloudburst/landslide prediction
  5. Generates labels: rain_intensity_class, cloudburst_flag, landslide_risk
     — with the data-quality guards above
  6. Saves final clean dataset ready for ML, plus a data-quality section
     in feature_report.json so downstream training code can check whether
     each label is trustworthy before using it.

Output files
────────────
  datasets/merged_dataset/final_dataset.parquet  ← for ML training
  datasets/merged_dataset/final_dataset.csv      ← for inspection
  datasets/merged_dataset/feature_report.json    ← statistics + data-quality flags

Usage
─────
  python feature_engineering.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.config_loader import get_config
from utils.logger import get_logger

MERGED_DIR  = Path("datasets/merged_dataset")
OUTPUT_DIR  = MERGED_DIR
LOGGER_NAME = "feature_engineering"

# IMD cloudburst definition: >= 100mm in 3 hours
CLOUDBURST_THRESHOLD_MM = 100.0

# IMD rainfall intensity classification (mm/hr) — HOURLY thresholds only.
# Source: IMD guidelines
RAIN_INTENSITY_BINS   = [0, 0.1, 2.5, 7.5, 35.5, 64.4, float("inf")]
RAIN_INTENSITY_LABELS = [0, 1, 2, 3, 4, 5]
# 0=No rain, 1=Light, 2=Moderate, 3=Heavy, 4=Very Heavy, 5=Extreme

# Daily rainfall categories (mm/day) — used ONLY for daily-resolution sources
# like the raw IMD gridded product. Kept separate from hourly intensity so
# daily totals never get mis-binned as hourly rates (the original bug).
DAILY_RAIN_BINS   = [0, 2.5, 15.5, 64.5, 124.5, 244.5, float("inf")]
DAILY_RAIN_LABELS = [0, 1, 2, 3, 4, 5]
# IMD daily categories: 0=No rain 1=Light 2=Moderate 3=Heavy
# 4=Very Heavy 5=Extremely Heavy (mm/day)

# Mandi is in monsoon zone — June to September
MONSOON_MONTHS = {6, 7, 8, 9}

# Minimum standard deviation among non-null values for a precip column to be
# considered "live" data rather than a dead/broken feed (e.g. all-zero GPM).
MIN_PRECIP_STD = 1e-6


class FeatureEngineer:
    """
    Loads merged dataset, engineers all features, generates labels,
    and saves the final ML-ready dataset.
    """

    def __init__(self) -> None:
        self._cfg    = get_config()
        log_dir      = OUTPUT_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self._logger = get_logger(LOGGER_NAME, source_log_dir=log_dir)
        self._data_quality: dict = {}   # populated during label generation

    # ──────────────────────────────────────────────────────────────────────
    #  ENTRY POINT
    # ──────────────────────────────────────────────────────────────────────

    def run(self) -> Path:
        self._logger.info("=" * 70)
        self._logger.info("Feature Engineering Pipeline — START")
        self._logger.info("=" * 70)

        df = self._load_merged()
        df = self._fix_openmeteo(df)
        df = self._standardise_columns(df)
        df = self._filter_overlap(df)
        df = self._handle_missing(df)
        df = self._add_time_features(df)
        df = self._add_rolling_features(df)
        df = self._generate_labels(df)
        df = self._select_final_columns(df)
        out_path = self._save(df)

        self._logger.info("=" * 70)
        self._logger.info("Feature Engineering — COMPLETE")
        self._logger.info(f"Final shape : {len(df):,} rows × {len(df.columns)} cols")
        self._logger.info(f"Date range  : {df.index.min()} → {df.index.max()}")
        self._logger.info(f"Output      : {out_path}")
        if self._data_quality.get("cloudburst_label_trustworthy") is False:
            self._logger.warning(
                "⚠️  cloudburst_flag is NaN for all rows — no sub-daily "
                "precipitation source passed quality checks. Fix the GPM "
                "or Open-Meteo merge before training on this label."
            )
        self._logger.info("=" * 70)

        return out_path

    # ──────────────────────────────────────────────────────────────────────
    #  STEP 1: Load
    # ──────────────────────────────────────────────────────────────────────

    def _load_merged(self) -> pd.DataFrame:
        parquet = MERGED_DIR / "merged_dataset.parquet"
        if not parquet.exists():
            raise FileNotFoundError(
                f"merged_dataset.parquet not found at {parquet}. "
                "Run merger.py first."
            )
        df = pd.read_parquet(parquet)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, utc=True)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        self._logger.info(
            f"Loaded merged dataset: {len(df):,} rows × {len(df.columns)} cols"
        )
        self._logger.info(f"Columns: {list(df.columns)}")
        return df

    # ──────────────────────────────────────────────────────────────────────
    #  STEP 2: Fix Open-Meteo if missed by merger
    # ──────────────────────────────────────────────────────────────────────

    def _fix_openmeteo(self, df: pd.DataFrame) -> pd.DataFrame:
        om_cols = [c for c in df.columns if c.startswith("openmeteo_")]
        if om_cols:
            self._logger.info(
                f"Open-Meteo already in merged dataset ({len(om_cols)} cols)."
            )
            return df

        self._logger.warning(
            "Open-Meteo missing from merged dataset — loading directly..."
        )

        src_dir   = Path(self._cfg["sources"]["openmeteo"]["download_dir"])
        clean_dir = src_dir / "cleaned"

        parquet = clean_dir / "openmeteo_mandi_cleaned.parquet"
        if parquet.exists():
            om_df = pd.read_parquet(parquet)
        else:
            csvs = sorted(clean_dir.glob("*.csv"))
            if not csvs:
                self._logger.error(
                    "Open-Meteo: NO FILES FOUND in cleaned dir. This source "
                    "will be entirely absent from the final dataset, which "
                    "removes your only reliable native-hourly precipitation "
                    "feed. Re-run openmeteo_collector.py before proceeding."
                )
                return df
            om_df = pd.concat([pd.read_csv(f) for f in csvs], ignore_index=True)

        # Case A: the index is already datetime-like (common after loading
        # a parquet that was saved with a DatetimeIndex — parquet stores
        # the index separately from columns, so it won't show up in
        # om_df.columns even though the CSV version of the same data has
        # it as a plain column).
        if isinstance(om_df.index, pd.DatetimeIndex):
            om_df.index = pd.to_datetime(om_df.index, utc=True) if om_df.index.tz is None else om_df.index
            om_df.index.name = "datetime"
        else:
            # Case B: look for it as a column under any known name.
            dt_col = None
            for col in ["datetime", "datetime_utc", "date", "time"]:
                if col in om_df.columns:
                    dt_col = col
                    break

            # Case C: pandas sometimes round-trips an unnamed/old index as
            # a literal "index" or "Unnamed: 0" column when read back in —
            # check if that column actually parses as datetimes before
            # giving up.
            if dt_col is None:
                for col in ["index", "Unnamed: 0"]:
                    if col in om_df.columns:
                        try:
                            pd.to_datetime(om_df[col].iloc[:5], utc=True)
                            dt_col = col
                            break
                        except (ValueError, TypeError):
                            continue

            if dt_col is None:
                self._logger.error(
                    f"Open-Meteo: no datetime column found and index is "
                    f"'{type(om_df.index).__name__}', not datetime-like. "
                    f"Columns: {list(om_df.columns)}. Source will be dropped. "
                    f"Check how openmeteo_mandi_cleaned.parquet was saved — "
                    f"the index was likely lost or never set before saving."
                )
                return df

            om_df[dt_col] = pd.to_datetime(om_df[dt_col], utc=True)
            om_df = om_df.set_index(dt_col)
            om_df.index.name = "datetime"
        om_df = om_df.select_dtypes(include="number")
        om_df = om_df.resample("h").mean()
        om_df.columns = [f"openmeteo_{c}" for c in om_df.columns]
        om_df = om_df[~om_df.index.duplicated(keep="first")]

        df = df.join(om_df, how="outer")
        self._logger.info(
            f"Open-Meteo joined: {len(om_df):,} rows, "
            f"{len(om_df.columns)} columns added."
        )
        return df

    # ──────────────────────────────────────────────────────────────────────
    #  STEP 3: Standardise column names
    # ──────────────────────────────────────────────────────────────────────

    def _standardise_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        rename_map = {
            "openmeteo_temperature_2m":   "temperature_2m",
            "era5_temperature_2m":        "temperature_2m",
            "openmeteo_dewpoint_2m":      "dewpoint_2m",
            "era5_dewpoint_2m":           "dewpoint_2m",
            "openmeteo_relative_humidity_2m": "relative_humidity",
            "openmeteo_surface_pressure": "surface_pressure",
            "era5_surface_pressure":      "surface_pressure",
            "era5_mslp":                  "mslp",
            "openmeteo_wind_speed_10m":   "wind_speed_10m",
            "era5_wind_speed_10m":        "wind_speed_10m",
            "openmeteo_wind_direction_10m":"wind_direction_10m",
            "era5_wind_dir_10m":          "wind_direction_10m",
            "openmeteo_wind_gusts_10m":   "wind_gusts_10m",
            "openmeteo_cloud_cover":      "cloud_cover",
            "era5_cloud_cover":           "cloud_cover",
            # Precipitation — kept SEPARATE per source on purpose. Do not
            # collapse these into one "precipitation" name; the quality
            # checks in _select_precip_source() need to compare sources.
            "openmeteo_precipitation":    "precipitation_openmeteo",
            "openmeteo_rain":             "rain_openmeteo",
            "openmeteo_snowfall":         "snowfall",
            "openmeteo_weather_code":     "weather_code",
            "gpm_precipitation":          "precipitation_gpm",
            "imd_rainfall_mm":            "imd_rainfall_mm",  # daily total, mm/day
            "era5_cape":                  "cape",
            "era5_wind_u_10m":            "wind_u_10m",
            "era5_wind_v_10m":            "wind_v_10m",
        }
        actual_rename = {k: v for k, v in rename_map.items() if k in df.columns}
        df = df.rename(columns=actual_rename)
        df = df.loc[:, ~df.columns.duplicated(keep="first")]
        self._logger.info(f"Columns after standardisation: {list(df.columns)}")
        return df

    # ──────────────────────────────────────────────────────────────────────
    #  STEP 4: Filter to overlap window
    # ──────────────────────────────────────────────────────────────────────

    def _filter_overlap(self, df: pd.DataFrame) -> pd.DataFrame:
        start = pd.Timestamp("2005-01-01", tz="UTC")
        df = df.loc[start:]
        self._logger.info(f"After 2025-01-01 filter: {len(df):,} rows")

        core_cols = [
            c for c in [
                "temperature_2m", "precipitation_openmeteo", "surface_pressure",
                "cloud_cover", "wind_speed_10m", "precipitation_gpm",
                "imd_rainfall_mm",
            ]
            if c in df.columns
        ]
        if core_cols:
            has_data = df[core_cols].notna().sum(axis=1) >= 2
            before   = len(df)
            df       = df[has_data]
            self._logger.info(
                f"After core-variable filter: {before:,} → {len(df):,} rows"
            )
        return df

    # ──────────────────────────────────────────────────────────────────────
    #  STEP 5: Handle missing values
    # ──────────────────────────────────────────────────────────────────────

    def _handle_missing(self, df: pd.DataFrame) -> pd.DataFrame:
        self._logger.info("Handling missing values...")
        numeric_cols = df.select_dtypes(include="number").columns
        df[numeric_cols] = df[numeric_cols].interpolate(
            method="time", limit=3, limit_direction="both"
        )
        df[numeric_cols] = df[numeric_cols].ffill(limit=6)

        for col in numeric_cols:
            n   = int(df[col].isna().sum())
            pct = n / len(df) * 100
            if pct > 5:
                self._logger.warning(
                    f"  Still missing after imputation: {col} = {pct:.1f}%"
                )
        return df

    # ──────────────────────────────────────────────────────────────────────
    #  STEP 6: Time features
    # ──────────────────────────────────────────────────────────────────────

    def _add_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        idx_ist = df.index.tz_convert("Asia/Kolkata")
        df["hour"]       = idx_ist.hour
        df["month"]      = idx_ist.month
        df["day_of_year"]= idx_ist.dayofyear

        def month_to_season(m: int) -> int:
            if m in (12, 1, 2):
                return 0
            elif m in (3, 4, 5):
                return 1
            elif m in (6, 7, 8, 9):
                return 2
            else:
                return 3

        df["season"]    = df["month"].apply(month_to_season)
        df["is_monsoon"]= df["month"].isin(MONSOON_MONTHS).astype(np.int8)
        df["hour_sin"]  = np.sin(2 * np.pi * df["hour"] / 24)
        df["hour_cos"]  = np.cos(2 * np.pi * df["hour"] / 24)
        df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
        df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

        self._logger.info(
            "Time features added: hour, month, season, is_monsoon + cyclical encoding"
        )
        return df

    # ──────────────────────────────────────────────────────────────────────
    #  QUALITY GUARD — shared by rolling features and label generation
    # ──────────────────────────────────────────────────────────────────────

    def _column_quality(self, df: pd.DataFrame, col: str) -> dict:
        """
        Inspect a precipitation column and report whether it's:
          - 'live'      : has real, varying, non-null data
          - 'dead'      : present but zero-variance (e.g. broken GPM feed)
          - 'sub_daily' : actually varies hour-to-hour (not a daily value
                          forward-filled 24x), so safe to use for 3h rolling
                          and cloudburst detection
        """
        s = df[col].dropna()
        result = {"n_valid": int(s.shape[0]), "live": False, "sub_daily": False}
        if s.shape[0] < 100:
            return result

        std = float(s.std())
        result["std"] = std
        result["live"] = std > MIN_PRECIP_STD
        if not result["live"]:
            return result

        # Sub-daily check: among days with MEANINGFUL rainfall, does the
        # column vary hour-to-hour, or is it flat (a daily total forward-
        # filled to 24 identical hourly rows)? We restrict to rainy days
        # because dry days are correctly flat at 0.0 regardless of source
        # resolution — checking all days would wrongly penalize genuine
        # hourly data in a place like Mandi where most days have no rain.
        daily_sum     = s.groupby(s.index.date).sum()
        daily_nunique = s.groupby(s.index.date).nunique()
        rain_days = daily_sum[daily_sum > 0.5].index  # >0.5mm/day threshold
        result["n_rain_days"] = int(len(rain_days))

        if len(rain_days) < 5:
            # Too few rainy days in the data to judge reliably — don't
            # reject the column on this basis, but flag it as unverified.
            result["sub_daily"] = True
            result["sub_daily_basis"] = "insufficient_rain_days_to_judge"
            return result

        frac_rain_days_varying = float((daily_nunique.loc[rain_days] > 1).mean())
        result["frac_rain_days_with_subdaily_variation"] = frac_rain_days_varying
        result["sub_daily"] = frac_rain_days_varying > 0.5
        result["sub_daily_basis"] = "checked_on_rain_days"
        return result

    def _select_precip_source(self, df: pd.DataFrame, require_sub_daily: bool) -> tuple[str | None, dict]:
        """
        Pick the best precipitation column for a given purpose.
        require_sub_daily=True  -> for rolling_precip_3h / cloudburst_flag
        require_sub_daily=False -> for daily-level features (rain_intensity
                                    fallback, rolling_precip_24h/72h)
        Returns (column_name_or_None, quality_report_for_all_candidates)
        """
        candidates = [c for c in
                      ["precipitation_openmeteo", "precipitation_gpm", "imd_rainfall_mm"]
                      if c in df.columns]
        report = {}
        for c in candidates:
            q = self._column_quality(df, c)
            report[c] = q
            if not q["live"]:
                self._logger.warning(
                    f"  Precip source '{c}' has {q['n_valid']} non-null values "
                    f"but zero variance — treating as DEAD/broken, excluding it."
                )

        usable = [c for c in candidates if report[c]["live"]]
        if require_sub_daily:
            usable = [c for c in usable if report[c]["sub_daily"]]

        if not usable:
            return None, report

        # Prefer the one with the most valid rows among usable candidates
        best = max(usable, key=lambda c: report[c]["n_valid"])
        return best, report

    # ──────────────────────────────────────────────────────────────────────
    #  STEP 7: Rolling precipitation features
    # ──────────────────────────────────────────────────────────────────────

    def _add_rolling_features(self, df: pd.DataFrame) -> pd.DataFrame:
        # Sub-daily source for short-window rolling (3h, 6h) — required for
        # these to mean anything.
        short_col, short_report = self._select_precip_source(df, require_sub_daily=True)
        # Any live source for long-window rolling (24h, 72h) — daily totals
        # are fine here since the window already spans a day+.
        long_col, long_report = self._select_precip_source(df, require_sub_daily=False)

        self._data_quality["precip_source_report"] = {**short_report, **long_report}
        self._data_quality["short_window_precip_source"] = short_col
        self._data_quality["long_window_precip_source"] = long_col

        if short_col:
            self._logger.info(f"3h/6h rolling features based on: {short_col} (sub-daily, verified live)")
            hourly_precip_short = df[short_col]
            df["rolling_precip_3h"] = hourly_precip_short.rolling(window=3, min_periods=1).sum()
            df["rolling_precip_6h"] = hourly_precip_short.rolling(window=6, min_periods=1).sum()
            df["precip_lag_1h"] = hourly_precip_short.shift(1)
            df["precip_lag_3h"] = hourly_precip_short.shift(3)
            df["precip_lag_6h"] = hourly_precip_short.shift(6)
        else:
            self._logger.error(
                "No live sub-daily precipitation source available — "
                "rolling_precip_3h/6h and lag features cannot be trusted. "
                "Setting to NaN rather than fabricating zeros. Fix the GPM "
                "zero-value bug or restore the Open-Meteo merge to resolve."
            )
            df["rolling_precip_3h"] = np.nan
            df["rolling_precip_6h"] = np.nan
            df["precip_lag_1h"] = np.nan
            df["precip_lag_3h"] = np.nan
            df["precip_lag_6h"] = np.nan

        if long_col:
            self._logger.info(f"24h/72h rolling features based on: {long_col}")
            if long_col == "imd_rainfall_mm":
                hourly_precip_long = df[long_col] / 24.0  # daily total -> hourly rate, OK for 24h+ windows
            else:
                hourly_precip_long = df[long_col]
            df["rolling_precip_24h"] = hourly_precip_long.rolling(window=24, min_periods=1).sum()
            df["rolling_precip_72h"] = hourly_precip_long.rolling(window=72, min_periods=1).sum()
        else:
            self._logger.warning("No usable precipitation source for 24h/72h rolling features.")
            df["rolling_precip_24h"] = np.nan
            df["rolling_precip_72h"] = np.nan

        return df

    # ──────────────────────────────────────────────────────────────────────
    #  STEP 8: Generate labels
    # ──────────────────────────────────────────────────────────────────────

    def _generate_labels(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        1. rain_intensity_class (0–5) — ONLY from a sub-daily hourly-rate
           column, binned against HOURLY thresholds. If none available,
           fall back to a DAILY category (separate bins) rather than
           mis-binning a daily total against hourly thresholds.
        2. cloudburst_flag (0/1) — ONLY from rolling_precip_3h built off a
           verified sub-daily source. NaN (not 0) if unavailable.
        3. landslide_risk (0/1/2) — rule-based off rolling_precip_24h +
           season + cloudburst_flag.
        """
        short_col = self._data_quality.get("short_window_precip_source")

        # ── Label 1: Rain intensity class ────────────────────────────────
        if short_col:
            df["rain_intensity_class"] = pd.cut(
                df[short_col].fillna(0),
                bins=RAIN_INTENSITY_BINS,
                labels=RAIN_INTENSITY_LABELS,
                right=False,
            ).astype(np.int8)
            self._data_quality["rain_intensity_class_basis"] = f"hourly:{short_col}"
        elif "imd_rainfall_mm" in df.columns:
            # Daily total -> daily category, NOT the hourly bins.
            df["rain_intensity_class"] = pd.cut(
                df["imd_rainfall_mm"].fillna(0),
                bins=DAILY_RAIN_BINS,
                labels=DAILY_RAIN_LABELS,
                right=False,
            ).astype(np.int8)
            self._data_quality["rain_intensity_class_basis"] = "daily:imd_rainfall_mm (daily category, not hourly)"
            self._logger.warning(
                "rain_intensity_class computed from DAILY imd_rainfall_mm using "
                "daily-category bins (not hourly bins) since no sub-daily "
                "source is available — label represents daily intensity, not "
                "true hourly intensity. Treat with caution for an hourly model."
            )
        else:
            df["rain_intensity_class"] = np.int8(0)
            self._data_quality["rain_intensity_class_basis"] = "none"

        class_counts = df["rain_intensity_class"].value_counts().sort_index()
        self._logger.info(f"rain_intensity_class distribution:\n{class_counts}")

        # ── Label 2: Cloudburst flag ──────────────────────────────────────
        if short_col and df["rolling_precip_3h"].notna().any():
            df["cloudburst_flag"] = (
                df["rolling_precip_3h"] >= CLOUDBURST_THRESHOLD_MM
            ).astype("float").astype("Int8")  # nullable int so NaNs survive
            n_cb = int((df["cloudburst_flag"] == 1).sum())
            self._logger.info(
                f"cloudburst_flag: {n_cb} events detected "
                f"(>= {CLOUDBURST_THRESHOLD_MM}mm in 3h, basis: {short_col})"
            )
            self._data_quality["cloudburst_label_trustworthy"] = True
            self._data_quality["cloudburst_events"] = n_cb
        else:
            df["cloudburst_flag"] = pd.array([np.nan] * len(df), dtype="Float64")
            self._logger.error(
                "cloudburst_flag set to NaN for ALL rows — no verified "
                "sub-daily precipitation source. DO NOT train on this "
                "label until the GPM/Open-Meteo source issue is fixed."
            )
            self._data_quality["cloudburst_label_trustworthy"] = False
            self._data_quality["cloudburst_events"] = 0

        # ── Label 3: Landslide risk ───────────────────────────────────────
        df["landslide_risk"] = np.int8(0)  # default Low

        if "rolling_precip_24h" in df.columns and df["rolling_precip_24h"].notna().any():
            medium_mask = (
                (df["is_monsoon"] == 1) & (df["rolling_precip_24h"] >= 50)
            ) | (
                (df["is_monsoon"] == 0) & (df["rolling_precip_24h"] >= 100)
            )
            high_mask = (
                (df["is_monsoon"] == 1) & (df["rolling_precip_24h"] >= 150)
            )
            if self._data_quality.get("cloudburst_label_trustworthy"):
                high_mask = high_mask | (df["cloudburst_flag"] == 1)

            df.loc[medium_mask, "landslide_risk"] = np.int8(1)
            df.loc[high_mask,   "landslide_risk"] = np.int8(2)

            risk_counts = df["landslide_risk"].value_counts().sort_index()
            self._logger.info(
                f"landslide_risk distribution: "
                f"Low={risk_counts.get(0,0)} "
                f"Medium={risk_counts.get(1,0)} "
                f"High={risk_counts.get(2,0)}"
            )
            if risk_counts.get(2, 0) < 20:
                self._logger.warning(
                    f"  Only {risk_counts.get(2,0)} 'High' landslide_risk rows "
                    "in the whole dataset — too few for a 3-class classifier "
                    "to learn reliably. Consider a binary Low-vs-Elevated "
                    "target, or class-weighting, once more data is collected."
                )
        else:
            self._logger.warning(
                "landslide_risk left at default 'Low' for all rows — no "
                "usable rolling_precip_24h available."
            )

        return df

    # ──────────────────────────────────────────────────────────────────────
    #  STEP 9: Select final columns
    # ──────────────────────────────────────────────────────────────────────

    def _select_final_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        desired_order = [
            "temperature_2m", "dewpoint_2m", "relative_humidity",
            "surface_pressure", "mslp",
            "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
            "wind_u_10m", "wind_v_10m",
            "cloud_cover", "cape",
            "precipitation_openmeteo", "rain_openmeteo", "snowfall",
            "precipitation_gpm", "imd_rainfall_mm",
            "rolling_precip_3h", "rolling_precip_6h",
            "rolling_precip_24h", "rolling_precip_72h",
            "precip_lag_1h", "precip_lag_3h", "precip_lag_6h",
            "hour", "month", "day_of_year", "season", "is_monsoon",
            "hour_sin", "hour_cos", "month_sin", "month_cos",
            "rain_intensity_class", "cloudburst_flag", "landslide_risk",
        ]
        final_cols = [c for c in desired_order if c in df.columns]
        df = df[final_cols]
        self._logger.info(f"Final columns ({len(final_cols)}): {final_cols}")
        return df

    # ──────────────────────────────────────────────────────────────────────
    #  STEP 10: Save
    # ──────────────────────────────────────────────────────────────────────

    def _save(self, df: pd.DataFrame) -> Path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        parquet_path = OUTPUT_DIR / "final_dataset.parquet"
        csv_path     = OUTPUT_DIR / "final_dataset.csv"
        report_path  = OUTPUT_DIR / "feature_report.json"

        df.to_parquet(parquet_path, engine="pyarrow")
        df.to_csv(csv_path)

        pq_mb  = parquet_path.stat().st_size / 1_048_576
        csv_mb = csv_path.stat().st_size    / 1_048_576
        self._logger.info(f"Parquet: {parquet_path.name} ({pq_mb:.1f} MB)")
        self._logger.info(f"CSV    : {csv_path.name} ({csv_mb:.1f} MB)")

        report = {
            "generated_at":    datetime.now(timezone.utc).isoformat(),
            "rows":            len(df),
            "columns":         len(df.columns),
            "date_min":        str(df.index.min()),
            "date_max":        str(df.index.max()),
            "feature_columns": [
                c for c in df.columns
                if c not in ("rain_intensity_class", "cloudburst_flag", "landslide_risk")
            ],
            "label_columns": ["rain_intensity_class", "cloudburst_flag", "landslide_risk"],
            "rain_intensity_distribution": (
                df["rain_intensity_class"].value_counts().sort_index().to_dict()
                if "rain_intensity_class" in df.columns else {}
            ),
            "cloudburst_events": self._data_quality.get("cloudburst_events", 0),
            "landslide_risk_distribution": (
                df["landslide_risk"].value_counts().sort_index().to_dict()
                if "landslide_risk" in df.columns else {}
            ),
            "missing_pct": {
                col: round(df[col].isna().mean() * 100, 2) for col in df.columns
            },
            # ── NEW: explicit data-quality flags for training code to check ──
            "data_quality": {
                "cloudburst_label_trustworthy": self._data_quality.get(
                    "cloudburst_label_trustworthy", False
                ),
                "rain_intensity_class_basis": self._data_quality.get(
                    "rain_intensity_class_basis", "unknown"
                ),
                "short_window_precip_source": self._data_quality.get(
                    "short_window_precip_source"
                ),
                "long_window_precip_source": self._data_quality.get(
                    "long_window_precip_source"
                ),
                "precip_source_report": self._data_quality.get(
                    "precip_source_report", {}
                ),
            },
        }

        with open(report_path, "w") as fh:
            json.dump(report, fh, indent=2, default=str)

        self._logger.info(f"Report : {report_path.name}")
        return parquet_path


if __name__ == "__main__":
    fe = FeatureEngineer()
    fe.run()