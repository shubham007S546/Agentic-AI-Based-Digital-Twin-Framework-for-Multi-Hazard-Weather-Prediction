"""
feature_engineering.py
==============================================================================
Phase 2 -- Feature Engineering for Mandi, Kullu, and Chamba Weather Prediction
Production-grade pipeline with:
  1. Multi-district awareness (Mandi, Kullu, Chamba)
  2. No inter-district boundary leakage during rolling/lag computation
  3. Strict physical data validation and quality guards
  4. IMD rainfall intensity classification (mm/hr)
  5. IMD cloudburst detection (>= 100mm in 3h)
  6. Multi-hazard landslide risk calculation
  7. Pure ASCII logging (Windows cp1252 safe)

Output files:
  datasets/merged_dataset/final_dataset.parquet  (Master ML training set)
  datasets/merged_dataset/final_dataset.csv      (Master inspection CSV)
  datasets/merged_dataset/final_dataset_mandi.parquet / .csv
  datasets/merged_dataset/final_dataset_kullu.parquet / .csv
  datasets/merged_dataset/final_dataset_chamba.parquet / .csv
  datasets/merged_dataset/feature_report.json    (Data quality report)

Usage:
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

# IMD rainfall intensity classification (mm/hr) - HOURLY thresholds only.
RAIN_INTENSITY_BINS   = [0, 0.1, 2.5, 7.5, 35.5, 64.4, float("inf")]
RAIN_INTENSITY_LABELS = [0, 1, 2, 3, 4, 5]
# 0=No rain, 1=Light, 2=Moderate, 3=Heavy, 4=Very Heavy, 5=Extreme

# Daily rainfall categories (mm/day) - fallback for daily-resolution sources
DAILY_RAIN_BINS   = [0, 2.5, 15.5, 64.5, 124.5, 244.5, float("inf")]
DAILY_RAIN_LABELS = [0, 1, 2, 3, 4, 5]

# Himachal Pradesh monsoon zone - June to September
MONSOON_MONTHS = {6, 7, 8, 9}

# Minimum standard deviation among non-null values for a precip column
MIN_PRECIP_STD = 1e-6


class FeatureEngineer:
    """
    Loads merged dataset, engineers features per district, generates labels,
    and saves the final ML-ready datasets.
    """

    def __init__(self) -> None:
        self._cfg    = get_config()
        log_dir      = OUTPUT_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self._logger = get_logger(LOGGER_NAME, source_log_dir=log_dir)
        self._data_quality: dict = {}

    def run(self) -> Path:
        self._logger.info("=" * 70)
        self._logger.info("Feature Engineering Pipeline - START")
        self._logger.info("=" * 70)

        df_raw = self._load_merged()
        districts = df_raw["district"].unique().tolist() if "district" in df_raw.columns else [None]
        self._logger.info(f"Districts found for feature engineering: {districts}")

        processed_districts: dict[str, pd.DataFrame] = {}

        for d in districts:
            dist_label = d if d else "default"
            self._logger.info("-" * 50)
            self._logger.info(f"Processing district: {dist_label}")
            self._logger.info("-" * 50)

            if d is not None:
                d_df = df_raw[df_raw["district"] == d].copy()
            else:
                d_df = df_raw.copy()

            if "datetime" in d_df.columns and not isinstance(d_df.index, pd.DatetimeIndex):
                d_df["datetime"] = pd.to_datetime(d_df["datetime"], utc=True)
                d_df = d_df.set_index("datetime")
            elif isinstance(d_df.index, pd.DatetimeIndex):
                if d_df.index.tz is None:
                    d_df.index = d_df.index.tz_localize("UTC")
            d_df = d_df.sort_index()

            d_df = self._fix_openmeteo(d_df)
            d_df = self._standardise_columns(d_df)
            d_df = self._filter_overlap(d_df)
            d_df = self._handle_missing(d_df)
            d_df = self._add_time_features(d_df)
            d_df = self._add_rolling_features(d_df)
            d_df = self._generate_labels(d_df)
            d_df = self._select_final_columns(d_df)

            processed_districts[dist_label] = d_df

        out_path = self._save(processed_districts)

        self._logger.info("=" * 70)
        self._logger.info("Feature Engineering - COMPLETE")
        total_rows = sum(len(df) for df in processed_districts.values())
        first_df = list(processed_districts.values())[0]
        self._logger.info(f"Total shape : {total_rows:,} rows x {len(first_df.columns)} cols")
        self._logger.info(f"Output      : {out_path}")
        if self._data_quality.get("cloudburst_label_trustworthy") is False:
            self._logger.warning(
                "[WARN] cloudburst_flag is NaN for all rows - no sub-daily "
                "precipitation source passed quality checks."
            )
        self._logger.info("=" * 70)

        return out_path

    # ----------------------------------------------------------------------
    #  STEP 1: Load merged dataset
    # ----------------------------------------------------------------------

    def _load_merged(self) -> pd.DataFrame:
        parquet = MERGED_DIR / "merged_dataset.parquet"
        if not parquet.exists():
            raise FileNotFoundError(
                f"merged_dataset.parquet not found at {parquet}. "
                "Run merger.py first."
            )
        df = pd.read_parquet(parquet)
        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
            if not isinstance(df.index, pd.DatetimeIndex):
                df = df.set_index("datetime")
        elif not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, utc=True)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        self._logger.info(
            f"Loaded merged dataset: {len(df):,} rows x {len(df.columns)} cols"
        )
        self._logger.info(f"Columns: {list(df.columns)}")
        return df

    # ----------------------------------------------------------------------
    #  STEP 2: Fix Open-Meteo if missed
    # ----------------------------------------------------------------------

    def _fix_openmeteo(self, df: pd.DataFrame) -> pd.DataFrame:
        om_cols = [c for c in df.columns if c.startswith("openmeteo_")]
        if om_cols:
            self._logger.info(
                f"Open-Meteo already in merged dataset ({len(om_cols)} cols)."
            )
            return df

        self._logger.warning(
            "Open-Meteo missing from merged dataset - loading directly..."
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
                    "Open-Meteo: NO FILES FOUND in cleaned dir. Source absent."
                )
                return df
            om_df = pd.concat([pd.read_csv(f) for f in csvs], ignore_index=True)

        if isinstance(om_df.index, pd.DatetimeIndex):
            om_df.index = pd.to_datetime(om_df.index, utc=True) if om_df.index.tz is None else om_df.index
            om_df.index.name = "datetime"
        else:
            dt_col = None
            for col in ["datetime", "datetime_utc", "date", "time"]:
                if col in om_df.columns:
                    dt_col = col
                    break
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
                self._logger.error("Open-Meteo: no datetime column found.")
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

    # ----------------------------------------------------------------------
    #  STEP 3: Standardise column names
    # ----------------------------------------------------------------------

    def _standardise_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        rename_map = {
            "openmeteo_temperature_2m":       "temperature_2m",
            "era5_temperature_2m":            "temperature_2m",
            "openmeteo_dew_point_2m":         "dewpoint_2m",
            "openmeteo_dewpoint_2m":          "dewpoint_2m",
            "era5_dewpoint_2m":               "dewpoint_2m",
            "openmeteo_relative_humidity_2m": "relative_humidity",
            "openmeteo_surface_pressure":     "surface_pressure",
            "era5_surface_pressure":          "surface_pressure",
            "era5_mslp":                      "mslp",
            "openmeteo_wind_speed_10m":       "wind_speed_10m",
            "era5_wind_speed_10m":            "wind_speed_10m",
            "openmeteo_wind_direction_10m":   "wind_direction_10m",
            "era5_wind_dir_10m":              "wind_direction_10m",
            "openmeteo_wind_gusts_10m":       "wind_gusts_10m",
            "openmeteo_cloud_cover":          "cloud_cover",
            "era5_cloud_cover":               "cloud_cover",
            "openmeteo_precipitation":        "precipitation_openmeteo",
            "openmeteo_rain":                 "rain_openmeteo",
            "openmeteo_snowfall":             "snowfall",
            "openmeteo_weather_code":         "weather_code",
            "openmeteo_soil_temperature_0_to_7cm": "soil_temperature_0_to_7cm",
            "openmeteo_soil_moisture_0_to_7cm":    "soil_moisture_0_to_7cm",
            "gpm_precipitation":              "precipitation_gpm",
            "imd_rainfall_mm":                "imd_rainfall_mm",
            "era5_cape":                      "cape",
            "era5_wind_u_10m":                "wind_u_10m",
            "era5_wind_v_10m":                "wind_v_10m",
        }
        actual_rename = {k: v for k, v in rename_map.items() if k in df.columns}
        df = df.rename(columns=actual_rename)
        df = df.loc[:, ~df.columns.duplicated(keep="first")]
        self._logger.info(f"Columns after standardisation: {len(df.columns)} columns")
        return df

    # ----------------------------------------------------------------------
    #  STEP 4: Filter to overlap window
    # ----------------------------------------------------------------------

    def _filter_overlap(self, df: pd.DataFrame) -> pd.DataFrame:
        start = pd.Timestamp("2022-01-01", tz="UTC")
        df = df[df.index >= start]
        self._logger.info(f"After 2022-01-01 filter: {len(df):,} rows")

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
                f"After core-variable filter: {before:,} -> {len(df):,} rows"
            )
        return df

    # ----------------------------------------------------------------------
    #  STEP 5: Handle missing values
    # ----------------------------------------------------------------------

    def _handle_missing(self, df: pd.DataFrame) -> pd.DataFrame:
        self._logger.info("Handling missing values...")
        numeric_cols = df.select_dtypes(include="number").columns
        df[numeric_cols] = df[numeric_cols].interpolate(
            method="time", limit=3, limit_direction="both"
        )
        df[numeric_cols] = df[numeric_cols].ffill(limit=6)

        for col in numeric_cols:
            n   = int(df[col].isna().sum())
            pct = n / len(df) * 100 if len(df) > 0 else 0.0
            if pct > 5:
                self._logger.warning(
                    f"  Still missing after imputation: {col} = {pct:.1f}%"
                )
        return df

    # ----------------------------------------------------------------------
    #  STEP 6: Time features
    # ----------------------------------------------------------------------

    def _add_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        idx_ist = df.index.tz_convert("Asia/Kolkata")
        df["hour"]        = idx_ist.hour
        df["month"]       = idx_ist.month
        df["day_of_year"] = idx_ist.dayofyear
        df["week_of_year"]= idx_ist.isocalendar().week.astype(np.int8)
        df["day_of_week"] = idx_ist.dayofweek.astype(np.int8)
        df["is_weekend"]  = idx_ist.dayofweek.isin([5, 6]).astype(np.int8)

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
            "Time features added: hour, month, season, is_monsoon, week_of_year, day_of_week + cyclic"
        )
        return df

    # ----------------------------------------------------------------------
    #  QUALITY GUARD
    # ----------------------------------------------------------------------

    def _column_quality(self, df: pd.DataFrame, col: str) -> dict:
        s = df[col].dropna()
        result = {"n_valid": int(s.shape[0]), "live": False, "sub_daily": False}
        if s.shape[0] < 100:
            return result

        std = float(s.std())
        result["std"] = std
        result["live"] = std > MIN_PRECIP_STD
        if not result["live"]:
            return result

        daily_sum     = s.groupby(s.index.date).sum()
        daily_nunique = s.groupby(s.index.date).nunique()
        rain_days = daily_sum[daily_sum > 0.5].index
        result["n_rain_days"] = int(len(rain_days))

        if len(rain_days) < 5:
            result["sub_daily"] = True
            result["sub_daily_basis"] = "insufficient_rain_days_to_judge"
            return result

        frac_rain_days_varying = float((daily_nunique.loc[rain_days] > 1).mean())
        result["frac_rain_days_with_subdaily_variation"] = frac_rain_days_varying
        result["sub_daily"] = frac_rain_days_varying > 0.5
        result["sub_daily_basis"] = "checked_on_rain_days"
        return result

    def _select_precip_source(self, df: pd.DataFrame, require_sub_daily: bool) -> tuple[str | None, dict]:
        candidates = [c for c in
                      ["precipitation_openmeteo", "precipitation_gpm", "imd_rainfall_mm"]
                      if c in df.columns]
        report = {}
        for c in candidates:
            q = self._column_quality(df, c)
            report[c] = q
            if not q["live"]:
                self._logger.warning(
                    f"  Precip source '{c}' has {q['n_valid']} values but zero variance - excluding."
                )

        usable = [c for c in candidates if report[c]["live"]]
        if require_sub_daily:
            usable = [c for c in usable if report[c]["sub_daily"]]

        if not usable:
            return None, report

        best = max(usable, key=lambda c: report[c]["n_valid"])
        return best, report

    # ----------------------------------------------------------------------
    #  STEP 7: Rolling precipitation features
    # ----------------------------------------------------------------------

    def _add_rolling_features(self, df: pd.DataFrame) -> pd.DataFrame:
        short_col, short_report = self._select_precip_source(df, require_sub_daily=True)
        long_col, long_report = self._select_precip_source(df, require_sub_daily=False)

        self._data_quality["precip_source_report"] = {**short_report, **long_report}
        self._data_quality["short_window_precip_source"] = short_col
        self._data_quality["long_window_precip_source"] = long_col

        if short_col:
            self._logger.info(f"3h/6h rolling features based on: {short_col} (sub-daily, verified live)")
            hourly_precip_short = df[short_col]
            df["rolling_precip_3h"] = hourly_precip_short.rolling(window=3, min_periods=1).sum()
            df["rolling_precip_6h"] = hourly_precip_short.rolling(window=6, min_periods=1).sum()
            df["precip_lag_1h"]  = hourly_precip_short.shift(1).fillna(0.0)
            df["precip_lag_3h"]  = hourly_precip_short.shift(3).fillna(0.0)
            df["precip_lag_6h"]  = hourly_precip_short.shift(6).fillna(0.0)
            df["precip_lag_12h"] = hourly_precip_short.shift(12).fillna(0.0)
            df["precip_lag_24h"] = hourly_precip_short.shift(24).fillna(0.0)
            df["precip_lag_48h"] = hourly_precip_short.shift(48).fillna(0.0)
            df["precip_lag_72h"] = hourly_precip_short.shift(72).fillna(0.0)
        else:
            self._logger.error(
                "No live sub-daily precipitation source available. Setting rolling/lag to NaN."
            )
            for c in ["rolling_precip_3h", "rolling_precip_6h", "precip_lag_1h", "precip_lag_3h",
                      "precip_lag_6h", "precip_lag_12h", "precip_lag_24h", "precip_lag_48h", "precip_lag_72h"]:
                df[c] = np.nan

        if long_col:
            self._logger.info(f"24h/72h rolling features based on: {long_col}")
            if long_col == "imd_rainfall_mm":
                hourly_precip_long = df[long_col] / 24.0
            else:
                hourly_precip_long = df[long_col]
            df["rolling_precip_24h"] = hourly_precip_long.rolling(window=24, min_periods=1).sum()
            df["rolling_precip_72h"] = hourly_precip_long.rolling(window=72, min_periods=1).sum()
        else:
            self._logger.warning("No usable precipitation source for 24h/72h rolling features.")
            df["rolling_precip_24h"] = np.nan
            df["rolling_precip_72h"] = np.nan

        return df

    # ----------------------------------------------------------------------
    #  STEP 8: Generate labels
    # ----------------------------------------------------------------------

    def _generate_labels(self, df: pd.DataFrame) -> pd.DataFrame:
        short_col = self._data_quality.get("short_window_precip_source")

        # Label 1: Rain intensity class
        if short_col:
            df["rain_intensity_class"] = pd.cut(
                df[short_col].fillna(0),
                bins=RAIN_INTENSITY_BINS,
                labels=RAIN_INTENSITY_LABELS,
                right=False,
            ).astype(np.int8)
            self._data_quality["rain_intensity_class_basis"] = f"hourly:{short_col}"
        elif "imd_rainfall_mm" in df.columns:
            df["rain_intensity_class"] = pd.cut(
                df["imd_rainfall_mm"].fillna(0),
                bins=DAILY_RAIN_BINS,
                labels=DAILY_RAIN_LABELS,
                right=False,
            ).astype(np.int8)
            self._data_quality["rain_intensity_class_basis"] = "daily:imd_rainfall_mm"
        else:
            df["rain_intensity_class"] = np.int8(0)
            self._data_quality["rain_intensity_class_basis"] = "none"

        class_counts = df["rain_intensity_class"].value_counts().sort_index()
        self._logger.info(f"rain_intensity_class distribution:\n{class_counts}")

        # Label 2: Cloudburst flag
        if short_col and df["rolling_precip_3h"].notna().any():
            df["cloudburst_flag"] = (
                df["rolling_precip_3h"] >= CLOUDBURST_THRESHOLD_MM
            ).astype("float").astype("Int8")
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
                "cloudburst_flag set to NaN for ALL rows - no verified sub-daily precipitation source."
            )
            self._data_quality["cloudburst_label_trustworthy"] = False
            self._data_quality["cloudburst_events"] = 0

        # Label 3: Landslide risk
        df["landslide_risk"] = np.int8(0)

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
        return df

    # ----------------------------------------------------------------------
    #  STEP 9: Select final columns
    # ----------------------------------------------------------------------

    def _select_final_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        desired_order = [
            "district",
            "temperature_2m", "dewpoint_2m", "relative_humidity",
            "surface_pressure", "mslp",
            "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
            "wind_u_10m", "wind_v_10m",
            "cloud_cover", "cape", "lifted_index",
            "precipitation_openmeteo", "rain_openmeteo", "snowfall",
            "precipitation_gpm", "imd_rainfall_mm",
            "soil_temperature_0_to_7cm", "soil_moisture_0_to_7cm",
            "rolling_precip_3h", "rolling_precip_6h",
            "rolling_precip_24h", "rolling_precip_72h",
            "precip_lag_1h", "precip_lag_3h", "precip_lag_6h",
            "precip_lag_12h", "precip_lag_24h", "precip_lag_48h", "precip_lag_72h",
            "hour", "month", "day_of_year", "season", "is_monsoon",
            "week_of_year", "day_of_week", "is_weekend",
            "hour_sin", "hour_cos", "month_sin", "month_cos",
            "rain_intensity_class", "cloudburst_flag", "landslide_risk",
        ]
        final_cols = [c for c in desired_order if c in df.columns]
        df = df[final_cols]
        self._logger.info(f"Final columns ({len(final_cols)}): {final_cols}")
        return df

    # ----------------------------------------------------------------------
    #  STEP 10: Save datasets
    # ----------------------------------------------------------------------

    def _save(self, processed_districts: dict[str, pd.DataFrame]) -> Path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        for dist_name, d_df in processed_districts.items():
            if dist_name != "default":
                pq_d = OUTPUT_DIR / f"final_dataset_{dist_name}.parquet"
                csv_d = OUTPUT_DIR / f"final_dataset_{dist_name}.csv"
                d_df.to_parquet(pq_d, engine="pyarrow")
                d_df.to_csv(csv_d)
                self._logger.info(f"Saved district '{dist_name}': {len(d_df):,} rows -> {pq_d.name}")

        all_dfs = list(processed_districts.values())
        master_df = pd.concat(all_dfs, axis=0) if len(all_dfs) > 1 else all_dfs[0]

        parquet_path = OUTPUT_DIR / "final_dataset.parquet"
        csv_path     = OUTPUT_DIR / "final_dataset.csv"
        report_path  = OUTPUT_DIR / "feature_report.json"

        master_df.to_parquet(parquet_path, engine="pyarrow")
        master_df.to_csv(csv_path)

        pq_mb  = parquet_path.stat().st_size / 1_048_576
        csv_mb = csv_path.stat().st_size    / 1_048_576
        self._logger.info(f"Master Parquet: {parquet_path.name} ({pq_mb:.1f} MB)")
        self._logger.info(f"Master CSV    : {csv_path.name} ({csv_mb:.1f} MB)")

        report = {
            "generated_at":    datetime.now(timezone.utc).isoformat(),
            "rows":            len(master_df),
            "columns":         len(master_df.columns),
            "districts":       list(processed_districts.keys()),
            "date_min":        str(master_df.index.min()),
            "date_max":        str(master_df.index.max()),
            "feature_columns": [
                c for c in master_df.columns
                if c not in ("rain_intensity_class", "cloudburst_flag", "landslide_risk")
            ],
            "label_columns": ["rain_intensity_class", "cloudburst_flag", "landslide_risk"],
            "rain_intensity_distribution": (
                master_df["rain_intensity_class"].value_counts().sort_index().to_dict()
                if "rain_intensity_class" in master_df.columns else {}
            ),
            "cloudburst_events": self._data_quality.get("cloudburst_events", 0),
            "landslide_risk_distribution": (
                master_df["landslide_risk"].value_counts().sort_index().to_dict()
                if "landslide_risk" in master_df.columns else {}
            ),
            "missing_pct": {
                col: round(master_df[col].isna().mean() * 100, 2) for col in master_df.columns
            },
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