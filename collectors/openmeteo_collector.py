"""
collectors/openmeteo_collector.py
══════════════════════════════════════════════════════════════════════════════
SOURCE 5 — Open-Meteo ERA5 Reanalysis Archive (Supplementary)
         ERA5 Historical Weather API
         Endpoint : https://archive-api.open-meteo.com/v1/archive

BUGS FIXED (from original version)
────────────────────────────────────
  BUG 1 — Wrong URL in code
    BEFORE: historical-forecast-api.open-meteo.com  ← causes 500 errors
    AFTER : archive-api.open-meteo.com              ← correct ERA5 endpoint
    WHY   : historical-forecast-api only archives forecast model runs from ~2022.
            The archive-api serves ERA5 reanalysis from 1940 to present.

  BUG 2 — cape and lifted_index requested on archive endpoint
    BEFORE: variables list included cape, lifted_index
    AFTER : both removed from config.yaml and not requested
    WHY   : cape and lifted_index are forecast-model variables.
            They do NOT exist on the ERA5 archive endpoint.
            Requesting them causes HTTP 500 ResponseError.

  BUG 3 — models=best_match sent to archive endpoint
    BEFORE: params included "models": "best_match"
    AFTER : models parameter removed entirely
    WHY   : archive-api does not accept a models parameter.
            Sending it causes a 400 or 500 error.

What this collector does
────────────────────────
  1. Reads all settings from config/config.yaml.
  2. Downloads hourly ERA5 data in monthly chunks (avoids timeout).
  3. Saves each month's raw data as a parquet file.
  4. Concatenates and applies basic cleaning only:
       - parse datetime index
       - remove duplicate timestamps
       - sort chronologically
       - coerce all values to float64
       - NaN-out negative precipitation values
       - log missing value summary
  5. Saves cleaned parquet + CSV.
  6. Writes metadata.json.

Variables available on archive-api (ERA5)
──────────────────────────────────────────
  precipitation, rain, snowfall, temperature_2m, relative_humidity_2m,
  wind_speed_10m, wind_gusts_10m, wind_direction_10m, surface_pressure,
  cloud_cover, weather_code, et0_fao_evapotranspiration,
  soil_temperature_0_to_7cm, soil_moisture_0_to_7cm
  (cape and lifted_index are NOT available — forecast-only)

Install
───────
  pip install openmeteo-requests requests-cache retry-requests pandas pyarrow tqdm

Usage
─────
  python -m collectors.openmeteo_collector
"""

from __future__ import annotations

import calendar
import sys
import time
from datetime import date
from pathlib import Path
from typing import Iterator, Optional

import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.config_loader   import get_config, get_source_dir, get_date_range
from utils.logger          import get_logger
from utils.metadata_writer import write_metadata


SOURCE_KEY     = "openmeteo"
COLLECTOR_NAME = "openmeteo_collector"
POLITENESS_DELAY = 1.0   # seconds between monthly API calls


class OpenMeteoCollector:
    """
    Downloads hourly ERA5 reanalysis weather data for Mandi district
    from Open-Meteo's archive API (archive-api.open-meteo.com).

    Downloads in monthly chunks to avoid API timeout errors.
    All configuration driven by config/config.yaml.
    """

    def __init__(self) -> None:
        self._cfg        = get_config()
        self._src_cfg    = self._cfg["sources"][SOURCE_KEY]
        self._loc        = self._cfg["location"]
        self._source_dir = get_source_dir(SOURCE_KEY)
        self._raw_dir    = self._source_dir / "raw"
        self._clean_dir  = self._source_dir / "cleaned"
        self._log_dir    = self._source_dir / "logs"

        for d in (self._raw_dir, self._clean_dir, self._log_dir):
            d.mkdir(parents=True, exist_ok=True)

        self._logger = get_logger(COLLECTOR_NAME, source_log_dir=self._log_dir)

        # SDK client with cache (avoids re-downloading on restart) and retry
        cache_session  = requests_cache.CachedSession(
            str(self._source_dir / ".om_cache"), expire_after=3600
        )
        retry_session  = retry(cache_session, retries=3, backoff_factor=2.0)
        self._om_client = openmeteo_requests.Client(session=retry_session)

        self._start_date, self._end_date = get_date_range()
        self._lat  = float(self._loc["latitude"])
        self._lon  = float(self._loc["longitude"])
        self._vars = self._src_cfg["variables"]["hourly"]
        self._tz   = self._src_cfg.get("timezone", "Asia/Kolkata")

        # FIX 1: Always use the archive endpoint from config
        self._url = self._src_cfg["base_url"]
        # Verify it is the archive endpoint — warn if wrong
        if "historical-forecast-api" in self._url:
            self._logger.warning(
                "WARNING: base_url points to historical-forecast-api which does NOT "
                "support cape/lifted_index and causes 500 errors. "
                "Fix: set base_url to https://archive-api.open-meteo.com/v1/archive"
            )

        # FIX 2: Verify cape/lifted_index not in variable list
        blocked = {"cape", "lifted_index"}
        bad_vars = blocked.intersection(set(self._vars))
        if bad_vars:
            self._logger.warning(
                f"Removing {bad_vars} from variable list — "
                f"these are NOT available on the archive endpoint and cause 500 errors."
            )
            self._vars = [v for v in self._vars if v not in blocked]

    # ══════════════════════════════════════════════════════════
    #  PUBLIC ENTRY POINT
    # ══════════════════════════════════════════════════════════

    def run(self) -> Path:
        self._logger.info("=" * 70)
        self._logger.info("Open-Meteo ERA5 Archive Collector — START")
        self._logger.info(f"Endpoint  : {self._url}")
        self._logger.info(f"Location  : {self._loc['district']}, {self._loc['state']}")
        self._logger.info(f"Lat/Lon   : {self._lat}, {self._lon}")
        self._logger.info(f"Period    : {self._start_date} → {self._end_date}")
        self._logger.info(f"Variables : {self._vars}")
        self._logger.info(f"Chunks    : Monthly (avoids timeout)")
        self._logger.info("=" * 70)

        raw_dfs = list(self._download_all_chunks())

        if not raw_dfs:
            msg = "No data downloaded. Check internet connection and config."
            self._logger.error(msg)
            raise RuntimeError(f"OpenMeteoCollector: {msg}")

        df_raw = pd.concat(raw_dfs, axis=0, ignore_index=True)
        self._logger.info(
            f"Raw combined: {len(df_raw):,} rows × {len(df_raw.columns)} columns"
        )

        raw_path                    = self._save_raw(df_raw)
        df_cleaned                  = self._clean(df_raw)
        cleaned_parquet, cleaned_csv = self._save_cleaned(df_cleaned)

        meta_path = write_metadata(
            source_dir        = self._source_dir,
            source_name       = self._src_cfg["name"],
            api_url           = self._url,
            update_frequency  = self._src_cfg["update_frequency"],
            df_cleaned        = df_cleaned.reset_index(),
            raw_file_path     = raw_path,
            cleaned_file_path = cleaned_parquet,
            extra={
                "endpoint":               "ERA5 Historical Weather API (archive-api)",
                "variables_downloaded":   self._vars,
                "latitude":               self._lat,
                "longitude":              self._lon,
                "timezone":               self._tz,
                "resolution":             "Hourly (ERA5 reanalysis, ~25km)",
                "chunk_strategy":         "Monthly (avoids timeout)",
                "sdk":                    "openmeteo-requests (FlatBuffers protocol)",
                "cape_available":         False,
                "lifted_index_available": False,
                "era5_coverage":          "1940-01-01 to present",
                "note": (
                    "cape and lifted_index removed — not available on archive endpoint. "
                    "They are forecast-only variables."
                ),
            },
        )

        self._logger.info("=" * 70)
        self._logger.info("Open-Meteo ERA5 Collector — COMPLETE")
        self._logger.info(f"Cleaned rows : {len(df_cleaned):,}")
        self._logger.info(f"CSV          : {cleaned_csv}")
        self._logger.info(f"Parquet      : {cleaned_parquet}")
        self._logger.info(f"Metadata     : {meta_path}")
        self._logger.info("=" * 70)

        return cleaned_parquet

    # ══════════════════════════════════════════════════════════
    #  MONTHLY CHUNK ITERATOR
    # ══════════════════════════════════════════════════════════

    def _iter_monthly_chunks(self) -> Iterator[tuple[date, date]]:
        """
        Yield (chunk_start, chunk_end) one per calendar month.
        Monthly chunks (~720 rows each) are reliable.
        Yearly chunks (~8760 rows) time out on the archive API.
        """
        cur = date(self._start_date.year, self._start_date.month, 1)
        while cur <= self._end_date:
            last_day    = calendar.monthrange(cur.year, cur.month)[1]
            chunk_end   = min(date(cur.year, cur.month, last_day), self._end_date)
            chunk_start = max(cur, self._start_date)
            yield chunk_start, chunk_end
            # Advance to first of next month
            if cur.month == 12:
                cur = date(cur.year + 1, 1, 1)
            else:
                cur = date(cur.year, cur.month + 1, 1)

    # ══════════════════════════════════════════════════════════
    #  DOWNLOAD
    # ══════════════════════════════════════════════════════════

    def _download_all_chunks(self) -> Iterator[pd.DataFrame]:
        chunks = list(self._iter_monthly_chunks())
        self._logger.info(
            f"Downloading {len(chunks)} monthly chunk(s) "
            f"({self._start_date} → {self._end_date})..."
        )

        for chunk_start, chunk_end in tqdm(chunks, desc="Downloading months", unit="month"):
            self._logger.info(f"  Chunk: {chunk_start} → {chunk_end}")
            df = self._fetch_chunk(chunk_start, chunk_end)

            if df is None or df.empty:
                self._logger.warning(f"  {chunk_start}–{chunk_end}: empty, skipping.")
                continue

            # Save monthly raw parquet
            fname    = f"openmeteo_mandi_{chunk_start.year}{chunk_start.month:02d}_raw.parquet"
            raw_path = self._raw_dir / fname
            df.to_parquet(raw_path, index=False, engine="pyarrow")
            self._logger.info(f"  Saved: {fname} ({len(df):,} rows)")

            time.sleep(POLITENESS_DELAY)
            yield df

    def _fetch_chunk(self, start: date, end: date) -> Optional[pd.DataFrame]:
        """
        Fetch one monthly chunk using the openmeteo-requests SDK.

        Key fixes applied here:
          - No 'models' parameter (invalid on archive endpoint)
          - No cape or lifted_index (not available on archive endpoint)
          - URL always points to archive-api (set in __init__)
        """
        params = {
            "latitude":           self._lat,
            "longitude":          self._lon,
            "start_date":         start.strftime("%Y-%m-%d"),
            "end_date":           end.strftime("%Y-%m-%d"),
            "hourly":             self._vars,
            "timezone":           self._tz,
            "wind_speed_unit":    self._src_cfg.get("wind_speed_unit", "kmh"),
            "precipitation_unit": self._src_cfg.get("precipitation_unit", "mm"),
            # FIX 3: NO "models" parameter — not valid on archive endpoint
        }

        try:
            responses = self._om_client.weather_api(self._url, params=params)
            response  = responses[0]
            hourly    = response.Hourly()
            n_vars    = hourly.VariablesLength()

            # Build datetime index from FlatBuffers timestamps
            times = pd.date_range(
                start     = pd.to_datetime(hourly.Time(),    unit="s", utc=True),
                end       = pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
                freq      = pd.Timedelta(seconds=hourly.Interval()),
                inclusive = "left",
            )

            data: dict = {"time": times}
            for i, var_name in enumerate(self._vars):
                if i < n_vars:
                    data[var_name] = hourly.Variables(i).ValuesAsNumpy()
                else:
                    import numpy as np
                    data[var_name] = np.full(len(times), float("nan"))
                    self._logger.warning(f"  '{var_name}' not returned by API — NaN filled.")

            df = pd.DataFrame(data)
            self._logger.info(f"  ✓ {len(df):,} rows × {n_vars} vars ({start} → {end})")
            return df

        except Exception as exc:
            self._logger.error(f"  Fetch failed {start}–{end}: {type(exc).__name__}: {exc}")
            return None

    # ══════════════════════════════════════════════════════════
    #  BASIC CLEANING  (no feature engineering)
    # ══════════════════════════════════════════════════════════

    def _clean(self, df: pd.DataFrame) -> pd.DataFrame:
        self._logger.info("Cleaning: starting basic cleaning pipeline...")
        df = df.copy()
        original_rows = len(df)

        # Parse datetime → UTC-aware index
        df["time"] = pd.to_datetime(df["time"], errors="coerce", utc=True)
        df = df.set_index("time")
        df.index.name = "datetime_utc"

        # Remove duplicate timestamps
        dupes = df.index.duplicated(keep="first").sum()
        if dupes > 0:
            self._logger.warning(f"  Removing {dupes} duplicate timestamps.")
            df = df[~df.index.duplicated(keep="first")]

        # Sort chronologically
        df = df.sort_index()

        # Coerce all value columns to float64
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

        # NaN-out negative precipitation values (physically impossible)
        precip_cols = [c for c in df.columns if "precipitation" in c or c in ("rain", "snowfall")]
        for col in precip_cols:
            neg = int((df[col] < 0).sum())
            if neg > 0:
                df.loc[df[col] < 0, col] = float("nan")
                self._logger.warning(f"  {neg} negative values in '{col}' → NaN.")

        # Missing value summary
        self._logger.info("  Missing value summary:")
        for col in df.columns:
            n = int(df[col].isna().sum())
            if n > 0:
                self._logger.warning(f"    {col:<35}: {n:>5} missing ({n/len(df)*100:.1f}%)")
            else:
                self._logger.info(f"    {col:<35}: 0 missing")

        self._logger.info(
            f"  Cleaning complete: {original_rows:,} → {len(df):,} rows"
        )
        return df

    # ══════════════════════════════════════════════════════════
    #  SAVE
    # ══════════════════════════════════════════════════════════

    def _save_raw(self, df: pd.DataFrame) -> Path:
        path = self._raw_dir / "openmeteo_mandi_all_raw.parquet"
        df.to_parquet(path, index=False, engine="pyarrow")
        self._logger.info(f"Raw consolidated: {path.name} ({len(df):,} rows)")
        return path

    def _save_cleaned(self, df: pd.DataFrame) -> tuple[Path, Path]:
        parquet_path = self._clean_dir / "openmeteo_mandi_cleaned.parquet"
        csv_path     = self._clean_dir / "openmeteo_mandi_cleaned.csv"
        df.to_parquet(parquet_path, index=True, engine="pyarrow")
        df.to_csv(csv_path, index=True)
        size_mb = parquet_path.stat().st_size / 1_048_576
        self._logger.info(f"Cleaned parquet : {parquet_path.name} ({size_mb:.2f} MB)")
        self._logger.info(f"Cleaned CSV     : {csv_path.name}")
        return parquet_path, csv_path


if __name__ == "__main__":
    collector = OpenMeteoCollector()
    collector.run()