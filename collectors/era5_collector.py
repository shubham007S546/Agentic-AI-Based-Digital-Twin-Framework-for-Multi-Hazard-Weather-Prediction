"""
collectors/era5_collector.py
══════════════════════════════════════════════════════════════════════════════
SOURCE 4 — ERA5 Reanalysis via Copernicus Climate Data Store (CDS API)

Replaces: WRIS (India-WRIS river basin data)
Reason: ERA5 gives complete, consistent, gridded hourly reanalysis data
        covering the full Mandi bounding box from 1940 onwards.

What this collector does
────────────────────────
  1. Reads all settings from config/config.yaml — no hard-coded values.
  2. Authenticates using the CDS API key from config (api_keys.cds_api_key).
  3. Downloads ERA5 single-level reanalysis in monthly NetCDF chunks,
     cropped to the Mandi bounding box.
  4. Parses each NetCDF, extracts all variables, crops to bbox.
  5. Derives wind speed and direction from U/V components.
  6. Converts units: temperature K→°C, precipitation m→mm, pressure Pa→hPa.
  7. Saves raw NetCDF files and cleaned monthly CSVs.
  8. Writes metadata.json after the full run.

Variables downloaded (from config.yaml → sources.era5.variables)
────────────────────────────────────────────────────────────────
  10m_u_component_of_wind              → wind_u_10m (m/s)
  10m_v_component_of_wind              → wind_v_10m (m/s)
  2m_dewpoint_temperature              → dewpoint_2m (°C)
  2m_temperature                       → temperature_2m (°C)
  mean_sea_level_pressure              → mslp (hPa)
  surface_pressure                     → surface_pressure (hPa)
  total_precipitation                  → total_precipitation (mm)
  total_cloud_cover                    → cloud_cover (0–1)
  convective_precipitation             → convective_precipitation (mm)
  convective_available_potential_energy→ cape (J/kg)

Derived variables (computed after download)
────────────────────────────────────────────
  wind_speed_10m   = sqrt(u² + v²)           m/s
  wind_dir_10m     = atan2(-u, -v) * 180/π   degrees from North

Output files
────────────
  datasets/source_4_era5/raw/era5_mandi_YYYY_MM.nc      (NetCDF per month)
  datasets/source_4_era5/cleaned/era5_mandi_YYYYMM_cleaned.csv
  datasets/source_4_era5/metadata.json
  datasets/source_4_era5/logs/era5_collector_YYYYMMDD.log

Usage
─────
  pip install cdsapi xarray netcdf4 scipy numpy pandas tqdm
  python -m collectors.era5_collector

CDS API key setup
─────────────────
  1. Register at https://cds.climate.copernicus.eu
  2. Go to Profile → API key
  3. Copy your key (format: "UID:KEY")
  4. Paste into config/config.yaml → api_keys.cds_api_key
"""

from __future__ import annotations

import calendar
import sys
import time
from datetime import date
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
POLITENESS_DELAY = 2.0  # seconds between CDS requests

# Mapping: CDS variable name → clean column name in output CSV
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
    Downloads ERA5 monthly NetCDF files from the Copernicus CDS.

    Uses cdsapi.Client, which reads credentials from the CDS API key
    that we inject programmatically from config.yaml.

    Parameters
    ----------
    cds_client : cdsapi.Client
    raw_dir    : Path — destination for NetCDF files
    dataset    : str  — CDS dataset name
    product_type : str
    variables  : list[str] — CDS variable names
    bbox       : dict — lat_min, lat_max, lon_min, lon_max
    logger
    """

    def __init__(
        self,
        cds_client: cdsapi.Client,
        raw_dir: Path,
        dataset: str,
        product_type: str,
        variables: list[str],
        bbox: dict,
        logger,
    ) -> None:
        self._client = cds_client
        self._raw_dir = raw_dir
        self._dataset = dataset
        self._product_type = product_type
        self._variables = variables
        self._bbox = bbox
        self._logger = logger

    def download_month(self, year: int, month: int) -> Optional[Path]:
        """
        Download one month of ERA5 data as a NetCDF file.

        CDS sometimes returns a ZIP archive even when NetCDF is requested
        (magic bytes 504B0304). This method auto-detects and extracts ZIPs.

        Parameters
        ----------
        year  : int
        month : int

        Returns
        -------
        Path to the final .nc file, or None on failure.
        """
        import zipfile

        nc_path = self._raw_dir / f"era5_mandi_{year}_{month:02d}.nc"

        # ── Duplicate / cache check ──────────────────────────────────────
        # Only skip if the cached file is a real NetCDF, not a ZIP
        if nc_path.exists() and nc_path.stat().st_size > 0:
            with open(nc_path, "rb") as fh:
                magic = fh.read(4)
            if magic[:4] != b"PK\x03\x04":  # not a ZIP
                self._logger.info(
                    f"  Cached (valid): {nc_path.name} — skipping."
                )
                return nc_path
            else:
                # It's a ZIP saved with .nc extension — delete and re-download
                self._logger.warning(
                    f"  Cached file is a ZIP disguised as .nc — deleting "
                    f"and re-downloading: {nc_path.name}"
                )
                nc_path.unlink()

        # Build request
        last_day = calendar.monthrange(year, month)[1]
        days = [f"{d:02d}" for d in range(1, last_day + 1)]
        hours = [f"{h:02d}:00" for h in range(24)]
        area = [
            self._bbox["lat_max"],
            self._bbox["lon_min"],
            self._bbox["lat_min"],
            self._bbox["lon_max"],
        ]

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

        self._logger.info(
            f"  Requesting CDS: {year}-{month:02d} "
            f"({len(days)} days × 24 hrs × {len(self._variables)} vars)"
        )

        # Download to a temp path first
        tmp_path = self._raw_dir / f"era5_mandi_{year}_{month:02d}.tmp"

        try:
            self._client.retrieve(self._dataset, request).download(
                str(tmp_path)
            )
        except Exception as exc:
            self._logger.error(
                f"  CDS download failed for {year}-{month:02d}: {exc}"
            )
            tmp_path.unlink(missing_ok=True)
            return None

        # ── Check what CDS actually sent ─────────────────────────────────
        with open(tmp_path, "rb") as fh:
            magic = fh.read(4)

        if magic[:4] == b"PK\x03\x04":
            # CDS returned a ZIP — extract the .nc inside it
            self._logger.info(
                f"  CDS returned ZIP — extracting NetCDF..."
            )
            try:
                with zipfile.ZipFile(tmp_path, "r") as zf:
                    nc_files = [
                        n for n in zf.namelist()
                        if n.lower().endswith(".nc")
                    ]
                    if not nc_files:
                        self._logger.error(
                            f"  ZIP contains no .nc files: {zf.namelist()}"
                        )
                        tmp_path.unlink(missing_ok=True)
                        return None

                    # Extract the first (usually only) .nc file
                    extracted_name = nc_files[0]
                    zf.extract(extracted_name, self._raw_dir)
                    extracted_path = self._raw_dir / extracted_name

                    # Rename to our standard naming convention
                    extracted_path.rename(nc_path)
                    self._logger.info(
                        f"  Extracted: {extracted_name} → {nc_path.name}"
                    )

                tmp_path.unlink(missing_ok=True)

            except Exception as exc:
                self._logger.error(f"  ZIP extraction failed: {exc}")
                tmp_path.unlink(missing_ok=True)
                return None

        else:
            # Already a NetCDF — just rename temp to final
            tmp_path.rename(nc_path)

        size_mb = nc_path.stat().st_size / 1_048_576
        self._logger.info(
            f"  Ready: {nc_path.name} ({size_mb:.1f} MB)"
        )
        return nc_path


class ERA5Parser:
    """
    Parses a single ERA5 NetCDF file into a clean Pandas DataFrame.

    Responsibilities
    ────────────────
    - Open NetCDF with xarray.
    - Extract all variables, flatten to (time, lat, lon) rows.
    - Rename CDS short names to readable column names.
    - Convert units: K→°C, m→mm for precipitation, Pa→hPa for pressure.
    - Derive wind_speed_10m and wind_dir_10m from U/V components.
    - Validate non-negative precipitation.

    Parameters
    ----------
    bbox   : dict
    logger
    """

    def __init__(self, bbox: dict, logger) -> None:
        self._bbox = bbox
        self._logger = logger

    def parse(self, nc_path: Path) -> Optional[pd.DataFrame]:
        """
        Parse one NetCDF file and return a cleaned DataFrame.

        Parameters
        ----------
        nc_path : Path

        Returns
        -------
        pd.DataFrame with columns: time, latitude, longitude, + all variables.
        None on failure.
        """
        self._logger.debug(f"Parsing: {nc_path.name}")

        # ── Detect actual file format from magic bytes ───────────────────
        # CDS sometimes delivers GRIB even when NetCDF is requested.
        # Magic: NetCDF4/HDF5 = \x89HDF  |  GRIB = GRIB  |  NetCDF3 = CDF
        with open(nc_path, "rb") as fh:
            magic = fh.read(4)

        ds = None

        if magic[:4] == b"GRIB":
            self._logger.info(
                f"  {nc_path.name} is GRIB — using cfgrib engine."
            )
            try:
                import cfgrib  # noqa: F401
                datasets = xr.open_datasets(nc_path, engine="cfgrib")
                ds = xr.merge(datasets)
            except ImportError:
                self._logger.error(
                    "cfgrib not installed. Run: pip install cfgrib eccodes"
                )
                return None
            except Exception as exc:
                self._logger.error(
                    f"Cannot open GRIB {nc_path.name}: {exc}"
                )
                return None

        else:
            # NetCDF3 (CDF\x01) or NetCDF4/HDF5 (\x89HDF)
            for engine in ("netcdf4", "h5netcdf", "scipy"):
                try:
                    ds = xr.open_dataset(nc_path, engine=engine)
                    self._logger.debug(
                        f"  Opened {nc_path.name} with engine='{engine}'"
                    )
                    break
                except Exception:
                    continue

            if ds is None:
                self._logger.error(
                    f"Cannot open {nc_path.name}. "
                    f"Magic bytes: {magic.hex()}. "
                    "Run: pip install netcdf4 h5netcdf cfgrib eccodes\n"
                    "Or delete the file and re-run to re-download it."
                )
                return None

        try:
            # Convert to DataFrame — xarray handles the cartesian product
            df = ds.to_dataframe().reset_index()
            ds.close()

            # Rename columns: CDS short name → readable name
            df = df.rename(columns=VARIABLE_RENAME)

            # Rename coordinate columns if present
            df = df.rename(columns={
                "latitude": "latitude",
                "longitude": "longitude",
                "valid_time": "time",
            })

            # Ensure time column is UTC datetime
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"], utc=True)
            elif "valid_time" in df.columns:
                df["time"] = pd.to_datetime(df["valid_time"], utc=True)
                df = df.drop(columns=["valid_time"], errors="ignore")

            # ── Unit conversions ─────────────────────────────────────────
            # Temperature: Kelvin → Celsius
            for col in ["temperature_2m", "dewpoint_2m"]:
                if col in df.columns:
                    df[col] = df[col] - 273.15

            # Precipitation: metres → millimetres
            for col in ["total_precipitation", "convective_precipitation"]:
                if col in df.columns:
                    df[col] = df[col] * 1000.0
                    # Set negative (floating point noise) to 0
                    df.loc[df[col] < 0, col] = 0.0

            # Pressure: Pa → hPa
            for col in ["mslp", "surface_pressure"]:
                if col in df.columns:
                    df[col] = df[col] / 100.0

            # ── Derive wind speed and direction ──────────────────────────
            if "wind_u_10m" in df.columns and "wind_v_10m" in df.columns:
                df["wind_speed_10m"] = np.sqrt(
                    df["wind_u_10m"] ** 2 + df["wind_v_10m"] ** 2
                )
                df["wind_dir_10m"] = (
                    np.degrees(
                        np.arctan2(-df["wind_u_10m"], -df["wind_v_10m"])
                    ) % 360
                )

            # ── Drop expver column if present (CDS metadata artifact) ────
            df = df.drop(
                columns=[c for c in ["expver", "number"] if c in df.columns]
            )

            # ── Sort ─────────────────────────────────────────────────────
            sort_cols = [c for c in ["time", "latitude", "longitude"]
                        if c in df.columns]
            df = df.sort_values(sort_cols).reset_index(drop=True)

            self._logger.debug(
                f"  Parsed {nc_path.name}: {len(df):,} rows"
            )
            return df

        except Exception as exc:
            self._logger.error(f"Parse error {nc_path.name}: {exc}")
            return None


class ERA5Collector:
    """
    Orchestrates the full ERA5 data collection pipeline.

    Pipeline (per month)
    ─────────────────────
    1. Download NetCDF from CDS → raw/
    2. Parse NetCDF → DataFrame
    3. Save monthly cleaned CSV → cleaned/

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

        # ── CDS API client ───────────────────────────────────────────────
        cds_key = self._cfg["api_keys"].get("cds_api_key", "")
        if not cds_key or cds_key == "YOUR_CDS_API_KEY_HERE":
            raise ValueError(
                "CDS API key not configured. "
                "Set api_keys.cds_api_key in config/config.yaml.\n"
                "Format: 'UID:API-KEY'\n"
                "Get your key at: https://cds.climate.copernicus.eu → Profile"
            )

        # Inject key programmatically — no need for ~/.cdsapirc file
        self._cds_client = cdsapi.Client(
            url="https://cds.climate.copernicus.eu/api",
            key=cds_key,
            quiet=True,
            verify=True,
        )

        self._downloader = ERA5Downloader(
            cds_client=self._cds_client,
            raw_dir=self._raw_dir,
            dataset=self._src_cfg["dataset"],
            product_type=self._src_cfg["product_type"],
            variables=self._src_cfg["variables"],
            bbox=self._bbox,
            logger=self._logger,
        )
        self._parser = ERA5Parser(bbox=self._bbox, logger=self._logger)

    # ──────────────────────────────────────────────────────────────────────
    #  PUBLIC ENTRY POINT
    # ──────────────────────────────────────────────────────────────────────

    def run(self) -> None:
        self._logger.info("=" * 70)
        self._logger.info("ERA5 Reanalysis Collector — START")
        self._logger.info(
            f"Location  : {self._loc['district']}, {self._loc['state']}"
        )
        self._logger.info(
            f"Bbox      : N={self._bbox['lat_max']} S={self._bbox['lat_min']} "
            f"W={self._bbox['lon_min']} E={self._bbox['lon_max']}"
        )
        self._logger.info(
            f"Period    : {self._start_date} → {self._end_date}"
        )
        self._logger.info(
            f"Variables : {self._src_cfg['variables']}"
        )
        self._logger.info("=" * 70)

        months = list(self._iter_months())
        total = len(months)
        processed = 0
        skipped = 0
        total_records = 0
        total_missing: dict[str, int] = {}

        for i, (year, month) in enumerate(
            tqdm(months, desc="ERA5 months", unit="month"), start=1
        ):
            self._logger.info(
                f"[{i}/{total}] {year}-{month:02d}"
            )

            # Step 1: Download
            nc_path = self._downloader.download_month(year, month)
            if nc_path is None:
                skipped += 1
                continue

            # Step 2: Parse
            df = self._parser.parse(nc_path)
            if df is None or df.empty:
                self._logger.warning(
                    f"  Parse returned empty for {year}-{month:02d}. Skipping."
                )
                skipped += 1
                continue

            # Step 3: Save cleaned CSV
            csv_path = self._save_cleaned_month(df, year, month)

            # Accumulate stats
            total_records += len(df)
            for col in df.select_dtypes(include="number").columns:
                n_miss = int(df[col].isna().sum())
                total_missing[col] = total_missing.get(col, 0) + n_miss

            processed += 1
            self._logger.info(
                f"  Done: {len(df):,} records → {csv_path.name}"
            )

            time.sleep(POLITENESS_DELAY)

        # Step 4: Metadata
        self._write_metadata(total_records, total_missing)

        # Summary
        self._logger.info("=" * 70)
        self._logger.info("ERA5 Reanalysis Collector — COMPLETE")
        self._logger.info(f"Total months  : {total}")
        self._logger.info(f"Processed     : {processed}")
        self._logger.info(f"Skipped       : {skipped}")
        self._logger.info(f"Total records : {total_records:,}")
        self._logger.info("=" * 70)

    # ──────────────────────────────────────────────────────────────────────
    #  PRIVATE HELPERS
    # ──────────────────────────────────────────────────────────────────────

    def _iter_months(self) -> Iterator[tuple[int, int]]:
        """Yield (year, month) tuples for the configured date range."""
        cur = date(self._start_date.year, self._start_date.month, 1)
        end = date(self._end_date.year, self._end_date.month, 1)
        while cur <= end:
            yield cur.year, cur.month
            if cur.month == 12:
                cur = date(cur.year + 1, 1, 1)
            else:
                cur = date(cur.year, cur.month + 1, 1)

    def _save_cleaned_month(
        self, df: pd.DataFrame, year: int, month: int
    ) -> Path:
        """Save one month's cleaned DataFrame as CSV."""
        csv_path = (
            self._clean_dir / f"era5_mandi_{year}{month:02d}_cleaned.csv"
        )
        df.to_csv(csv_path, index=False)
        size_kb = csv_path.stat().st_size / 1024
        self._logger.info(
            f"  Saved CSV: {csv_path.name} ({size_kb:.0f} KB)"
        )
        return csv_path

    def _write_metadata(
        self,
        total_records: int,
        total_missing: dict[str, int],
    ) -> None:
        dummy_df = pd.DataFrame()
        cleaned_csvs = sorted(
            self._clean_dir.glob("era5_mandi_*_cleaned.csv")
        )
        cleaned_path = (
            cleaned_csvs[-1]
            if cleaned_csvs
            else self._clean_dir / "no_data.csv"
        )
        raw_ncs = sorted(self._raw_dir.glob("era5_mandi_*.nc"))
        raw_path = (
            raw_ncs[0] if raw_ncs else self._raw_dir / "no_data.nc"
        )

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
                    "temperature": "K → °C",
                    "precipitation": "m → mm",
                    "pressure": "Pa → hPa",
                },
                "bounding_box": self._bbox,
                "total_records": total_records,
                "missing_values_summary": total_missing,
                "start_date": str(self._start_date),
                "end_date": str(self._end_date),
            },
        )
        self._logger.info(f"Metadata written: {meta}")


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    collector = ERA5Collector()
    collector.run()