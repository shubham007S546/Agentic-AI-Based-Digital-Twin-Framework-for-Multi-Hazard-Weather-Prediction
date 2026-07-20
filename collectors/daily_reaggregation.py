"""
daily_reaggregation.py
==============================================================================
Collapses merged_dataset.parquet (hourly, but with a flat-filled daily
IMD target) down to its TRUE native resolution: one row per day.

WHY THIS EXISTS
---------------
merged_dataset.parquet is hourly because ERA5/Open-Meteo/GPM genuinely are
hourly. But IMD rainfall (the actual prediction target) is a DAILY total
that was forward-filled across 24 identical hourly rows during merging
(confirmed: 100% of IMD-covered days have zero within-day variation).

Every hourly lag/rolling feature built on that column is manufacturing
false signal from a constant -- this is the exact issue the project's
own model comparison flagged (validation score stopped predicting test
performance; more expressive models increasingly overfit the artifact).

This script produces a second, DAILY-grain dataset where every column is
properly aggregated to one real value per day, so features and models
built on it reflect actual day-to-day dynamics rather than a repeated
constant.

AGGREGATION RULES (per column type)
-------------------------------------
  Flux/accumulation (sum over the day):
    openmeteo_precipitation, openmeteo_rain, openmeteo_snowfall

  Already-daily / already-constant-within-day (take first, NOT sum --
  these are the flat-filled or forward-filled columns; summing would
  multiply a daily value by 24):
    imd_rainfall_mm, datagov_Avg_rainfall, datagov_Year, datagov_Month,
    climidx_*, modis_evi_mean, modis_good_pixel_pct

  Instantaneous / state variables (mean + min + max, since intraday
  extremes matter for cloudburst/heavy-rain detection):
    *_temperature_2m, *_dewpoint_2m, *_surface_pressure,
    *_relative_humidity, *_wind_speed_10m, *_cape,
    *_total_column_water_vapour, openmeteo_cloud_cover,
    openmeteo_wind_gusts_10m

  Directional (circular mean would be more correct, but a simple mean
  is used here as a first pass -- flag for revisiting if wind direction
  features matter for your models):
    *_wind_direction_10m, *_wind_dir_10m, era5_wind_u_10m, era5_wind_v_10m

  Categorical-ish (most frequent value of the day):
    openmeteo_weather_code

OUTPUT
------
  datasets/merged_dataset/daily_dataset.parquet
  datasets/merged_dataset/daily_dataset.csv
  datasets/merged_dataset/daily_reaggregation_report.json

Usage
-----
  python daily_reaggregation.py
  python daily_reaggregation.py --input datasets/merged_dataset/merged_dataset.parquet
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ── Column classification rules ──────────────────────────────────────────

SUM_COLS = [
    "openmeteo_precipitation", "openmeteo_rain", "openmeteo_snowfall",
]

FIRST_COLS = [
    "imd_rainfall_mm", "datagov_Avg_rainfall", "datagov_Year", "datagov_Month",
    "modis_evi_mean", "modis_good_pixel_pct",
]
FIRST_PREFIXES = ["climidx_"]

MEAN_MINMAX_COLS = [
    "openmeteo_temperature_2m", "openmeteo_relative_humidity_2m",
    "openmeteo_wind_speed_10m", "openmeteo_wind_gusts_10m",
    "openmeteo_surface_pressure", "openmeteo_cloud_cover",
    "era5_temperature_2m", "era5_dewpoint_2m", "era5_surface_pressure",
    "era5_total_column_water_vapour", "era5_cape", "era5_wind_speed_10m",
    "era5_relative_humidity",
]

CIRCULAR_MEAN_COLS = [
    "openmeteo_wind_direction_10m", "era5_wind_dir_10m",
    "era5_wind_u_10m", "era5_wind_v_10m",
]

MODE_COLS = ["openmeteo_weather_code"]


def classify_column(col: str) -> str:
    """Return the aggregation strategy for a given column name."""
    if col in SUM_COLS:
        return "sum"
    if col in FIRST_COLS or any(col.startswith(p) for p in FIRST_PREFIXES):
        return "first"
    if col in MEAN_MINMAX_COLS:
        return "mean_minmax"
    if col in CIRCULAR_MEAN_COLS:
        return "mean"
    if col in MODE_COLS:
        return "mode"
    return "mean_minmax"  # sensible default for anything unrecognized


def aggregate_daily(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Resample an hourly DataFrame to daily, per-column aggregation rules."""
    daily_frames = []
    classification: dict[str, str] = {}

    for col in df.columns:
        strategy = classify_column(col)
        classification[col] = strategy
        series = df[col]

        if strategy == "sum":
            out = series.resample("D").sum(min_count=1).to_frame(col)
        elif strategy == "first":
            out = series.resample("D").first().to_frame(col)
        elif strategy == "mean":
            out = series.resample("D").mean().to_frame(col)
        elif strategy == "mode":
            out = series.resample("D").agg(
                lambda s: s.mode().iloc[0] if not s.mode().empty else pd.NA
            ).to_frame(col)
        else:  # mean_minmax
            g = series.resample("D")
            out = pd.DataFrame({
                f"{col}_mean": g.mean(),
                f"{col}_min":  g.min(),
                f"{col}_max":  g.max(),
            })

        daily_frames.append(out)

    daily = pd.concat(daily_frames, axis=1)
    return daily, classification


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-aggregate hourly merged dataset to daily resolution.")
    parser.add_argument("--input", default="datasets/merged_dataset/merged_dataset.parquet")
    parser.add_argument("--output-dir", default="datasets/merged_dataset")
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        # fall back to CSV if parquet isn't there
        alt = in_path.with_suffix(".csv")
        if alt.exists():
            in_path = alt
        else:
            print(f"ERROR: input not found: {args.input} (or .csv fallback)")
            sys.exit(1)

    print(f"Loading: {in_path}")
    if in_path.suffix == ".parquet":
        df = pd.read_parquet(in_path)
    else:
        df = pd.read_csv(in_path, index_col=0, parse_dates=[0])

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index.name = "date"

    print(f"Input shape: {df.shape[0]:,} hourly rows x {df.shape[1]} columns")
    print(f"Date range : {df.index.min()} -> {df.index.max()}")

    # Verify + report the flat-fill artifact before collapsing it away,
    # so there's a record of why this step exists.
    if "imd_rainfall_mm" in df.columns:
        d = df[["imd_rainfall_mm"]].dropna().copy()
        d["_date"] = d.index.date
        within_day_nunique = d.groupby("_date")["imd_rainfall_mm"].nunique()
        flat_pct = (within_day_nunique == 1).mean() * 100
        print(f"\nIMD flat-fill check: {flat_pct:.1f}% of days have zero within-day variation "
              f"({(within_day_nunique==1).sum():,}/{len(within_day_nunique):,} days)")

    print("\nAggregating to daily resolution...")
    daily, classification = aggregate_daily(df)
    daily = daily.sort_index()

    print(f"Output shape: {daily.shape[0]:,} daily rows x {daily.shape[1]} columns")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / "daily_dataset.parquet"
    csv_path = out_dir / "daily_dataset.csv"

    daily.to_parquet(parquet_path, engine="pyarrow")
    daily.to_csv(csv_path)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_file": str(in_path.resolve()),
        "input_rows_hourly": int(df.shape[0]),
        "output_rows_daily": int(daily.shape[0]),
        "output_columns": int(daily.shape[1]),
        "date_range": [str(daily.index.min()), str(daily.index.max())],
        "column_aggregation_strategy": classification,
    }
    report_path = out_dir / "daily_reaggregation_report.json"
    with open(report_path, "w") as fh:
        json.dump(report, fh, indent=2, default=str)

    print(f"\nSaved: {parquet_path}")
    print(f"Saved: {csv_path}")
    print(f"Saved: {report_path}")
    print("\nColumn aggregation strategy summary:")
    from collections import Counter
    for strategy, count in Counter(classification.values()).items():
        print(f"  {strategy:<15}: {count} column(s)")


if __name__ == "__main__":
    main()
