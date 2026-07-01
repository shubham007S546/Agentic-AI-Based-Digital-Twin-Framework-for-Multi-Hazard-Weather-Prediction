"""
collectors/nasa_collector.py
══════════════════════════════════════════════════════════════════════════════
SOURCE 3 — NASA GPM IMERG Half-Hourly Final Precipitation (3IMERGHH V07)

SPEED PATCH (this version) — on top of the previously-fixed version
─────────────────────────────────────────────────────────────────────
  SPEEDUP 1 — Day-level resume skip
    BEFORE: every run queried CMR and re-checked all 48 cached HDF5 files
            for EVERY day in range, even days fully completed in a prior run.
    AFTER : if the cleaned CSV for a day already exists, skip that day
            entirely — zero network calls, zero HDF5 checks.
    WHY    : on a restart/resume, this turns "redo everything" into
             "pick up exactly where you stopped," which is the difference
             between a multi-hour run and a multi-second skip-ahead.

  SPEEDUP 2 — Parallel downloads within a day
    BEFORE: 48 files/day downloaded one at a time, each followed by a
            blocking 0.5s sleep — fully serial, ~24s of sleep alone per day
            before any transfer time, times ~1000 days.
    AFTER : downloads within a day run concurrently via a thread pool
            (default 6 workers — modest, polite, NASA-server-friendly).
            Network I/O overlaps instead of stacking up sequentially.
    WHY    : downloading is I/O-bound; the original code never let more
             than one request be in flight, which wastes most of the wall
             clock time waiting on the network instead of using it.

  SPEEDUP 3 — Progress + ETA logging
    AFTER : logs "[idx/total] X% complete, elapsed Hh Mm, ETA ~Yh Zm" every
            10 days, so you can tell at a glance whether to keep waiting or
            something's actually stuck (e.g. repeated 403s).

BUGS FIXED FROM SUBMITTED VERSION (carried over from prior patch)
───────────────────────────────────
  BUG 1 — Wrong SOURCE_KEY / config key mismatch — fixed, config authoritative.
  BUG 2 — Hard-coded config values — fixed, everything config-driven.
  BUG 3 — _write_final_metadata passed an empty dummy DataFrame — fixed.
  BUG 4 — No config_loader validation for nasa_gpm source key — fixed.

What this collector does
────────────────────────
  1.  Reads ALL settings from config/config.yaml — nothing hard-coded.
  2.  Authenticates against NASA Earthdata using Bearer Token.
  3.  Uses NASA CMR Search API to discover granule download URLs.
  4.  For each day in [start_date, end_date] NOT already completed:
        a. Query CMR for all 48 half-hourly granule URLs
        b. Download files concurrently (skip if cached & valid)
        c. Parse HDF5 → extract time, lat, lon, precipitation, QI
        d. Crop to Mandi bounding box
        e. Clean: replace fill values, validate non-negative, log missing
        f. Save daily cleaned CSV
  5.  Write metadata.json after all days processed.

How to get NASA Earthdata token
────────────────────────────────
  1. Go to https://urs.earthdata.nasa.gov
  2. Register for a free account
  3. Login → Profile (top right) → Generate Token
  4. Copy token → paste in config.yaml under api_keys.nasa_earthdata

Install requirements
────────────────────
  pip install requests h5py numpy pandas pyarrow tqdm pyyaml

Output files
────────────
  datasets/nasa/raw/<HDF5_filename>
  datasets/nasa/cleaned/nasa_gpm_YYYYMMDD_cleaned.csv
  datasets/nasa/metadata.json
  datasets/nasa/logs/nasa_collector_YYYYMMDD.log

Usage
─────
  python -m collectors.nasa_collector
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator, Optional

import h5py
import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.config_loader   import get_config, get_source_dir, get_date_range
from utils.logger          import get_logger
from utils.http_client     import build_session, get_timeout
from utils.metadata_writer import write_metadata


# ── Module constants (truly fixed, not config-driven) ──────────────────────
SOURCE_KEY:     str = "nasa_gpm"
COLLECTOR_NAME: str = "nasa_collector"

CMR_SEARCH_URL: str = "https://cmr.earthdata.nasa.gov/search/granules.json"
_GPM_EPOCH: datetime = datetime(1980, 1, 6, 0, 0, 0)

# Pause between download requests SUBMITTED from the SAME worker thread.
# With parallel workers this is per-thread, not global, so total request
# rate is still bounded but no longer single-file-at-a-time.
POLITENESS_DELAY: float = 0.5

# How many files to download concurrently. 6 is a reasonable, polite
# default for GES DISC. If you see repeated 429s, lower this rather than
# raising it.
DOWNLOAD_CONCURRENCY: int = 6

# Log a progress/ETA line every N days processed.
PROGRESS_LOG_INTERVAL_DAYS: int = 10


# ══════════════════════════════════════════════════════════════════════════════
#  NASAGPMDownloader
# ══════════════════════════════════════════════════════════════════════════════

class NASAGPMDownloader:
    """
    Discovers and downloads GPM 3IMERGHH V07 HDF5 files using the NASA CMR
    Search API. Downloads within a day run concurrently via a thread pool.
    """

    def __init__(
        self,
        session:     requests.Session,
        raw_dir:     Path,
        timeout:     int,
        max_retries: int,
        backoff:     float,
        cmr_concept: str,
        cmr_short:   str,
        cmr_version: str,
        cmr_provider:str,
        cmr_page:    int,
        logger,
        concurrency: int = DOWNLOAD_CONCURRENCY,
    ) -> None:
        self._session      = session
        self._raw_dir      = raw_dir
        self._timeout      = timeout
        self._max_retries  = max_retries
        self._backoff      = backoff
        self._cmr_concept  = cmr_concept
        self._cmr_short    = cmr_short
        self._cmr_version  = cmr_version
        self._cmr_provider = cmr_provider
        self._cmr_page     = cmr_page
        self._logger       = logger
        self._concurrency  = max(1, concurrency)

    # ── Public ─────────────────────────────────────────────────────────────

    def download_day(self, target_date: date) -> list[Path]:
        """
        Discover and download all half-hourly HDF5 granules for one day.
        Downloads run concurrently (bounded by self._concurrency).
        """
        self._logger.debug(f"[{target_date}] Querying CMR for granules...")
        granule_urls = self._query_cmr(target_date)

        if not granule_urls:
            self._logger.warning(
                f"[{target_date}] CMR returned 0 granules. "
                "Data may not yet be published for this date."
            )
            return []

        self._logger.info(
            f"[{target_date}] CMR found {len(granule_urls)} granule(s). "
            f"Downloading with {self._concurrency} concurrent workers..."
        )

        local_paths: list[Path] = []
        with ThreadPoolExecutor(max_workers=self._concurrency) as pool:
            futures = {
                pool.submit(self._download_file_throttled, url,
                            self._raw_dir / url.split("/")[-1]): url
                for url in granule_urls
            }
            for fut in as_completed(futures):
                result = fut.result()
                if result is not None:
                    local_paths.append(result)

        return local_paths

    def _download_file_throttled(self, file_url: str, local_path: Path) -> Optional[Path]:
        """Wraps _download_file with the politeness delay, run inside a worker thread."""
        result = self._download_file(file_url, local_path)
        time.sleep(POLITENESS_DELAY)
        return result

    # ── CMR discovery ───────────────────────────────────────────────────────

    def _query_cmr(self, target_date: date) -> list[str]:
        temporal = (
            f"{target_date.strftime('%Y-%m-%d')}T00:00:00Z,"
            f"{target_date.strftime('%Y-%m-%d')}T23:59:59Z"
        )
        base_params: dict = {
            "concept_id":  self._cmr_concept,
            "temporal[]":  temporal,
            "page_size":   self._cmr_page,
            "sort_key":    "start_date",
        }

        all_urls: list[str] = []
        page_num = 1

        while True:
            params        = {**base_params, "page_num": page_num}
            response_json = self._cmr_get(params)

            if response_json is None:
                break

            entries = response_json.get("feed", {}).get("entry", [])
            if not entries:
                break

            for entry in entries:
                url = self._extract_https_url(entry)
                if url:
                    all_urls.append(url)
                else:
                    links = entry.get("links", [])
                    self._logger.debug(
                        f"  No HDF5 URL found in entry '{entry.get('title','')}'. "
                        f"Links present: {[(l.get('rel',''),l.get('href','')[:60]) for l in links[:5]]}"
                    )

            if len(entries) < self._cmr_page:
                break

            page_num += 1

        return sorted(all_urls)

    def _cmr_get(self, params: dict) -> Optional[dict]:
        for attempt in range(1, self._max_retries + 2):
            try:
                resp = self._session.get(
                    CMR_SEARCH_URL, params=params, timeout=self._timeout
                )
                if resp.status_code == 429:
                    wait = 10 * attempt
                    self._logger.warning(f"  CMR rate limited. Waiting {wait}s...")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.Timeout:
                wait = self._backoff ** attempt
                self._logger.warning(f"  CMR timeout (attempt {attempt}). Retry in {wait:.1f}s...")
                time.sleep(wait)
            except requests.exceptions.ConnectionError as exc:
                wait = self._backoff ** attempt
                self._logger.warning(f"  CMR connection error (attempt {attempt}): {exc}. Retry in {wait:.1f}s...")
                time.sleep(wait)
            except (requests.exceptions.RequestException, ValueError) as exc:
                self._logger.error(f"  CMR request/parse failed: {exc}")
                return None

        self._logger.error("  CMR: all retries exhausted.")
        return None

    @staticmethod
    def _extract_https_url(entry: dict) -> Optional[str]:
        for link in entry.get("links", []):
            href: str = link.get("href", "")
            rel:  str = link.get("rel",  "")
            if (
                href.startswith("https")
                and ".HDF5" in href.upper()
                and ("data#" in rel or "/data" in rel or "#data" in rel)
            ):
                return href

        for link in entry.get("links", []):
            href: str = link.get("href", "")
            if href.startswith("https") and ".HDF5" in href.upper():
                return href

        return None

    # ── Download ────────────────────────────────────────────────────────────

    def _download_file(self, file_url: str, local_path: Path) -> Optional[Path]:
        if local_path.exists():
            if self._is_valid_hdf5(local_path):
                self._logger.debug(f"Cached (valid): {local_path.name} — skipping.")
                return local_path
            else:
                self._logger.warning(f"Cached file corrupted: {local_path.name} — re-downloading.")
                local_path.unlink(missing_ok=True)

        self._logger.info(f"  Downloading: {local_path.name}")

        for attempt in range(1, self._max_retries + 2):
            try:
                resp = self._session.get(
                    file_url,
                    timeout=self._timeout,
                    stream=True,
                    allow_redirects=True,
                )
                if resp.status_code == 403:
                    self._logger.error(
                        f"  403 Forbidden for {local_path.name}. "
                        "Check that GES DISC app is authorized at "
                        "urs.earthdata.nasa.gov/approve_app?client_id=e2WVk8Xj-YZtRg "
                        "and that your token is fresh."
                    )
                    return None
                resp.raise_for_status()

                # Use a per-thread-safe unique temp suffix to avoid collisions
                # between concurrent downloads if two workers somehow ever
                # touch the same filename (shouldn't happen, but cheap safety).
                tmp_path = local_path.with_suffix(f".tmp{id(local_path) % 10000}")
                with open(tmp_path, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1_048_576):
                        fh.write(chunk)

                if self._is_valid_hdf5(tmp_path):
                    tmp_path.rename(local_path)
                    size_kb = local_path.stat().st_size / 1024
                    self._logger.info(f"  Downloaded: {local_path.name} ({size_kb:.1f} KB)")
                    return local_path
                else:
                    self._logger.warning(f"  Corrupted after download (attempt {attempt}): {local_path.name}")
                    tmp_path.unlink(missing_ok=True)

            except requests.exceptions.Timeout:
                wait = self._backoff ** attempt
                self._logger.warning(f"  Timeout (attempt {attempt}). Retry in {wait:.1f}s...")
                time.sleep(wait)
            except requests.exceptions.ConnectionError as exc:
                wait = self._backoff ** attempt
                self._logger.warning(f"  Connection error (attempt {attempt}): {exc}")
                time.sleep(wait)
            except requests.exceptions.RequestException as exc:
                self._logger.error(f"  HTTP error (attempt {attempt}): {exc}")
                time.sleep(self._backoff ** attempt)

        self._logger.error(f"  All retries exhausted for {local_path.name}. Skipping.")
        return None

    @staticmethod
    def _is_valid_hdf5(path: Path) -> bool:
        if not path.exists() or path.stat().st_size == 0:
            return False
        try:
            with h5py.File(path, "r") as _:
                pass
            return True
        except (OSError, RuntimeError):
            return False


# ══════════════════════════════════════════════════════════════════════════════
#  HDF5Parser
# ══════════════════════════════════════════════════════════════════════════════

class HDF5Parser:
    """Parses a single GPM 3IMERGHH V07 HDF5 file (unchanged from prior fix)."""

    def __init__(self, bbox: dict, hdf5_paths: dict, fill_value: float, logger) -> None:
        self._bbox       = bbox
        self._hdf5_paths = hdf5_paths
        self._fill_value = fill_value
        self._logger     = logger

    def parse(self, hdf5_path: Path) -> Optional[dict]:
        self._logger.debug(f"Parsing: {hdf5_path.name}")

        try:
            with h5py.File(hdf5_path, "r") as hf:
                for ds_key, ds_path in self._hdf5_paths.items():
                    if ds_path not in hf:
                        self._logger.error(
                            f"'{ds_path}' not found in {hdf5_path.name}. Skipping."
                        )
                        return None

                time_raw   = hf[self._hdf5_paths["time"]][:]
                lat_all    = hf[self._hdf5_paths["lat"]][:].astype(np.float32)
                lon_all    = hf[self._hdf5_paths["lon"]][:].astype(np.float32)
                precip_raw = hf[self._hdf5_paths["precipitation"]][:]
                qi_raw     = hf[self._hdf5_paths["precipitationQualityIndex"]][:]

        except OSError as exc:
            self._logger.error(f"Cannot open {hdf5_path.name}: {exc}")
            return None
        except Exception as exc:
            self._logger.error(f"Unexpected error parsing {hdf5_path.name}: {exc}")
            return None

        timestamp = _GPM_EPOCH + timedelta(seconds=int(time_raw[0]))
        timestamp = pd.Timestamp(timestamp, tz="UTC")

        lat_mask = (lat_all >= self._bbox["lat_min"]) & (lat_all <= self._bbox["lat_max"])
        lon_mask = (lon_all >= self._bbox["lon_min"]) & (lon_all <= self._bbox["lon_max"])

        lat_cropped = lat_all[lat_mask]
        lon_cropped = lon_all[lon_mask]

        if lat_cropped.size == 0 or lon_cropped.size == 0:
            self._logger.error(
                f"Bounding box yields 0 grid points for {hdf5_path.name}. "
                "Check location.bounding_box in config.yaml."
            )
            return None

        lat_idx = np.where(lat_mask)[0]
        lon_idx = np.where(lon_mask)[0]

        precip_2d = precip_raw[0, :, :].T
        qi_2d     = qi_raw[0, :, :].T

        precip_cropped = precip_2d[np.ix_(lat_idx, lon_idx)].astype(np.float32)
        qi_cropped     = qi_2d[np.ix_(lat_idx, lon_idx)].astype(np.float32)

        self._logger.debug(
            f"  Parsed: {hdf5_path.name} | t={timestamp} | "
            f"grid={lat_cropped.size}×{lon_cropped.size}"
        )

        return {
            "timestamp":                 timestamp,
            "latitudes":                 lat_cropped,
            "longitudes":                lon_cropped,
            "precipitation":             precip_cropped,
            "precipitationQualityIndex": qi_cropped,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  DataCleaner
# ══════════════════════════════════════════════════════════════════════════════

class DataCleaner:
    """Flattens parsed HDF5 records into a cleaned DataFrame (unchanged from prior fix)."""

    def __init__(self, fill_value: float, logger) -> None:
        self._fill_value = fill_value
        self._logger     = logger

    def build_dataframe(self, records: list[dict]) -> pd.DataFrame:
        if not records:
            return pd.DataFrame()

        rows: list[dict] = []
        for rec in records:
            ts   = rec["timestamp"]
            lats = rec["latitudes"]
            lons = rec["longitudes"]
            prec = rec["precipitation"]
            qi   = rec["precipitationQualityIndex"]
            for i, lat in enumerate(lats):
                for j, lon in enumerate(lons):
                    rows.append({
                        "timestamp":                 ts,
                        "latitude":                  float(lat),
                        "longitude":                 float(lon),
                        "precipitation":             float(prec[i, j]),
                        "precipitationQualityIndex": float(qi[i, j]),
                    })

        df = pd.DataFrame(rows)
        if df.empty:
            return df

        original_count = len(df)

        for col in ("precipitation", "precipitationQualityIndex"):
            fill_mask = df[col] < -9000
            n = int(fill_mask.sum())
            if n > 0:
                df.loc[fill_mask, col] = np.nan
                self._logger.debug(f"Replaced {n} fill-values in '{col}' with NaN.")

        neg_mask  = df["precipitation"] < 0
        neg_count = int(neg_mask.sum())
        if neg_count > 0:
            df.loc[neg_mask, "precipitation"] = np.nan
            self._logger.warning(
                f"Cleaning: {neg_count} negative precipitation values → NaN."
            )

        qi_invalid = (
            (df["precipitationQualityIndex"] < 0) |
            (df["precipitationQualityIndex"] > 1)
        ) & df["precipitationQualityIndex"].notna()
        qi_n = int(qi_invalid.sum())
        if qi_n > 0:
            df.loc[qi_invalid, "precipitationQualityIndex"] = np.nan
            self._logger.warning(f"Cleaning: {qi_n} out-of-range QI values → NaN.")

        both_null = df["precipitation"].isna() & df["precipitationQualityIndex"].isna()
        n_removed = int(both_null.sum())
        if n_removed > 0:
            df = df[~both_null].copy()
            self._logger.warning(
                f"Cleaning: removed {n_removed} fully-null rows. "
                f"Remaining: {len(df):,}/{original_count:,}"
            )

        df["latitude"]                  = df["latitude"].astype(np.float32)
        df["longitude"]                 = df["longitude"].astype(np.float32)
        df["precipitation"]             = df["precipitation"].astype(np.float32)
        df["precipitationQualityIndex"] = df["precipitationQualityIndex"].astype(np.float32)

        df = df.sort_values(
            ["timestamp", "latitude", "longitude"]
        ).reset_index(drop=True)

        self._logger.info("Cleaning: missing value summary:")
        total = len(df)
        for col in ("precipitation", "precipitationQualityIndex"):
            n   = int(df[col].isna().sum())
            pct = n / total * 100 if total > 0 else 0
            line = f"  {col:<35}: {n:>6} missing ({pct:.2f}%)"
            if n > 0:
                self._logger.warning(line)
            else:
                self._logger.info(line)

        return df


# ══════════════════════════════════════════════════════════════════════════════
#  NASAGPMCollector  (orchestrator)
# ══════════════════════════════════════════════════════════════════════════════

class NASAGPMCollector:
    """Orchestrates the full NASA GPM IMERG half-hourly collection pipeline."""

    def __init__(self) -> None:
        self._cfg = get_config()

        if SOURCE_KEY not in self._cfg.get("sources", {}):
            raise KeyError(
                f"Source key '{SOURCE_KEY}' not found in config.yaml under 'sources'. "
                f"Available keys: {list(self._cfg.get('sources', {}).keys())}"
            )

        self._src_cfg    = self._cfg["sources"][SOURCE_KEY]
        self._loc        = self._cfg["location"]
        self._source_dir = get_source_dir(SOURCE_KEY)
        self._raw_dir    = self._source_dir / "raw"
        self._clean_dir  = self._source_dir / "cleaned"
        self._log_dir    = self._source_dir / "logs"

        for d in (self._raw_dir, self._clean_dir, self._log_dir):
            d.mkdir(parents=True, exist_ok=True)

        self._logger = get_logger(COLLECTOR_NAME, source_log_dir=self._log_dir)

        self._bbox = self._loc["bounding_box"]

        bearer_token: str = self._cfg["api_keys"].get("nasa_earthdata", "")
        if not bearer_token or "YOUR_NASA" in bearer_token:
            raise ValueError(
                "NASA Earthdata token not set in config.yaml under api_keys.nasa_earthdata.\n"
                "Get a free token at: https://urs.earthdata.nasa.gov → Profile → Generate Token"
            )

        self._session = build_session(
            extra_headers={"Authorization": f"Bearer {bearer_token}"}
        )
        self._timeout = get_timeout()
        http_cfg      = self._cfg["http"]

        self._start_date, self._end_date = get_date_range()

        self._setup_netrc()

        # Allow overriding concurrency from config.yaml (sources.nasa_gpm.download_concurrency),
        # falling back to the module default if not set.
        concurrency = int(self._src_cfg.get("download_concurrency", DOWNLOAD_CONCURRENCY))

        self._downloader = NASAGPMDownloader(
            session      = self._session,
            raw_dir      = self._raw_dir,
            timeout      = self._timeout,
            max_retries  = int(http_cfg["max_retries"]),
            backoff      = float(http_cfg["backoff_factor"]),
            cmr_concept  = self._src_cfg["cmr_concept_id"],
            cmr_short    = self._src_cfg["cmr_short_name"],
            cmr_version  = self._src_cfg["cmr_version"],
            cmr_provider = self._src_cfg["cmr_provider"],
            cmr_page     = int(self._src_cfg["cmr_page_size"]),
            logger       = self._logger,
            concurrency  = concurrency,
        )

        hdf5_paths = {k: v for k, v in self._src_cfg["hdf5_paths"].items()}
        fill_value = float(self._src_cfg["fill_value"])

        self._parser  = HDF5Parser(
            bbox       = self._bbox,
            hdf5_paths = hdf5_paths,
            fill_value = fill_value,
            logger     = self._logger,
        )
        self._cleaner = DataCleaner(
            fill_value = fill_value,
            logger     = self._logger,
        )

    # ── Netrc setup ─────────────────────────────────────────────────────────

    def _setup_netrc(self) -> None:
        import os, stat
        from pathlib import Path

        username = self._cfg["api_keys"].get("nasa_username", "")
        password = self._cfg["api_keys"].get("nasa_password", "")

        if not username or not password:
            self._logger.warning(
                "nasa_username / nasa_password not set in config.yaml. "
                "GES DISC file downloads may return 403. "
                "Add these under api_keys in config.yaml for reliable downloads."
            )
            return

        netrc_path = Path.home() / ".netrc"
        line1 = "machine urs.earthdata.nasa.gov login " + username + " password " + password
        line2 = "machine data.gesdisc.earthdata.nasa.gov login " + username + " password " + password
        netrc_entry = line1 + chr(10) + line2 + chr(10)

        existing = netrc_path.read_text() if netrc_path.exists() else ""
        if "urs.earthdata.nasa.gov" not in existing:
            with open(netrc_path, "a") as f:
                f.write(netrc_entry)
            try:
                os.chmod(netrc_path, stat.S_IRUSR | stat.S_IWUSR)
            except Exception:
                pass
            self._logger.info(f".netrc updated for GES DISC authentication: {netrc_path}")
        else:
            self._logger.debug(".netrc already contains URS entry — skipping.")

    # ── Public entry point ──────────────────────────────────────────────────

    def run(self) -> None:
        self._logger.info("=" * 70)
        self._logger.info("NASA GPM IMERG Half-Hourly Collector — START")
        self._logger.info(f"Location  : {self._loc['district']}, {self._loc['state']}")
        self._logger.info(
            f"Bbox      : N={self._bbox['lat_max']} S={self._bbox['lat_min']} "
            f"W={self._bbox['lon_min']} E={self._bbox['lon_max']}"
        )
        self._logger.info(f"Period    : {self._start_date} → {self._end_date}")
        self._logger.info(f"Product   : {self._src_cfg['product']} V{self._src_cfg['version']}")
        self._logger.info(f"CMR ID    : {self._src_cfg['cmr_concept_id']} ({self._src_cfg['cmr_short_name']} V{self._src_cfg['cmr_version']})")
        self._logger.info(f"Concurrency: {self._downloader._concurrency} parallel downloads/day")
        self._logger.info("=" * 70)

        all_days        = list(self._iter_days())
        processed_days  = 0
        skipped_days    = 0
        already_done    = 0
        total_records   = 0
        total_missing   = {"precipitation": 0, "precipitationQualityIndex": 0}
        last_df: Optional[pd.DataFrame] = None
        run_start = time.monotonic()

        for idx, target_date in enumerate(all_days, 1):
            existing_csv = self._clean_dir / f"nasa_gpm_{target_date.strftime('%Y%m%d')}_cleaned.csv"

            # SPEEDUP 1: skip fully-completed days with zero network calls.
            if existing_csv.exists() and existing_csv.stat().st_size > 0:
                already_done += 1
                self._maybe_log_progress(idx, len(all_days), run_start)
                continue

            self._logger.info(f"[{idx}/{len(all_days)}] Processing {target_date}...")

            hdf5_paths = self._downloader.download_day(target_date)

            if not hdf5_paths:
                self._logger.warning(f"  No files downloaded for {target_date}. Skipping.")
                skipped_days += 1
                self._maybe_log_progress(idx, len(all_days), run_start)
                continue

            records = self._parse_files(hdf5_paths)
            if not records:
                self._logger.warning(f"  All files failed parsing for {target_date}. Skipping.")
                skipped_days += 1
                self._maybe_log_progress(idx, len(all_days), run_start)
                continue

            df_day = self._cleaner.build_dataframe(records)
            if df_day.empty:
                self._logger.warning(f"  Empty DataFrame for {target_date}. Skipping.")
                skipped_days += 1
                self._maybe_log_progress(idx, len(all_days), run_start)
                continue

            csv_path = self._save_cleaned_day(df_day, target_date)

            total_records += len(df_day)
            for col in total_missing:
                if col in df_day.columns:
                    total_missing[col] += int(df_day[col].isna().sum())

            last_df = df_day
            processed_days += 1
            self._logger.info(f"  Done: {len(df_day):,} records → {csv_path.name}")
            self._maybe_log_progress(idx, len(all_days), run_start)

        self._write_final_metadata(total_records, total_missing, last_df)

        elapsed = time.monotonic() - run_start
        self._logger.info("=" * 70)
        self._logger.info("NASA GPM IMERG Collector — COMPLETE")
        self._logger.info(f"Total days     : {len(all_days)}")
        self._logger.info(f"Already done   : {already_done} (skipped, no network calls)")
        self._logger.info(f"Newly processed: {processed_days}")
        self._logger.info(f"Skipped (fail) : {skipped_days}")
        self._logger.info(f"Total records  : {total_records:,}")
        self._logger.info(f"Elapsed        : {elapsed/3600:.1f}h")
        self._logger.info("=" * 70)

    def _maybe_log_progress(self, idx: int, total: int, run_start: float) -> None:
        """SPEEDUP 3: periodic progress + ETA, so you know whether to keep waiting."""
        if idx % PROGRESS_LOG_INTERVAL_DAYS != 0 and idx != total:
            return
        elapsed = time.monotonic() - run_start
        pct = idx / total * 100
        if idx > 0 and elapsed > 0:
            eta_seconds = (elapsed / idx) * (total - idx)
            eta_h, rem = divmod(eta_seconds, 3600)
            eta_m = rem // 60
            self._logger.info(
                f"  PROGRESS: {idx}/{total} days ({pct:.1f}%) | "
                f"elapsed {elapsed/3600:.1f}h | ETA ~{int(eta_h)}h {int(eta_m)}m"
            )

    # ── Private helpers ─────────────────────────────────────────────────────

    def _iter_days(self) -> Iterator[date]:
        cur = self._start_date
        while cur <= self._end_date:
            yield cur
            cur += timedelta(days=1)

    def _parse_files(self, hdf5_paths: list[Path]) -> list[dict]:
        records: list[dict] = []
        for path in hdf5_paths:
            rec = self._parser.parse(path)
            if rec is not None:
                records.append(rec)
            else:
                self._logger.warning(f"  Skipped (parse failed): {path.name}")
        return records

    def _save_cleaned_day(self, df: pd.DataFrame, target_date: date) -> Path:
        date_str = target_date.strftime("%Y%m%d")
        csv_path = self._clean_dir / f"nasa_gpm_{date_str}_cleaned.csv"
        df.to_csv(csv_path, index=False)
        size_kb  = csv_path.stat().st_size / 1024
        self._logger.info(
            f"  Saved: {csv_path.name} ({size_kb:.1f} KB, {len(df):,} rows)"
        )
        return csv_path

    def _write_final_metadata(
        self,
        total_records: int,
        total_missing: dict[str, int],
        last_df: Optional[pd.DataFrame],
    ) -> None:
        if last_df is not None and not last_df.empty:
            meta_df = last_df
        else:
            meta_df = pd.DataFrame({
                "timestamp":                 pd.Series(dtype="datetime64[ns, UTC]"),
                "latitude":                  pd.Series(dtype="float32"),
                "longitude":                 pd.Series(dtype="float32"),
                "precipitation":             pd.Series(dtype="float32"),
                "precipitationQualityIndex": pd.Series(dtype="float32"),
            })
            self._logger.warning(
                "No data collected — writing metadata with empty schema."
            )

        cleaned_csvs    = sorted(self._clean_dir.glob("nasa_gpm_*_cleaned.csv"))
        cleaned_path    = cleaned_csvs[-1] if cleaned_csvs else self._clean_dir / "none.csv"
        raw_hdf5s       = sorted(self._raw_dir.glob("*.HDF5"))
        raw_path        = raw_hdf5s[0]    if raw_hdf5s    else self._raw_dir    / "none.HDF5"

        meta_path = write_metadata(
            source_dir        = self._source_dir,
            source_name       = self._src_cfg["name"],
            api_url           = self._src_cfg["earthdata_base"],
            update_frequency  = self._src_cfg["update_frequency"],
            df_cleaned        = meta_df,
            raw_file_path     = raw_path,
            cleaned_file_path = cleaned_path,
            extra={
                "product":              self._src_cfg["product"],
                "version":              self._src_cfg["version"],
                "temporal_resolution":  "Half-Hourly (30-minute)",
                "spatial_resolution":   "0.1 degree (~11 km)",
                "precipitation_unit":   "mm/hr",
                "bounding_box":         self._bbox,
                "total_records":        total_records,
                "missing_summary":      total_missing,
                "date_range":           f"{self._start_date} → {self._end_date}",
                "authentication":       "NASA Earthdata Bearer Token",
                "granule_discovery":    "NASA CMR Search API",
                "files_per_day":        self._src_cfg.get("files_per_day", 48),
                "source_priority":      "Tertiary — Satellite cross-validation",
                "note": (
                    "Each daily cleaned CSV covers 48 half-hourly slots × "
                    "all grid pixels within Mandi bounding box."
                ),
            },
        )
        self._logger.info(f"Metadata written: {meta_path}")


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    collector = NASAGPMCollector()
    collector.run()