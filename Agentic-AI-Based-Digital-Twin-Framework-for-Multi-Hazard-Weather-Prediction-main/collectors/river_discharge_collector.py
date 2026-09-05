"""
river_discharge_collector.py
============================
Collects river discharge and water-level data for Himachal Pradesh districts
from three sources in priority order: CWC → NHP → WRIS.

DATA STRATEGY PER SOURCE
------------------------
CWC  : CWC does NOT publish per-station bulk CSV/XML download links, and it
       does NOT expose a live "list all stations" API either -- there is no
       such endpoint on the FFS portal. Station -> stationCode mapping is a
       static, manually-curated table (see `cwc.station_code_map` in
       config.yaml), the same approach used by the published GUARDIAN
       scraper (Patidar, Indu & Karmakar, 2024, Sci Data,
       https://doi.org/10.1038/s41597-024-03923-8; code:
       https://github.com/girishpatidar/discharge_india). Each station's
       `ffs_station_code` is found ONCE via browser DevTools and stored in
       config -- it is never fetched at runtime.
       Real data endpoint (verified working, POST):
         https://ffs.india-water.gov.in/web-api/getHGStationDataForFFS/
       Fallback endpoint if the above is ever pulled (verified working, GET):
         https://ffs.india-water.gov.in/iam/api/new-entry-data/specification/sorted
       If a station also has `known_files` configured, those are downloaded
       first and merged; the live API then fills any remaining gap.

NHP  : Same pattern as CWC — known_files first, then NHP portal API fallback.
       Currently no real station codes are configured, so NHP is a clean skip.

WRIS : Disabled in config (indiawris.gov.in/wris/ subpath serves nothing but
       a default Apache test page as of July 2026 -- dead deployment, not a
       transient outage). Clean skip. www.indiawris.gov.in (the current,
       actively maintained portal) is a possible future replacement but has
       not been wired up yet -- see TODO in config.

OUTPUT
------
Per district, per source:
  digital_twin/hydrology/River_Discharge/
    raw/<district>/<source>/<station_id>_raw.parquet
    cleaned/<district>/<source>/<station_id>_cleaned.parquet
    logs/<district>_river_discharge.log
    metadata.json   (updated after every run)

CHANGELOG
---------
2026-07-05 (v3): Replaced the fictitious CWC "list stations" + GET
            "stationdata" API with the two REAL endpoints used by the
            published GUARDIAN scraper (see module docstring above):
              1. POST https://ffs.india-water.gov.in/web-api/getHGStationDataForFFS/
                 payload: {"stationCode": "'<code>'", "startDate": "...", "endDate": "..."}
                 (note: stationCode value is wrapped in literal single quotes)
              2. GET https://ffs.india-water.gov.in/iam/api/new-entry-data/specification/sorted
                 (fallback if #1 is ever retired -- uses a URL-encoded
                 "specification" filter object instead of simple params)
            REMOVED `_fetch_cwc_station_list()` and the whole "prefetch a
            live station map" flow -- there is no such live endpoint; CWC
            never published one and the FFS Angular app doesn't call one
            either. Station codes now come STRAIGHT FROM CONFIG
            (`station['ffs_station_code']`), matching the same
            manually-curated-mapping approach the GUARDIAN paper's own code
            uses (their `name-code.xlsx`). This is a one-time lookup per
            station via browser DevTools, not a per-run network call.
            Candidate HP-region stations (from the GUARDIAN paper's public
            station_locations.csv, code TBD by manual DevTools lookup):
            BAROT (32.05N 76.83E, Mandi dist., Uhl river), RAMPUR (31.45N
            77.63E, near Kullu, Sutlej river), KOTHI (32.32N 77.20E, near
            Manali), TANDI (32.55N 76.98E, Lahaul-Spiti, Chandra/Bhaga
            confluence).

2026-07-05 (v2): Fixed silent-skip bug in _collect_station(). Previously,
            when cwc_station_map was empty, the whole CWC-live-API block was
            skipped with NO per-station log line. Now every CWC station
            logs an explicit ERROR/WARNING when its code is missing, and
            per-station diagnostics are unconditional. (Superseded by v3
            above, which removes cwc_station_map entirely, but the
            per-station diagnostic-logging discipline this fix established
            is kept.)

2026-07-05 (v1): Fixed `_get()` swallowing per-call `timeout=` kwargs
            (collided with the hardcoded default -> TypeError -> silently
            caught by broad `except Exception` at every call site). Also
            made 4xx errors fail fast instead of retrying 5x with backoff.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
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
    """GET with retry/backoff aligned to config. (See v1 changelog entry.)"""
    rc = _req_cfg(cfg)
    retries = rc.get("retries", 5)
    backoff = rc.get("backoff_factor", 2.0)
    timeout = kwargs.pop("timeout", rc.get("timeout", 120))
    verify  = kwargs.pop("verify", rc.get("verify_ssl", True))

    for attempt in range(retries):
        try:
            r = session.get(url, timeout=timeout, verify=verify, **kwargs)
            r.raise_for_status()
            return r
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status is not None and 400 <= status < 500 and status != 429:
                logger.error(
                    "GET %s -> %s %s (client error, NOT retrying -- the URL "
                    "or parameters are wrong, this will not fix itself on "
                    "retry): %s",
                    url, status, exc.response.reason if exc.response is not None else "",
                    exc,
                )
                raise
            if attempt == retries - 1:
                raise
            wait = backoff ** attempt
            logger.warning("GET %s failed (%s), retrying in %.1fs …", url, exc, wait)
            time.sleep(wait)
        except requests.RequestException as exc:
            if attempt == retries - 1:
                raise
            wait = backoff ** attempt
            logger.warning("GET %s failed (%s), retrying in %.1fs …", url, exc, wait)
            time.sleep(wait)
    raise RuntimeError(f"GET {url} failed after {retries} attempts")  # never reached


def _post(session: requests.Session, url: str, cfg: dict, json_body: dict, **kwargs) -> requests.Response:
    """POST with the same retry/backoff discipline as _get(). Needed because
    the real CWC FFS data endpoint is a POST with a JSON body, not a GET."""
    rc = _req_cfg(cfg)
    retries = rc.get("retries", 5)
    backoff = rc.get("backoff_factor", 2.0)
    timeout = kwargs.pop("timeout", rc.get("timeout", 120))
    verify  = kwargs.pop("verify", rc.get("verify_ssl", True))

    for attempt in range(retries):
        try:
            r = session.post(url, json=json_body, timeout=timeout, verify=verify, **kwargs)
            r.raise_for_status()
            return r
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status is not None and 400 <= status < 500 and status != 429:
                logger.error(
                    "POST %s -> %s %s (client error, NOT retrying): %s",
                    url, status, exc.response.reason if exc.response is not None else "",
                    exc,
                )
                raise
            if attempt == retries - 1:
                raise
            wait = backoff ** attempt
            logger.warning("POST %s failed (%s), retrying in %.1fs …", url, exc, wait)
            time.sleep(wait)
        except requests.RequestException as exc:
            if attempt == retries - 1:
                raise
            wait = backoff ** attempt
            logger.warning("POST %s failed (%s), retrying in %.1fs …", url, exc, wait)
            time.sleep(wait)
    raise RuntimeError(f"POST {url} failed after {retries} attempts")  # never reached


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
#  CWC FFS live API  (REAL endpoints, verified against the published
#  GUARDIAN scraper -- Patidar, Indu & Karmakar 2024, Sci Data,
#  https://doi.org/10.1038/s41597-024-03923-8,
#  code: https://github.com/girishpatidar/discharge_india)
# ---------------------------------------------------------------------------
#
# IMPORTANT: there is no live "list all stations" endpoint on this portal.
# CWC/FFS never published one, and the Angular front-end doesn't call one
# either -- station codes are looked up client-side against a bundled
# dataset. The only reliable way to get a station's code is:
#   1. open https://ffs.india-water.gov.in/ in a real browser
#   2. search for / select the station on the map or station list
#   3. open DevTools -> Network -> XHR/Fetch, look at the request to
#      getHGStationDataForFFS (or the fallback specification/sorted
#      endpoint), and read the stationCode value out of the request body
#   4. put that code in config.yaml under the station's `ffs_station_code`
#      field (see _collect_station below) -- this is a ONE-TIME lookup,
#      not a per-run fetch.
#
# Candidate stations inside the Himachal Pradesh bounding box, pulled from
# the GUARDIAN paper's public station_locations.csv (name + lat/lon only --
# codes still need the manual DevTools lookup above):
#   BAROT   32.0500N 76.8300E  -- Mandi district, Uhl river (Beas tributary)
#   RAMPUR  31.4500N 77.6333E  -- near Kullu, Sutlej river
#   KOTHI   32.3164N 77.1997E  -- near Manali, Kullu district
#   TANDI   32.5503N 76.9797E  -- Lahaul-Spiti, Chandra/Bhaga confluence
#   GHOUSHAL 32.5331N 76.9331E -- Lahaul-Spiti area
#   UDAIPUR 32.6997N 76.6497E  -- Lahaul-Spiti, Chenab river
#   HANSA   32.4486N 77.8628E  -- Spiti area
#   Sangla  31.4225N 78.2650E  -- Kinnaur, Baspa river
#   NATHPA  31.5664N 77.9831E  -- Kinnaur, Sutlej river

CWC_FFS_BASE = "https://ffs.india-water.gov.in"

# Primary: real, verified working endpoint (POST + JSON body)
CWC_STATIONDATA_URL = f"{CWC_FFS_BASE}/web-api/getHGStationDataForFFS/"

# Fallback: real, verified working endpoint (GET + URL-encoded specification
# filter). Used only if the primary POST endpoint stops responding, since it
# is uglier to build and the response schema is different (id.dataTime /
# dataValue instead of actualTime / value).
CWC_STATIONDATA_FALLBACK_URL = f"{CWC_FFS_BASE}/iam/api/new-entry-data/specification/sorted"

_PRIMARY_DT_FMT  = "%Y-%m-%d %H:%M:%S.%f"   # actualTime format from primary endpoint
_FALLBACK_DT_FMT = "%Y-%m-%dT%H:%M:%S"      # id.dataTime format from fallback endpoint


def _fetch_cwc_observations_primary(
    session: requests.Session,
    cfg: dict,
    station_code: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame | None:
    """
    Fetch water-level time series from the primary (POST) CWC FFS endpoint.
    station_code is the raw code (e.g. "1234") -- the literal single quotes
    the API expects are added here, matching the GUARDIAN scraper exactly.
    """
    payload = {
        "stationCode": f"'{station_code}'",
        "startDate": start_date,
        "endDate": end_date,
    }
    try:
        r = _post(session, CWC_STATIONDATA_URL, cfg, json_body=payload, timeout=60)
        data = r.json()
    except Exception as exc:
        logger.warning(
            "CWC FFS primary endpoint failed for station code %s: %s",
            station_code, exc,
        )
        return None

    if not isinstance(data, list) or not data:
        logger.debug(
            "CWC FFS primary endpoint returned no usable records for station "
            "code %s (type=%s)", station_code, type(data).__name__,
        )
        return None

    rows = []
    for rec in data:
        try:
            rows.append({
                "observation_datetime": datetime.strptime(rec["actualTime"], _PRIMARY_DT_FMT),
                "water_level": rec["value"],
                "cwc_station_code": rec.get("stationCode", station_code),
            })
        except (KeyError, ValueError, TypeError):
            continue

    if not rows:
        logger.debug("CWC FFS primary endpoint: 0 parseable rows for station code %s", station_code)
        return None

    df = pd.DataFrame(rows).sort_values("observation_datetime")
    logger.debug("CWC FFS primary endpoint: %d rows for station code %s", len(df), station_code)
    return df


def _fetch_cwc_observations_fallback(
    session: requests.Session,
    cfg: dict,
    station_code: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame | None:
    """
    Fetch water-level time series from the fallback (GET) CWC FFS endpoint.
    Only tried if the primary POST endpoint fails or returns nothing.
    datatypeCode is fixed to "HHS" (hourly water-level series), matching the
    GUARDIAN scraper's v2 notebook.
    """
    specification = (
        '%7B%22where%22:%7B%22where%22:%7B%22where%22:%7B%22expression%22:'
        '%7B%22valueIsRelationField%22:false,%22fieldName%22:%22id.stationCode%22,'
        f'%22operator%22:%22eq%22,%22value%22:%22{station_code}%22%7D%7D,'
        '%22and%22:%7B%22expression%22:%7B%22valueIsRelationField%22:false,'
        '%22fieldName%22:%22id.datatypeCode%22,%22operator%22:%22eq%22,'
        '%22value%22:%22HHS%22%7D%7D%7D,%22and%22:%7B%22expression%22:'
        '%7B%22valueIsRelationField%22:false,%22fieldName%22:%22dataValue%22,'
        '%22operator%22:%22null%22,%22value%22:%22false%22%7D%7D%7D,'
        '%22and%22:%7B%22expression%22:%7B%22valueIsRelationField%22:false,'
        '%22fieldName%22:%22id.dataTime%22,%22operator%22:%22btn%22,'
        f'%22value%22:%22{start_date}T00:00:00.000,{end_date}T23:59:59.000%22%7D%7D%7D'
    )
    params = {
        "sort-criteria": (
            '%7B%22sortOrderDtos%22:%5B%7B%22sortDirection%22:%22ASC%22,'
            '%22field%22:%22id.dataTime%22%7D%5D%7D'
        ),
        "specification": specification,
    }
    try:
        r = _get(session, CWC_STATIONDATA_FALLBACK_URL, cfg, params=params, timeout=60)
        data = r.json()
    except Exception as exc:
        logger.warning(
            "CWC FFS fallback endpoint failed for station code %s: %s",
            station_code, exc,
        )
        return None

    if not isinstance(data, list) or not data:
        logger.debug(
            "CWC FFS fallback endpoint returned no usable records for "
            "station code %s", station_code,
        )
        return None

    rows = []
    for rec in data:
        try:
            rows.append({
                "observation_datetime": datetime.strptime(rec["id"]["dataTime"], _FALLBACK_DT_FMT),
                "water_level": rec["dataValue"],
                "cwc_station_code": rec.get("stationCode", station_code),
            })
        except (KeyError, ValueError, TypeError):
            continue

    if not rows:
        logger.debug("CWC FFS fallback endpoint: 0 parseable rows for station code %s", station_code)
        return None

    df = pd.DataFrame(rows).sort_values("observation_datetime")
    logger.debug("CWC FFS fallback endpoint: %d rows for station code %s", len(df), station_code)
    return df


def _fetch_cwc_observations(
    session: requests.Session,
    cfg: dict,
    station_code: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame | None:
    """Try the primary POST endpoint first, then the fallback GET endpoint."""
    df = _fetch_cwc_observations_primary(session, cfg, station_code, start_date, end_date)
    if df is not None and not df.empty:
        return df

    logger.info(
        "CWC FFS primary endpoint gave no data for station code %s -- trying fallback endpoint",
        station_code,
    )
    return _fetch_cwc_observations_fallback(session, cfg, station_code, start_date, end_date)


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
) -> bool:
    """
    Attempt to collect data for one station.
    Returns True if any data was saved, False otherwise.

    NOTE (v3): the `cwc_station_map` parameter from the previous version is
    gone. There is no live station-code lookup anymore -- CWC stations must
    carry an explicit `ffs_station_code` in config, found once via DevTools
    (see the CWC FFS live API section above).
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
    if source_name.lower() == "cwc":
        ffs_code = station.get("ffs_station_code")
        if not ffs_code:
            logger.warning(
                "Station '%s' (%s, district '%s') -- SKIPPED CWC FFS live API: "
                "no 'ffs_station_code' set in config for this station. There is "
                "no live station-list endpoint to look this up automatically -- "
                "find it once via https://ffs.india-water.gov.in/ in a browser "
                "(DevTools -> Network -> find the getHGStationDataForFFS request "
                "for this station -> copy its stationCode) and add "
                "'ffs_station_code: <code>' to this station's config entry.",
                sid, source_name, district,
            )
        else:
            df_live = _fetch_cwc_observations(session, cfg, ffs_code, start_date, end_date)
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
                    "CWC FFS returned no data for station '%s' (ffs code %s) via "
                    "either endpoint -- station may be inactive, outside date "
                    "range, or the code may be stale/incorrect",
                    sname, ffs_code,
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

    # NOTE (v3): no more pre-fetch of a global CWC station map -- there is no
    # live endpoint for that. Each station's ffs_station_code is read
    # directly from config inside _collect_station().
    cwc_cfg = rd_cfg.get("sources", {}).get("cwc", {})
    if cwc_cfg.get("enabled", True):
        n_with_code = 0
        n_total = 0
        for district_cfg in cwc_cfg.get("districts", {}).values():
            for station in district_cfg.get("stations") or []:
                n_total += 1
                if station.get("ffs_station_code"):
                    n_with_code += 1
        logger.info(
            "CWC source enabled: %d/%d configured stations have an "
            "ffs_station_code set (the rest will log a per-station WARNING "
            "and skip the live API step)",
            n_with_code, n_total,
        )
    else:
        logger.info("Source 'cwc' is disabled in config")

    # Set up per-district log files
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    metadata: dict[str, Any] = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
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
            )
            if ok:
                district_meta["sources_succeeded"].append(source_key)
                success = True
                # Do NOT break — collect from all sources; merge later if needed

        if not success:
            logger.error(
                "No source (%s) produced usable data for district '%s'. "
                "For CWC stations, check that ffs_station_code is set and "
                "still valid (station codes can be re-verified any time via "
                "DevTools on https://ffs.india-water.gov.in/).",
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