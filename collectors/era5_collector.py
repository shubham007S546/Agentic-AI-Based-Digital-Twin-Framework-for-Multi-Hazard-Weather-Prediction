"""
collectors/era5_collector.py
══════════════════════════════════════════════════════════════════════════════
SOURCE 4 — ERA5 Reanalysis via Copernicus Climate Data Store (CDS API)

WHY THIS VERSION IS "MONTHLY + CONCURRENT" (NOT YEARLY)
────────────────────────────────────────────────────────
  The previous "yearly chunk" version tried to cut queue-wait overhead by
  requesting a full year (365×24×10 ≈ 87,600 fields) in one call. That
  looked safe under CDS's OLD field-count limit, but the CURRENT CDS-Beta
  backend prices requests using its own "cost" metric that also weights
  bounding-box area and grid resolution — not just raw field count. Every
  one of your 11 yearly requests came back with:

      "Cost limits exceeded... your request is too large, please reduce
      your selection."

  So: yearly requests are no longer viable at 10 variables. The fix is to
  go back to MONTHLY requests (small enough to always clear CDS's cost
  cap — a month × 24h × 10 vars is ~7,440 fields, comfortably under any
  version of their limit), but still submit them CONCURRENTLY via
  ThreadPoolExecutor instead of one-at-a-time. You lose the extra "12x
  fewer requests" win, but you keep most of the speedup from parallel
  queue-waiting, and — critically — every request actually succeeds.

  If you ever want to try bigger chunks again (e.g. quarterly), do it
  cautiously and expect to dial it back down if CDS rejects it — there's
  no documented exact number to target, since the cost formula isn't
  published. Monthly is the known-safe baseline.

What this collector does
────────────────────────
  1. Reads all settings from config/config.yaml — no hard-coded values.
  2. Authenticates using the CDS API key from config (api_keys.cds_api_key).
  3. Downloads ERA5 single-level reanalysis in MONTHLY NetCDF chunks,
     cropped to the Mandi bounding box, submitted concurrently.
  4. Parses each NetCDF, extracts all variables, crops to bbox.
  5. Derives wind speed and direction from U/V components.
  6. Converts units: temperature K→°C, precipitation m→mm, pressure Pa→hPa.
  7. Saves raw monthly NetCDF files and cleaned MONTHLY CSVs.
  8. Writes metadata.json after the full run.

Output files
─────────────
  datasets/source_4_era5/raw/era5_mandi_YYYYMM.nc
  datasets/source_4_era5/cleaned/era5_mandi_YYYYMM_cleaned.csv
  datasets/source_4_era5/metadata.json
  datasets/source_4_era5/logs/era5_collector_YYYYMMDD.log

Usage
─────
  pip install cdsapi xarray netcdf4 scipy numpy pandas tqdm
  python -m collectors.era5_collector

Config options (config.yaml → sources.era5)
──────────────────────────────────────────────
  max_concurrent_downloads: 3   # how many monthly requests to submit at once
                                 # (CDS accounts typically allow a small number
                                 #  of concurrent queued requests per user —
                                 #  going much above ~4-5 risks CDS itself
                                 #  queuing your requests behind each other)

CDS API key setup
─────────────────
  1. Register at https://cds.climate.copernicus.eu
  2. Go to Profile → API key
  3. Copy your key (format: "UID:KEY")
  4. Paste into config/config.yaml → api_keys.cds_api_key
"""

from __future__ import annotations

import sys
import time
import zipfile
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterator, Optional
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.config_loader import get_config, get_source_dir, get_date_range
from utils.logger import get_logger
from utils.metadata_writer import write_metadata

try:
    import cdsapi
    import xarray as xr
    import pandas as pd
    from tqdm import tqdm
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: pip install cdsapi xarray netcdf4 scipy numpy pandas tqdm")
    sys.exit(1)


SOURCE_KEY = "era5"
COLLECTOR_NAME = "era5_collector"
DEFAULT_MAX_CONCURRENT = 3   # concurrent CDS requests — see module docstring

# Substrings CDS uses in its "too large" error — used to give a clearer
# log message (and would be the hook point if you ever add auto-splitting).
COST_LIMIT_MARKERS = ("cost limit", "too large", "reduce your selection")

VARIABLE_RENAME = {
    "u10":  "wind_u_10m",
    "v10":  "wind_v_10m",
    "d2m":  "dewpoint_2m",
    "t2m":  "temperature_2m",
    "msl":  "mslp",
    "sp":   "surface_pressure",
    "tp":   "total_precipitation",
    "tcc":  "cloud_cover",
    "cp":   "convective_precipitation",
    "cape": "cape",
}


class ERA5Downloader:
    """
    Downloads ERA5 MONTHLY NetCDF files from the Copernicus CDS.

    Each call to download_month() creates its OWN cdsapi.Client instance —
    this is what makes it safe to call from multiple threads concurrently.
    Sharing one client across threads risks corrupted concurrent requests
    since cdsapi.Client wraps a requests.Session that isn't documented as
    thread-safe.
    """

    def __init__(
        self,
        cds_url: str,
        cds_key: str,
        raw_dir: Path,
        dataset: str,
        product_type: str,
        variables: list[str],
        bbox: dict,
        logger,
    ) -> None:
        self._cds_url = cds_url
        self._cds_key = cds_key
        self._raw_dir = raw_dir
        self._dataset = dataset
        self._product_type = product_type
        self._variables = variables
        self._bbox = bbox
        self._logger = logger

    def download_month(self, year: int, month: int) -> Optional[Path]:
        """
        Download one MONTH of ERA5 data as a single NetCDF file.

        Returns
        -------
        Path to the final .nc file, or None on failure.
        """
        nc_path = self._raw_dir / f"era5_mandi_{year}{month:02d}.nc"

        # ── Cache check ────────────────────────────────────────────────
        if nc_path.exists() and nc_path.stat().st_size > 0:
            with open(nc_path, "rb") as fh:
                magic = fh.read(4)
            if magic[:4] != b"PK\x03\x04":
                self._logger.info(f"  Cached (valid): {nc_path.name} — skipping.")
                return nc_path
            self._logger.warning(
                f"  Cached file is a ZIP disguised as .nc — deleting and re-downloading: {nc_path.name}"
            )
            nc_path.unlink()

        # Fresh client per call — safe for concurrent threads
        client = cdsapi.Client(url=self._cds_url, key=self._cds_key, quiet=True, verify=True)

        n_days = monthrange(year, month)[1]
        days = [f"{d:02d}" for d in range(1, n_days + 1)]
        hours = [f"{h:02d}:00" for h in range(24)]
        area = [self._bbox["lat_max"], self._bbox["lon_min"],
                self._bbox["lat_min"], self._bbox["lon_max"]]

        request = {
            "product_type": [self._product_type],
            "variable": self._variables,
            "year": [str(year)],
            "month": [f"{month:02d}"],
            "day": days,
            "time": hours,
            "data_format": "netcdf",
            "download_format": "unarchived",
            "area": area,
        }

        n_fields = len(days) * 24 * len(self._variables)
        self._logger.info(
            f"  Requesting CDS: {year}-{month:02d} "
            f"(~{n_fields:,} fields, {len(self._variables)} vars)"
        )

        tmp_path = self._raw_dir / f"era5_mandi_{year}{month:02d}.tmp"

        try:
            t0 = time.perf_counter()
            client.retrieve(self._dataset, request).download(str(tmp_path))
            elapsed = time.perf_counter() - t0
            self._logger.info(f"  CDS request for {year}-{month:02d} completed in {elapsed:.1f}s")
        except Exception as exc:
            msg = str(exc).lower()
            if any(marker in msg for marker in COST_LIMIT_MARKERS):
                self._logger.error(
                    f"  CDS rejected {year}-{month:02d} as too large even at monthly "
                    f"granularity ({exc}). Try reducing the variable list in config.yaml, "
                    f"or shrinking the bounding box."
                )
            else:
                self._logger.error(f"  CDS download failed for {year}-{month:02d}: {exc}")
            tmp_path.unlink(missing_ok=True)
            return None

        with open(tmp_path, "rb") as fh:
            magic = fh.read(4)

        if magic[:4] == b"PK\x03\x04":
            self._logger.info(f"  CDS returned ZIP for {year}-{month:02d} — extracting NetCDF...")
            try:
                with zipfile.ZipFile(tmp_path, "r") as zf:
                    nc_files = [n for n in zf.namelist() if n.lower().endswith(".nc")]
                    if not nc_files:
                        self._logger.error(f"  ZIP contains no .nc files: {zf.namelist()}")
                        tmp_path.unlink(missing_ok=True)
                        return None
                    extracted_name = nc_files[0]
                    zf.extract(extracted_name, self._raw_dir)
                    (self._raw_dir / extracted_name).rename(nc_path)
                    self._logger.info(f"  Extracted: {extracted_name} → {nc_path.name}")
                tmp_path.unlink(missing_ok=True)
            except Exception as exc:
                self._logger.error(f"  ZIP extraction failed: {exc}")
                tmp_path.unlink(missing_ok=True)
                return None
        else:
            tmp_path.rename(nc_path)

        size_mb = nc_path.stat().st_size / 1_048_576
        self._logger.info(f"  Ready: {nc_path.name} ({size_mb:.1f} MB)")
        return nc_path


class ERA5Parser:
    """
    Parses a single ERA5 monthly NetCDF file into a clean DataFrame.
    """

    def __init__(self, bbox: dict, logger) -> None:
        self._bbox = bbox
        self._logger = logger

    def parse(self, nc_path: Path) -> Optional[pd.DataFrame]:
        self._logger.debug(f"Parsing: {nc_path.name}")

        with open(nc_path, "rb") as fh:
            magic = fh.read(4)

        ds = None
        if magic[:4] == b"GRIB":
            self._logger.info(f"  {nc_path.name} is GRIB — using cfgrib engine.")
            try:
                import cfgrib  # noqa: F401
                datasets = xr.open_datasets(nc_path, engine="cfgrib")
                ds = xr.merge(datasets)
            except ImportError:
                self._logger.error("cfgrib not installed. Run: pip install cfgrib eccodes")
                return None
            except Exception as exc:
                self._logger.error(f"Cannot open GRIB {nc_path.name}: {exc}")
                return None
        else:
            for engine in ("netcdf4", "h5netcdf", "scipy"):
                try:
                    ds = xr.open_dataset(nc_path, engine=engine)
                    self._logger.debug(f"  Opened {nc_path.name} with engine='{engine}'")
                    break
                except Exception:
                    continue
            if ds is None:
                self._logger.error(
                    f"Cannot open {nc_path.name}. Magic bytes: {magic.hex()}. "
                    "Run: pip install netcdf4 h5netcdf cfgrib eccodes\n"
                    "Or delete the file and re-run to re-download it."
                )
                return None

        try:
            df = ds.to_dataframe().reset_index()
            ds.close()
            df = df.rename(columns=VARIABLE_RENAME)
            df = df.rename(columns={"latitude": "latitude", "longitude": "longitude",
                                    "valid_time": "time"})

            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"], utc=True)
            elif "valid_time" in df.columns:
                df["time"] = pd.to_datetime(df["valid_time"], utc=True)
                df = df.drop(columns=["valid_time"], errors="ignore")

            for col in ["temperature_2m", "dewpoint_2m"]:
                if col in df.columns:
                    df[col] = df[col] - 273.15

            for col in ["total_precipitation", "convective_precipitation"]:
                if col in df.columns:
                    df[col] = df[col] * 1000.0
                    df.loc[df[col] < 0, col] = 0.0

            for col in ["mslp", "surface_pressure"]:
                if col in df.columns:
                    df[col] = df[col] / 100.0

            if "wind_u_10m" in df.columns and "wind_v_10m" in df.columns:
                df["wind_speed_10m"] = np.sqrt(df["wind_u_10m"]**2 + df["wind_v_10m"]**2)
                df["wind_dir_10m"] = (
                    np.degrees(np.arctan2(-df["wind_u_10m"], -df["wind_v_10m"])) % 360
                )

            df = df.drop(columns=[c for c in ["expver", "number"] if c in df.columns])

            sort_cols = [c for c in ["time", "latitude", "longitude"] if c in df.columns]
            df = df.sort_values(sort_cols).reset_index(drop=True)

            self._logger.debug(f"  Parsed {nc_path.name}: {len(df):,} rows")
            return df

        except Exception as exc:
            self._logger.error(f"Parse error {nc_path.name}: {exc}")
            return None


class ERA5Collector:
    """
    Orchestrates the full ERA5 data collection pipeline.

    Pipeline (per month, submitted CONCURRENTLY)
    ─────────────────────────────────────────────
    1. Download MONTHLY NetCDF from CDS → raw/     (threaded, I/O-bound)
    2. Parse NetCDF → DataFrame
    3. Save cleaned monthly CSV → cleaned/

    After all months:
    4. Write metadata.json
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

        cds_key = self._cfg["api_keys"].get("cds_api_key", "")
        if not cds_key or cds_key == "YOUR_CDS_API_KEY_HERE":
            raise ValueError(
                "CDS API key not configured. Set api_keys.cds_api_key in config/config.yaml.\n"
                "Format: 'UID:API-KEY'\n"
                "Get your key at: https://cds.climate.copernicus.eu → Profile"
            )
        self._cds_url = "https://cds.climate.copernicus.eu/api"
        self._cds_key = cds_key

        self._max_concurrent = int(
            self._src_cfg.get("max_concurrent_downloads", DEFAULT_MAX_CONCURRENT)
        )

        self._downloader = ERA5Downloader(
            cds_url=self._cds_url, cds_key=self._cds_key,
            raw_dir=self._raw_dir, dataset=self._src_cfg["dataset"],
            product_type=self._src_cfg["product_type"], variables=self._src_cfg["variables"],
            bbox=self._bbox, logger=self._logger,
        )
        self._parser = ERA5Parser(bbox=self._bbox, logger=self._logger)

    # ──────────────────────────────────────────────────────────────────────
    #  PUBLIC ENTRY POINT
    # ──────────────────────────────────────────────────────────────────────

    def run(self) -> None:
        self._logger.info("=" * 70)
        self._logger.info("ERA5 Reanalysis Collector — START (monthly + concurrent)")
        self._logger.info(f"Location  : {self._loc['district']}, {self._loc['state']}")
        self._logger.info(
            f"Bbox      : N={self._bbox['lat_max']} S={self._bbox['lat_min']} "
            f"W={self._bbox['lon_min']} E={self._bbox['lon_max']}"
        )
        self._logger.info(f"Period    : {self._start_date} → {self._end_date}")
        self._logger.info(f"Variables : {self._src_cfg['variables']}")
        self._logger.info(f"Concurrent downloads: {self._max_concurrent}")
        self._logger.info("=" * 70)

        year_months = list(self._iter_year_months())
        total_months = len(year_months)
        self._logger.info(f"Plan: {total_months} monthly request(s), {self._max_concurrent} at a time")

        processed = 0
        skipped = 0
        total_records = 0
        total_missing: dict[str, int] = {}

        # ── Concurrent download + parse + save, per month ──────────────
        with ThreadPoolExecutor(max_workers=self._max_concurrent) as executor:
            futures = {
                executor.submit(self._process_month, year, month): (year, month)
                for year, month in year_months
            }

            with tqdm(total=total_months, desc="ERA5 months", unit="month") as pbar:
                for future in as_completed(futures):
                    year, month = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        self._logger.error(f"  {year}-{month:02d} failed with exception: {exc}")
                        result = None

                    if result is None:
                        skipped += 1
                    else:
                        n_recs, missing = result
                        processed += 1
                        total_records += n_recs
                        for col, n in missing.items():
                            total_missing[col] = total_missing.get(col, 0) + n

                    pbar.update(1)

        self._write_metadata(total_records, total_missing)

        self._logger.info("=" * 70)
        self._logger.info("ERA5 Reanalysis Collector — COMPLETE")
        self._logger.info(f"Total months   : {total_months}")
        self._logger.info(f"Processed      : {processed}")
        self._logger.info(f"Skipped        : {skipped}")
        self._logger.info(f"Total records  : {total_records:,}")
        if skipped:
            self._logger.warning(
                f"{skipped} month(s) failed — check the log above for CDS error details "
                f"and re-run (cached months will be skipped automatically)."
            )
        self._logger.info("=" * 70)

    # ──────────────────────────────────────────────────────────────────────
    #  PER-MONTH WORKER  (runs inside a thread)
    # ──────────────────────────────────────────────────────────────────────

    def _process_month(self, year: int, month: int) -> Optional[tuple[int, dict]]:
        """
        Download one month, parse it, save cleaned CSV.
        Runs inside a worker thread — returns (n_records, missing_value_counts)
        or None on failure.
        """
        nc_path = self._downloader.download_month(year, month)
        if nc_path is None:
            return None

        df = self._parser.parse(nc_path)
        if df is None or df.empty:
            self._logger.warning(f"  Parse returned empty for {year}-{month:02d}. Skipping.")
            return None

        csv_path = self._clean_dir / f"era5_mandi_{year}{month:02d}_cleaned.csv"
        df.to_csv(csv_path, index=False)
        size_kb = csv_path.stat().st_size / 1024
        self._logger.info(
            f"  Saved CSV: {csv_path.name} ({size_kb:.0f} KB, {len(df):,} rows)"
        )

        missing: dict[str, int] = {}
        for col in df.select_dtypes(include="number").columns:
            missing[col] = int(df[col].isna().sum())

        return len(df), missing

    # ──────────────────────────────────────────────────────────────────────
    #  PRIVATE HELPERS
    # ──────────────────────────────────────────────────────────────────────

    def _iter_year_months(self) -> Iterator[tuple[int, int]]:
        """
        Yield (year, month) for every calendar month inside
        [start_date, end_date], inclusive.
        """
        start_year, start_month = self._start_date.year, self._start_date.month
        end_year, end_month = self._end_date.year, self._end_date.month

        year, month = start_year, start_month
        while (year, month) <= (end_year, end_month):
            yield year, month
            if month == 12:
                year, month = year + 1, 1
            else:
                month += 1

    def _write_metadata(self, total_records: int, total_missing: dict[str, int]) -> None:
        dummy_df = pd.DataFrame()
        cleaned_csvs = sorted(self._clean_dir.glob("era5_mandi_*_cleaned.csv"))
        cleaned_path = cleaned_csvs[-1] if cleaned_csvs else self._clean_dir / "no_data.csv"
        raw_ncs = sorted(self._raw_dir.glob("era5_mandi_*.nc"))
        raw_path = raw_ncs[0] if raw_ncs else self._raw_dir / "no_data.nc"

        meta = write_metadata(
            source_dir=self._source_dir,
            source_name=self._src_cfg["name"],
            api_url="https://cds.climate.copernicus.eu/api",
            update_frequency=self._src_cfg["update_frequency"],
            df_cleaned=dummy_df,
            raw_file_path=raw_path,
            cleaned_file_path=cleaned_path,
            extra={
                "dataset": self._src_cfg["dataset"],
                "product_type": self._src_cfg["product_type"],
                "variables_requested": self._src_cfg["variables"],
                "variables_derived": ["wind_speed_10m", "wind_dir_10m"],
                "unit_conversions": {
                    "temperature": "K → °C", "precipitation": "m → mm", "pressure": "Pa → hPa",
                },
                "bounding_box": self._bbox,
                "total_records": total_records,
                "missing_values_summary": total_missing,
                "start_date": str(self._start_date),
                "end_date": str(self._end_date),
                "download_strategy": "monthly chunks, concurrent (see module docstring)",
                "max_concurrent_downloads": self._max_concurrent,
            },
        )
        self._logger.info(f"Metadata written: {meta}")

if __name__ == "__main__":
    collector = ERA5Collector()
    collector.run()
