"""
collectors/openmeteo_collector_multi.py
════════════════════════════════════════════════════════════════════════════
Multi-district wrapper for OpenMeteoCollector.

The original openmeteo_collector.py reads cfg["location"] — a single
top-level block hardcoded to Mandi. This meant Kullu and Chamba were never
collected, even though config.yaml already has correct per-district
lat/lon under cfg["districts"].

This version loops over cfg["active_districts"] and runs the same
download/clean/save pipeline once per district, using that district's own
latitude/longitude. Output files are named with the district, matching the
convention already used by era5_collector.py:

    digital_twin/climate_indices/OpenMeteo/cleaned/openmeteo_<district>_cleaned.parquet
    digital_twin/climate_indices/OpenMeteo/cleaned/openmeteo_<district>_cleaned.csv

Usage
─────
    python -m collectors.openmeteo_collector_multi
    python -m collectors.openmeteo_collector_multi --districts kullu,chamba
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.openmeteo_collector import OpenMeteoCollector
from utils.config_loader import get_config
from utils.logger import get_logger

COLLECTOR_NAME = "openmeteo_collector_multi"


class DistrictOpenMeteoCollector(OpenMeteoCollector):
    """
    Same as OpenMeteoCollector, but overrides __init__ to use a specific
    district's lat/lon (from cfg["districts"][district_key]) instead of
    the single hardcoded cfg["location"] block. Also namespaces output
    files by district so runs for different districts don't overwrite
    each other.
    """

    def __init__(self, district_key: str) -> None:
        # Run the parent __init__ first (sets up cfg, dirs, http client, etc.)
        super().__init__()

        self._district_key = district_key
        district_cfg = self._cfg["districts"][district_key]

        # Override location to this district's coordinates
        self._loc = {
            "district": district_key.capitalize(),
            "state": district_cfg.get("state", "Himachal Pradesh"),
            "latitude": district_cfg["latitude"],
            "longitude": district_cfg["longitude"],
        }
        self._lat = float(district_cfg["latitude"])
        self._lon = float(district_cfg["longitude"])

        self._logger.info(
            f"[{district_key}] Using district-specific coordinates: "
            f"lat={self._lat}, lon={self._lon}"
        )

    # ── Override save paths to namespace by district ──────────────────────

    def _save_raw(self, df):
        path = self._raw_dir / f"openmeteo_{self._district_key}_all_raw.parquet"
        df.to_parquet(path, index=False, engine="pyarrow")
        self._logger.info(f"Raw consolidated: {path.name} ({len(df):,} rows)")
        return path

    def _save_cleaned(self, df):
        parquet_path = self._clean_dir / f"openmeteo_{self._district_key}_cleaned.parquet"
        csv_path = self._clean_dir / f"openmeteo_{self._district_key}_cleaned.csv"
        df.to_parquet(parquet_path, index=True, engine="pyarrow")
        df.to_csv(csv_path, index=True)
        size_mb = parquet_path.stat().st_size / 1_048_576
        self._logger.info(f"Cleaned parquet : {parquet_path.name} ({size_mb:.2f} MB)")
        self._logger.info(f"Cleaned CSV     : {csv_path.name}")
        return parquet_path, csv_path

    def _download_all_chunks(self):
        """Same as parent, but namespaces monthly raw files by district."""
        chunks = list(self._iter_monthly_chunks())
        self._logger.info(
            f"[{self._district_key}] Downloading {len(chunks)} monthly chunk(s) "
            f"({self._start_date} → {self._end_date})..."
        )
        import time
        from tqdm import tqdm

        for chunk_start, chunk_end in tqdm(
            chunks, desc=f"Downloading {self._district_key}", unit="month"
        ):
            self._logger.info(f"  Chunk: {chunk_start} → {chunk_end}")
            df = self._fetch_chunk(chunk_start, chunk_end)

            if df is None or df.empty:
                self._logger.warning(f"  {chunk_start}–{chunk_end}: empty, skipping.")
                continue

            fname = f"openmeteo_{self._district_key}_{chunk_start.year}{chunk_start.month:02d}_raw.parquet"
            raw_path = self._raw_dir / fname
            df.to_parquet(raw_path, index=False, engine="pyarrow")
            self._logger.info(f"  Saved: {fname} ({len(df):,} rows)")

            time.sleep(1.0)
            yield df


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Open-Meteo collector for multiple districts.")
    parser.add_argument(
        "--districts",
        type=str,
        default=None,
        help="Comma-separated district keys (e.g. 'kullu,chamba'). Defaults to config.yaml's active_districts minus mandi (already collected).",
    )
    args = parser.parse_args()

    cfg = get_config()

    if args.districts:
        districts = [d.strip().lower() for d in args.districts.split(",")]
    else:
        # Default: only the districts NOT already collected (skip mandi)
        districts = [d for d in cfg.get("active_districts", ["mandi", "kullu", "chamba"]) if d != "mandi"]

    logger = get_logger(COLLECTOR_NAME)
    logger.info(f"Running Open-Meteo collector for districts: {districts}")

    for district in districts:
        if district not in cfg["districts"]:
            logger.error(f"District '{district}' not found in config.yaml districts block. Skipping.")
            continue

        logger.info("=" * 70)
        logger.info(f"STARTING: {district}")
        logger.info("=" * 70)

        try:
            collector = DistrictOpenMeteoCollector(district)
            collector.run()
        except Exception as exc:
            logger.error(f"[{district}] Collector failed: {exc}", exc_info=True)
            continue

    logger.info("All requested districts processed.")


if __name__ == "__main__":
    main()
