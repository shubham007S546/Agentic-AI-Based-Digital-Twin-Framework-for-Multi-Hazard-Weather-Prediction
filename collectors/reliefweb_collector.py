"""
reliefweb_collector.py
=======================

Collector for OCHA ReliefWeb disaster reports used in the Himachal Climate
Digital Twin pipeline's disaster-history domain.

Collects reports tagged with any of the configured disaster types AND
mentioning any of the configured locations (Himachal Pradesh, Mandi, Kullu,
Chamba), restricted to India, within the configured start_year/end_year
window. All request parameters (appname, locations, disaster types, date
range, paging, retry policy) are read from config/config.yaml -- nothing is
hardcoded, so the collector is reusable for other states/districts/disaster
types purely by editing config.yaml.

API notes
---------
- ReliefWeb API v1 is decommissioned; this collector uses v2 (`POST
  /v2/reports`), which requires a pre-approved `appname` (see
  api_keys.reliefweb_appname in config.yaml).
- The API has no first-class state/district filter for India, so locations
  are matched as free-text query terms (title/body) in addition to the
  country + disaster_type + date filters.
- API limits: max 1000 results per call, max 1000 calls/day (ReliefWeb ToS).
  This collector paginates with `offset`/`limit` and respects those limits
  via the configured page_size.

Output layout
-------------
datasets/digital_twin/disaster_history/ReliefWeb/
    raw/        -> one JSON file per API page (untouched API responses)
    cleaned/    -> deduplicated, normalized long-format CSV + JSON
    logs/       -> per-run log file
    metadata.json

Usage
-----
    python -m collectors.reliefweb_collector
    python collectors/reliefweb_collector.py --force
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
import requests
import yaml

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - fallback if tqdm isn't installed
    def tqdm(iterable=None, *args, **kwargs):
        return iterable if iterable is not None else []


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

COLLECTOR_NAME = "reliefweb_collector"
CONFIG_PATH = Path("config/config.yaml")

# Fields requested from the ReliefWeb API for every report. Kept explicit
# (rather than relying on a `profile`) so the response shape is predictable.
API_FIELDS_INCLUDE = [
    "title",
    "date",
    "country",
    "primary_country",
    "disaster_type",
    "body",
    "url",
    "url_alias",
    "source",
]

API_MAX_LIMIT = 1000  # hard ReliefWeb API ceiling per call


# --------------------------------------------------------------------------- #
# Config loading
# --------------------------------------------------------------------------- #

@dataclass
class ReliefWebConfig:
    """Resolved configuration for a single collector run."""

    start_year: int
    end_year: int
    base_dir: Path
    base_url: str
    appname: str
    country_filter: str
    country_iso3: str
    locations: List[str]
    disaster_types: List[str]
    page_size: int = 500
    preset: str = "analysis"
    max_retries: int = 5
    backoff_factor: float = 2.0
    timeout_seconds: int = 120
    retry_on_status: List[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])
    user_agent: str = "himachal-climate-digital-twin/2.1"
    force: bool = False


def load_config(config_path: Path = CONFIG_PATH) -> ReliefWebConfig:
    """Load and validate collector configuration from config/config.yaml.

    Reads:
        project.start_year / project.end_year        -> date range
        paths.root.digital_twin                        -> base output root
        paths.disaster_history.reliefweb                -> ReliefWeb output dir
        digital_twin_sources.reliefweb.*                -> API/query settings
        api_keys.reliefweb_appname                       -> ReliefWeb appname
        http.*                                          -> shared retry/timeout policy

    Raises:
        FileNotFoundError: if config.yaml is missing.
        ValueError: if required keys are absent, invalid, or the ReliefWeb
            appname hasn't been filled in yet (still the unresolved
            "${RELIEFWEB_APPNAME}" placeholder).
    """
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found at '{config_path}'. "
            "Copy config/config.example.yaml to config/config.yaml and fill it in."
        )

    with open(config_path, "r", encoding="utf-8") as fh:
        raw_cfg = yaml.safe_load(fh) or {}

    project_cfg = raw_cfg.get("project", {}) or {}
    start_year = project_cfg.get("start_year")
    end_year = project_cfg.get("end_year")
    if start_year is None or end_year is None:
        raise ValueError(
            "config.yaml must define project.start_year and project.end_year"
        )
    start_year, end_year = int(start_year), int(end_year)
    if start_year > end_year:
        raise ValueError(
            f"start_year ({start_year}) cannot be greater than end_year ({end_year})"
        )

    paths_cfg = raw_cfg.get("paths", {}) or {}
    digital_twin_root = Path(
        (paths_cfg.get("root", {}) or {}).get("digital_twin", "digital_twin")
    )
    disaster_history_cfg = paths_cfg.get("disaster_history", {}) or {}
    base_dir = Path(
        disaster_history_cfg.get("reliefweb", digital_twin_root / "disaster_history" / "ReliefWeb")
    )

    dt_sources = raw_cfg.get("digital_twin_sources", {}) or {}
    rw_cfg = dt_sources.get("reliefweb", {}) or {}
    if not rw_cfg:
        raise ValueError(
            "config.yaml is missing digital_twin_sources.reliefweb -- nothing to collect"
        )

    base_url = rw_cfg.get("base_url")
    if not base_url:
        raise ValueError("digital_twin_sources.reliefweb.base_url is required")

    country_filter = rw_cfg.get("country_filter", "India")
    country_iso3 = rw_cfg.get("country_iso3", "IND")

    locations = rw_cfg.get("locations") or []
    if not locations:
        raise ValueError("digital_twin_sources.reliefweb.locations must be a non-empty list")

    disaster_types = rw_cfg.get("disaster_types") or []
    if not disaster_types:
        raise ValueError("digital_twin_sources.reliefweb.disaster_types must be a non-empty list")

    page_size = int(rw_cfg.get("page_size", 500))
    if not (0 < page_size <= API_MAX_LIMIT):
        raise ValueError(
            f"digital_twin_sources.reliefweb.page_size must be between 1 and {API_MAX_LIMIT}"
        )
    preset = rw_cfg.get("preset", "analysis")

    api_keys = raw_cfg.get("api_keys", {}) or {}
    appname = api_keys.get("reliefweb_appname", "")
    if not appname or appname.strip().startswith("${"):
        raise ValueError(
            "api_keys.reliefweb_appname is not set in config.yaml. ReliefWeb "
            "requires a pre-approved appname (see "
            "https://apidoc.reliefweb.int/ for how to request one)."
        )

    http_cfg = raw_cfg.get("http", {}) or {}

    return ReliefWebConfig(
        start_year=start_year,
        end_year=end_year,
        base_dir=base_dir,
        base_url=base_url,
        appname=appname,
        country_filter=country_filter,
        country_iso3=country_iso3,
        locations=locations,
        disaster_types=disaster_types,
        page_size=page_size,
        preset=preset,
        max_retries=int(http_cfg.get("max_retries", 5)),
        backoff_factor=float(http_cfg.get("backoff_factor", 2.0)),
        timeout_seconds=int(http_cfg.get("timeout_seconds", 120)),
        retry_on_status=list(http_cfg.get("retry_on_status", [429, 500, 502, 503, 504])),
        user_agent="himachal-climate-digital-twin/2.1",
    )


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #

def setup_logger(log_dir: Path) -> logging.Logger:
    """Create a logger that writes to both console and a per-run log file."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"reliefweb_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.log"

    logger = logging.getLogger(COLLECTOR_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:  # avoid duplicate handlers on repeated calls
        logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger


# --------------------------------------------------------------------------- #
# Retry helper
# --------------------------------------------------------------------------- #

def retry_with_backoff(
    func: Callable[[], Any],
    max_retries: int,
    backoff_factor: float,
    logger: logging.Logger,
    description: str = "operation",
) -> Any:
    """Run `func` with exponential backoff retry on any exception.

    Raises the last exception if all attempts are exhausted.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001 - intentionally broad, network I/O
            last_exc = exc
            wait = backoff_factor ** (attempt - 1)
            logger.warning(
                "Attempt %d/%d failed for %s: %s", attempt, max_retries, description, exc
            )
            if attempt < max_retries:
                logger.info("Retrying %s in %.1fs...", description, wait)
                time.sleep(wait)
    logger.error("All %d attempts failed for %s", max_retries, description)
    raise last_exc  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Query construction
# --------------------------------------------------------------------------- #

def build_payload(cfg: ReliefWebConfig, offset: int) -> Dict[str, Any]:
    """Build the POST body for a single ReliefWeb /v2/reports request.

    Filters on country + disaster_type + date range; free-text queries on
    the configured location names (title/body) since ReliefWeb has no
    district-level taxonomy filter for India.
    """
    date_from = f"{cfg.start_year}-01-01T00:00:00+00:00"
    date_to = f"{cfg.end_year}-12-31T23:59:59+00:00"

    return {
        "preset": cfg.preset,
        "limit": cfg.page_size,
        "offset": offset,
        "sort": ["date:asc"],  # deterministic ordering across paginated calls
        "query": {
            "value": " OR ".join(f'"{loc}"' for loc in cfg.locations),
            "fields": ["title", "body"],
            "operator": "OR",
        },
        "filter": {
            "operator": "AND",
            "conditions": [
                {"field": "country.iso3", "value": cfg.country_iso3},
                {
                    "field": "disaster_type.name",
                    "value": cfg.disaster_types,
                    "operator": "OR",
                },
                {
                    "field": "date.original",
                    "value": {"from": date_from, "to": date_to},
                },
            ],
        },
        "fields": {"include": API_FIELDS_INCLUDE},
    }


# --------------------------------------------------------------------------- #
# Download / pagination
# --------------------------------------------------------------------------- #

def existing_page_offsets(raw_dir: Path) -> List[int]:
    """Return the sorted list of offsets already downloaded to raw/, based on
    filenames matching `page_<offset>.json`, to support resuming a partial run.
    """
    offsets = []
    pattern = re.compile(r"^page_(\d+)\.json$")
    if raw_dir.exists():
        for path in raw_dir.iterdir():
            m = pattern.match(path.name)
            if m:
                offsets.append(int(m.group(1)))
    return sorted(offsets)


def fetch_page(
    cfg: ReliefWebConfig,
    offset: int,
    logger: logging.Logger,
) -> Dict[str, Any]:
    """Fetch a single page of results from the ReliefWeb API with retries.

    Raises:
        requests.RequestException: if all retry attempts fail.
        ValueError: if the response isn't valid JSON or is missing `data`.
    """
    payload = build_payload(cfg, offset)
    headers = {"User-Agent": cfg.user_agent, "Content-Type": "application/json"}
    params = {"appname": cfg.appname}

    def _fetch() -> Dict[str, Any]:
        resp = requests.post(
            cfg.base_url,
            params=params,
            json=payload,
            headers=headers,
            timeout=cfg.timeout_seconds,
        )
        if resp.status_code in cfg.retry_on_status:
            resp.raise_for_status()
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError as exc:
            raise ValueError(f"Non-JSON response from ReliefWeb API at offset {offset}") from exc
        if "data" not in data:
            raise ValueError(f"ReliefWeb response missing 'data' key at offset {offset}: {data}")
        return data

    return retry_with_backoff(
        _fetch,
        cfg.max_retries,
        cfg.backoff_factor,
        logger,
        description=f"fetch ReliefWeb page (offset={offset})",
    )


def validate_page(data: Dict[str, Any], offset: int) -> None:
    """Basic sanity validation of a downloaded API page.

    Raises:
        ValueError: if the page structure is missing expected keys.
    """
    if "data" not in data or not isinstance(data["data"], list):
        raise ValueError(f"Malformed ReliefWeb page at offset {offset}: missing/invalid 'data'")
    if "totalCount" not in data:
        raise ValueError(f"Malformed ReliefWeb page at offset {offset}: missing 'totalCount'")


def collect_pages(cfg: ReliefWebConfig, raw_dir: Path, logger: logging.Logger) -> List[Path]:
    """Paginate through all ReliefWeb results, downloading and saving each page
    as raw JSON, skipping/resuming pages already on disk (unless force=True).

    Returns:
        Sorted list of raw page file paths covering the full result set.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    success_marker = raw_dir / "_SUCCESS"

    if success_marker.exists() and not cfg.force:
        logger.info("Raw pages already fully downloaded (found _SUCCESS marker), reusing them.")
        return sorted(raw_dir.glob("page_*.json"))

    if cfg.force:
        for stale in raw_dir.glob("page_*.json"):
            stale.unlink()
        if success_marker.exists():
            success_marker.unlink()
        start_offset = 0
    else:
        done_offsets = existing_page_offsets(raw_dir)
        start_offset = (max(done_offsets) + cfg.page_size) if done_offsets else 0
        if done_offsets:
            logger.info("Resuming pagination from offset=%d (found %d cached pages)",
                        start_offset, len(done_offsets))

    page_paths = sorted(raw_dir.glob("page_*.json"))
    offset = start_offset
    total_count: Optional[int] = None
    pbar = tqdm(desc="ReliefWeb pages", unit="page")

    while True:
        page_path = raw_dir / f"page_{offset:07d}.json"
        if page_path.exists() and not cfg.force:
            with open(page_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = fetch_page(cfg, offset, logger)
            validate_page(data, offset)
            with open(page_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            logger.info(
                "Fetched offset=%d -> %d records (totalCount=%d) -> %s",
                offset, len(data["data"]), data.get("totalCount", -1), page_path,
            )

        if page_path not in page_paths:
            page_paths.append(page_path)
        pbar.update(1)

        total_count = data.get("totalCount", total_count)
        returned = len(data.get("data", []))
        offset += cfg.page_size

        if returned < cfg.page_size or (total_count is not None and offset >= total_count):
            break

    pbar.close()
    success_marker.write_text(
        json.dumps({"completed_at_utc": datetime.now(timezone.utc).isoformat(),
                    "total_count": total_count}),
        encoding="utf-8",
    )
    logger.info("Pagination complete. total_count=%s, pages=%d", total_count, len(page_paths))
    return sorted(page_paths)


# --------------------------------------------------------------------------- #
# Parsing / normalization
# --------------------------------------------------------------------------- #

def normalize_date(raw_date: Optional[str]) -> Optional[str]:
    """Normalize a ReliefWeb ISO-8601 date string (e.g. '2023-07-10T00:00:00+00:00')
    to a plain 'YYYY-MM-DD' string. Returns None if the input can't be parsed.
    """
    if not raw_date:
        return None
    try:
        cleaned = raw_date.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def extract_coordinates(fields: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """Extract (lat, lon) from a report's `primary_country.location`, if present.

    ReliefWeb only exposes country-level coordinates for India, not
    district-level ones, so this is a best-effort country-centroid value,
    not a precise disaster location.
    """
    primary_country = fields.get("primary_country") or {}
    location = primary_country.get("location") or {}
    lat = location.get("lat")
    lon = location.get("lon")
    return (float(lat) if lat is not None else None, float(lon) if lon is not None else None)


def match_district(text: str, locations: List[str]) -> Optional[str]:
    """Best-effort district match: return the first configured location (other
    than the state name itself) found (case-insensitive) in the given text,
    or None if only the state name (or nothing) matches.
    """
    text_lower = text.lower()
    for loc in locations:
        if loc.lower() == "himachal pradesh":
            continue
        if loc.lower() in text_lower:
            return loc
    return None


def parse_report(item: Dict[str, Any], cfg: ReliefWebConfig) -> Optional[Dict[str, Any]]:
    """Convert a single raw ReliefWeb API report record into a flat dict
    matching the target schema. Returns None if the record lacks a usable id.
    """
    report_id = item.get("id")
    if report_id is None:
        return None

    fields = item.get("fields", {}) or {}
    title = fields.get("title", "") or ""
    body = fields.get("body", "") or ""

    date_field = fields.get("date", {}) or {}
    raw_date = date_field.get("original") or date_field.get("created")
    date_normalized = normalize_date(raw_date)

    countries = [c.get("name") for c in (fields.get("country") or []) if c.get("name")]
    primary_country = (fields.get("primary_country") or {}).get("name")
    country_name = primary_country or (countries[0] if countries else None)

    disaster_types = [d.get("name") for d in (fields.get("disaster_type") or []) if d.get("name")]
    sources = [s.get("name") for s in (fields.get("source") or []) if s.get("name")]

    district = match_district(f"{title} {body}", cfg.locations)
    state = "Himachal Pradesh" if "himachal pradesh" in f"{title} {body}".lower() or district else None

    lat, lon = extract_coordinates(fields)

    url = fields.get("url") or fields.get("url_alias") or f"https://reliefweb.int/node/{report_id}"

    return {
        "report_id": report_id,
        "title": title.strip(),
        "date": date_normalized,
        "country": country_name,
        "state": state,
        "district": district,
        "disaster_type": "; ".join(disaster_types) if disaster_types else None,
        "description": re.sub(r"\s+", " ", body).strip()[:5000],  # cap to keep CSV sane
        "latitude": lat,
        "longitude": lon,
        "source": "; ".join(sources) if sources else None,
        "url": url,
    }


def parse_all_pages(page_paths: List[Path], cfg: ReliefWebConfig, logger: logging.Logger) -> List[Dict[str, Any]]:
    """Load and parse every raw page file into a flat list of report dicts."""
    records: List[Dict[str, Any]] = []
    for page_path in page_paths:
        with open(page_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for item in data.get("data", []):
            record = parse_report(item, cfg)
            if record is not None:
                records.append(record)
    logger.info("Parsed %d raw report records across %d pages", len(records), len(page_paths))
    return records


def deduplicate_records(records: List[Dict[str, Any]], logger: logging.Logger) -> List[Dict[str, Any]]:
    """Remove duplicate reports by report_id, keeping the last occurrence."""
    by_id: Dict[Any, Dict[str, Any]] = {}
    for rec in records:
        by_id[rec["report_id"]] = rec
    deduped = list(by_id.values())
    removed = len(records) - len(deduped)
    if removed:
        logger.info("Removed %d duplicate report(s) by report_id", removed)
    return deduped


def clean_and_filter(records: List[Dict[str, Any]], cfg: ReliefWebConfig, logger: logging.Logger) -> pd.DataFrame:
    """Build a validated, date-filtered, sorted DataFrame from parsed records.

    Rows with an unparseable date are dropped (logged), since the date range
    filter and downstream analysis both depend on a valid date.
    """
    if not records:
        logger.warning("No records to clean (0 reports matched the query).")
        return pd.DataFrame(columns=[
            "report_id", "title", "date", "country", "state", "district",
            "disaster_type", "description", "latitude", "longitude",
            "source", "url",
        ])

    df = pd.DataFrame(records)
    before = len(df)
    df["date_parsed"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date_parsed"])
    dropped = before - len(df)
    if dropped:
        logger.warning("Dropped %d record(s) with unparseable/missing dates", dropped)

    mask = (df["date_parsed"].dt.year >= cfg.start_year) & (df["date_parsed"].dt.year <= cfg.end_year)
    df = df.loc[mask].copy()
    df = df.sort_values("date_parsed").drop(columns=["date_parsed"]).reset_index(drop=True)

    logger.info("Filtered to %d records within %d-%d", len(df), cfg.start_year, cfg.end_year)
    return df


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

def file_checksum(path: Path) -> str:
    """Return the SHA-256 checksum of a file, used for metadata + validation."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_cleaned_output(csv_path: Path, min_bytes: int = 20) -> None:
    """Sanity-check the cleaned CSV output exists and isn't suspiciously small.

    A header-only file (0 matching reports) is valid and expected in some
    date ranges/locations, so this only checks the file was written, not
    that it's non-empty of data rows.

    Raises:
        ValueError: if the file is missing entirely.
    """
    if not csv_path.exists():
        raise ValueError(f"Expected cleaned CSV does not exist: {csv_path}")
    if csv_path.stat().st_size < min_bytes:
        raise ValueError(f"Cleaned CSV {csv_path} is suspiciously small/corrupt")


def save_cleaned_outputs(df: pd.DataFrame, cleaned_dir: Path, cfg: ReliefWebConfig, logger: logging.Logger) -> Tuple[Path, Path]:
    """Write the cleaned DataFrame to both CSV and JSON, returning their paths."""
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    csv_path = cleaned_dir / f"reliefweb_{cfg.start_year}_{cfg.end_year}.csv"
    json_path = cleaned_dir / f"reliefweb_{cfg.start_year}_{cfg.end_year}.json"

    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient="records", indent=2, date_format="iso")

    logger.info("Wrote cleaned CSV -> %s", csv_path)
    logger.info("Wrote cleaned JSON -> %s", json_path)
    return csv_path, json_path


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #

def build_metadata(
    cfg: ReliefWebConfig,
    raw_pages: List[Path],
    csv_path: Path,
    json_path: Path,
    df: pd.DataFrame,
) -> Dict[str, Any]:
    """Assemble a metadata.json payload describing this collection run."""
    return {
        "source": "ReliefWeb Disaster Reports (OCHA)",
        "api_endpoint": cfg.base_url,
        "license": "Creative Commons Attribution 4.0 (CC BY 4.0)",
        "country": cfg.country_filter,
        "locations_queried": cfg.locations,
        "disaster_types_queried": cfg.disaster_types,
        "requested_time_period": {"start_year": cfg.start_year, "end_year": cfg.end_year},
        "actual_time_period": {
            "start_date": df["date"].min() if not df.empty else None,
            "end_date": df["date"].max() if not df.empty else None,
        },
        "raw_pages": [str(p) for p in raw_pages],
        "raw_pages_sha256": {str(p): file_checksum(p) for p in raw_pages},
        "cleaned_csv": str(csv_path),
        "cleaned_csv_sha256": file_checksum(csv_path) if csv_path.exists() else None,
        "cleaned_json": str(json_path),
        "cleaned_json_sha256": file_checksum(json_path) if json_path.exists() else None,
        "record_count": int(len(df)),
        "columns": list(df.columns),
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "collector": COLLECTOR_NAME,
        "collector_version": "1.0.0",
    }


def write_metadata(metadata: Dict[str, Any], base_dir: Path) -> Path:
    """Write metadata.json, merging with any prior run history (last 10 kept)."""
    metadata_path = base_dir / "metadata.json"
    history: List[Dict[str, Any]] = []
    if metadata_path.exists():
        try:
            with open(metadata_path, "r", encoding="utf-8") as fh:
                existing = json.load(fh)
            history = existing.get("history", [])
            if "collected_at_utc" in existing:
                history.append({k: v for k, v in existing.items() if k != "history"})
        except (json.JSONDecodeError, OSError):
            history = []

    metadata_with_history = dict(metadata)
    metadata_with_history["history"] = history[-9:]  # keep last 9 + current = 10 runs

    with open(metadata_path, "w", encoding="utf-8") as fh:
        json.dump(metadata_with_history, fh, indent=2, default=str)
    return metadata_path


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def run(cfg: ReliefWebConfig, logger: logging.Logger) -> bool:
    """Run the full download -> validate -> parse -> dedupe -> clean -> save ->
    metadata pipeline for ReliefWeb disaster reports.

    Returns:
        True on success, False if the run failed (logged, not raised).
    """
    raw_dir = cfg.base_dir / "raw"
    cleaned_dir = cfg.base_dir / "cleaned"

    csv_path = cleaned_dir / f"reliefweb_{cfg.start_year}_{cfg.end_year}.csv"
    if csv_path.exists() and not cfg.force:
        logger.info("Cleaned output already exists, skipping (use --force to re-run): %s", csv_path)
        return True

    logger.info("=== Starting ReliefWeb collection ===")
    logger.info("Country: %s | Locations: %s", cfg.country_filter, cfg.locations)
    logger.info("Disaster types: %s", cfg.disaster_types)
    logger.info("Period: %d-%d", cfg.start_year, cfg.end_year)

    try:
        raw_pages = collect_pages(cfg, raw_dir, logger)
        if not raw_pages:
            raise ValueError("No raw pages were downloaded or found on disk")

        records = parse_all_pages(raw_pages, cfg, logger)
        deduped = deduplicate_records(records, logger)
        df = clean_and_filter(deduped, cfg, logger)

        csv_path, json_path = save_cleaned_outputs(df, cleaned_dir, cfg, logger)
        validate_cleaned_output(csv_path)

        metadata = build_metadata(cfg, raw_pages, csv_path, json_path, df)
        metadata_path = write_metadata(metadata, cfg.base_dir)
        logger.info("Wrote metadata -> %s", metadata_path)

        logger.info("=== Completed ReliefWeb collection successfully (%d records) ===", len(df))
        return True

    except Exception as exc:  # noqa: BLE001 - top-level guard, mirrors other collectors
        logger.error("ReliefWeb collection failed: %s", exc, exc_info=True)
        return False


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect ReliefWeb disaster reports.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download and re-process even if outputs already exist.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help="Path to config.yaml (default: config/config.yaml)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[{COLLECTOR_NAME}] Config error: {exc}", file=sys.stderr)
        return 1

    cfg.force = args.force
    logger = setup_logger(cfg.base_dir / "logs")

    print(f"[{COLLECTOR_NAME}] Collecting ReliefWeb reports for "
          f"{cfg.country_filter} ({', '.join(cfg.locations)}), {cfg.start_year}-{cfg.end_year}")

    ok = run(cfg, logger)
    if not ok:
        print(f"[{COLLECTOR_NAME}] Collection failed. See logs for details.", file=sys.stderr)
        return 1

    print(f"[{COLLECTOR_NAME}] ReliefWeb collection completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())