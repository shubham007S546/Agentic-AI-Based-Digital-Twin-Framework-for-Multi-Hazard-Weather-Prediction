"""
collectors/openmeteo_collector.py
══════════════════════════════════════════════════════════════════════════════
SOURCE: Open-Meteo Historical Weather Archive & Forecast API
SCOPE: Grounded hourly meteorological observations and reanalysis for Himachal Pradesh study districts.

Variables:
  • temperature_2m (°C)
  • relative_humidity_2m (%)
  • dew_point_2m (°C)
  • apparent_temperature (°C)
  • precipitation (mm)
  • rain (mm)
  • surface_pressure (hPa)
  • wind_speed_10m (km/h)
  • wind_direction_10m (degrees)
  • wind_gusts_10m (km/h)
  • soil_temperature_0_to_7cm (°C)
  • soil_moisture_0_to_7cm (m³/m³)

Zero synthetic/mock values:
  All data points originate directly from Open-Meteo REST endpoints. If the endpoint
  fails or limits requests, the error is raised or logged with retry backoff.

Usage:
  python -m collectors.openmeteo_collector
  python -m collectors.openmeteo_collector --districts mandi,kullu,chamba --start-date 2024-01-01 --end-date 2024-01-07
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

import pandas as pd
import requests

from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.config_loader import get_config, get_source_paths, get_district_coords, get_active_districts, to_long_path
from utils.logger import get_logger

COLLECTOR_NAME = "openmeteo_collector"
OPENMETEO_ENDPOINTS = [
    "https://archive-api.open-meteo.com/v1/archive",
    "https://historical-forecast-api.open-meteo.com/v1/forecast",
]
OPENMETEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

DEFAULT_HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "apparent_temperature",
    "precipitation",
    "rain",
    "snowfall",
    "surface_pressure",
    "cloud_cover",
    "weather_code",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "soil_temperature_0_to_7cm",
    "soil_moisture_0_to_7cm",
    "cape",
    "lifted_index",
]


class OpenMeteoCollector:
    """
    Production-grade collector for Open-Meteo meteorological datasets.
    Retrieves real hourly records per district and outputs raw and cleaned Parquet/CSV files.
    """

    def __init__(
        self,
        district: str = "mandi",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        variables: Optional[List[str]] = None,
        force: bool = False,
    ) -> None:
        self.district = district.lower()
        self.cfg = get_config()
        self.logger = get_logger(f"{COLLECTOR_NAME}.{self.district}")
        self.force = force

        # Coordinates
        coords = get_district_coords(self.district)
        self.latitude = coords["latitude"]
        self.longitude = coords["longitude"]

        # Date range default: 2022-01-01 to 2024-09-30 (matching DATASET_SCHEME.md)
        global_dates = self.cfg.get("dates", {})
        self.start_date = start_date or global_dates.get("start_date", "2022-01-01")
        self.end_date = end_date or global_dates.get("end_date", "2024-09-30")

        self.variables = variables or DEFAULT_HOURLY_VARIABLES

        # Directories
        paths = get_source_paths("openmeteo")
        self.raw_dir = paths["raw"] if "raw" in paths else paths.get("raw_dir")
        self.clean_dir = paths["cleaned"] if "cleaned" in paths else paths.get("cleaned_dir")
        self.meta_dir = paths["metadata"] if "metadata" in paths else paths.get("metadata_dir")
        self.logs_dir = paths["logs"] if "logs" in paths else paths.get("logs_dir")

        for d in [self.raw_dir, self.clean_dir, self.meta_dir, self.logs_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "himachal-climate-digital-twin/2.0"})
        retries = Retry(
            total=5,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def fetch_time_range(
        self,
        chunk_start: str,
        chunk_end: str,
        max_retries: int = 4,
        backoff_sec: float = 2.0,
    ) -> Optional[pd.DataFrame]:
        """
        Fetch real meteorological observations from Open-Meteo Archive API.
        Enforces retry with exponential backoff on network issues or rate limits.
        """
        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "start_date": chunk_start,
            "end_date": chunk_end,
            "hourly": ",".join(self.variables),
            "timezone": "UTC",
        }

        for endpoint in OPENMETEO_ENDPOINTS:
            for attempt in range(1, max_retries + 1):
                try:
                    self.logger.debug(f"Querying Open-Meteo ({endpoint}): {chunk_start} to {chunk_end} (attempt {attempt})")
                    resp = self.session.get(endpoint, params=params, timeout=20)

                    if resp.status_code == 200:
                        data = resp.json()
                        hourly = data.get("hourly", {})
                        if not hourly or "time" not in hourly:
                            self.logger.warning(f"Empty hourly payload received for {chunk_start} to {chunk_end}")
                            return None

                        df = pd.DataFrame(hourly)
                        df["datetime"] = pd.to_datetime(df["time"], utc=True)
                        df["district"] = self.district
                        df["latitude"] = self.latitude
                        df["longitude"] = self.longitude
                        return df

                    elif resp.status_code == 429:
                        wait_time = backoff_sec * (2 ** (attempt - 1))
                        self.logger.warning(f"Rate limited (429). Backing off for {wait_time:.1f}s...")
                        time.sleep(wait_time)
                    elif resp.status_code in (500, 502, 503, 504):
                        self.logger.warning(f"Endpoint {endpoint} returned {resp.status_code}. Trying alternative endpoint...")
                        break  # Try next endpoint
                    else:
                        self.logger.error(f"HTTP error {resp.status_code}: {resp.text[:200]}")
                        if attempt < max_retries:
                            time.sleep(backoff_sec)

                except requests.RequestException as exc:
                    self.logger.warning(f"Request to {endpoint} failed ({type(exc).__name__}): {exc}. Attempt {attempt}/{max_retries}")
                    if attempt < max_retries:
                        time.sleep(backoff_sec * attempt)

        self.logger.error(f"Failed to fetch data for {chunk_start} to {chunk_end} from all endpoints.")
        return None

    def iter_monthly_chunks(self) -> Generator[Tuple[str, str], None, None]:
        """Generate monthly date slices between start_date and end_date."""
        cur = datetime.strptime(self.start_date, "%Y-%m-%d").date()
        target_end = datetime.strptime(self.end_date, "%Y-%m-%d").date()

        while cur <= target_end:
            # End of month or target_end
            next_month = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
            chunk_end = min(next_month - timedelta(days=1), target_end)
            yield cur.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")
            cur = chunk_end + timedelta(days=1)

    def clean_dataset(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Validate physical meteorological bounds and standardize cleaned dataset.
        Zero fabrication: records violating physical reality are flagged or set to NaN.
        """
        cleaned = df.copy()

        # Remove duplicate datetimes
        cleaned = cleaned.drop_duplicates(subset=["datetime"]).sort_values("datetime")

        # Physical boundary checks
        if "temperature_2m" in cleaned.columns:
            cleaned.loc[(cleaned["temperature_2m"] < -50.0) | (cleaned["temperature_2m"] > 55.0), "temperature_2m"] = None

        if "precipitation" in cleaned.columns:
            cleaned.loc[cleaned["precipitation"] < 0.0, "precipitation"] = 0.0

        if "rain" in cleaned.columns:
            cleaned.loc[cleaned["rain"] < 0.0, "rain"] = 0.0

        if "snowfall" in cleaned.columns:
            cleaned.loc[cleaned["snowfall"] < 0.0, "snowfall"] = 0.0

        if "relative_humidity_2m" in cleaned.columns:
            cleaned.loc[cleaned["relative_humidity_2m"] < 0.0, "relative_humidity_2m"] = 0.0
            cleaned.loc[cleaned["relative_humidity_2m"] > 100.0, "relative_humidity_2m"] = 100.0

        if "cloud_cover" in cleaned.columns:
            cleaned.loc[cleaned["cloud_cover"] < 0.0, "cloud_cover"] = 0.0
            cleaned.loc[cleaned["cloud_cover"] > 100.0, "cloud_cover"] = 100.0

        if "surface_pressure" in cleaned.columns:
            cleaned.loc[(cleaned["surface_pressure"] < 300.0) | (cleaned["surface_pressure"] > 1100.0), "surface_pressure"] = None

        if "wind_speed_10m" in cleaned.columns:
            cleaned.loc[cleaned["wind_speed_10m"] < 0.0, "wind_speed_10m"] = 0.0

        if "cape" in cleaned.columns:
            cleaned.loc[cleaned["cape"] < 0.0, "cape"] = 0.0
            cleaned.loc[cleaned["cape"] > 15000.0, "cape"] = None

        return cleaned

    def run(self) -> Optional[Tuple[Path, Path]]:
        """
        Execute collection for this district across all requested date chunks.
        Saves raw parquet, cleaned parquet, cleaned CSV, and metadata.json.
        """
        self.logger.info(f"Starting Open-Meteo collection for district '{self.district}' ({self.start_date} -> {self.end_date})")

        chunks = list(self.iter_monthly_chunks())
        all_dfs = []

        for c_start, c_end in chunks:
            raw_filename = f"openmeteo_{self.district}_{c_start.replace('-', '')}_{c_end.replace('-', '')}_raw.parquet"
            raw_filepath = self.raw_dir / raw_filename

            # Check if cached chunk already has the complete variables
            if raw_filepath.exists() and not self.force:
                try:
                    cached_chunk = pd.read_parquet(to_long_path(raw_filepath))
                    if all(v in cached_chunk.columns for v in self.variables):
                        self.logger.info(f"Loaded valid cached monthly chunk: {raw_filename} ({len(cached_chunk)} rows)")
                        all_dfs.append(cached_chunk)
                        continue
                except Exception:
                    pass

            df_chunk = self.fetch_time_range(c_start, c_end)
            if df_chunk is not None and not df_chunk.empty:
                # Save monthly raw parquet
                raw_filepath.parent.mkdir(parents=True, exist_ok=True)
                df_chunk.to_parquet(to_long_path(raw_filepath), index=False, engine="pyarrow")
                self.logger.info(f"Saved raw monthly chunk: {raw_filename} ({len(df_chunk)} rows)")
                all_dfs.append(df_chunk)
            time.sleep(0.3)  # polite throttle for public endpoint

        if not all_dfs:
            self.logger.error(f"No data successfully collected for district '{self.district}'")
            return None

        consolidated_df = pd.concat(all_dfs, ignore_index=True)
        raw_all_path = self.raw_dir / f"openmeteo_{self.district}_all_raw.parquet"
        raw_all_path.parent.mkdir(parents=True, exist_ok=True)
        consolidated_df.to_parquet(to_long_path(raw_all_path), index=False, engine="pyarrow")

        # Clean
        cleaned_df = self.clean_dataset(consolidated_df)
        clean_parquet_path = self.clean_dir / f"openmeteo_{self.district}_cleaned.parquet"
        clean_csv_path = self.clean_dir / f"openmeteo_{self.district}_cleaned.csv"
        clean_parquet_path.parent.mkdir(parents=True, exist_ok=True)

        cleaned_df.to_parquet(to_long_path(clean_parquet_path), index=False, engine="pyarrow")
        cleaned_df.to_csv(to_long_path(clean_csv_path), index=False)

        # Hash and metadata
        with open(to_long_path(clean_parquet_path), "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        metadata = {
            "source_id": "openmeteo",
            "district": self.district,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "total_records": len(cleaned_df),
            "columns": list(cleaned_df.columns),
            "sha256": file_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provider": "Open-Meteo Reanalysis/Archive API",
            "is_synthetic": False,
        }

        meta_path = self.meta_dir / f"metadata_{self.district}.json"
        with open(to_long_path(meta_path), "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        self.logger.info(f"Successfully processed {self.district}: {len(cleaned_df)} records saved to {clean_parquet_path.name}")
        return clean_parquet_path, clean_csv_path


# Alias for backward compatibility with older scripts
DistrictOpenMeteoCollector = OpenMeteoCollector


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect real Open-Meteo meteorological data for Himachal Pradesh.")
    parser.add_argument(
        "--districts",
        type=str,
        default=None,
        help="Comma-separated district names (default: active_districts from config.yaml)",
    )
    parser.add_argument("--start-date", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default=None, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    cfg = get_config()
    if args.districts:
        districts = [d.strip().lower() for d in args.districts.split(",")]
    else:
        districts = get_active_districts()

    logger = get_logger(COLLECTOR_NAME)
    logger.info(f"Initiating Open-Meteo collection for districts: {districts}")

    for district in districts:
        collector = OpenMeteoCollector(
            district=district,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        collector.run()

    logger.info("Open-Meteo collection process completed.")


if __name__ == "__main__":
    main()