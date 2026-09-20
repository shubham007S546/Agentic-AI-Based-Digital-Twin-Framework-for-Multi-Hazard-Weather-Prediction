"""
pipeline/collect_all.py
════════════════════════
Master CLI tool to run environmental data collectors across Himachal Pradesh study districts.

Usage:
    python -m pipeline.collect_all --dry-run
    python -m pipeline.collect_all --source openmeteo --district mandi --start-date 2024-06-01 --end-date 2024-06-07
    python -m pipeline.collect_all --source climate_indices
    python -m pipeline.collect_all --source all_available
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.config_loader import (
    get_active_districts,
    get_config,
    get_data_sources_registry,
    get_source_paths,
    to_long_path,
)
from utils.logger import get_logger

LOGGER = get_logger("pipeline.collect_all")


def run_dry_run(
    sources: List[str],
    districts: List[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> None:
    """Print an honest, structured dry-run plan of collection tasks."""
    registry = get_data_sources_registry().get("sources", {})
    cfg = get_config()
    dates_cfg = cfg.get("dates", {})
    s_date = start_date or dates_cfg.get("start_date", "2005-01-01")
    e_date = end_date or dates_cfg.get("end_date", "2025-12-31")

    print("\n" + "=" * 80)
    print("  HIMACHAL CLIMATE DIGITAL TWIN — COLLECTION DRY-RUN PLAN")
    print("=" * 80)
    print(f"Date Range       : {s_date} -> {e_date}")
    print(f"Target Districts : {', '.join(districts)}")
    print(f"Target Sources   : {', '.join(sources)}")
    print("-" * 80)

    for src in sources:
        src_meta = registry.get(src, {})
        auth_req = src_meta.get("authentication_required", False)
        status = src_meta.get("status", "UNKNOWN")
        endpoint = src_meta.get("api_endpoint", "N/A")
        collector = src_meta.get("collector", "N/A")

        print(f"\n[Source: {src.upper()}]")
        print(f"  Name            : {src_meta.get('name', src)}")
        print(f"  Provider        : {src_meta.get('provider', 'N/A')}")
        print(f"  Endpoint        : {endpoint}")
        print(f"  Auth Required   : {auth_req}")
        print(f"  Collector Module: {collector}")
        print(f"  Registry Status : {status}")

        paths = get_source_paths(src)
        print(f"  Target Raw Dir  : {paths['raw']}")
        print(f"  Target Clean Dir: {paths['cleaned']}")

    print("\n" + "=" * 80)
    print("Dry run complete. No network requests or file writes were performed.")
    print("=" * 80 + "\n")


def execute_collection(
    sources: List[str],
    districts: List[str],
    start_date: Optional[str],
    end_date: Optional[str],
    force: bool = False,
) -> Dict[str, Any]:
    """Execute collection across specified sources."""
    results: Dict[str, Any] = {}
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    summary_log = logs_dir / "collection_runs.jsonl"

    for src in sources:
        LOGGER.info(f"Starting execution for source: {src}")
        start_time = time.time()
        status = "FAILED"
        records_collected = 0
        error_msg: Optional[str] = None

        try:
            if src == "openmeteo":
                from collectors.openmeteo_collector import OpenMeteoCollector

                for district in districts:
                    LOGGER.info(f"Collecting Open-Meteo for district: {district}")
                    col = OpenMeteoCollector(
                        district=district,
                        start_date=start_date,
                        end_date=end_date,
                    )
                    out = col.run()
                    if out:
                        status = "SUCCESS"

            elif src == "climate_indices":
                from collectors.climate_index_collector import ClimateIndexConfig, run as run_ci_collector

                cfg = ClimateIndexConfig(
                    start_year=int((start_date or "2005-01-01")[:4]),
                    end_year=int((end_date or "2025-12-31")[:4]),
                    base_dir=PROJECT_ROOT / "digital_twin" / "climate_indices",
                    force=force,
                )
                ci_res = run_ci_collector(cfg)
                if any(ci_res.values()):
                    status = "SUCCESS"

            elif src in ("nasa_gpm", "copernicus_era5", "copernicus_era5_land", "india_wris"):
                status = "AUTH_REQUIRED"
                error_msg = f"Source '{src}' requires credentials. Set relevant API token in .env or config/config.yaml."
                LOGGER.warning(f"Skipping {src}: {error_msg}")

            else:
                status = "DATA_UNAVAILABLE"
                error_msg = f"No automated zero-mock collector configured for source '{src}'"
                LOGGER.warning(error_msg)

        except Exception as exc:
            error_msg = str(exc)
            LOGGER.error(f"Error executing source {src}: {exc}", exc_info=True)

        duration = time.time() - start_time
        run_record = {
            "source": src,
            "districts": districts,
            "start_date": start_date,
            "end_date": end_date,
            "status": status,
            "duration_seconds": round(duration, 2),
            "error": error_msg,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        results[src] = run_record

        with open(to_long_path(summary_log), "a", encoding="utf-8") as f:
            f.write(json.dumps(run_record) + "\n")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Master environmental data collection CLI.")
    parser.add_argument(
        "--source",
        type=str,
        default="all_available",
        help="Source ID to collect (e.g. 'openmeteo', 'climate_indices', 'all_available')",
    )
    parser.add_argument(
        "--district",
        type=str,
        default=None,
        help="Comma-separated district keys (e.g. 'mandi,kullu,chamba')",
    )
    parser.add_argument("--start-date", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without running network requests")
    parser.add_argument("--force", action="store_true", help="Re-collect even if files already exist")
    args = parser.parse_args()

    if args.district:
        districts = [d.strip().lower() for d in args.district.split(",")]
    else:
        districts = get_active_districts()

    registry = get_data_sources_registry().get("sources", {})
    all_sources = list(registry.keys())

    if args.source == "all_available":
        # Sources with verified public availability
        sources = ["openmeteo", "climate_indices"]
    elif args.source in ("all", "all_sources"):
        sources = all_sources
    else:
        sources = [s.strip().lower() for s in args.source.split(",")]

    if args.dry_run:
        run_dry_run(sources, districts, args.start_date, args.end_date)
        return

    LOGGER.info(f"Executing collection pipeline for sources: {sources} in districts: {districts}")
    results = execute_collection(
        sources=sources,
        districts=districts,
        start_date=args.start_date,
        end_date=args.end_date,
        force=args.force,
    )

    print("\n" + "=" * 80)
    print("  COLLECTION EXECUTION SUMMARY")
    print("=" * 80)
    for src, res in results.items():
        print(f"[{src.upper()}] Status: {res['status']} | Duration: {res['duration_seconds']}s")
        if res.get("error"):
            print(f"  Note: {res['error']}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
