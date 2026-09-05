"""
collectors/imd_collector_multi.py
════════════════════════════════════════════════════════════════════════════
Multi-district wrapper for IMDCollector.

The original imd_collector.py reads cfg["location"]["bounding_box"] — a
single bbox hardcoded to Mandi. This meant Kullu and Chamba were never
collected, even though config.yaml has boundary GeoJSON files for all
three districts under digital_twin/metadata/boundaries/.

This version loops over cfg["active_districts"], derives each district's
bounding box from its GeoJSON boundary file (with a small buffer so the
IMD 0.25° grid has margin around the district edge), and runs the same
download/parse/clean/save pipeline per district.

Falls back to a fixed-size buffer around the district's lat/lon centroid
(same span as Mandi's existing bbox: ~0.6° lat x ~1.0° lon) if geopandas
or the boundary file isn't available — this is an approximation, so a
warning is logged when the fallback is used.

Output files (namespaced by district, matching era5_collector.py convention):
    datasets/source_1_imd/cleaned/imd_<district>_YYYY_cleaned.csv

Usage
─────
    python -m collectors.imd_collector_multi
    python -m collectors.imd_collector_multi --districts kullu,chamba
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from tqdm import tqdm

from collectors.imd_collector import IMDDownloader, IMDParser
from utils.config_loader import get_config, get_source_dir, get_date_range
from utils.logger import get_logger
from utils.metadata_writer import write_metadata

SOURCE_KEY = "imd"
COLLECTOR_NAME = "imd_collector_multi"

# Fallback buffer (degrees) around district centroid if boundary GeoJSON
# can't be read. Matches Mandi's existing bbox span (lat 31.5-32.1 = 0.6,
# lon 76.5-77.5 = 1.0), applied symmetrically around the centroid.
FALLBACK_LAT_BUFFER = 0.3
FALLBACK_LON_BUFFER = 0.5


def get_district_bbox(district_key: str, district_cfg: dict, logger) -> dict:
    """
    Derive a bounding box for the district, preferring its GeoJSON
    boundary file (config: districts.<district>.boundary) over a fallback
    buffer around lat/lon.
    """
    boundary_path = Path(district_cfg.get("boundary", ""))

    if boundary_path.exists():
        try:
            import geopandas as gpd
            gdf = gpd.read_file(boundary_path)
            minx, miny, maxx, maxy = gdf.total_bounds
            # Small margin so the IMD 0.25° grid has coverage at the edges
            margin = 0.15
            bbox = {
                "lat_min": float(miny - margin),
                "lat_max": float(maxy + margin),
                "lon_min": float(minx - margin),
                "lon_max": float(maxx + margin),
            }
            logger.info(f"[{district_key}] bbox from boundary GeoJSON: {bbox}")
            return bbox
        except ImportError:
            logger.warning(
                f"[{district_key}] geopandas not installed — falling back to "
                f"lat/lon buffer bbox. Run: pip install geopandas"
            )
        except Exception as exc:
            logger.warning(
                f"[{district_key}] Failed to read boundary GeoJSON ({exc}) — "
                f"falling back to lat/lon buffer bbox."
            )
    else:
        logger.warning(
            f"[{district_key}] Boundary file not found at {boundary_path} — "
            f"falling back to lat/lon buffer bbox."
        )

    # Fallback: buffer around centroid
    lat = float(district_cfg["latitude"])
    lon = float(district_cfg["longitude"])
    bbox = {
        "lat_min": lat - FALLBACK_LAT_BUFFER,
        "lat_max": lat + FALLBACK_LAT_BUFFER,
        "lon_min": lon - FALLBACK_LON_BUFFER,
        "lon_max": lon + FALLBACK_LON_BUFFER,
    }
    logger.warning(
        f"[{district_key}] APPROXIMATE bbox (fallback buffer, not true "
        f"district boundary): {bbox}"
    )
    return bbox


def run_for_district(district_key: str, cfg: dict, logger) -> None:
    src_cfg = cfg["sources"][SOURCE_KEY]
    district_cfg = cfg["districts"][district_key]

    bbox = get_district_bbox(district_key, district_cfg, logger)

    source_dir = get_source_dir(SOURCE_KEY)
    raw_dir = source_dir / "raw"
    clean_dir = source_dir / "cleaned"
    log_dir = source_dir / "logs"
    for d in (raw_dir, clean_dir, log_dir):
        d.mkdir(parents=True, exist_ok=True)

    start_date, end_date = get_date_range()
    variables: list[str] = src_cfg.get("variables", ["rain"])

    downloader = IMDDownloader(raw_dir=raw_dir, variables=variables, logger=logger)
    parser = IMDParser(raw_dir=raw_dir, bbox=bbox, logger=logger)

    logger.info("=" * 70)
    logger.info(f"IMD Gridded Collector — {district_key.upper()} — START")
    logger.info(f"Bbox: {bbox}")
    logger.info(f"Period: {start_date.year} → {end_date.year}")
    logger.info("=" * 70)

    years = list(range(start_date.year, end_date.year + 1))
    total_records = 0
    total_missing: dict[str, int] = {}
    processed = 0
    skipped = 0

    for year in tqdm(years, desc=f"IMD years [{district_key}]", unit="year"):
        download_results = downloader.download_year(year)
        available_vars = [v for v, ok in download_results.items() if ok]

        if not available_vars:
            logger.warning(f"  [{district_key}] No variables downloaded for {year}. Skipping.")
            skipped += 1
            continue

        df = parser.parse_year(year, available_vars)
        if df is None or df.empty:
            logger.warning(f"  [{district_key}] Parse returned empty for {year}. Skipping.")
            skipped += 1
            continue

        csv_path = clean_dir / f"imd_{district_key}_{year}_cleaned.csv"
        df.to_csv(csv_path, index=False)
        logger.info(f"  [{district_key}] Saved: {csv_path.name} ({len(df):,} rows)")

        total_records += len(df)
        for col in df.select_dtypes(include="number").columns:
            n_miss = int(df[col].isna().sum())
            total_missing[col] = total_missing.get(col, 0) + n_miss
        processed += 1

    logger.info(f"[{district_key}] COMPLETE — processed={processed}, skipped={skipped}, records={total_records:,}")

    cleaned_csvs = sorted(clean_dir.glob(f"imd_{district_key}_*_cleaned.csv"))
    cleaned_path = cleaned_csvs[-1] if cleaned_csvs else clean_dir / "no_data.csv"
    raw_grds = sorted(raw_dir.rglob("*.grd"))
    raw_path = raw_grds[0] if raw_grds else raw_dir / "no_data.grd"

    write_metadata(
        source_dir=source_dir,
        source_name=f"{src_cfg['name']} ({district_key})",
        api_url="https://imdpune.gov.in/",
        update_frequency=src_cfg["update_frequency"],
        df_cleaned=pd.DataFrame(),
        raw_file_path=raw_path,
        cleaned_file_path=cleaned_path,
        extra={
            "district": district_key,
            "bounding_box": bbox,
            "total_records": total_records,
            "missing_values_summary": total_missing,
            "start_year": start_date.year,
            "end_year": end_date.year,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run IMD collector for multiple districts.")
    parser.add_argument(
        "--districts",
        type=str,
        default=None,
        help="Comma-separated district keys (e.g. 'kullu,chamba'). Defaults to active_districts minus mandi.",
    )
    args = parser.parse_args()

    cfg = get_config()

    if args.districts:
        districts = [d.strip().lower() for d in args.districts.split(",")]
    else:
        districts = [d for d in cfg.get("active_districts", ["mandi", "kullu", "chamba"]) if d != "mandi"]

    logger = get_logger(COLLECTOR_NAME)
    logger.info(f"Running IMD collector for districts: {districts}")

    for district in districts:
        if district not in cfg["districts"]:
            logger.error(f"District '{district}' not found in config.yaml. Skipping.")
            continue
        try:
            run_for_district(district, cfg, logger)
        except Exception as exc:
            logger.error(f"[{district}] Collector failed: {exc}", exc_info=True)
            continue

    logger.info("All requested districts processed.")


if __name__ == "__main__":
    main()
