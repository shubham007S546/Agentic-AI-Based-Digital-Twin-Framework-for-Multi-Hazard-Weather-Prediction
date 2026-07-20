"""
collectors/era5_collector.py
══════════════════════════════════════════════════════════════════════════════
SOURCE — ERA5 Atmospheric Reanalysis via Copernicus Climate Data Store (CDS API)

SCOPE: ERA5 ATMOSPHERIC REANALYSIS ONLY
────────────────────────────────────────
  This collector is strictly for ERA5 single-level atmospheric reanalysis.
  ERA5-Land variables (soil moisture, runoff, skin temperature, etc.) are
  handled by the separate era5_land_collector.py.

  Variables collected here:
    • 2m_temperature
    • 2m_dewpoint_temperature
    • surface_pressure
    • 10m_u_component_of_wind
    • 10m_v_component_of_wind
    • total_column_water_vapour
    • convective_available_potential_energy (CAPE)
    • total_precipitation

  Derived variables computed after download:
    • wind_speed_10m      — from U/V components
    • wind_dir_10m        — from U/V components
    • relative_humidity   — from 2m temperature and dewpoint (Magnus formula)

WHY MONTHLY + CONCURRENT (NOT YEARLY)
────────────────────────────────────────────────────────
  The previous "yearly chunk" version tried to cut queue-wait overhead by
  requesting a full year (365×24×10 ≈ 87,600 fields) in one call. That
  looked safe under CDS's OLD field-count limit, but the CURRENT CDS-Beta
  backend prices requests using its own "cost" metric that also weights
  bounding-box area and grid resolution — not just raw field count. Every
  one of those yearly requests came back with:

      "Cost limits exceeded... your request is too large, please reduce
      your selection."

  So: yearly requests are no longer viable at 8 variables over the HP bbox.
  The fix is MONTHLY requests (a month × 24h × 8 vars × HP area is
  comfortably under any version of CDS's cost cap), submitted CONCURRENTLY
  via ThreadPoolExecutor. You lose the "12x fewer requests" win, but you
  keep most of the speedup from parallel queue-waiting, and every request
  actually succeeds.

SPATIAL COVERAGE
────────────────────────────────────────────────────────
  • Download: full Himachal Pradesh bounding box (from config).
  • Extract: data is spatially clipped to individual district boundaries
    using GeoJSON files. Currently configured districts: Mandi, Kullu,
    Chamba (all driven by config — no hard-coded district names).
  • Each district gets its own cleaned CSV per month.

What this collector does
────────────────────────
  1. Reads all settings from config/config.yaml — no hard-coded values.
  2. Authenticates using the CDS API key from config (api_keys.cds_api_key).
  3. Downloads ERA5 single-level reanalysis in MONTHLY NetCDF chunks,
     cropped to the HP bounding box, submitted concurrently.
  4. Parses each NetCDF, extracts all variables.
  5. Derives wind speed, wind direction, and relative humidity.
  6. Converts units: temperature K→°C, precipitation m→mm, pressure Pa→hPa.
  7. Clips grid points to per-district GeoJSON boundaries.
  8. Saves raw monthly NetCDF files and per-district cleaned monthly CSVs.
  9. Writes metadata.json after the full run.

Output files
─────────────
  datasets/digital_twin/climate/ERA5/raw/era5_himachal_{YYYYMM}.nc
  datasets/digital_twin/climate/ERA5/cleaned/{district}/era5_{district}_{YYYYMM}_cleaned.csv
  datasets/digital_twin/climate/ERA5/metadata.json
  datasets/digital_twin/climate/ERA5/logs/era5_collector_YYYYMMDD.log

Usage
─────
  pip install cdsapi xarray netcdf4 scipy numpy pandas tqdm shapely geopandas
  python -m collectors.era5_collector

Config options (config.yaml → sources.era5)
──────────────────────────────────────────────
  dataset:             reanalysis-era5-single-levels
  product_type:        reanalysis
  variables:           [list of 8 ERA5 atmospheric variables — see above]
  max_concurrent_downloads: 3
    # CDS accounts typically allow a small number of concurrent queued
    # requests per user — going much above ~4-5 risks CDS queuing your
    # requests behind each other.
  geojson_dir:         data/boundaries/   # directory containing district .geojson files
  districts:           [mandi, kullu, chamba]
    # Each entry must have a matching <district>.geojson in geojson_dir.

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
    print("Run: pip install cdsapi xarray netcdf4 scipy numpy pandas tqdm shapely geopandas")
    sys.exit(1)


SOURCE_KEY = "era5"
COLLECTOR_NAME = "era5_collector"
DEFAULT_MAX_CONCURRENT = 3   # concurrent CDS requests — see module docstring

# ERA5 Atmospheric Reanalysis — the ONLY dataset this collector is responsible for.
# ERA5-Land variables are handled by era5_land_collector.py.
ERA5_DATASET = "reanalysis-era5-single-levels"

# Substrings CDS uses in its "too large" error — used to give a clearer
# log message (and would be the hook point if you ever add auto-splitting).
COST_LIMIT_MARKERS = ("cost limit", "too large", "reduce your selection")

# Canonical ERA5 short-name → project column-name mapping.
# Only ERA5 atmospheric variables are listed here; ERA5-Land variables
# (e.g. stl1, swvl1, ro) must NOT be added to this collector.
VARIABLE_RENAME = {
    "u10":  "wind_u_10m",
    "v10":  "wind_v_10m",
    "d2m":  "dewpoint_2m",
    "t2m":  "temperature_2m",
    "sp":   "surface_pressure",
    "tp":   "total_precipitation",
    "tcwv": "total_column_water_vapour",
    "cape": "cape",
}

# Magnus-formula constants for relative humidity derivation (WMO standard).
_MAGNUS_A = 17.625
_MAGNUS_B = 243.04   # °C


def _relative_humidity(t_celsius: "pd.Series", td_celsius: "pd.Series") -> "pd.Series":
    """
    Compute relative humidity (%) from temperature and dewpoint (both in °C)
    using the Magnus formula.

        RH = 100 × exp(a·Td / (b+Td)) / exp(a·T / (b+T))

    Returns values clipped to [0, 100].
    """
    gamma_t  = _MAGNUS_A * t_celsius  / (_MAGNUS_B + t_celsius)
    gamma_td = _MAGNUS_A * td_celsius / (_MAGNUS_B + td_celsius)
    rh = 100.0 * np.exp(gamma_td - gamma_t)
    return rh.clip(0.0, 100.0)


class DistrictClipper:
    """
    Clips a DataFrame (with 'latitude' and 'longitude' columns) to grid
    points that fall inside a district polygon loaded from a GeoJSON file.

    Lazy-loads geopandas/shapely on first use so the rest of the collector
    still works if those libraries are absent (it will just skip clipping).
    """

    def __init__(self, geojson_dir: Path, districts: list[str], logger) -> None:
        self._geojson_dir = Path(geojson_dir)
        self._districts = [d.lower() for d in districts]
        self._logger = logger
        self._geometries: dict[str, object] = {}   # district → shapely geometry
        self._gp_available: Optional[bool] = None  # None = not yet checked

    def _ensure_geopandas(self) -> bool:
        if self._gp_available is None:
            try:
                import geopandas as gpd          # noqa: F401
                from shapely.geometry import Point  # noqa: F401
                self._gp_available = True
            except ImportError:
                self._logger.warning(
                    "geopandas/shapely not installed — district clipping will be skipped. "
                    "Run: pip install geopandas shapely"
                )
                self._gp_available = False
        return self._gp_available

    def _load_geometry(self, district: str):
        """Load and cache the union geometry for a district from its GeoJSON."""
        if district in self._geometries:
            return self._geometries[district]

        import geopandas as gpd

        geojson_path = self._geojson_dir / f"{district}.geojson"
        if not geojson_path.exists():
            self._logger.warning(
                f"GeoJSON not found for district '{district}': {geojson_path}. "
                "Skipping clip for this district."
            )
            self._geometries[district] = None
            return None

        gdf = gpd.read_file(geojson_path)
        self._geometries[district] = gdf.geometry.union_all()
        self._logger.debug(f"Loaded boundary for '{district}' from {geojson_path.name}")
        return self._geometries[district]

    def clip(self, df: pd.DataFrame, district: str) -> pd.DataFrame:
        """
        Return rows whose (longitude, latitude) grid point falls inside
        the district boundary. Falls back to the full HP DataFrame if
        geopandas is unavailable or the GeoJSON is missing.
        """
        if not self._ensure_geopandas():
            return df

        from shapely.geometry import Point
        from shapely.vectorized import contains as shp_contains

        geometry = self._load_geometry(district)
        if geometry is None:
            return df

        # Vectorised point-in-polygon using shapely.vectorized for speed.
        try:
            mask = shp_contains(geometry, df["longitude"].values, df["latitude"].values)
        except Exception:
            # shapely.vectorized may not exist in all versions; fall back to row-wise.
            mask = df.apply(
                lambda row: geometry.contains(Point(row["longitude"], row["latitude"])),
                axis=1,
            ).values

        clipped = df[mask].copy()
        self._logger.debug(
            f"  Clipped '{district}': {len(df):,} HP rows → {len(clipped):,} district rows"
        )
        return clipped


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
        nc_path = self._raw_dir / f"era5_himachal_{year}{month:02d}.nc"

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
            f"(~{n_fields:,} fields, {len(self._variables)} vars, HP bbox)"
        )

        tmp_path = self._raw_dir / f"era5_himachal_{year}{month:02d}.tmp"

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
    Parses a single ERA5 monthly NetCDF file into a clean DataFrame
    covering the full Himachal Pradesh extent.

    Unit conversions applied:
      temperature_2m, dewpoint_2m : K → °C
      total_precipitation         : m → mm  (negatives clamped to 0)
      surface_pressure            : Pa → hPa

    Derived variables added:
      wind_speed_10m   : sqrt(u² + v²)
      wind_dir_10m     : meteorological convention (degrees from North)
      relative_humidity: Magnus formula from temperature and dewpoint (%)
    """

    def __init__(self, logger) -> None:
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

            # ── Rename columns ─────────────────────────────────────────
            df = df.rename(columns=VARIABLE_RENAME)
            df = df.rename(columns={"valid_time": "time"})

            if "time" not in df.columns and "valid_time" in df.columns:
                df["time"] = pd.to_datetime(df["valid_time"], utc=True)
                df = df.drop(columns=["valid_time"], errors="ignore")
            elif "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"], utc=True)

            # ── Unit conversions ───────────────────────────────────────
            for col in ["temperature_2m", "dewpoint_2m"]:
                if col in df.columns:
                    df[col] = df[col] - 273.15

            for col in ["total_precipitation"]:
                if col in df.columns:
                    df[col] = df[col] * 1000.0
                    df.loc[df[col] < 0, col] = 0.0

            for col in ["surface_pressure"]:
                if col in df.columns:
                    df[col] = df[col] / 100.0

            # ── Derived: wind speed and direction ──────────────────────
            if "wind_u_10m" in df.columns and "wind_v_10m" in df.columns:
                df["wind_speed_10m"] = np.sqrt(
                    df["wind_u_10m"] ** 2 + df["wind_v_10m"] ** 2
                )
                df["wind_dir_10m"] = (
                    np.degrees(np.arctan2(-df["wind_u_10m"], -df["wind_v_10m"])) % 360
                )

            # ── Derived: relative humidity (Magnus formula) ────────────
            if "temperature_2m" in df.columns and "dewpoint_2m" in df.columns:
                df["relative_humidity"] = _relative_humidity(
                    df["temperature_2m"], df["dewpoint_2m"]
                )

            # ── Drop internal CDS bookkeeping columns ──────────────────
            df = df.drop(columns=[c for c in ["expver", "number"] if c in df.columns])

            sort_cols = [c for c in ["time", "latitude", "longitude"] if c in df.columns]
            df = df.sort_values(sort_cols).reset_index(drop=True)

            self._logger.debug(f"  Parsed {nc_path.name}: {len(df):,} rows (HP extent)")
            return df

        except Exception as exc:
            self._logger.error(f"Parse error {nc_path.name}: {exc}")
            return None


class ERA5Collector:
    """
    Orchestrates the full ERA5 Atmospheric Reanalysis data collection pipeline.

    Pipeline (per month, submitted CONCURRENTLY)
    ─────────────────────────────────────────────
    1. Download MONTHLY NetCDF from CDS (HP bbox) → raw/       (threaded)
    2. Parse NetCDF → HP-wide DataFrame with unit conversions + derived vars
    3. Clip to each district using its GeoJSON boundary
    4. Save one cleaned CSV per district per month → cleaned/<district>/

    After all months:
    5. Write metadata.json
    """

    def __init__(self) -> None:
        self._cfg = get_config()
        self._src_cfg = self._cfg["sources"][SOURCE_KEY]
        self._loc = self._cfg["location"]

        # ── Output directory: datasets/digital_twin/climate/ERA5/ ──────
        # Driven by config; falls back to the hardcoded project path only
        # if the config key is absent (backward-compat guard).
        output_root = Path(
            self._src_cfg.get(
                "output_dir",
                "datasets/digital_twin/climate/ERA5"
            )
        )
        self._source_dir = output_root
        self._raw_dir    = output_root / "raw"
        self._clean_dir  = output_root / "cleaned"
        self._log_dir    = output_root / "logs"

        for d in (self._raw_dir, self._clean_dir, self._log_dir):
            d.mkdir(parents=True, exist_ok=True)

        self._logger = get_logger(COLLECTOR_NAME, source_log_dir=self._log_dir)

        # ── Bounding box: Himachal Pradesh extent (from config) ─────────
        self._bbox = self._src_cfg.get(
            "himachal_bbox",
            self._cfg["location"]["bounding_box"],   # fallback: whatever bbox is in location
        )

        self._start_date, self._end_date = get_date_range()

        # ── CDS credentials ─────────────────────────────────────────────
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

        # ── District clipping ────────────────────────────────────────────
        geojson_dir = Path(self._src_cfg.get("geojson_dir", "data/boundaries"))
        self._districts: list[str] = [
            d.lower() for d in self._src_cfg.get("districts", [])
        ]
        self._clipper = DistrictClipper(geojson_dir, self._districts, self._logger)

        # Pre-create per-district output directories
        for district in self._districts:
            (self._clean_dir / district).mkdir(parents=True, exist_ok=True)

        # ── Validate dataset is ERA5 atmospheric (not ERA5-Land) ─────────
        dataset = self._src_cfg.get("dataset", ERA5_DATASET)
        if "land" in dataset.lower():
            raise ValueError(
                f"Dataset '{dataset}' looks like ERA5-Land. "
                "This collector is for ERA5 atmospheric reanalysis only. "
                "Use era5_land_collector.py for ERA5-Land variables."
            )

        self._downloader = ERA5Downloader(
            cds_url=self._cds_url, cds_key=self._cds_key,
            raw_dir=self._raw_dir,
            dataset=dataset,
            product_type=self._src_cfg["product_type"],
            variables=self._src_cfg["variables"],
            bbox=self._bbox,
            logger=self._logger,
        )
        self._parser = ERA5Parser(logger=self._logger)

    # ──────────────────────────────────────────────────────────────────────
    #  PUBLIC ENTRY POINT
    # ──────────────────────────────────────────────────────────────────────

    def run(self) -> None:
        self._logger.info("=" * 70)
        self._logger.info("ERA5 Atmospheric Reanalysis Collector — START (monthly + concurrent)")
        self._logger.info(f"Coverage  : Himachal Pradesh")
        self._logger.info(
            f"Bbox (HP) : N={self._bbox['lat_max']} S={self._bbox['lat_min']} "
            f"W={self._bbox['lon_min']} E={self._bbox['lon_max']}"
        )
        self._logger.info(f"Districts : {self._districts or '(none — HP-wide only)'}")
        self._logger.info(f"Period    : {self._start_date} → {self._end_date}")
        self._logger.info(f"Variables : {self._src_cfg['variables']}")
        self._logger.info(f"Derived   : wind_speed_10m, wind_dir_10m, relative_humidity")
        self._logger.info(f"Concurrent downloads: {self._max_concurrent}")
        self._logger.info("=" * 70)

        year_months = list(self._iter_year_months())
        total_months = len(year_months)
        self._logger.info(
            f"Plan: {total_months} monthly request(s), {self._max_concurrent} at a time"
        )

        processed = 0
        skipped = 0
        total_records: dict[str, int] = {}          # district → row count
        total_missing: dict[str, dict[str, int]] = {}

        # ── Concurrent download + parse + clip + save, per month ───────
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
                        self._logger.error(
                            f"  {year}-{month:02d} failed with exception: {exc}"
                        )
                        result = None

                    if result is None:
                        skipped += 1
                    else:
                        district_results = result
                        processed += 1
                        for district, (n_recs, missing) in district_results.items():
                            total_records[district] = total_records.get(district, 0) + n_recs
                            if district not in total_missing:
                                total_missing[district] = {}
                            for col, n in missing.items():
                                total_missing[district][col] = (
                                    total_missing[district].get(col, 0) + n
                                )

                    pbar.update(1)

        self._write_metadata(total_records, total_missing)

        self._logger.info("=" * 70)
        self._logger.info("ERA5 Atmospheric Reanalysis Collector — COMPLETE")
        self._logger.info(f"Total months   : {total_months}")
        self._logger.info(f"Processed      : {processed}")
        self._logger.info(f"Skipped        : {skipped}")
        for district, n in total_records.items():
            self._logger.info(f"  Records [{district}]: {n:,}")
        if skipped:
            self._logger.warning(
                f"{skipped} month(s) failed — check the log above for CDS error details "
                f"and re-run (cached months will be skipped automatically)."
            )
        self._logger.info("=" * 70)

    # ──────────────────────────────────────────────────────────────────────
    #  PER-MONTH WORKER  (runs inside a thread)
    # ──────────────────────────────────────────────────────────────────────

    def _process_month(
        self, year: int, month: int
    ) -> Optional[dict[str, tuple[int, dict]]]:
        """
        Download one month (HP bbox), parse it, clip to each district,
        save per-district cleaned CSVs.

        Runs inside a worker thread.

        Returns
        -------
        dict: { district_name: (n_records, missing_value_counts) }
        or None on download/parse failure.
        """
        nc_path = self._downloader.download_month(year, month)
        if nc_path is None:
            return None

        df_hp = self._parser.parse(nc_path)
        if df_hp is None or df_hp.empty:
            self._logger.warning(f"  Parse returned empty for {year}-{month:02d}. Skipping.")
            return None

        results: dict[str, tuple[int, dict]] = {}

        # If no districts configured, save the raw HP-wide CSV as a fallback.
        if not self._districts:
            label = "himachal"
            csv_path = self._clean_dir / f"era5_himachal_{year}{month:02d}_cleaned.csv"
            df_hp.to_csv(csv_path, index=False)
            size_kb = csv_path.stat().st_size / 1024
            self._logger.info(
                f"  Saved HP-wide CSV: {csv_path.name} ({size_kb:.0f} KB, {len(df_hp):,} rows)"
            )
            missing = {
                col: int(df_hp[col].isna().sum())
                for col in df_hp.select_dtypes(include="number").columns
            }
            results[label] = (len(df_hp), missing)
            return results

        # Per-district clip and save
        for district in self._districts:
            df_district = self._clipper.clip(df_hp, district)

            if df_district.empty:
                self._logger.warning(
                    f"  No grid points inside '{district}' boundary for "
                    f"{year}-{month:02d} — check the GeoJSON resolution vs. ERA5 grid spacing."
                )
                results[district] = (0, {})
                continue

            csv_path = (
                self._clean_dir / district
                / f"era5_{district}_{year}{month:02d}_cleaned.csv"
            )
            df_district.to_csv(csv_path, index=False)
            size_kb = csv_path.stat().st_size / 1024
            self._logger.info(
                f"  Saved CSV [{district}]: {csv_path.name} "
                f"({size_kb:.0f} KB, {len(df_district):,} rows)"
            )

            missing = {
                col: int(df_district[col].isna().sum())
                for col in df_district.select_dtypes(include="number").columns
            }
            results[district] = (len(df_district), missing)

        return results

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

    def _write_metadata(
        self,
        total_records: dict[str, int],
        total_missing: dict[str, dict[str, int]],
    ) -> None:
        dummy_df = pd.DataFrame()

        # Point metadata at the most recent files for reference paths
        cleaned_csvs: list[Path] = []
        for district in self._districts or ["himachal"]:
            district_dir = self._clean_dir / (district if self._districts else "")
            cleaned_csvs.extend(sorted(district_dir.glob("era5_*_cleaned.csv")))
        cleaned_path = cleaned_csvs[-1] if cleaned_csvs else self._clean_dir / "no_data.csv"

        raw_ncs = sorted(self._raw_dir.glob("era5_himachal_*.nc"))
        raw_path = raw_ncs[0] if raw_ncs else self._raw_dir / "no_data.nc"

        meta = write_metadata(
            source_dir=self._source_dir,
            source_name=self._src_cfg.get("name", "ERA5 Atmospheric Reanalysis"),
            api_url="https://cds.climate.copernicus.eu/api",
            update_frequency=self._src_cfg.get("update_frequency", "monthly"),
            df_cleaned=dummy_df,
            raw_file_path=raw_path,
            cleaned_file_path=cleaned_path,
            extra={
                # ── Dataset identity ────────────────────────────────────
                "dataset_type":        "ERA5 Atmospheric Reanalysis (single-levels)",
                "dataset":             self._src_cfg.get("dataset", ERA5_DATASET),
                "product_type":        self._src_cfg.get("product_type", "reanalysis"),
                # ── Resolution ──────────────────────────────────────────
                "spatial_resolution":  "0.25° × 0.25° (~28 km)",
                "temporal_resolution": "hourly",
                # ── Coverage ────────────────────────────────────────────
                "coverage":            "Himachal Pradesh, India",
                "bounding_box":        self._bbox,
                "extracted_districts": self._districts,
                # ── Variables ───────────────────────────────────────────
                "variables_downloaded": self._src_cfg.get("variables", []),
                "variables_derived": [
                    "wind_speed_10m",
                    "wind_dir_10m",
                    "relative_humidity",
                ],
                "unit_conversions": {
                    "temperature":   "K → °C",
                    "dewpoint":      "K → °C",
                    "precipitation": "m → mm",
                    "pressure":      "Pa → hPa",
                },
                # ── Period & record counts ───────────────────────────────
                "start_date":              str(self._start_date),
                "end_date":                str(self._end_date),
                "records_per_district":    total_records,
                "missing_values_summary":  total_missing,
                # ── Download strategy ────────────────────────────────────
                "download_strategy":            "monthly chunks, concurrent (see module docstring)",
                "max_concurrent_downloads":     self._max_concurrent,
                "note_era5_land":               (
                    "ERA5-Land variables are NOT collected here. "
                    "Use era5_land_collector.py for soil moisture, runoff, skin temperature, etc."
                ),
            },
        )
        self._logger.info(f"Metadata written: {meta}")


if __name__ == "__main__":
    collector = ERA5Collector()
    collector.run()