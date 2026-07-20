"""
collectors/imd_collector.py
══════════════════════════════════════════════════════════════════════════════
SOURCE 1 — IMD Gridded Rainfall (imdlib / IMD Pune)

What this collector does
────────────────────────
  1. Reads all settings from config/config.yaml — no hard-coded values.
  2. Uses imdlib to download IMD gridded binary (.grd) rainfall data
     directly from IMD Pune servers — no manual download needed.
  3. Downloads year by year for all years in [start_date, end_date].
  4. Skips years already downloaded (duplicate detection).
  5. Opens each .grd file with imdlib → xarray Dataset.
  6. Crops the global India grid to the Mandi bounding box.
  7. Replaces IMD fill value (-999.0) with NaN.
  8. Validates non-negative rainfall.
  9. Saves raw .grd files into   datasets/source_1_imd/raw/
 10. Saves cleaned yearly CSVs → datasets/source_1_imd/cleaned/
 11. Writes metadata.json after the full run.

IMD dataset details
────────────────────
  Variable  : Daily rainfall (mm)
  Resolution: 0.25° × 0.25° (~28 km)
  Coverage  : All India (lat 6.5–38.5, lon 66.5–100.0)
  Period    : 1901 onwards (archive) / real-time (recent years)
  Fill value: -999.0 (missing / ocean cells)
  Format    : Binary .grd (imdlib reads natively)

Output files
────────────
  datasets/source_1_imd/raw/rain/         (imdlib saves .grd here)
  datasets/source_1_imd/cleaned/imd_mandi_YYYY_cleaned.csv
  datasets/source_1_imd/metadata.json
  datasets/source_1_imd/logs/imd_collector_YYYYMMDD.log

Usage
─────
  pip install imdlib xarray pandas numpy tqdm
  python -m collectors.imd_collector
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.config_loader import get_config, get_source_dir, get_date_range
from utils.logger import get_logger
from utils.metadata_writer import write_metadata

try:
    import imdlib as imd
except ImportError:
    print("imdlib not installed. Run: pip install imdlib")
    sys.exit(1)

try:
    import xarray as xr
except ImportError:
    print("xarray not installed. Run: pip install xarray")
    sys.exit(1)


SOURCE_KEY = "imd"
COLLECTOR_NAME = "imd_collector"

# IMD fill value for missing / ocean cells
IMD_FILL_VALUE: float = -999.0

# imdlib variable names → readable column names in output CSV
VARIABLE_RENAME: dict[str, str] = {
    "rain": "rainfall_mm",
    "tmin": "temp_min_c",
    "tmax": "temp_max_c",
}


class IMDDownloader:
    """
    Downloads IMD gridded .grd files using imdlib.

    imdlib.get_data() downloads directly from IMD Pune servers.
    Files are saved into subdirectories under raw_dir:
        raw_dir/rain/YYYY.grd
        raw_dir/tmin/YYYY.grd   (if tmin is requested)
        raw_dir/tmax/YYYY.grd   (if tmax is requested)

    Parameters
    ----------
    raw_dir   : Path — parent directory; imdlib creates variable subdirs
    variables : list[str] — list of imdlib variable names ('rain','tmin','tmax')
    logger
    """

    def __init__(
        self,
        raw_dir: Path,
        variables: list[str],
        logger,
    ) -> None:
        self._raw_dir = raw_dir
        self._variables = variables
        self._logger = logger

    def download_year(self, year: int) -> dict[str, bool]:
        """
        Download all requested variables for one year.

        imdlib saves files as: raw_dir/<variable>/<YYYY>.grd
        Skips if file already exists.

        Parameters
        ----------
        year : int

        Returns
        -------
        Dict mapping variable name → True if available, False if failed.
        """
        results: dict[str, bool] = {}

        for variable in self._variables:
            grd_path = self._raw_dir / variable / f"{year}.grd"

            # Duplicate detection
            if grd_path.exists() and grd_path.stat().st_size > 0:
                self._logger.info(
                    f"  Cached: {variable}/{year}.grd — skipping download."
                )
                results[variable] = True
                continue

            # Create subdirectory (imdlib expects it to exist)
            (self._raw_dir / variable).mkdir(parents=True, exist_ok=True)

            self._logger.info(
                f"  Downloading: {variable} for year {year}..."
            )

            try:
                imd.get_data(
                    var_type=variable,
                    start_yr=year,
                    end_yr=year,
                    fn_format="yearwise",
                    file_dir=str(self._raw_dir),
                )

                if grd_path.exists() and grd_path.stat().st_size > 0:
                    size_mb = grd_path.stat().st_size / 1_048_576
                    self._logger.info(
                        f"  Downloaded: {variable}/{year}.grd ({size_mb:.1f} MB)"
                    )
                    results[variable] = True
                else:
                    self._logger.error(
                        f"  Download appeared to succeed but file not found: "
                        f"{grd_path}"
                    )
                    results[variable] = False

            except Exception as exc:
                self._logger.error(
                    f"  imdlib download failed for {variable} {year}: {exc}"
                )
                results[variable] = False

        return results


class IMDParser:
    """
    Parses IMD .grd files using imdlib and crops to Mandi bounding box.

    imdlib.open_data() reads the binary .grd into an xarray Dataset.
    We then convert to a flat Pandas DataFrame and crop spatially.

    Parameters
    ----------
    raw_dir : Path — same raw_dir passed to IMDDownloader
    bbox    : dict — lat_min, lat_max, lon_min, lon_max
    logger
    """

    def __init__(self, raw_dir: Path, bbox: dict, logger) -> None:
        self._raw_dir = raw_dir
        self._bbox = bbox
        self._logger = logger

    def parse_year(
        self, year: int, variables: list[str]
    ) -> Optional[pd.DataFrame]:
        """
        Read all variables for one year, crop to bbox, return DataFrame.

        Parameters
        ----------
        year      : int
        variables : list[str] — imdlib variable names

        Returns
        -------
        pd.DataFrame with columns: date, latitude, longitude, + variables
        None if all variables fail to parse.
        """
        dfs: list[pd.DataFrame] = []

        for variable in variables:
            grd_path = self._raw_dir / variable / f"{year}.grd"
            if not grd_path.exists():
                self._logger.warning(
                    f"  .grd not found, skipping: {grd_path}"
                )
                continue

            df_var = self._parse_variable(year, variable)
            if df_var is not None:
                dfs.append(df_var)

        if not dfs:
            return None

        # Merge all variables on (date, lat, lon)
        df = dfs[0]
        for df_extra in dfs[1:]:
            merge_cols = ["date", "latitude", "longitude"]
            df = df.merge(df_extra, on=merge_cols, how="outer")

        return df.sort_values(
            ["date", "latitude", "longitude"]
        ).reset_index(drop=True)

    def _parse_variable(
        self, year: int, variable: str
    ) -> Optional[pd.DataFrame]:
        """
        Read one variable's .grd file → crop → clean → DataFrame.

        Parameters
        ----------
        year     : int
        variable : str — 'rain', 'tmin', or 'tmax'

        Returns
        -------
        pd.DataFrame or None
        """
        try:
            # imdlib.open_data reads the binary .grd
            data_obj = imd.open_data(
                var_type=variable,
                start_yr=year,
                end_yr=year,
                fn_format="yearwise",
                file_dir=str(self._raw_dir),
            )

            # Convert imdlib object → xarray Dataset
            ds: xr.Dataset = data_obj.get_xarray()

        except Exception as exc:
            self._logger.error(
                f"  imdlib failed to open {variable}/{year}.grd: {exc}"
            )
            return None

        try:
            # Crop to Mandi bounding box using xarray selection
            ds_crop = ds.sel(
                lat=slice(self._bbox["lat_min"], self._bbox["lat_max"]),
                lon=slice(self._bbox["lon_min"], self._bbox["lon_max"]),
            )

            if ds_crop[variable].size == 0:
                self._logger.error(
                    f"  Bounding box yields 0 grid points for "
                    f"{variable}/{year}. Check bbox config."
                )
                return None

            # Convert to flat DataFrame
            df = ds_crop.to_dataframe().reset_index()

            # Rename coordinate columns
            df = df.rename(columns={
                "lat": "latitude",
                "lon": "longitude",
                "time": "date",
                variable: VARIABLE_RENAME.get(variable, variable),
            })

            # Parse date column
            df["date"] = pd.to_datetime(df["date"]).dt.date

            # Replace IMD fill value with NaN
            col = VARIABLE_RENAME.get(variable, variable)
            fill_mask = df[col] <= IMD_FILL_VALUE + 1  # -999 and below
            n_fill = int(fill_mask.sum())
            if n_fill > 0:
                df.loc[fill_mask, col] = np.nan
                self._logger.debug(
                    f"  Replaced {n_fill} fill values in {col} with NaN."
                )

            # Validate: rainfall must be non-negative
            if variable == "rain":
                neg_mask = df[col] < 0
                n_neg = int(neg_mask.sum())
                if n_neg > 0:
                    df.loc[neg_mask, col] = np.nan
                    self._logger.warning(
                        f"  {n_neg} negative rainfall values → NaN."
                    )

            self._logger.debug(
                f"  Parsed {variable}/{year}: {len(df):,} rows, "
                f"bbox grid = "
                f"{ds_crop['lat'].size}lat × {ds_crop['lon'].size}lon"
            )

            return df[["date", "latitude", "longitude", col]]

        except Exception as exc:
            self._logger.error(
                f"  Parse failed for {variable}/{year}: {exc}"
            )
            return None


class IMDCollector:
    """
    Orchestrates the full IMD gridded data collection pipeline.

    Pipeline (per year)
    ─────────────────────
    1. Download .grd via imdlib → raw/rain/YYYY.grd
    2. Open .grd → xarray → crop to Mandi bbox → DataFrame
    3. Clean (fill values, negative rainfall)
    4. Save yearly cleaned CSV → cleaned/

    After all years:
    5. Write metadata.json
    """

    def __init__(self) -> None:
        self._cfg = get_config()
        self._src_cfg = self._cfg["sources"][SOURCE_KEY]
        self._loc = self._cfg["location"]
        self._source_dir = get_source_dir(SOURCE_KEY)
        self._raw_dir = self._source_dir / "raw"
        self._clean_dir = self._source_dir / "cleaned"
        self._log_dir = self._source_dir / "logs"

        for d in (self._raw_dir, self._clean_dir, self._log_dir):
            d.mkdir(parents=True, exist_ok=True)

        self._logger = get_logger(COLLECTOR_NAME, source_log_dir=self._log_dir)
        self._bbox = self._cfg["location"]["bounding_box"]
        self._start_date, self._end_date = get_date_range()
        self._variables: list[str] = self._src_cfg.get("variables", ["rain"])

        self._downloader = IMDDownloader(
            raw_dir=self._raw_dir,
            variables=self._variables,
            logger=self._logger,
        )
        self._parser = IMDParser(
            raw_dir=self._raw_dir,
            bbox=self._bbox,
            logger=self._logger,
        )

    # ──────────────────────────────────────────────────────────────────────
    #  PUBLIC ENTRY POINT
    # ──────────────────────────────────────────────────────────────────────

    def run(self) -> None:
        self._logger.info("=" * 70)
        self._logger.info("IMD Gridded Collector — START")
        self._logger.info(
            f"Location  : {self._loc['district']}, {self._loc['state']}"
        )
        self._logger.info(
            f"Bbox      : N={self._bbox['lat_max']} S={self._bbox['lat_min']} "
            f"W={self._bbox['lon_min']} E={self._bbox['lon_max']}"
        )
        self._logger.info(
            f"Period    : {self._start_date.year} → {self._end_date.year}"
        )
        self._logger.info(f"Variables : {self._variables}")
        self._logger.info(f"Resolution: 0.25° daily gridded")
        self._logger.info("=" * 70)

        years = list(range(self._start_date.year, self._end_date.year + 1))
        total = len(years)
        processed = 0
        skipped = 0
        total_records = 0
        total_missing: dict[str, int] = {}

        for i, year in enumerate(
            tqdm(years, desc="IMD years", unit="year"), start=1
        ):
            self._logger.info(f"[{i}/{total}] Year: {year}")

            # Step 1: Download
            download_results = self._downloader.download_year(year)
            available_vars = [
                v for v, ok in download_results.items() if ok
            ]

            if not available_vars:
                self._logger.warning(
                    f"  No variables downloaded for {year}. Skipping."
                )
                skipped += 1
                continue

            # Step 2: Parse + crop
            df = self._parser.parse_year(year, available_vars)

            if df is None or df.empty:
                self._logger.warning(
                    f"  Parse returned empty for {year}. Skipping."
                )
                skipped += 1
                continue

            # Step 3: Save cleaned CSV
            csv_path = self._save_cleaned(df, year)

            # Accumulate stats
            total_records += len(df)
            for col in df.select_dtypes(include="number").columns:
                n_miss = int(df[col].isna().sum())
                total_missing[col] = total_missing.get(col, 0) + n_miss

            processed += 1
            self._logger.info(
                f"  Done: {len(df):,} records → {csv_path.name}"
            )

        # Step 4: Metadata
        self._write_metadata(total_records, total_missing)

        self._logger.info("=" * 70)
        self._logger.info("IMD Gridded Collector — COMPLETE")
        self._logger.info(f"Years total   : {total}")
        self._logger.info(f"Processed     : {processed}")
        self._logger.info(f"Skipped       : {skipped}")
        self._logger.info(f"Total records : {total_records:,}")
        self._logger.info("=" * 70)

    # ──────────────────────────────────────────────────────────────────────
    #  PRIVATE HELPERS
    # ──────────────────────────────────────────────────────────────────────

    def _save_cleaned(self, df: pd.DataFrame, year: int) -> Path:
        """Save cleaned yearly DataFrame as CSV."""
        csv_path = self._clean_dir / f"imd_mandi_{year}_cleaned.csv"
        df.to_csv(csv_path, index=False)
        size_kb = csv_path.stat().st_size / 1024
        self._logger.info(
            f"  Saved: {csv_path.name} ({size_kb:.0f} KB)"
        )
        return csv_path

    def _write_metadata(
        self,
        total_records: int,
        total_missing: dict[str, int],
    ) -> None:
        """Write metadata.json using the shared utility."""
        cleaned_csvs = sorted(
            self._clean_dir.glob("imd_mandi_*_cleaned.csv")
        )
        cleaned_path = (
            cleaned_csvs[-1]
            if cleaned_csvs
            else self._clean_dir / "no_data.csv"
        )
        raw_grds = sorted(self._raw_dir.rglob("*.grd"))
        raw_path = (
            raw_grds[0] if raw_grds else self._raw_dir / "no_data.grd"
        )

        meta = write_metadata(
            source_dir=self._source_dir,
            source_name=self._src_cfg["name"],
            api_url="https://imdpune.gov.in/",
            update_frequency=self._src_cfg["update_frequency"],
            df_cleaned=pd.DataFrame(),
            raw_file_path=raw_path,
            cleaned_file_path=cleaned_path,
            extra={
                "library": "imdlib",
                "variables": self._variables,
                "spatial_resolution_deg": self._src_cfg.get(
                    "resolution_deg", 0.25
                ),
                "temporal_resolution": "Daily",
                "fill_value": IMD_FILL_VALUE,
                "bounding_box": self._bbox,
                "total_records": total_records,
                "missing_values_summary": total_missing,
                "start_year": self._start_date.year,
                "end_year": self._end_date.year,
                "data_source": "IMD Pune gridded archive",
                "reference": (
                    "Pai et al. (2014), High resolution daily gridded "
                    "rainfall data for the Indian region"
                ),
            },
        )
        self._logger.info(f"Metadata written: {meta}")


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    collector = IMDCollector()
    collector.run()
