"""
river_discharge_collector.py
============================
Collects river discharge and water-level data for Himachal Pradesh districts
from three sources in priority order: CWC → NHP → WRIS.

DATA STRATEGY PER SOURCE
------------------------
CWC  : CWC does NOT publish per-station bulk CSV/XML download links. Data is
       fetched from the CWC Flood Forecast System (FFS) live portal:
         https://ffs.india-water.gov.in/
       The collector uses the FFS internal JSON API (discovered from the portal's
       network traffic) to pull historical water-level observations per station.
       If a station also has `known_files` configured, those are downloaded first
       and merged; the live API is then used to fill any remaining gap.

NHP  : Same pattern as CWC — known_files first, then NHP portal API fallback.
       Currently no real station codes are configured, so NHP is a clean skip.

WRIS : Disabled in config (API endpoint down as of July 2026). Clean skip.

OUTPUT
------
Per district, per source:
  digital_twin/hydrology/River_Discharge/
    raw/<district>/<source>/<station_id>_raw.parquet
    cleaned/<district>/<source>/<station_id>_cleaned.parquet
    logs/<district>_river_discharge.log
    metadata.json   (updated after every run)
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yaml
from tqdm import tqdm

# ---------------------------------------------------------------------------
#  Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("river_discharge_collector")


# ---------------------------------------------------------------------------
#  Config helpers
# ---------------------------------------------------------------------------

def load_config(path: str = "config/config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _req_cfg(cfg: dict) -> dict:
    return cfg.get("river_discharge", {}).get("request", {})


def _make_session(cfg: dict) -> requests.Session:
    s = requests.Session()
    rc = _req_cfg(cfg)
    s.headers.update({"User-Agent": rc.get(
        "user_agent",
        "Mozilla/5.0 (compatible; HimachalDigitalTwinBot/2.1; +https://example.org/bot)",
    )})
    return s


def _get(session: requests.Session, url: str, cfg: dict, **kwargs) -> requests.Response:
    """GET with retry/backoff aligned to config."""
    rc = _req_cfg(cfg)
    retries = rc.get("retries", 5)
    backoff = rc.get("backoff_factor", 2.0)
    timeout = rc.get("timeout", 120)
    verify  = rc.get("verify_ssl", True)

    for attempt in range(retries):
        try:
            r = session.get(url, timeout=timeout, verify=verify, **kwargs)
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            if attempt == retries - 1:
                raise
            wait = backoff ** attempt
            logger.warning("GET %s failed (%s), retrying in %.1fs …", url, exc, wait)
            time.sleep(wait)
    raise RuntimeError(f"GET {url} failed after {retries} attempts")  # never reached


# ---------------------------------------------------------------------------
#  Column normalisation
# ---------------------------------------------------------------------------

def normalise_columns(df: pd.DataFrame, mapping: dict[str, list[str]]) -> pd.DataFrame:
    """Rename raw column names to canonical schema using the mapping dict."""
    rename = {}
    for canonical, aliases in mapping.items():
        for alias in aliases:
            if alias in df.columns:
                rename[alias] = canonical
                break
    return df.rename(columns=rename)


# ---------------------------------------------------------------------------
#  CWC FFS live API
# ---------------------------------------------------------------------------

# CWC's Flood Forecast System exposes an undocumented internal JSON API used
# by its Angular front-end. These endpoints were discovered by inspecting
# network traffic on https://ffs.india-water.gov.in/
#
# Endpoints used:
#   /api/v1/stations          — list all stations (GET, no auth)
#   /api/v1/stationdata       — water-level time series for one station (GET)
#
# Parameters for /api/v1/stationdata:
#   stationCode : station code from the stations list (field: stationCode)
#   fromDate    : "YYYY-MM-DD"
#   toDate      : "YYYY-MM-DD"
#
# NOTE: These are internal endpoints with no SLA guarantee. If they stop
# responding, set cwc.enabled: false in config and implement an alternative
# (e.g. scraping the hydrograph SVG data or requesting CWC data sharing).

CWC_FFS_BASE   = "https://ffs.india-water.gov.in"
CWC_STATIONS   = f"{CWC_FFS_BASE}/api/v1/stations"
CWC_STATIONDATA = f"{CWC_FFS_BASE}/api/v1/stationdata"

# Fallback: some older CWC deployments used this base instead
CWC_FFS_BASE_ALT    = "https://cwc.gov.in/ffs"
CWC_STATIONS_ALT    = f"{CWC_FFS_BASE_ALT}/api/v1/stations"
CWC_STATIONDATA_ALT = f"{CWC_FFS_BASE_ALT}/api/v1/stationdata"


def _fetch_cwc_station_list(session: requests.Session, cfg: dict) -> dict[str, str]:
    """
    Returns {station_name_upper: stationCode} from the CWC FFS stations API.
    Tries primary FFS base, falls back to alternate base.
    Returns {} on failure (collector will skip live fetch and warn).
    """
    for url in [CWC_STATIONS, CWC_STATIONS_ALT]:
        try:
            r = _get(session, url, cfg, timeout=30)
            data = r.json()
            # Response is either a list or {"data": [...]}
            if isinstance(data, list):
                stations = data
            elif isinstance(data, dict):
                stations = data.get("data") or data.get("stations") or []
            else:
                stations = []

            mapping = {}
            for s in stations:
                code = s.get("stationCode") or s.get("station_code") or s.get("id")
                name = s.get("stationName") or s.get("station_name") or s.get("name") or ""
                if code and name:
                    mapping[name.strip().upper()] = str(code)
            if mapping:
                logger.debug("CWC FFS station list loaded: %d stations from %s", len(mapping), url)
                return mapping
        except Exception as exc:
            logger.warning("CWC FFS station list unavailable at %s: %s", url, exc)
    return {}


def _fetch_cwc_observations(
    session: requests.Session,
    cfg: dict,
    station_code: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame | None:
    """
    Fetch water-level time series from CWC FFS for one station.
    Returns a DataFrame with columns [observation_datetime, water_level]
    or None if the request fails.
    """
    params = {
        "stationCode": station_code,
        "fromDate":    start_date,
        "toDate":      end_date,
    }
    for url in [CWC_STATIONDATA, CWC_STATIONDATA_ALT]:
        try:
            r = _get(session, url, cfg, params=params, timeout=60)
            data = r.json()

            # Response shape varies — normalise to a list of records
            if isinstance(data, list):
                records = data
            elif isinstance(data, dict):
                records = (
                    data.get("data")
                    or data.get("observations")
                    or data.get("waterLevel")
                    or []
                )
            else:
                records = []

            if not records:
                logger.debug("CWC FFS returned empty data for station %s", station_code)
                return None

            df = pd.DataFrame(records)
            df = normalise_columns(df, {
                "observation_datetime": [
                    "date", "Date", "datetime", "DateTime", "observationDate",
                    "observation_date", "Timestamp", "timestamp",
                ],
                "water_level": [
                    "waterLevel", "water_level", "WaterLevel", "level",
                    "Level", "gauge", "Gauge",
                ],
                "river_discharge": [
                    "discharge", "Discharge", "Q", "flow", "Flow",
                ],
            })

            # Ensure datetime column is parsed
            if "observation_datetime" in df.columns:
                df["observation_datetime"] = pd.to_datetime(
                    df["observation_datetime"], errors="coerce"
                )
                df = df.dropna(subset=["observation_datetime"])

            logger.debug(
                "CWC FFS: %d rows for station %s from %s",
                len(df), station_code, url,
            )
            return df

        except Exception as exc:
            logger.warning(
                "CWC FFS data fetch failed for station %s at %s: %s",
                station_code, url, exc,
            )

    return None


# ---------------------------------------------------------------------------
#  known_files downloader  (shared by CWC, NHP)
# ---------------------------------------------------------------------------

def _download_known_files(
    session: requests.Session,
    cfg: dict,
    station: dict,
    out_raw_dir: Path,
) -> list[Path]:
    """
    Download any files listed in station['known_files'].
    Returns list of successfully downloaded local paths.
    """
    downloaded = []
    for kf in station.get("known_files") or []:
        url      = kf.get("url")
        filename = kf.get("filename") or Path(url).name
        dest     = out_raw_dir / filename

        if dest.exists():
            logger.debug("known_file already present, skipping download: %s", dest)
            downloaded.append(dest)
            continue

        try:
            r = _get(session, url, cfg, stream=True)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as fh:
                for chunk in r.iter_content(chunk_size=1_048_576):
                    fh.write(chunk)
            logger.info("Downloaded known_file: %s → %s", url, dest)
            downloaded.append(dest)
        except Exception as exc:
            logger.warning("Failed to download known_file %s: %s", url, exc)

    return downloaded


def _load_known_file(path: Path, col_mapping: dict) -> pd.DataFrame | None:
    """Load a downloaded known_file into a normalised DataFrame."""
    try:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            df = pd.read_csv(path)
        elif suffix in (".xls", ".xlsx"):
            df = pd.read_excel(path)
        elif suffix == ".parquet":
            df = pd.read_parquet(path)
        else:
            logger.warning("Unsupported known_file format: %s", path)
            return None

        df = normalise_columns(df, col_mapping)
        if "observation_datetime" in df.columns:
            df["observation_datetime"] = pd.to_datetime(
                df["observation_datetime"], errors="coerce"
            )
            df = df.dropna(subset=["observation_datetime"])
        return df

    except Exception as exc:
        logger.warning("Could not load known_file %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
#  Per-station data assembly
# ---------------------------------------------------------------------------

def _collect_station(
    session:       requests.Session,
    cfg:           dict,
    station:       dict,
    source_name:   str,
    district:      str,
    start_date:    str,
    end_date:      str,
    out_raw_dir:   Path,
    out_clean_dir: Path,
    cwc_station_map: dict[str, str],   # {NAME_UPPER: stationCode} — empty for non-CWC
) -> bool:
    """
    Attempt to collect data for one station.
    Returns True if any data was saved, False otherwise.
    """
    sid      = station.get("station_id", "UNKNOWN")
    sname    = station.get("station_name", sid)
    river    = station.get("river_name", "")
    basin    = station.get("basin_name", "")
    lat      = station.get("latitude")
    lon      = station.get("longitude")
    enabled  = station.get("enabled", True)

    if not enabled:
        logger.info(
            "Station '%s' (%s, district '%s') is disabled in config -- skipping",
            sid, source_name, district,
        )
        return False

    col_mapping = cfg.get("river_discharge", {}).get("column_mapping", {})

    frames: list[pd.DataFrame] = []

    # ── 1. known_files (file download) ─────────────────────────────────────
    known = station.get("known_files") or []
    if known:
        downloaded = _download_known_files(session, cfg, station, out_raw_dir)
        for path in downloaded:
            df = _load_known_file(path, col_mapping)
            if df is not None and not df.empty:
                frames.append(df)
    else:
        logger.debug(
            "Station '%s' (%s, district '%s') has no known_files -- will try live API",
            sid, source_name, district,
        )

    # ── 2. CWC FFS live API (CWC only) ─────────────────────────────────────
    if source_name.lower() == "cwc" and cwc_station_map:
        # Try to find this station's FFS code by matching station_name
        fss_code = cwc_station_map.get(sname.strip().upper())
        if not fss_code:
            # Fuzzy fallback: check if any FFS station name contains our name
            for ffs_name, code in cwc_station_map.items():
                if sname.upper() in ffs_name or ffs_name in sname.upper():
                    fss_code = code
                    logger.debug(
                        "Station '%s': fuzzy-matched FFS name '%s' (code %s)",
                        sname, ffs_name, code,
                    )
                    break

        if fss_code:
            df_live = _fetch_cwc_observations(
                session, cfg, fss_code, start_date, end_date
            )
            if df_live is not None and not df_live.empty:
                df_live["station_id"]   = sid
                df_live["station_name"] = sname
                df_live["river_name"]   = river
                df_live["basin_name"]   = basin
                df_live["latitude"]     = lat
                df_live["longitude"]    = lon
                df_live["source"]       = "cwc_ffs_live"
                frames.append(df_live)
            else:
                logger.info(
                    "CWC FFS returned no data for station '%s' (code %s) -- "
                    "station may be inactive or outside date range",
                    sname, fss_code,
                )
        else:
            logger.warning(
                "Station '%s' not found in CWC FFS station list. "
                "FFS may use a different name — check https://ffs.india-water.gov.in/ "
                "and update station_name in config if needed.",
                sname,
            )

    # ── 3. Merge and save ──────────────────────────────────────────────────
    if not frames:
        logger.info(
            "Station '%s' (%s, district '%s') -- no data from any path",
            sid, source_name, district,
        )
        return False

    df = pd.concat(frames, ignore_index=True)

    # Add metadata columns if missing
    for col, val in [
        ("station_id",   sid),
        ("station_name", sname),
        ("river_name",   river),
        ("basin_name",   basin),
        ("latitude",     lat),
        ("longitude",    lon),
        ("district",     district),
        ("source",       source_name),
    ]:
        if col not in df.columns:
            df[col] = val

    # Deduplicate on datetime
    if "observation_datetime" in df.columns:
        df = df.sort_values("observation_datetime").drop_duplicates(
            subset=["station_id", "observation_datetime"]
        )

    # Save raw
    out_raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_raw_dir / f"{sid}_raw.parquet"
    df.to_parquet(raw_path, index=False, compression="snappy")
    logger.info("Saved raw data: %s (%d rows)", raw_path, len(df))

    # Clean: drop rows with no numeric value at all
    value_cols = [c for c in ["water_level", "river_discharge"] if c in df.columns]
    if value_cols:
        df_clean = df.dropna(subset=value_cols, how="all").copy()
    else:
        df_clean = df.copy()

    out_clean_dir.mkdir(parents=True, exist_ok=True)
    clean_path = out_clean_dir / f"{sid}_cleaned.parquet"
    df_clean.to_parquet(clean_path, index=False, compression="snappy")
    logger.info("Saved cleaned data: %s (%d rows)", clean_path, len(df_clean))

    return True


# ---------------------------------------------------------------------------
#  Per-source collector
# ---------------------------------------------------------------------------

def _collect_source(
    session:    requests.Session,
    cfg:        dict,
    source_key: str,
    district:   str,
    start_date: str,
    end_date:   str,
    base_dir:   Path,
    cwc_station_map: dict[str, str],
) -> bool:
    """
    Run collection for one source (cwc/nhp/wris) for one district.
    Returns True if at least one station produced data.
    """
    rd_cfg   = cfg.get("river_discharge", {})
    src_cfg  = rd_cfg.get("sources", {}).get(source_key, {})

    if not src_cfg.get("enabled", True):
        logger.info("Source '%s' is disabled in config -- skipping", source_key)
        return False

    district_cfg = src_cfg.get("districts", {}).get(district, {})
    stations     = district_cfg.get("stations") or []

    if not stations:
        logger.info(
            "Source '%s' has no stations configured for district '%s' -- skipping",
            source_key, district,
        )
        return False

    src_label    = src_cfg.get("name", source_key)
    out_raw_dir  = base_dir / "raw"   / district / source_key
    out_clean_dir = base_dir / "cleaned" / district / source_key

    any_data = False
    for station in stations:
        ok = _collect_station(
            session       = session,
            cfg           = cfg,
            station       = station,
            source_name   = source_key,
            district      = district,
            start_date    = start_date,
            end_date      = end_date,
            out_raw_dir   = out_raw_dir,
            out_clean_dir = out_clean_dir,
            cwc_station_map = cwc_station_map,
        )
        if ok:
            any_data = True

    if not any_data:
        logger.info(
            "Source '%s' produced no usable data for district '%s'",
            src_label, district,
        )
    return any_data


# ---------------------------------------------------------------------------
#  Orchestrator
# ---------------------------------------------------------------------------

def orchestrate(cfg: dict, dry_run: bool = False) -> None:
    rd_cfg     = cfg.get("river_discharge", {})
    base_dir   = Path(rd_cfg.get("base_dir", "digital_twin/hydrology/River_Discharge"))
    priorities = rd_cfg.get("source_priority", ["cwc", "nhp", "wris"])
    districts  = cfg.get("active_districts", ["mandi", "kullu", "chamba"])
    start_date = cfg.get("dates", {}).get("start_date", "2005-01-01")
    end_date   = cfg.get("dates", {}).get("end_date",   "2025-12-31")

    logger.info(
        "Starting River Discharge collection run: districts=%s, "
        "source_priority=%s, dry_run=%s",
        districts, priorities, dry_run,
    )
    logger.info("Output dir -> %s", base_dir)

    if dry_run:
        logger.info("DRY RUN — no files will be written")
        return

    session = _make_session(cfg)

    # Pre-fetch CWC FFS station list once (reused across all districts)
    cwc_station_map: dict[str, str] = {}
    cwc_cfg = rd_cfg.get("sources", {}).get("cwc", {})
    if cwc_cfg.get("enabled", True):
        logger.info("Fetching CWC FFS station list …")
        cwc_station_map = _fetch_cwc_station_list(session, cfg)
        if cwc_station_map:
            logger.info("CWC FFS station list: %d stations available", len(cwc_station_map))
        else:
            logger.warning(
                "CWC FFS station list could not be fetched. "
                "Live water-level data will be unavailable. "
                "Check https://ffs.india-water.gov.in/ and verify the API endpoints "
                "in this file (CWC_STATIONS / CWC_STATIONDATA constants)."
            )

    # Set up per-district log files
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    metadata: dict[str, Any] = {
        "run_timestamp": datetime.utcnow().isoformat() + "Z",
        "start_date":    start_date,
        "end_date":      end_date,
        "districts":     {},
    }

    for district in tqdm(districts, desc="Districts"):
        district_log_path = log_dir / f"{district}_river_discharge.log"
        fh = logging.FileHandler(district_log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        ))
        logger.addHandler(fh)

        district_meta: dict[str, Any] = {"sources_tried": [], "sources_succeeded": []}
        success = False

        for source_key in priorities:
            district_meta["sources_tried"].append(source_key)
            ok = _collect_source(
                session         = session,
                cfg             = cfg,
                source_key      = source_key,
                district        = district,
                start_date      = start_date,
                end_date        = end_date,
                base_dir        = base_dir,
                cwc_station_map = cwc_station_map,
            )
            if ok:
                district_meta["sources_succeeded"].append(source_key)
                success = True
                # Do NOT break — collect from all sources; merge later if needed
                # (comment out the line above and uncomment below to use first-wins)
                # break

        if not success:
            logger.error(
                "No source (%s) produced usable data for district '%s'. "
                "CWC FFS API may be unreachable — check connectivity and "
                "verify CWC_STATIONS endpoint in river_discharge_collector.py.",
                ", ".join(priorities), district,
            )

        metadata["districts"][district] = district_meta
        logger.removeHandler(fh)
        fh.close()

    # Write metadata
    meta_path = base_dir / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)
    logger.info("Metadata written: %s", meta_path)
    logger.info("River Discharge collection run finished")


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Himachal River Discharge Collector")
    ap.add_argument("--config",  default="config/config.yaml", help="Path to config.yaml")
    ap.add_argument("--dry-run", action="store_true",           help="Validate config without writing files")
    ap.add_argument("--log-level", default="INFO",
                    choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = ap.parse_args()

    logging.basicConfig(
        level   = getattr(logging, args.log_level),
        format  = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt = "%Y-%m-%d %H:%M:%S",
    )

    cfg = load_config(args.config)
    orchestrate(cfg, dry_run=args.dry_run)