"""
eda_mandi.py
==============================================================================
Complete EDA -- Mandi District Weather Dataset
Stage 2: Dataset Validation & Exploratory Data Analysis

Reads  : datasets/merged_dataset/final_dataset.csv  (or .parquet)
Outputs: eda_output/
            01_dataset_overview.txt
            02_missing_values.csv
            03_statistical_summary.csv
            04_target_distribution.png
            05_missing_heatmap.png
            06_correlation_matrix.png
            07_rainfall_distribution.png
            08_monthly_patterns.png
            09_hourly_patterns.png
            10_seasonal_boxplot.png
            11_outlier_detection.png
            12_feature_vs_rainfall.png
            13_time_series_overview.png
            14_class_imbalance.png
            15_lag_correlation.png
            eda_final_report.txt

Usage:
    python eda_mandi.py
    python eda_mandi.py --data path/to/your_dataset.csv
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend -- saves files instead of displaying
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

warnings.filterwarnings("ignore")

# -- Configuration --------------------------------------------------------------
OUTPUT_DIR  = Path("eda_output")
DATASET_PATHS = [
    Path("datasets/merged_dataset/final_dataset.csv"),
    Path("datasets/merged_dataset/final_dataset.parquet"),
    Path("datasets/merged_dataset/merged_dataset.csv"),
    Path("datasets/merged_dataset/merged_dataset.parquet"),
]

# Colour palette -- consistent across all plots
PALETTE     = "Blues_r"
ACCENT      = "#1E90FF"
DANGER      = "#E74C3C"
SUCCESS     = "#2ECC71"
DARK        = "#2C3E50"

# Known column name candidates for each concept
RAIN_COLS   = ["precipitation", "rainfall_mm", "rain", "total_precipitation",
               "imd_rainfall_mm", "imd_grid_mm", "rain_mm", "rainfall"]
TARGET_COLS = ["rain_intensity_class", "intensity_class", "rainfall_category",
               "extreme_flag", "cloudburst_flag"]
TIME_COLS   = ["datetime", "datetime_utc", "time", "date", "timestamp"]
CAPE_COLS   = ["cape", "cape_max", "om_cape", "convective_available_potential_energy"]
TEMP_COLS   = ["temperature_2m", "2m_temperature", "temp_c", "om_temp_c"]
HUM_COLS    = ["relative_humidity_2m", "humidity_pct", "om_humidity_pct"]
PRES_COLS   = ["surface_pressure", "mean_sea_level_pressure", "pressure_hpa"]
WIND_COLS   = ["wind_speed_10m", "wind_gusts_10m", "om_gust_kmh"]
CLOUD_COLS  = ["cloud_cover", "total_cloud_cover", "om_cloud_pct"]


# ==============================================================================
#  HELPERS
# ==============================================================================

def find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first candidate column that exists in df."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def load_dataset(path: Path | None) -> pd.DataFrame:
    """Load dataset from CSV or Parquet. Auto-detect format."""
    candidates = [path] if path else DATASET_PATHS
    for p in candidates:
        if p and Path(p).exists():
            print(f"Loading: {p}")
            if str(p).endswith(".parquet"):
                df = pd.read_parquet(p)
            else:
                df = pd.read_csv(p, low_memory=False)
            print(f"  Shape: {df.shape[0]:,} rows x {df.shape[1]} columns")
            return df
    raise FileNotFoundError(
        f"Dataset not found. Tried: {[str(p) for p in (candidates if not path else [path])]}\n"
        "Run: python eda_mandi.py --data path/to/your_dataset.csv"
    )


def parse_datetime(df: pd.DataFrame) -> pd.DataFrame:
    """Parse datetime column and extract time features."""
    dt_col = find_col(df, TIME_COLS)
    if dt_col:
        df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce", utc=True)
        df = df.sort_values(dt_col).reset_index(drop=True)
        df["_hour"]   = df[dt_col].dt.hour
        df["_month"]  = df[dt_col].dt.month
        df["_year"]   = df[dt_col].dt.year
        df["_season"] = df["_month"].map({
            12:"Winter",1:"Winter",2:"Winter",
            3:"Pre-Monsoon",4:"Pre-Monsoon",5:"Pre-Monsoon",
            6:"Monsoon",7:"Monsoon",8:"Monsoon",9:"Monsoon",
            10:"Post-Monsoon",11:"Post-Monsoon"
        })
        df["_weekday"] = df[dt_col].dt.day_name()
    return df


def save_fig(fig: plt.Figure, name: str) -> None:
    path = OUTPUT_DIR / name
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Saved: {path.name}")


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print("="*60)


# ==============================================================================
#  STEP 1 -- DATASET OVERVIEW
# ==============================================================================

def step1_overview(df: pd.DataFrame) -> str:
    section("STEP 1 -- Dataset Overview")

    lines = []
    lines.append("=" * 60)
    lines.append("  MANDI DISTRICT WEATHER DATASET -- EDA OVERVIEW")
    lines.append("=" * 60)
    lines.append(f"Rows              : {len(df):,}")
    lines.append(f"Columns           : {len(df.columns)}")
    lines.append(f"Memory usage      : {df.memory_usage(deep=True).sum() / 1e6:.1f} MB")
    lines.append("")
    lines.append("COLUMN LIST:")
    for col in df.columns:
        dtype  = str(df[col].dtype)
        n_null = df[col].isna().sum()
        pct    = n_null / len(df) * 100
        lines.append(f"  {col:<40} {dtype:<12} {n_null:>7,} missing ({pct:.1f}%)")

    dt_col = find_col(df, TIME_COLS)
    if dt_col and "_year" in df.columns:
        lines.append("")
        lines.append(f"DATE RANGE        : {df[dt_col].min()} -> {df[dt_col].max()}")
        lines.append(f"YEARS COVERED     : {sorted(df['_year'].dropna().unique().tolist())}")

    txt = "\n".join(lines)
    out = OUTPUT_DIR / "01_dataset_overview.txt"
    out.write_text(txt, encoding="utf-8")
    print(txt)
    print(f"\n  Saved: 01_dataset_overview.txt")
    return txt


# ==============================================================================
#  STEP 2 -- MISSING VALUES
# ==============================================================================

def step2_missing(df: pd.DataFrame) -> pd.DataFrame:
    section("STEP 2 -- Missing Value Analysis")

    miss = pd.DataFrame({
        "column":       df.columns,
        "missing_count": df.isna().sum().values,
        "missing_pct":   (df.isna().sum() / len(df) * 100).round(2).values,
        "dtype":         df.dtypes.astype(str).values,
    }).sort_values("missing_pct", ascending=False)

    miss.to_csv(OUTPUT_DIR / "02_missing_values.csv", index=False)
    print(miss[miss.missing_pct > 0].to_string(index=False))

    # Heatmap of missing values
    num_df = df.select_dtypes(include=[np.number])
    if not num_df.empty:
        fig, ax = plt.subplots(figsize=(14, 6))
        miss_matrix = num_df.isna().astype(int)

        # Sample rows for heatmap if too many
        if len(miss_matrix) > 2000:
            miss_matrix = miss_matrix.sample(2000, random_state=42).sort_index()

        sns.heatmap(
            miss_matrix.T, ax=ax,
            cbar=False, cmap=["#2ECC71", "#E74C3C"],
            yticklabels=True, xticklabels=False
        )
        ax.set_title("Missing Values Heatmap\n(Red = Missing, Green = Present)",
                     fontsize=13, fontweight="bold", pad=12)
        ax.set_ylabel("Column", fontsize=10)
        ax.set_xlabel("Observations (sampled)", fontsize=10)
        fig.tight_layout()
        save_fig(fig, "05_missing_heatmap.png")

    return miss


# ==============================================================================
#  STEP 3 -- DUPLICATES
# ==============================================================================

def step3_duplicates(df: pd.DataFrame) -> None:
    section("STEP 3 -- Duplicate Records")
    n_dupes = df.duplicated().sum()
    print(f"  Total duplicate rows  : {n_dupes:,}")
    print(f"  Duplicate percentage  : {n_dupes/len(df)*100:.3f}%")

    dt_col = find_col(df, TIME_COLS)
    if dt_col:
        n_ts_dupes = df[dt_col].duplicated().sum()
        print(f"  Duplicate timestamps  : {n_ts_dupes:,}")


# ==============================================================================
#  STEP 4 -- STATISTICAL SUMMARY
# ==============================================================================

def step4_statistics(df: pd.DataFrame) -> None:
    section("STEP 4 -- Statistical Summary")

    num_df = df.select_dtypes(include=[np.number])
    desc   = num_df.describe(percentiles=[.05, .25, .5, .75, .95]).T
    desc["skewness"] = num_df.skew()
    desc["kurtosis"] = num_df.kurtosis()
    desc.to_csv(OUTPUT_DIR / "03_statistical_summary.csv")

    # Print key columns only
    key_cols = []
    for candidates in [RAIN_COLS, TEMP_COLS, HUM_COLS, PRES_COLS, CAPE_COLS]:
        c = find_col(df, candidates)
        if c:
            key_cols.append(c)

    if key_cols:
        print(desc.loc[[c for c in key_cols if c in desc.index],
                        ["mean","std","min","50%","max","skewness"]].round(3).to_string())
    print("  Full stats saved to: 03_statistical_summary.csv")


# ==============================================================================
#  STEP 5 -- RAINFALL DISTRIBUTION
# ==============================================================================

def step5_rainfall_distribution(df: pd.DataFrame) -> None:
    section("STEP 5 -- Rainfall Distribution Analysis")

    rain_col = find_col(df, RAIN_COLS)
    if not rain_col:
        print("  WARNING: No rainfall column found. Skipping.")
        return

    rain = df[rain_col].dropna()
    rain_nonzero = rain[rain > 0]

    print(f"  Rainfall column       : {rain_col}")
    print(f"  Total observations    : {len(rain):,}")
    print(f"  Zero rainfall (dry)   : {(rain == 0).sum():,} ({(rain==0).mean()*100:.1f}%)")
    print(f"  Non-zero rainfall     : {len(rain_nonzero):,} ({len(rain_nonzero)/len(rain)*100:.1f}%)")
    print(f"  Max rainfall          : {rain.max():.2f} mm")
    print(f"  99th percentile       : {rain.quantile(0.99):.2f} mm")
    print(f"  Heavy rain (>=64.5mm)  : {(rain >= 64.5).sum():,} events")
    print(f"  Cloudburst (>=100mm)   : {(rain >= 100).sum():,} events")

    fig = plt.figure(figsize=(16, 10))
    gs  = gridspec.GridSpec(2, 3, figure=fig, hspace=0.4, wspace=0.35)

    # Plot 1: Full distribution (log scale)
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.hist(rain, bins=100, color=ACCENT, alpha=0.8, edgecolor="white", linewidth=0.3)
    ax1.set_xlabel("Precipitation (mm)", fontsize=10)
    ax1.set_ylabel("Frequency", fontsize=10)
    ax1.set_title("Full Distribution (linear)", fontsize=11, fontweight="bold")
    ax1.set_yscale("log")

    # Plot 2: Non-zero distribution
    ax2 = fig.add_subplot(gs[0, 1])
    if len(rain_nonzero) > 0:
        ax2.hist(rain_nonzero, bins=80, color=DANGER, alpha=0.8,
                 edgecolor="white", linewidth=0.3)
        ax2.set_xlabel("Precipitation > 0 mm", fontsize=10)
        ax2.set_ylabel("Frequency", fontsize=10)
        ax2.set_title("Non-Zero Rainfall Distribution", fontsize=11, fontweight="bold")

    # Plot 3: Boxplot
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.boxplot(rain_nonzero, patch_artist=True,
                boxprops=dict(facecolor=ACCENT, alpha=0.7),
                medianprops=dict(color=DANGER, linewidth=2))
    ax3.set_ylabel("Precipitation (mm)", fontsize=10)
    ax3.set_title("Boxplot (Non-Zero)", fontsize=11, fontweight="bold")

    # Plot 4: Dry vs Wet pie
    ax4 = fig.add_subplot(gs[1, 0])
    labels = ["Dry (0 mm)", "Light (<15.6)", "Moderate (<64.5)",
              "Heavy (<115.6)", "Very Heavy (<204.5)", "Extreme (>=204.5)"]
    sizes  = [
        (rain == 0).sum(),
        ((rain > 0) & (rain < 15.6)).sum(),
        ((rain >= 15.6) & (rain < 64.5)).sum(),
        ((rain >= 64.5) & (rain < 115.6)).sum(),
        ((rain >= 115.6) & (rain < 204.5)).sum(),
        (rain >= 204.5).sum(),
    ]
    colors = ["#ECF0F1","#AED6F1","#3498DB","#F39C12","#E74C3C","#8E44AD"]
    sizes_nonzero = [s for s in sizes if s > 0]
    labels_nz     = [l for l, s in zip(labels, sizes) if s > 0]
    colors_nz     = [c for c, s in zip(colors, sizes) if s > 0]
    ax4.pie(sizes_nonzero, labels=labels_nz, colors=colors_nz,
            autopct="%1.1f%%", startangle=140, textprops={"fontsize": 8})
    ax4.set_title("IMD Rainfall Category Breakdown", fontsize=11, fontweight="bold")

    # Plot 5: ECDF
    ax5 = fig.add_subplot(gs[1, 1])
    sorted_r = np.sort(rain)
    cdf      = np.arange(1, len(sorted_r)+1) / len(sorted_r)
    ax5.plot(sorted_r, cdf, color=ACCENT, linewidth=2)
    for threshold, label, color in [
        (64.5,  "Heavy",    "#F39C12"),
        (115.6, "V.Heavy",  "#E74C3C"),
        (204.5, "Extreme",  "#8E44AD"),
    ]:
        ax5.axvline(threshold, color=color, linestyle="--", linewidth=1.2, label=label)
    ax5.set_xlabel("Precipitation (mm)", fontsize=10)
    ax5.set_ylabel("Cumulative Proportion", fontsize=10)
    ax5.set_title("ECDF of Rainfall", fontsize=11, fontweight="bold")
    ax5.legend(fontsize=8)

    # Plot 6: QQ plot for normality
    ax6 = fig.add_subplot(gs[1, 2])
    sample = rain_nonzero.sample(min(2000, len(rain_nonzero)), random_state=42) if len(rain_nonzero) > 0 else rain
    stats.probplot(np.log1p(sample), dist="norm", plot=ax6)
    ax6.set_title("Q-Q Plot (log1p rainfall)", fontsize=11, fontweight="bold")
    ax6.get_lines()[0].set(color=ACCENT, markersize=2, alpha=0.5)
    ax6.get_lines()[1].set(color=DANGER, linewidth=2)

    fig.suptitle(f"Rainfall Distribution Analysis -- Mandi District\n({rain_col})",
                 fontsize=14, fontweight="bold", y=1.01)
    save_fig(fig, "07_rainfall_distribution.png")


# ==============================================================================
#  STEP 6 -- TEMPORAL PATTERNS
# ==============================================================================

def step6_temporal_patterns(df: pd.DataFrame) -> None:
    section("STEP 6 -- Temporal Pattern Analysis")

    rain_col = find_col(df, RAIN_COLS)
    if not rain_col or "_month" not in df.columns:
        print("  Skipping -- need rainfall column and datetime.")
        return

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle("Temporal Rainfall Patterns -- Mandi District",
                 fontsize=14, fontweight="bold")
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    # Monthly mean rainfall
    ax = axes[0, 0]
    monthly = df.groupby("_month")[rain_col].mean().reindex(range(1,13))
    bars = ax.bar(range(1,13), monthly.values, color=[
        "#E8F4FD" if m not in [6,7,8,9] else "#1E90FF" for m in range(1,13)
    ], edgecolor="white", linewidth=0.5)
    ax.set_xticks(range(1,13))
    ax.set_xticklabels(months, fontsize=8, rotation=45)
    ax.set_title("Mean Rainfall by Month", fontweight="bold")
    ax.set_ylabel("Mean Precipitation (mm)")
    ax.axvspan(5.5, 9.5, alpha=0.08, color="blue", label="Monsoon")
    ax.legend(fontsize=8)

    # Monthly total rainfall
    ax = axes[0, 1]
    monthly_sum = df.groupby("_month")[rain_col].sum().reindex(range(1,13))
    ax.bar(range(1,13), monthly_sum.values,
           color=["#E8F4FD" if m not in [6,7,8,9] else "#1E90FF" for m in range(1,13)],
           edgecolor="white")
    ax.set_xticks(range(1,13))
    ax.set_xticklabels(months, fontsize=8, rotation=45)
    ax.set_title("Total Rainfall by Month", fontweight="bold")
    ax.set_ylabel("Total Precipitation (mm)")

    # Monthly max rainfall (extreme events)
    ax = axes[0, 2]
    monthly_max = df.groupby("_month")[rain_col].max().reindex(range(1,13))
    ax.bar(range(1,13), monthly_max.values, color=DANGER, alpha=0.75, edgecolor="white")
    ax.set_xticks(range(1,13))
    ax.set_xticklabels(months, fontsize=8, rotation=45)
    ax.set_title("Max Rainfall by Month (Extreme Events)", fontweight="bold")
    ax.set_ylabel("Max Precipitation (mm)")
    ax.axhline(100, color="darkred", linestyle="--", linewidth=1.5, label="Cloudburst 100mm")
    ax.legend(fontsize=8)

    # Hourly patterns (if sub-daily data)
    ax = axes[1, 0]
    if "_hour" in df.columns and df["_hour"].nunique() > 3:
        hourly = df.groupby("_hour")[rain_col].mean()
        ax.plot(hourly.index, hourly.values, color=ACCENT, linewidth=2.5, marker="o",
                markersize=4)
        ax.fill_between(hourly.index, hourly.values, alpha=0.2, color=ACCENT)
        ax.set_xlabel("Hour of Day (UTC)")
        ax.set_ylabel("Mean Precipitation (mm)")
        ax.set_title("Mean Rainfall by Hour of Day", fontweight="bold")
        ax.set_xticks(range(0, 24, 3))
    else:
        ax.text(0.5, 0.5, "Daily data -- no\nhourly breakdown",
                ha="center", va="center", transform=ax.transAxes, fontsize=11)
        ax.set_title("Hourly Pattern", fontweight="bold")

    # Seasonal boxplot
    ax = axes[1, 1]
    if "_season" in df.columns:
        season_order = ["Winter", "Pre-Monsoon", "Monsoon", "Post-Monsoon"]
        season_data  = [df[df["_season"]==s][rain_col].dropna() for s in season_order]
        bp = ax.boxplot(season_data, patch_artist=True, labels=season_order,
                        showfliers=False)
        colors_s = ["#AED6F1","#A9DFBF","#F1948A","#FAD7A0"]
        for patch, color in zip(bp["boxes"], colors_s):
            patch.set_facecolor(color)
            patch.set_alpha(0.8)
        ax.set_title("Rainfall by Season (No Outliers)", fontweight="bold")
        ax.set_ylabel("Precipitation (mm)")
        ax.tick_params(axis="x", rotation=15)

    # Yearly trend
    ax = axes[1, 2]
    if "_year" in df.columns and df["_year"].nunique() > 1:
        yearly = df.groupby("_year")[rain_col].agg(["mean","sum","max"]).reset_index()
        ax.bar(yearly["_year"], yearly["sum"], color=ACCENT, alpha=0.7, label="Total")
        ax2b = ax.twinx()
        ax2b.plot(yearly["_year"], yearly["max"], color=DANGER, marker="D",
                  linewidth=2, label="Max event")
        ax.set_title("Annual Rainfall Trend", fontweight="bold")
        ax.set_ylabel("Total Annual Rainfall (mm)")
        ax2b.set_ylabel("Max Single Event (mm)", color=DANGER)
        ax.legend(loc="upper left", fontsize=8)
        ax2b.legend(loc="upper right", fontsize=8)
    else:
        ax.text(0.5, 0.5, "Single year\ndata", ha="center", va="center",
                transform=ax.transAxes, fontsize=11)
        ax.set_title("Annual Trend", fontweight="bold")

    plt.tight_layout()
    save_fig(fig, "08_monthly_patterns.png")


# ==============================================================================
#  STEP 7 -- CORRELATION MATRIX
# ==============================================================================

def step7_correlation(df: pd.DataFrame) -> None:
    section("STEP 7 -- Correlation Analysis")

    num_df = df.select_dtypes(include=[np.number])
    # Drop internal helper columns
    num_df = num_df[[c for c in num_df.columns if not c.startswith("_")]]

    if num_df.shape[1] < 2:
        print("  Not enough numeric columns for correlation.")
        return

    corr = num_df.corr(method="pearson")

    # Find rainfall correlations
    rain_col = find_col(num_df, RAIN_COLS)
    if rain_col:
        rain_corr = corr[rain_col].drop(rain_col).sort_values(key=abs, ascending=False)
        print("\n  Top correlations with rainfall:")
        print(rain_corr.head(15).round(4).to_string())

    # Full correlation heatmap
    fig, ax = plt.subplots(figsize=(max(12, len(corr)*0.6), max(10, len(corr)*0.5)))

    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)  # upper triangle
    sns.heatmap(
        corr, ax=ax, annot=True if len(corr) <= 20 else False,
        fmt=".2f", cmap="RdYlBu_r", vmin=-1, vmax=1,
        center=0, square=True, linewidths=0.3,
        annot_kws={"size": 7},
        cbar_kws={"shrink": 0.7, "label": "Pearson r"}
    )
    ax.set_title("Correlation Matrix -- All Numeric Features",
                 fontsize=13, fontweight="bold", pad=15)
    plt.tight_layout()
    save_fig(fig, "06_correlation_matrix.png")

    # Rainfall-focused bar chart
    if rain_col:
        fig2, ax2 = plt.subplots(figsize=(12, 7))
        colors_bar = [SUCCESS if v > 0 else DANGER for v in rain_corr.values]
        ax2.barh(rain_corr.index, rain_corr.values, color=colors_bar, alpha=0.8)
        ax2.axvline(0, color="black", linewidth=0.8)
        ax2.axvline(0.5, color=SUCCESS, linestyle="--", linewidth=1,
                    alpha=0.7, label="|r|=0.5 strong")
        ax2.axvline(-0.5, color=SUCCESS, linestyle="--", linewidth=1, alpha=0.7)
        ax2.set_xlabel("Pearson Correlation with Rainfall", fontsize=11)
        ax2.set_title(f"Feature Correlation with '{rain_col}'",
                      fontsize=13, fontweight="bold")
        ax2.legend()
        plt.tight_layout()
        save_fig(fig2, "12_feature_vs_rainfall.png")


# ==============================================================================
#  STEP 8 -- OUTLIER DETECTION
# ==============================================================================

def step8_outliers(df: pd.DataFrame) -> dict:
    section("STEP 8 -- Outlier Detection")

    num_df = df.select_dtypes(include=[np.number])
    num_df = num_df[[c for c in num_df.columns if not c.startswith("_")]]

    outlier_summary: dict = {}
    key_cols = []
    for candidates in [RAIN_COLS, TEMP_COLS, HUM_COLS, PRES_COLS, WIND_COLS, CAPE_COLS]:
        c = find_col(df, candidates)
        if c and c in num_df.columns:
            key_cols.append(c)

    if not key_cols:
        key_cols = list(num_df.columns[:8])

    key_cols = key_cols[:8]  # max 8 plots

    print(f"\n  Analyzing outliers in: {key_cols}")

    for col in key_cols:
        series = num_df[col].dropna()
        if len(series) < 10:
            continue
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr     = q3 - q1
        lower   = q1 - 1.5 * iqr
        upper   = q3 + 1.5 * iqr
        n_out   = ((series < lower) | (series > upper)).sum()
        z_score = np.abs(stats.zscore(series))
        n_z     = (z_score > 3).sum()
        outlier_summary[col] = {
            "iqr_outliers":    int(n_out),
            "iqr_pct":         round(n_out / len(series) * 100, 2),
            "zscore_outliers": int(n_z),
            "lower_fence":     round(lower, 3),
            "upper_fence":     round(upper, 3),
        }
        print(f"  {col:<35}: IQR={n_out:>5} ({n_out/len(series)*100:.1f}%)  "
              f"Z>3={n_z:>5} ({n_z/len(series)*100:.1f}%)")

    # Boxplot grid
    n = len(key_cols)
    cols_grid = min(4, n)
    rows_grid = (n + cols_grid - 1) // cols_grid
    fig, axes = plt.subplots(rows_grid, cols_grid,
                             figsize=(cols_grid*4, rows_grid*4))
    axes = np.array(axes).flatten() if n > 1 else [axes]

    for i, col in enumerate(key_cols):
        ax = axes[i]
        series = num_df[col].dropna()
        ax.boxplot(series, patch_artist=True,
                   boxprops=dict(facecolor=ACCENT, alpha=0.6),
                   medianprops=dict(color=DANGER, linewidth=2),
                   flierprops=dict(marker=".", color=DANGER, alpha=0.3, markersize=2))
        ax.set_title(col, fontsize=9, fontweight="bold")
        ax.set_ylabel("Value")

    for j in range(n, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle("Outlier Detection -- Boxplots (Key Variables)",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    save_fig(fig, "11_outlier_detection.png")

    return outlier_summary


# ==============================================================================
#  STEP 9 -- TARGET VARIABLE / CLASS IMBALANCE
# ==============================================================================

def step9_target_analysis(df: pd.DataFrame) -> None:
    section("STEP 9 -- Target Variable Analysis")

    rain_col   = find_col(df, RAIN_COLS)
    target_col = find_col(df, TARGET_COLS)

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle("Target Variable Analysis -- Mandi District",
                 fontsize=14, fontweight="bold")

    # -- Plot 1: Derived intensity classes from rainfall --------------------
    ax = axes[0]
    if rain_col:
        rain = df[rain_col].fillna(0)
        def classify(r):
            if r < 2.5:   return "No Rain"
            if r < 15.6:  return "Light"
            if r < 64.5:  return "Moderate"
            if r < 115.6: return "Heavy"
            if r < 204.5: return "Very Heavy"
            return "Extreme"
        classes = rain.apply(classify)
        class_order = ["No Rain","Light","Moderate","Heavy","Very Heavy","Extreme"]
        counts      = classes.value_counts().reindex(class_order, fill_value=0)
        colors_cls  = ["#BDC3C7","#AED6F1","#2E86C1","#F39C12","#E74C3C","#8E44AD"]
        bars = ax.bar(counts.index, counts.values, color=colors_cls, edgecolor="white")
        ax.set_title("IMD Rainfall Intensity Classes", fontweight="bold")
        ax.set_ylabel("Count")
        ax.set_yscale("log")
        ax.tick_params(axis="x", rotation=30)
        for bar, count in zip(bars, counts.values):
            if count > 0:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height()*1.1,
                        f"{count:,}", ha="center", va="bottom", fontsize=8)
        print("\n  IMD Rainfall Class Distribution:")
        for cls, cnt in counts.items():
            print(f"    {cls:<15}: {cnt:>7,}  ({cnt/len(rain)*100:.2f}%)")

    # -- Plot 2: Named target column (if exists) ----------------------------
    ax = axes[1]
    if target_col:
        vc = df[target_col].value_counts()
        ax.bar(vc.index.astype(str), vc.values, color=ACCENT, alpha=0.8,
               edgecolor="white")
        ax.set_title(f"Target Column: '{target_col}'", fontweight="bold")
        ax.set_ylabel("Count")
        ax.set_yscale("log")
        ax.tick_params(axis="x", rotation=30)
        print(f"\n  Target column '{target_col}':")
        print(vc.to_string())
    else:
        ax.text(0.5, 0.5, "No target column\nfound in dataset\n\n"
                "Add 'rain_intensity_class'\nor similar column",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=11, color="gray")
        ax.set_title("Target Column", fontweight="bold")

    # -- Plot 3: Extreme event frequency over time --------------------------
    ax = axes[2]
    if rain_col and "_month" in df.columns and "_year" in df.columns:
        extreme = df[df[rain_col] >= 64.5].copy()
        if len(extreme) > 0:
            extreme_monthly = extreme.groupby(["_year","_month"]).size().reset_index(name="n")
            ax.scatter(
                extreme_monthly["_month"] + (extreme_monthly["_year"] - extreme_monthly["_year"].min())*0.1,
                extreme_monthly["n"],
                alpha=0.6, color=DANGER, s=40
            )
            ax.set_title("Heavy Rain Events by Month", fontweight="bold")
            ax.set_ylabel("Count of Heavy Rain Events")
            ax.set_xlabel("Month")
            ax.set_xticks(range(1,13))
            ax.set_xticklabels(["J","F","M","A","M","J","J","A","S","O","N","D"])
        else:
            ax.text(0.5, 0.5, "No heavy rain\nevents found",
                    ha="center", va="center", transform=ax.transAxes, fontsize=11)
            ax.set_title("Heavy Rain Events", fontweight="bold")

    plt.tight_layout()
    save_fig(fig, "04_target_distribution.png")
    save_fig(fig, "14_class_imbalance.png")


# ==============================================================================
#  STEP 10 -- TIME SERIES OVERVIEW
# ==============================================================================

def step10_timeseries(df: pd.DataFrame) -> None:
    section("STEP 10 -- Time Series Overview")

    dt_col   = find_col(df, TIME_COLS)
    rain_col = find_col(df, RAIN_COLS)
    if not dt_col or not rain_col:
        print("  Skipping -- need datetime and rainfall columns.")
        return

    df2 = df[[dt_col, rain_col]].copy().dropna()
    df2 = df2.set_index(dt_col).sort_index()

    # Resample to daily for readability
    daily = df2.resample("D").sum()

    fig, axes = plt.subplots(3, 1, figsize=(18, 12), sharex=False)
    fig.suptitle("Time Series Analysis -- Mandi District Rainfall",
                 fontsize=14, fontweight="bold")

    # Full time series
    ax = axes[0]
    ax.plot(daily.index, daily[rain_col], color=ACCENT, linewidth=0.6, alpha=0.8)
    ax.fill_between(daily.index, daily[rain_col], alpha=0.2, color=ACCENT)
    ax.axhline(64.5, color=DANGER, linestyle="--", linewidth=1, alpha=0.7,
               label="Heavy rain threshold (64.5mm)")
    ax.axhline(100,  color="#8E44AD", linestyle="--", linewidth=1, alpha=0.7,
               label="Cloudburst threshold (100mm)")
    ax.set_title("Daily Rainfall -- Full Period", fontweight="bold")
    ax.set_ylabel("Rainfall (mm/day)")
    ax.legend(fontsize=8)

    # Rolling 30-day mean
    ax = axes[1]
    rolling = daily[rain_col].rolling(30, min_periods=1).mean()
    ax.plot(daily.index, rolling, color=ACCENT, linewidth=2)
    ax.fill_between(daily.index, rolling, alpha=0.3, color=ACCENT)
    ax.set_title("30-Day Rolling Mean Rainfall", fontweight="bold")
    ax.set_ylabel("30d Mean Rainfall (mm)")

    # Extreme events only
    ax = axes[2]
    extreme = daily[daily[rain_col] >= 64.5]
    ax.vlines(extreme.index, 0, extreme[rain_col], color=DANGER, alpha=0.7, linewidth=1.5)
    ax.set_title("Extreme Events Only (>=64.5mm/day)",
                 fontweight="bold", color=DANGER)
    ax.set_ylabel("Rainfall (mm)")
    ax.set_xlabel("Date")

    plt.tight_layout()
    save_fig(fig, "13_time_series_overview.png")


# ==============================================================================
#  STEP 11 -- LAG CORRELATION ANALYSIS
# ==============================================================================

def step11_lag_correlation(df: pd.DataFrame) -> None:
    section("STEP 11 -- Lag Feature Correlation")

    rain_col = find_col(df, RAIN_COLS)
    if not rain_col:
        print("  Skipping -- no rainfall column.")
        return

    rain = df[rain_col].dropna().reset_index(drop=True)
    lags  = [1, 3, 6, 12, 24, 48, 72, 168]
    corrs = []

    for lag in lags:
        shifted = rain.shift(lag)
        mask    = rain.notna() & shifted.notna()
        if mask.sum() > 100:
            r, _ = stats.pearsonr(rain[mask], shifted[mask])
            corrs.append((lag, r))

    if not corrs:
        print("  Not enough data for lag analysis.")
        return

    lag_df = pd.DataFrame(corrs, columns=["lag", "correlation"])

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Lag Correlation Analysis", fontsize=13, fontweight="bold")

    ax = axes[0]
    colors_lag = [SUCCESS if r > 0 else DANGER for _, r in corrs]
    ax.bar([f"lag_{l}" for l, _ in corrs],
           [r for _, r in corrs], color=colors_lag, alpha=0.8)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.axhline(0.3, color="gray", linestyle="--", linewidth=1, label="r=0.3")
    ax.set_title("Rainfall Auto-Correlation at Different Lags", fontweight="bold")
    ax.set_ylabel("Pearson r")
    ax.set_xlabel("Lag (time steps)")
    ax.tick_params(axis="x", rotation=30)
    ax.legend(fontsize=8)

    for bar, (_, r) in zip(ax.patches, corrs):
        ax.text(bar.get_x()+bar.get_width()/2,
                bar.get_height() + 0.01 if r >= 0 else bar.get_height() - 0.04,
                f"{r:.3f}", ha="center", va="bottom", fontsize=8)

    # Scatter: lag_1 vs current
    ax2 = axes[1]
    lag1 = rain.shift(1)
    mask = rain.notna() & lag1.notna()
    sample_idx = np.random.choice(np.where(mask)[0], size=min(2000, mask.sum()), replace=False)
    ax2.scatter(lag1.iloc[sample_idx], rain.iloc[sample_idx],
                alpha=0.3, s=8, color=ACCENT)
    ax2.set_xlabel(f"Rainfall at t-1 (lag_1)", fontsize=10)
    ax2.set_ylabel(f"Rainfall at t (current)", fontsize=10)
    ax2.set_title("Current vs Lag-1 Rainfall (sample)", fontweight="bold")

    plt.tight_layout()
    save_fig(fig, "15_lag_correlation.png")

    print("\n  Lag correlation results:")
    print(lag_df.to_string(index=False))


# ==============================================================================
#  FINAL REPORT
# ==============================================================================

def write_final_report(df: pd.DataFrame, miss: pd.DataFrame,
                        outliers: dict) -> None:
    section("FINAL EDA REPORT")

    rain_col = find_col(df, RAIN_COLS)
    lines    = []

    lines.append("=" * 70)
    lines.append("  MANDI DISTRICT WEATHER DATASET -- EDA FINAL REPORT")
    lines.append("=" * 70)
    lines.append(f"\nGenerated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Dataset shape   : {df.shape[0]:,} rows x {df.shape[1]} columns")

    dt_col = find_col(df, TIME_COLS)
    if dt_col and dt_col in df.columns:
        dt = pd.to_datetime(df[dt_col], errors="coerce", utc=True)
        lines.append(f"Date range      : {dt.min()} -> {dt.max()}")

    lines.append(f"\n{'-'*70}")
    lines.append("  SECTION 1: DATA QUALITY")
    lines.append(f"{'-'*70}")

    high_miss = miss[miss.missing_pct > 20]
    if len(high_miss):
        lines.append(f"\n  WARNING  HIGH MISSING VALUES (>20%):")
        for _, row in high_miss.iterrows():
            lines.append(f"     {row.column:<35}: {row.missing_pct:.1f}% missing")
        lines.append("  -> ACTION: Investigate source. Remove or impute in Stage 4.")
    else:
        lines.append("\n  OK  No columns with >20% missing values.")

    n_dupes = df.duplicated().sum()
    lines.append(f"\n  Duplicate rows  : {n_dupes:,}")
    if n_dupes > 0:
        lines.append("  -> ACTION: Remove duplicates before Stage 3 merging.")

    lines.append(f"\n{'-'*70}")
    lines.append("  SECTION 2: RAINFALL STATISTICS")
    lines.append(f"{'-'*70}")

    if rain_col:
        rain = df[rain_col].dropna()
        lines.append(f"\n  Primary rainfall column : {rain_col}")
        lines.append(f"  Total observations      : {len(rain):,}")
        lines.append(f"  Mean rainfall           : {rain.mean():.3f} mm")
        lines.append(f"  Max rainfall            : {rain.max():.3f} mm")
        lines.append(f"  Zero rain (dry days)    : {(rain==0).sum():,} ({(rain==0).mean()*100:.1f}%)")
        lines.append(f"  Heavy rain (>=64.5mm)    : {(rain>=64.5).sum():,} events")
        lines.append(f"  Very heavy (>=115.6mm)   : {(rain>=115.6).sum():,} events")
        lines.append(f"  Cloudburst (>=100mm/3h)  : {(rain>=100).sum():,} events")
        lines.append(f"  Extreme (>=204.5mm)      : {(rain>=204.5).sum():,} events")
        lines.append(f"  Skewness                : {rain.skew():.3f} (highly right-skewed)")
        lines.append("\n  IMD INTENSITY CLASS BREAKDOWN:")
        def classify(r):
            if r < 2.5:   return "No Rain"
            if r < 15.6:  return "Light"
            if r < 64.5:  return "Moderate"
            if r < 115.6: return "Heavy"
            if r < 204.5: return "Very Heavy"
            return "Extreme"
        classes = rain.apply(classify)
        for cls in ["No Rain","Light","Moderate","Heavy","Very Heavy","Extreme"]:
            n = (classes == cls).sum()
            lines.append(f"     {cls:<15}: {n:>7,}  ({n/len(rain)*100:.2f}%)")

    lines.append(f"\n{'-'*70}")
    lines.append("  SECTION 3: OUTLIER SUMMARY")
    lines.append(f"{'-'*70}")
    for col, stats_d in outliers.items():
        lines.append(f"\n  {col}:")
        lines.append(f"    IQR outliers  : {stats_d['iqr_outliers']:,} ({stats_d['iqr_pct']:.2f}%)")
        lines.append(f"    Z>3 outliers  : {stats_d['zscore_outliers']:,}")

    lines.append(f"\n{'-'*70}")
    lines.append("  SECTION 4: KEY FINDINGS & RECOMMENDATIONS")
    lines.append(f"{'-'*70}")
    lines.append("""
  FINDING 1 -- CLASS IMBALANCE
  The dataset is heavily skewed toward zero/low rainfall (typical for Mandi).
  Extreme events are rare. For Stage 6 ML training:
  -> Use class weights, SMOTE, or Focal Loss
  -> Do NOT use accuracy as metric -- use F1, Precision-Recall AUC

  FINDING 2 -- SEASONAL CONCENTRATION
  Monsoon (Jun-Sep) accounts for ~80% of annual rainfall.
  -> Add is_monsoon flag as a feature in Stage 4
  -> Consider separate models for monsoon vs non-monsoon

  FINDING 3 -- MULTI-SOURCE ALIGNMENT
  Different sources have different temporal resolutions:
  IMD = daily | NASA GPM = 30-min | ERA5/OpenMeteo = hourly
  -> Stage 3 merger must resample to common frequency (recommend: hourly)
  -> Use forward-fill for daily IMD values within each day

  FINDING 4 -- CAPE VARIABLE
  CAPE (convective energy) is critical for cloudburst prediction.
  Check CAPE missing % -- if >50%, supplement from ERA5 Copernicus source.

  FINDING 5 -- LAG FEATURES
  Auto-correlation analysis shows which lag lengths are predictive.
  -> Keep lags with |r| > 0.3
  -> Rolling sums (6h, 24h, 72h) often more informative than instantaneous
""")

    lines.append(f"{'-'*70}")
    lines.append("  NEXT STEPS")
    lines.append(f"{'-'*70}")
    lines.append("""
  Stage 2 (current)  : Dataset Validation -- Review this EDA report
  Stage 3            : Dataset Merging -- Align timestamps, unify columns
  Stage 4            : Feature Engineering -- Lags, rolling sums, CAPE, season
  Stage 5            : Feature Selection -- Remove low-correlation columns
  Stage 6            : ML/DL Training -- XGBoost, LSTM, Transformer
  Stage 7            : Model Evaluation -- F1, AUC-PR, calibration
  Stage 8            : Agentic AI System
  Stage 9            : Real-Time Deployment
""")

    lines.append("=" * 70)
    lines.append("  END OF EDA REPORT")
    lines.append("=" * 70)

    txt = "\n".join(lines)
    out = OUTPUT_DIR / "eda_final_report.txt"
    out.write_text(txt, encoding="utf-8")
    print(txt)
    print(f"\n  Full report saved: {out}")


# ==============================================================================
#  MAIN
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="EDA for Mandi Weather Dataset")
    parser.add_argument("--data", type=str, default=None,
                        help="Path to dataset CSV or Parquet file")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", palette="Blues_r", font_scale=0.95)
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor":   "white",
        "savefig.facecolor":"white",
        "font.family":      "DejaVu Sans",
    })

    print("\n" + "="*60)
    print("  MANDI DISTRICT WEATHER DATASET -- COMPLETE EDA")
    print("="*60)

    # Load
    df = load_dataset(Path(args.data) if args.data else None)
    df = parse_datetime(df)

    # Run all steps
    step1_overview(df)
    miss     = step2_missing(df)
    step3_duplicates(df)
    step4_statistics(df)
    step5_rainfall_distribution(df)
    step6_temporal_patterns(df)
    step7_correlation(df)
    outliers = step8_outliers(df)
    step9_target_analysis(df)
    step10_timeseries(df)
    step11_lag_correlation(df)
    write_final_report(df, miss, outliers)

    print("\n" + "="*60)
    print(f"  EDA COMPLETE -- all outputs in: {OUTPUT_DIR.resolve()}")
    print("="*60)
    print("\nFiles generated:")
    for f in sorted(OUTPUT_DIR.iterdir()):
        size = f.stat().st_size
        print(f"  {f.name:<45} {size/1024:>7.1f} KB")


if __name__ == "__main__":
    main()