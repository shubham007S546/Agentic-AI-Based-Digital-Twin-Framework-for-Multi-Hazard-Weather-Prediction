"""
merger.py
══════════════════════════════════════════════════════════════════════════════
Phase 1 Final Step — Unified Dataset Merger for Mandi District

What this does
──────────────
  Reads all cleaned CSVs from every source, aligns them to a common hourly
  UTC datetime index, merges into one unified DataFrame, validates it, and
  saves the result to datasets/merged_dataset/.

Sources merged (in priority order for conflict resolution)
───────────────────────────────────────────────────────────
  1. Open-Meteo ERA5    → hourly  (already hourly)
  2. ERA5 CDS           → hourly  (already hourly)
  3. NASA GPM IMERG     → half-hourly → sum to hourly
  4. IMD gridded        → daily   → forward-fill to hourly
  5. data.gov.in        → monthly → forward-fill to hourly

Output
──────
  datasets/merged_dataset/merged_dataset.parquet  ← for ML pipeline
  datasets/merged_dataset/merged_dataset.csv      ← for Excel/inspection
  datasets/merged_dataset/merge_report.json       ← provenance + stats

Usage
─────
  python merger.py
  OR
  python -m merger
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.config_loader import get_config
from utils.logger import get_logger

MERGER_NAME = "merger"

# Output directory
MERGED_DIR = Path("datasets/merged_dataset")


# ══════════════════════════════════════════════════════════════════════════════
#  Individual source loaders
# ══════════════════════════════════════════════════════════════════════════════

class SourceLoader:
    """
    Loads and prepares one source's cleaned CSV files into a single
    hourly-indexed DataFrame.

    Each loader method:
      - Reads all matching CSV files from the source cleaned/ directory
      - Parses and normalises the datetime column
      - Converts to UTC
      - Resamples to hourly if needed
      - Returns a DataFrame indexed by datetime (UTC)
    """

    def __init__(self, cfg: dict, logger) -> None:
        self._cfg    = cfg
        self._logger = logger

    # ── Directory resolution ─────────────────────────────────────────────

    def _resolve_source_dir(
        self, source_key: str, path_fallback_key: Optional[str] = None
    ) -> Optional[Path]:
        """
        Resolve a source's base directory, tolerant of config
        inconsistencies (some sources use 'download_dir', some
        'output_dir', some have neither and only exist under
        paths.weather.<key>).
        """
        src_cfg = self._cfg.get("sources", {}).get(source_key, {})
        for key in ("download_dir", "output_dir"):
            if key in src_cfg:
                return Path(src_cfg[key])

        fallback = (
            self._cfg.get("paths", {})
            .get("weather", {})
            .get(path_fallback_key or source_key)
        )
        if fallback:
            self._logger.warning(
                f"  {source_key}: no download_dir/output_dir in "
                f"sources.{source_key}; falling back to "
                f"paths.weather.{path_fallback_key or source_key} = {fallback}"
            )
            return Path(fallback)

        self._logger.error(
            f"  {source_key}: could not resolve a directory from config "
            f"(checked sources.{source_key}.download_dir/output_dir and "
            f"paths.weather.{path_fallback_key or source_key})."
        )
        return None

    # ── Open-Meteo ────────────────────────────────────────────────────────

    def load_openmeteo(self) -> Optional[pd.DataFrame]:
        """Load Open-Meteo cleaned parquet or CSV — already hourly UTC."""
        src_dir = self._resolve_source_dir("openmeteo")
        if src_dir is None:
            return None
        clean_dir = src_dir / "cleaned"

        # Try parquet first (faster), then CSV
        parquet = clean_dir / "openmeteo_mandi_cleaned.parquet"
        csv_    = clean_dir / "openmeteo_mandi_cleaned.csv"

        if parquet.exists():
            self._logger.info(f"  Open-Meteo: loading {parquet.name}")
            df = pd.read_parquet(parquet)
        elif csv_.exists():
            self._logger.info(f"  Open-Meteo: loading {csv_.name}")
            df = pd.read_csv(csv_, parse_dates=["datetime"])
        else:
            # Try any CSV in cleaned/
            csvs = sorted(clean_dir.glob("*.csv"))
            if not csvs:
                self._logger.warning("  Open-Meteo: no cleaned files found.")
                return None
            df = pd.concat([pd.read_csv(f) for f in csvs], ignore_index=True)
            self._logger.info(f"  Open-Meteo: loaded {len(csvs)} CSV(s)")

        df = self._normalise_datetime(df, ["datetime", "date", "time"])
        if df is None:
            return None

        # Already hourly — just ensure no sub-hourly rows
        df = df.resample("h").mean(numeric_only=True)
        df.columns = [f"openmeteo_{c}" for c in df.columns]
        self._logger.info(
            f"  Open-Meteo: {len(df):,} hourly rows, "
            f"{len(df.columns)} columns"
        )
        return df

    # ── ERA5 CDS ──────────────────────────────────────────────────────────

    def load_era5(self) -> Optional[pd.DataFrame]:
        """Load ERA5 monthly cleaned CSVs — already hourly."""
        src_dir = self._resolve_source_dir("era5")
        if src_dir is None:
            return None
        clean_dir = src_dir / "cleaned"
        # ERA5 collector saves per-district subfolders:
        #   cleaned/<district>/era5_<district>_<yyyymm>_cleaned.csv
        # rglob so this works whether files are flat or nested.
        csvs = sorted(clean_dir.rglob("era5_mandi_*_cleaned.csv"))

        if not csvs:
            self._logger.warning("  ERA5: no cleaned CSVs found.")
            return None

        self._logger.info(f"  ERA5: loading {len(csvs)} monthly CSV(s)...")
        dfs = []
        for f in csvs:
            try:
                dfs.append(pd.read_csv(f))
            except Exception as exc:
                self._logger.warning(f"  ERA5: failed to read {f.name}: {exc}")

        if not dfs:
            return None

        df = pd.concat(dfs, ignore_index=True)
        df = self._normalise_datetime(df, ["time", "datetime", "valid_time"])
        if df is None:
            return None

        # ERA5 has lat/lon columns — average over the bbox grid
        num_cols = df.select_dtypes(include="number").columns.tolist()
        # Remove lat/lon from the mean (they're coordinates, not variables)
        var_cols = [c for c in num_cols
                    if c not in ("latitude", "longitude", "lat", "lon")]
        df = df[var_cols].resample("h").mean()
        df.columns = [f"era5_{c}" for c in df.columns]
        self._logger.info(
            f"  ERA5: {len(df):,} hourly rows, {len(df.columns)} columns"
        )
        return df

    # ── NASA GPM ──────────────────────────────────────────────────────────

    def load_nasa_gpm(self) -> Optional[pd.DataFrame]:
        """
        Load NASA GPM half-hourly cleaned CSVs.
        Resamples to hourly by SUMMING precipitation (mm/hr × 0.5hr = mm).
        """
        src_dir = self._resolve_source_dir("nasa_gpm")
        if src_dir is None:
            return None
        clean_dir = src_dir / "cleaned"
        csvs      = sorted(clean_dir.rglob("nasa_gpm_*_cleaned.csv"))

        if not csvs:
            self._logger.warning("  NASA GPM: no cleaned CSVs found.")
            return None

        self._logger.info(f"  NASA GPM: loading {len(csvs)} daily CSV(s)...")
        dfs = []
        for f in csvs:
            try:
                dfs.append(pd.read_csv(f))
            except Exception as exc:
                self._logger.warning(
                    f"  NASA GPM: failed to read {f.name}: {exc}"
                )

        if not dfs:
            return None

        df = pd.concat(dfs, ignore_index=True)
        df = self._normalise_datetime(df, ["timestamp", "time", "datetime"])
        if df is None:
            return None

        # Average over the spatial grid (lat/lon)
        num_cols = [
            c for c in df.select_dtypes(include="number").columns
            if c not in ("latitude", "longitude")
        ]
        df = df[num_cols]

        # Resample: precipitation → sum (mm/hr × 0.5hr); QI → mean
        agg = {}
        for col in df.columns:
            if "precipitation" in col.lower() and "quality" not in col.lower():
                agg[col] = "sum"
            else:
                agg[col] = "mean"
        df = df.resample("h").agg(agg)
        df.columns = [f"gpm_{c}" for c in df.columns]
        self._logger.info(
            f"  NASA GPM: {len(df):,} hourly rows, {len(df.columns)} columns"
        )
        return df

    # ── IMD gridded ───────────────────────────────────────────────────────

    def load_imd(self) -> Optional[pd.DataFrame]:
        """
        Load IMD daily gridded cleaned CSVs.
        Forward-fills daily values to hourly (constant within each day).
        """
        src_dir = self._resolve_source_dir("imd")
        if src_dir is None:
            return None
        clean_dir = src_dir / "cleaned"
        csvs      = sorted(clean_dir.rglob("imd_mandi_*_cleaned.csv"))

        if not csvs:
            self._logger.warning("  IMD: no cleaned CSVs found.")
            return None

        self._logger.info(f"  IMD: loading {len(csvs)} yearly CSV(s)...")
        dfs = []
        for f in csvs:
            try:
                dfs.append(pd.read_csv(f))
            except Exception as exc:
                self._logger.warning(
                    f"  IMD: failed to read {f.name}: {exc}"
                )

        if not dfs:
            return None

        df = pd.concat(dfs, ignore_index=True)
        df = self._normalise_datetime(df, ["date", "time", "datetime"])
        if df is None:
            return None

        # Average over bbox grid points
        num_cols = [
            c for c in df.select_dtypes(include="number").columns
            if c not in ("latitude", "longitude")
        ]
        # Resample to daily mean, then upsample to hourly and forward-fill
        df_daily = df[num_cols].resample("D").mean()
        df_hourly = df_daily.resample("h").ffill()
        df_hourly.columns = [f"imd_{c}" for c in df_hourly.columns]
        self._logger.info(
            f"  IMD: {len(df_hourly):,} hourly rows (forward-filled from daily)"
        )
        return df_hourly

    # ── data.gov.in ───────────────────────────────────────────────────────

    def load_datagov(self) -> Optional[pd.DataFrame]:
        """
        Load data.gov.in cleaned CSVs.
        Monthly data forward-filled to hourly.
        """
        src_dir = self._resolve_source_dir("datagov")
        if src_dir is None:
            return None
        clean_dir = src_dir / "cleaned"
        csvs      = sorted(clean_dir.glob("*.csv"))

        if not csvs:
            self._logger.warning("  data.gov.in: no cleaned CSVs found.")
            return None

        self._logger.info(
            f"  data.gov.in: loading {len(csvs)} CSV(s)..."
        )
        dfs = []
        for f in csvs:
            try:
                dfs.append(pd.read_csv(f))
            except Exception as exc:
                self._logger.warning(
                    f"  data.gov.in: failed to read {f.name}: {exc}"
                )

        if not dfs:
            return None

        df = pd.concat(dfs, ignore_index=True)

        # data.gov.in cleaned CSVs prefix every column with 'raw_'
        # (e.g. 'raw_Date', 'raw_Avg_rainfall') — strip that prefix so the
        # normal candidate-column matching below (and downstream naming)
        # works the same as for any other source.
        if any(c.startswith("raw_") for c in df.columns):
            df = df.rename(columns={c: c[len("raw_"):] for c in df.columns if c.startswith("raw_")})

        # Try to find a date/year/month column
        date_col = self._find_date_column(
            df, ["date", "datetime", "year", "month", "time"]
        )

        if date_col is None:
            self._logger.warning(
                "  data.gov.in: no datetime column found. Skipping."
            )
            return None

        # Handle year-only or year+month columns
        if date_col in ("year",):
            df["_date"] = pd.to_datetime(
                df[date_col].astype(str), format="%Y", errors="coerce"
            )
        else:
            df["_date"] = pd.to_datetime(df[date_col], errors="coerce")

        df = df.dropna(subset=["_date"])
        df = df.set_index("_date")
        df.index = df.index.tz_localize("UTC")
        df.index.name = "datetime"

        num_cols = df.select_dtypes(include="number").columns.tolist()
        df = df[num_cols]

        # Monthly → daily → hourly forward-fill
        df_monthly = df.resample("ME").mean()
        df_hourly  = df_monthly.resample("h").ffill()
        df_hourly.columns = [f"datagov_{c}" for c in df_hourly.columns]
        self._logger.info(
            f"  data.gov.in: {len(df_hourly):,} hourly rows "
            "(forward-filled from monthly)"
        )
        return df_hourly

    # ── ERA5-Land (daily hydrology) ──────────────────────────────────────

    def load_era5_land(self) -> Optional[pd.DataFrame]:
        """
        Load ERA5-Land daily cleaned CSVs for Mandi and forward-fill to
        hourly.

        Schema (from era5_land_collector.py — NOT guessed):
          era5_land_root = paths.hydrology.root / "ERA5_Land"
          cleaned files  = cleaned/era5_land_daily_<district>_<year>.csv
          columns        = date, district, {var}_mean, {var}_min, {var}_max
                            for each of: volumetric_soil_water_layer_1,
                            snow_depth, snowmelt, surface_runoff,
                            total_evaporation, skin_temperature,
                            soil_temperature_level_1
        """
        hydrology_root = self._cfg.get("paths", {}).get("hydrology", {}).get(
            "root", "digital_twin/hydrology"
        )
        clean_dir = Path(hydrology_root) / "ERA5_Land" / "cleaned"
        csvs = sorted(clean_dir.glob("era5_land_daily_mandi_*.csv"))

        if not csvs:
            self._logger.warning(
                f"  ERA5-Land: no cleaned CSVs found in {clean_dir} "
                "(expected era5_land_daily_mandi_<year>.csv)."
            )
            return None

        self._logger.info(f"  ERA5-Land: loading {len(csvs)} yearly CSV(s)...")
        dfs = []
        for f in csvs:
            try:
                dfs.append(pd.read_csv(f))
            except Exception as exc:
                self._logger.warning(f"  ERA5-Land: failed to read {f.name}: {exc}")

        if not dfs:
            return None

        df = pd.concat(dfs, ignore_index=True)

        # Filter to Mandi explicitly (file naming already implies this, but
        # be defensive in case a file ever contains multiple districts).
        if "district" in df.columns:
            df = df[df["district"].str.lower() == "mandi"]

        df = self._normalise_datetime(df, ["date", "datetime", "time"])
        if df is None:
            return None

        # Daily → hourly forward-fill (same pattern as IMD)
        df_daily = df.resample("D").mean()
        df_hourly = df_daily.resample("h").ffill()
        df_hourly.columns = [f"era5land_{c}" for c in df_hourly.columns]
        self._logger.info(
            f"  ERA5-Land: {len(df_hourly):,} hourly rows "
            f"(forward-filled from daily), {len(df_hourly.columns)} columns"
        )
        return df_hourly

    # ── Climate Indices (ENSO / IOD / SOI / CO2) ─────────────────────────

    def load_climate_indices(self) -> Optional[pd.DataFrame]:
        """
        Load monthly global climate indices and forward-fill to hourly.

        Schema (confirmed from actual file, not guessed):
          digital_twin/climate_indices/<ENSO|IOD|SOI|CO2>/cleaned/*.csv
          columns: date, value, index   (e.g. "2005-01-01,378.63,CO2_MLO")

        These are GLOBAL indices (not district-specific), so no spatial
        averaging is needed — just pivot each index name into its own
        column and align on date.
        """
        ci_paths = self._cfg.get("paths", {}).get("climate_indices", {})
        folders = {
            k: v for k, v in ci_paths.items() if k != "root"
        }
        if not folders:
            # Fallback to the conventional layout if config doesn't list them.
            base = Path(ci_paths.get("root", "digital_twin/climate_indices"))
            folders = {
                name.lower(): str(base / name)
                for name in ("ENSO", "IOD", "SOI", "CO2")
            }

        all_rows = []
        for name, folder in folders.items():
            clean_dir = Path(folder) / "cleaned"
            csvs = sorted(clean_dir.glob("*.csv"))
            if not csvs:
                self._logger.warning(f"  Climate indices [{name}]: no cleaned CSVs found in {clean_dir}.")
                continue
            for f in csvs:
                try:
                    df_i = pd.read_csv(f)
                    if {"date", "value", "index"}.issubset(df_i.columns):
                        all_rows.append(df_i[["date", "value", "index"]])
                    else:
                        self._logger.warning(
                            f"  Climate indices [{name}]: {f.name} missing expected "
                            f"columns (date/value/index); has {list(df_i.columns)}. Skipping."
                        )
                except Exception as exc:
                    self._logger.warning(f"  Climate indices [{name}]: failed to read {f.name}: {exc}")

        if not all_rows:
            self._logger.warning("  Climate indices: no usable data found across ENSO/IOD/SOI/CO2.")
            return None

        long_df = pd.concat(all_rows, ignore_index=True)
        long_df["date"] = pd.to_datetime(long_df["date"], errors="coerce", utc=True)
        long_df = long_df.dropna(subset=["date"])

        wide = long_df.pivot_table(index="date", columns="index", values="value", aggfunc="mean")
        wide = wide.sort_index()

        # Monthly → hourly forward-fill (same pattern as IMD/ERA5-Land)
        wide_monthly = wide.resample("ME").ffill()
        wide_hourly  = wide_monthly.resample("h").ffill()
        wide_hourly.columns = [f"climidx_{c}" for c in wide_hourly.columns]
        self._logger.info(
            f"  Climate indices: {len(wide_hourly):,} hourly rows "
            f"(forward-filled from monthly), columns: {list(wide_hourly.columns)}"
        )
        return wide_hourly

    # ── MODIS EVI (vegetation, 16-day) ───────────────────────────────────

    def load_modis_evi(self) -> Optional[pd.DataFrame]:
        """
        Load the Mandi EVI time series (produced by modis_process_evi.py)
        and forward-fill 16-day observations to hourly.

        Schema (from modis_process_evi.py's own output, not guessed):
          digital_twin/vegetation/MODIS/cleaned/mandi_evi_timeseries.csv
          columns: date, evi_mean, good_pixel_pct, n_pixels_total
        """
        veg_root = self._cfg.get("paths", {}).get("vegetation", {}).get(
            "modis", "digital_twin/vegetation/MODIS"
        )
        csv_path = Path(veg_root) / "cleaned" / "mandi_evi_timeseries.csv"

        if not csv_path.exists():
            self._logger.warning(
                f"  MODIS EVI: {csv_path} not found. Run modis_process_evi.py first."
            )
            return None

        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:
            self._logger.warning(f"  MODIS EVI: failed to read {csv_path.name}: {exc}")
            return None

        df = self._normalise_datetime(df, ["date", "datetime"])
        if df is None:
            return None

        # Keep only the numeric signal columns worth carrying forward.
        keep_cols = [c for c in ("evi_mean", "good_pixel_pct") if c in df.columns]
        if not keep_cols:
            self._logger.warning("  MODIS EVI: no usable numeric columns found after parsing.")
            return None
        df = df[keep_cols]

        # 16-day (irregular) → hourly forward-fill. resample().ffill() works
        # fine on an irregular-but-sorted DatetimeIndex — it just carries
        # each observation forward until the next one arrives.
        df_hourly = df.resample("h").ffill()
        df_hourly.columns = [f"modis_{c}" for c in df_hourly.columns]
        self._logger.info(
            f"  MODIS EVI: {len(df_hourly):,} hourly rows "
            f"(forward-filled from 16-day), columns: {list(df_hourly.columns)}"
        )
        return df_hourly

    # ── Shared helpers ─────────────────────────────────────────────────────

    def _normalise_datetime(
        self, df: pd.DataFrame, candidate_cols: list[str]
    ) -> Optional[pd.DataFrame]:
        """
        Find a datetime column, parse it, set as UTC index.
        Handles three cases:
          1. Datetime already a proper DatetimeIndex (e.g. round-tripped
             through parquet, which preserves the index) — just localise
             / convert to UTC.
          2. Index carries a datetime-like name (e.g. 'datetime') but
             isn't a DatetimeIndex yet — reset it into a column and parse.
          3. Datetime lives in one of candidate_cols as a normal column.
        Returns None if no datetime info found anywhere.
        """
        df = df.copy()

        if isinstance(df.index, pd.DatetimeIndex):
            idx = df.index
            idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
            df.index = idx
            df.index.name = "datetime"
        else:
            col = self._find_date_column(df, candidate_cols)
            if col is None and df.index.name and (
                df.index.name.lower() in [c.lower() for c in candidate_cols]
            ):
                # Datetime is sitting in the index but untyped/unparsed —
                # pull it back into a column so the normal path handles it.
                idx_name = df.index.name
                df = df.reset_index()
                col = idx_name

            if col is None:
                self._logger.error(
                    f"  No datetime column or index found among "
                    f"{candidate_cols}. Available columns: "
                    f"{list(df.columns[:10])}, index name: {df.index.name!r}"
                )
                return None

            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
            df = df.dropna(subset=[col])
            df = df.set_index(col)
            df.index.name = "datetime"

        # Drop string/object columns — keep only numeric for merge
        df = df.select_dtypes(include="number")

        # Sort chronologically
        df = df.sort_index()

        # Remove duplicate timestamps (keep first)
        dupes = df.index.duplicated(keep="first").sum()
        if dupes > 0:
            self._logger.warning(
                f"  Removed {dupes} duplicate timestamps."
            )
            df = df[~df.index.duplicated(keep="first")]

        return df

    @staticmethod
    def _find_date_column(
        df: pd.DataFrame, candidates: list[str]
    ) -> Optional[str]:
        """Return the first candidate column name that exists in df."""
        cols_lower = {c.lower(): c for c in df.columns}
        for candidate in candidates:
            if candidate.lower() in cols_lower:
                return cols_lower[candidate.lower()]
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  Validator
# ══════════════════════════════════════════════════════════════════════════════

class MergedDatasetValidator:
    """
    Runs basic validation on the merged DataFrame and returns a report dict.

    Checks
    ──────
    - Shape (rows × cols)
    - Date range coverage
    - Missing value % per column
    - Duplicate timestamps
    - Physical range violations (precipitation, temperature)
    """

    # Physical range constraints: (min_valid, max_valid)
    RANGE_CHECKS: dict[str, tuple[float, float]] = {
        "precipitation": (0.0, 500.0),    # mm/hr — extreme but possible
        "rainfall_mm":   (0.0, 500.0),
        "temperature":   (-50.0, 60.0),   # °C
        "temp":          (-50.0, 60.0),
        "humidity":      (0.0, 100.0),    # %
        "pressure":      (800.0, 1100.0), # hPa
        "cloud_cover":   (0.0, 100.0),    # %
        "wind_speed":    (0.0, 200.0),    # km/h
    }

    def __init__(self, logger) -> None:
        self._logger = logger

    def validate(self, df: pd.DataFrame) -> dict:
        """Run all validation checks and return a report dict."""
        self._logger.info("Validation: running checks...")
        report: dict = {}

        # Shape
        report["rows"]    = len(df)
        report["columns"] = len(df.columns)
        self._logger.info(f"  Shape: {len(df):,} rows × {len(df.columns)} cols")

        # Date range
        report["date_min"] = str(df.index.min())
        report["date_max"] = str(df.index.max())
        self._logger.info(
            f"  Date range: {report['date_min']} → {report['date_max']}"
        )

        # Missing values
        missing = {}
        for col in df.columns:
            n   = int(df[col].isna().sum())
            pct = round(n / len(df) * 100, 2) if len(df) > 0 else 0
            missing[col] = {"count": n, "pct": pct}
            if pct > 50:
                self._logger.warning(
                    f"  HIGH MISSING: {col} = {pct:.1f}%"
                )
        report["missing_values"] = missing

        # Duplicate timestamps
        dupes = int(df.index.duplicated().sum())
        report["duplicate_timestamps"] = dupes
        if dupes > 0:
            self._logger.warning(f"  Duplicate timestamps: {dupes}")
        else:
            self._logger.info("  Duplicate timestamps: 0 ✓")

        # Range violations
        violations: dict = {}
        for col in df.columns:
            col_lower = col.lower()
            for key, (lo, hi) in self.RANGE_CHECKS.items():
                if key in col_lower:
                    bad = int(
                        ((df[col] < lo) | (df[col] > hi)).sum()
                    )
                    if bad > 0:
                        violations[col] = bad
                        self._logger.warning(
                            f"  Range violation: {col} has {bad} values "
                            f"outside [{lo}, {hi}]"
                        )
                    break
        report["range_violations"] = violations

        if not violations:
            self._logger.info("  Range checks: all passed ✓")

        return report


# ══════════════════════════════════════════════════════════════════════════════
#  Merger  (orchestrator)
# ══════════════════════════════════════════════════════════════════════════════

class DatasetMerger:
    """
    Orchestrates the full merge pipeline.

    Pipeline
    ────────
    1. Load all 5 sources (hourly-resampled DataFrames)
    2. Outer join on datetime index
    3. Validate
    4. Save parquet + CSV + report JSON
    """

    def __init__(self) -> None:
        self._cfg    = get_config()
        MERGED_DIR.mkdir(parents=True, exist_ok=True)
        log_dir = MERGED_DIR / "logs"
        log_dir.mkdir(exist_ok=True)
        self._logger   = get_logger(MERGER_NAME, source_log_dir=log_dir)
        self._loader   = SourceLoader(cfg=self._cfg, logger=self._logger)
        self._validator= MergedDatasetValidator(logger=self._logger)

    def run(self) -> Path:
        """Execute the full merge pipeline. Returns path to saved parquet."""
        self._logger.info("=" * 70)
        self._logger.info("Dataset Merger — START")
        self._logger.info(f"Output dir: {MERGED_DIR.resolve()}")
        self._logger.info("=" * 70)

        # ── Step 1: Load all sources ─────────────────────────────────────
        self._logger.info("Step 1: Loading all sources...")
        sources: dict[str, Optional[pd.DataFrame]] = {
            "openmeteo":       self._loader.load_openmeteo(),
            "era5":            self._loader.load_era5(),
            "gpm":             self._loader.load_nasa_gpm(),
            "imd":             self._loader.load_imd(),
            "datagov":         self._loader.load_datagov(),
            "era5_land":       self._loader.load_era5_land(),
            "climate_indices": self._loader.load_climate_indices(),
            "modis_evi":       self._loader.load_modis_evi(),
        }

        available = {k: v for k, v in sources.items() if v is not None}
        if not available:
            self._logger.error("No sources loaded. Aborting.")
            raise RuntimeError("DatasetMerger: all sources failed to load.")

        self._logger.info(
            f"  Loaded {len(available)}/8 sources: "
            f"{list(available.keys())}"
        )

        # ── Step 2: Merge on datetime index ──────────────────────────────
        self._logger.info("Step 2: Merging on hourly datetime index...")
        df_merged = self._merge_sources(available)
        self._logger.info(
            f"  Merged shape: {len(df_merged):,} rows × "
            f"{len(df_merged.columns)} columns"
        )

        # ── Step 3: Validate ─────────────────────────────────────────────
        self._logger.info("Step 3: Validating merged dataset...")
        report = self._validator.validate(df_merged)

        # ── Step 4: Save ─────────────────────────────────────────────────
        self._logger.info("Step 4: Saving output files...")
        parquet_path, csv_path = self._save(df_merged)
        self._save_report(report, parquet_path, sources)

        self._logger.info("=" * 70)
        self._logger.info("Dataset Merger — COMPLETE")
        self._logger.info(f"Parquet : {parquet_path}")
        self._logger.info(f"CSV     : {csv_path}")
        self._logger.info(
            f"Rows    : {len(df_merged):,}   Columns: {len(df_merged.columns)}"
        )
        self._logger.info("=" * 70)

        return parquet_path

    # ── Private helpers ───────────────────────────────────────────────────

    def _merge_sources(
        self, sources: dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """
        Outer join all source DataFrames on their UTC datetime index.

        Strategy
        ────────
        Use pd.concat with axis=1 for an outer join — equivalent to a
        full outer join on the index. Each source already has a clean
        hourly UTC DatetimeIndex so alignment is automatic.
        """
        dfs = list(sources.values())

        if len(dfs) == 1:
            return dfs[0]

        # Outer concat — preserves all timestamps from all sources.
        # sort=False: indices are already individually sorted per-source;
        # avoids the pandas FutureWarning about implicit sort behavior.
        df = pd.concat(dfs, axis=1, join="outer", sort=False)

        # Sort chronologically
        df = df.sort_index()

        # Remove any residual fully-empty rows
        df = df.dropna(how="all")

        # Trim to configured date range — removes empty rows outside overlap
        # NOTE: fallback defaults below (2005-01-01 / 2025-12-31) match
        # config.yaml's dates: block (project.start_year=2005,
        # end_year=2025). Config values are always used when present;
        # these are only a safety net if dates: is ever missing.
        dates_cfg  = self._cfg.get("dates", {})
        start_trim = pd.Timestamp(
            dates_cfg.get("start_date", "2005-01-01"), tz="UTC"
        )
        end_trim = pd.Timestamp(
            dates_cfg.get("end_date", "2025-12-31"), tz="UTC"
        )
        before = len(df)
        df = df.loc[start_trim:end_trim]
        self._logger.info(
            f"  Trimmed to {start_trim.date()} → {end_trim.date()}: "
            f"{before:,} → {len(df):,} rows"
        )

        return df

    def _save(
        self, df: pd.DataFrame
    ) -> tuple[Path, Path]:
        """Save merged DataFrame as parquet and CSV."""
        parquet_path = MERGED_DIR / "merged_dataset.parquet"
        csv_path     = MERGED_DIR / "merged_dataset.csv"

        df.to_parquet(parquet_path, engine="pyarrow")
        df.to_csv(csv_path)

        pq_mb  = parquet_path.stat().st_size / 1_048_576
        csv_mb = csv_path.stat().st_size / 1_048_576
        self._logger.info(
            f"  Parquet saved: {parquet_path.name} ({pq_mb:.1f} MB)"
        )
        self._logger.info(
            f"  CSV saved    : {csv_path.name} ({csv_mb:.1f} MB)"
        )
        return parquet_path, csv_path

    def _save_report(
        self,
        report: dict,
        parquet_path: Path,
        sources: dict[str, Optional[pd.DataFrame]],
    ) -> None:
        """Write merge_report.json with provenance + validation stats."""
        report_path = MERGED_DIR / "merge_report.json"

        full_report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "output_file":  str(parquet_path.resolve()),
            "sources_loaded": {
                k: (len(v) if v is not None else 0)
                for k, v in sources.items()
            },
            "merged_rows":    report.get("rows", 0),
            "merged_columns": report.get("columns", 0),
            "date_min":       report.get("date_min"),
            "date_max":       report.get("date_max"),
            "duplicate_timestamps": report.get("duplicate_timestamps", 0),
            "range_violations": report.get("range_violations", {}),
            "missing_pct_over_50": {
                col: v["pct"]
                for col, v in report.get("missing_values", {}).items()
                if v["pct"] > 50
            },
        }

        with open(report_path, "w") as fh:
            json.dump(full_report, fh, indent=2)

        self._logger.info(f"  Report saved : {report_path.name}")


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    merger = DatasetMerger()
    merger.run()