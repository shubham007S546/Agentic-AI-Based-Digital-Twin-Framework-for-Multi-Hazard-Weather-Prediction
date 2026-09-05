"""
climate_index_collector.py
===========================

Collector for large-scale ocean-atmosphere climate indices used as predictors
in the Himachal Climate Digital Twin pipeline:

    1. ENSO   - Oceanic Nino Index / Nino 3.4               (NOAA CPC)
    2. IOD    - Indian Ocean Dipole / Dipole Mode Index       (NOAA PSL)
    3. SOI    - Southern Oscillation Index                    (NOAA CPC)
    4. CO2    - Atmospheric CO2 concentration, Mauna Loa       (NOAA GML)

All sources are official, public, and require no authentication. The
collector reads everything it needs (date range, paths, retry policy) from
config/config.yaml and follows the same architecture, logging style,
metadata generation, validation, retry/resume, and progress-bar conventions
used across the other collectors in this repository (see era5_collector.py,
hpsdma_collector.py, imd_collector.py, etc.).

Output layout
-------------
digital_twin/climate_indices/<INDEX>/
    raw/        -> untouched downloaded source files
    cleaned/    -> standardized long-format CSV (date, value[, extra cols])
    logs/       -> per-run log file for this index
    metadata.json

Usage
-----
    python -m collectors.climate_index_collector
    python collectors/climate_index_collector.py --index ENSO
    python collectors/climate_index_collector.py --force
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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

COLLECTOR_NAME = "climate_index_collector"
CONFIG_PATH = Path("config/config.yaml")

# Official public source endpoints. These are stable, well-known government
# data products and do not require API keys. Used as a fallback default when
# config.yaml doesn't specify a source_url for a given index (this is always
# the case for SOI, which has no entry under digital_twin_sources.climate_indices).
SOURCE_URLS: Dict[str, str] = {
    "ENSO": "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt",
    "IOD": "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data",
    "SOI": "https://www.cpc.ncep.noaa.gov/data/indices/soi",
    "CO2": "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.txt",
}

INDEX_NAMES = list(SOURCE_URLS.keys())

# Maps config.yaml's lowercase digital_twin_sources.climate_indices.indices
# keys back to this collector's internal uppercase index names.
CONFIG_INDEX_KEY_MAP = {"enso": "ENSO", "iod": "IOD", "co2": "CO2"}

MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

# Seasonal 3-letter codes used in the ONI file (DJF, JFM, FMA, ...) mapped to
# the representative (center) calendar month of the 3-month window.
ONI_SEASON_CENTER_MONTH = {
    "DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
    "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12,
}


# --------------------------------------------------------------------------- #
# Config loading
# --------------------------------------------------------------------------- #

@dataclass
class ClimateIndexConfig:
    """Resolved configuration for a single collector run."""

    start_year: int
    end_year: int
    base_dir: Path
    indices: List[str] = field(default_factory=lambda: list(INDEX_NAMES))
    source_urls: Dict[str, str] = field(default_factory=lambda: dict(SOURCE_URLS))
    max_retries: int = 3
    backoff_factor: float = 2.0
    timeout_seconds: int = 60
    user_agent: str = "himachal-climate-digital-twin/2.1"
    force: bool = False


def load_config(config_path: Path = CONFIG_PATH) -> ClimateIndexConfig:
    """Load and validate collector configuration from config/config.yaml.

    Reads (matching the project's actual config.yaml schema)::

        project:
          start_year: 2005
          end_year:   2025

        paths:
          root:
            digital_twin: digital_twin
          climate_indices:
            root: digital_twin/climate_indices

        digital_twin_sources:
          climate_indices:
            indices:
              enso: {source_url: ..., index_name: ...}
              iod:  {source_url: ..., index_name: ...}
              co2:  {source_url: ..., index_name: ...}

        http:
          timeout_seconds: 120
          max_retries: 5
          backoff_factor: 2.0

    Notes:
        - SOI has no entry under digital_twin_sources.climate_indices.indices
          in config.yaml, so it is always included by default (using the
          hardcoded SOURCE_URLS fallback) and can't currently be disabled or
          reconfigured from config.yaml. Add an `soi:` block there if you
          want that to change.
        - Per-index `source_url` values in config.yaml (when present) take
          priority over the hardcoded SOURCE_URLS defaults, so pointing
          config.yaml at a different mirror doesn't require a code change.

    Raises:
        FileNotFoundError: if config.yaml is missing.
        ValueError: if required keys (start_year/end_year) are absent or invalid.
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
    climate_indices_cfg = paths_cfg.get("climate_indices", {}) or {}
    base_dir = Path(
        climate_indices_cfg.get("root", digital_twin_root / "climate_indices")
    )

    # digital_twin_sources.climate_indices.indices is a dict keyed by lowercase
    # index name (enso/iod/co2), each with its own source_url/index_name.
    dt_sources = raw_cfg.get("digital_twin_sources", {}) or {}
    ci_cfg = dt_sources.get("climate_indices", {}) or {}
    ci_indices_cfg: Dict[str, Any] = ci_cfg.get("indices", {}) or {}

    configured_indices = [
        CONFIG_INDEX_KEY_MAP[k] for k in ci_indices_cfg if k in CONFIG_INDEX_KEY_MAP
    ]
    # SOI isn't represented in config.yaml at all; keep it available by default
    # since the collector still knows how to fetch/parse it.
    indices = configured_indices + (["SOI"] if "SOI" not in configured_indices else [])
    if not indices:
        indices = list(INDEX_NAMES)

    invalid = [i for i in indices if i not in INDEX_NAMES]
    if invalid:
        raise ValueError(
            f"Unknown climate index/indices in config: {invalid}. "
            f"Valid options are {INDEX_NAMES}"
        )

    # Let config.yaml override individual source URLs where it specifies them;
    # otherwise fall back to the hardcoded defaults (always true for SOI).
    source_urls = dict(SOURCE_URLS)
    for lower_key, upper_key in CONFIG_INDEX_KEY_MAP.items():
        entry = ci_indices_cfg.get(lower_key) or {}
        url = entry.get("source_url")
        if url:
            source_urls[upper_key] = url

    http_cfg = raw_cfg.get("http", {}) or {}

    return ClimateIndexConfig(
        start_year=start_year,
        end_year=end_year,
        base_dir=base_dir,
        indices=indices,
        source_urls=source_urls,
        max_retries=int(http_cfg.get("max_retries", 3)),
        backoff_factor=float(http_cfg.get("backoff_factor", 2.0)),
        timeout_seconds=int(http_cfg.get("timeout_seconds", 60)),
        user_agent="himachal-climate-digital-twin/2.1",
    )


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #

def setup_logger(name: str, log_dir: Path) -> logging.Logger:
    """Create a logger that writes to both console and a per-index log file."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{name.lower()}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.log"

    logger = logging.getLogger(f"{COLLECTOR_NAME}.{name}")
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
# Download
# --------------------------------------------------------------------------- #

def download_raw_file(
    url: str,
    dest_path: Path,
    cfg: ClimateIndexConfig,
    logger: logging.Logger,
    force: bool = False,
) -> Path:
    """Download a raw source file, skipping if it already exists (resume support).

    Args:
        url: source URL to fetch.
        dest_path: where the raw file should be written.
        cfg: resolved collector config (timeouts, retry policy, user agent).
        logger: logger for this index.
        force: if True, re-download even if the file already exists.

    Returns:
        Path to the downloaded (or pre-existing) raw file.

    Raises:
        requests.RequestException: if all retry attempts fail.
        ValueError: if the downloaded content is empty.
    """
    if dest_path.exists() and not force:
        logger.info("Raw file already exists, skipping download: %s", dest_path.name)
        return dest_path

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": cfg.user_agent}

    def _fetch() -> bytes:
        resp = requests.get(url, headers=headers, timeout=cfg.timeout_seconds)
        resp.raise_for_status()
        if not resp.content or not resp.content.strip():
            raise ValueError(f"Downloaded content from {url} is empty")
        return resp.content

    content = retry_with_backoff(
        _fetch, cfg.max_retries, cfg.backoff_factor, logger, description=f"download {url}"
    )

    with open(dest_path, "wb") as fh:
        fh.write(content)

    logger.info("Downloaded %s (%d bytes) -> %s", url, len(content), dest_path)
    return dest_path


def file_checksum(path: Path) -> str:
    """Return the SHA-256 checksum of a file, used for metadata + validation."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_raw_file(path: Path, min_bytes: int = 50) -> None:
    """Basic sanity validation of a downloaded raw file.

    Raises:
        ValueError: if the file is missing, empty, or suspiciously small
            (a common symptom of a captured error page instead of real data).
    """
    if not path.exists():
        raise ValueError(f"Expected raw file does not exist: {path}")
    size = path.stat().st_size
    if size < min_bytes:
        raise ValueError(f"Raw file {path} is only {size} bytes; likely invalid/corrupt")


# --------------------------------------------------------------------------- #
# Parsers - one per index, each returns a tidy long-format DataFrame with
# columns: date (YYYY-MM-01), value, index (+ any index-specific extra column)
# --------------------------------------------------------------------------- #

def parse_enso_oni(raw_path: Path) -> pd.DataFrame:
    """Parse the NOAA CPC ONI ascii file into a tidy monthly DataFrame.

    Source format (whitespace separated, one row per 3-month season)::

        SEAS  YR    TOTAL  ANOM
        DJF   1950  24.72  -1.53
        ...

    Each seasonal (3-month running mean) value is mapped to the center month
    of that season, e.g. DJF 1950 -> 1950-01-01.
    """
    df = pd.read_csv(raw_path, sep=r"\s+", engine="python")
    df.columns = [c.strip().upper() for c in df.columns]
    required = {"SEAS", "YR", "ANOM"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"ONI file missing expected columns: {missing}")

    def season_to_date(row) -> Optional[pd.Timestamp]:
        month = ONI_SEASON_CENTER_MONTH.get(str(row["SEAS"]).strip().upper())
        if month is None:
            return None
        return pd.Timestamp(year=int(row["YR"]), month=month, day=1)

    df["date"] = df.apply(season_to_date, axis=1)
    df = df.dropna(subset=["date"])
    out = pd.DataFrame(
        {
            "date": df["date"].dt.strftime("%Y-%m-%d"),
            "value": pd.to_numeric(df["ANOM"], errors="coerce"),
            "index": "ENSO_ONI",
        }
    )
    out = out.dropna(subset=["value"]).sort_values("date").reset_index(drop=True)
    return out


def parse_iod_dmi(raw_path: Path) -> pd.DataFrame:
    """Parse the NOAA PSL DMI (Dipole Mode Index) fixed-width text file.

    Source format::

        <start_year> <end_year>
        <year> <jan> <feb> ... <dec>
        ...
        <missing_value_flag>
        (trailing metadata/citation text)
    """
    with open(raw_path, "r", encoding="utf-8", errors="ignore") as fh:
        lines = [ln.strip() for ln in fh if ln.strip()]

    if not lines:
        raise ValueError(f"DMI file {raw_path} is empty after stripping blank lines")

    # First line: "start_year end_year"
    header_parts = lines[0].split()
    if len(header_parts) < 2:
        raise ValueError(f"Unexpected DMI header line: {lines[0]!r}")

    records = []
    missing_value: Optional[float] = None
    for line in lines[1:]:
        parts = line.split()
        # A valid data row is "year v1 v2 ... v12" (13 tokens), all numeric.
        if len(parts) == 13 and all(_is_number(p) for p in parts):
            year = int(float(parts[0]))
            for month_idx, val_str in enumerate(parts[1:], start=1):
                records.append((year, month_idx, float(val_str)))
        elif len(parts) == 1 and _is_number(parts[0]):
            # Trailing missing-value sentinel line, e.g. "-9999.0"
            missing_value = float(parts[0])
            break
        else:
            # Reached citation/footer text - stop parsing data rows.
            break

    if not records:
        raise ValueError(f"No numeric DMI data rows parsed from {raw_path}")

    df = pd.DataFrame(records, columns=["year", "month", "value"])
    if missing_value is not None:
        df = df[df["value"] != missing_value]
    df = df[df["value"].abs() < 900]  # guard against other sentinel encodings

    df["date"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=1))
    out = pd.DataFrame(
        {
            "date": df["date"].dt.strftime("%Y-%m-%d"),
            "value": df["value"],
            "index": "IOD_DMI",
        }
    )
    out = out.sort_values("date").reset_index(drop=True)
    return out


def parse_soi(raw_path: Path) -> pd.DataFrame:
    """Parse the NOAA CPC SOI text file into a tidy monthly DataFrame.

    Source format::

        <year> <jan> <feb> ... <dec>
        ...

    with header/footer text lines that are skipped.
    """
    records = []
    with open(raw_path, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) == 13 and _is_number(parts[0]) and len(parts[0]) == 4:
                year = int(parts[0])
                if not (1800 < year < 2100):
                    continue
                for month_idx, val_str in enumerate(parts[1:], start=1):
                    if _is_number(val_str):
                        records.append((year, month_idx, float(val_str)))

    if not records:
        raise ValueError(f"No numeric SOI data rows parsed from {raw_path}")

    df = pd.DataFrame(records, columns=["year", "month", "value"])
    df = df[df["value"].abs() < 900]  # drop sentinel/missing values (e.g. -999.9)
    df["date"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=1))
    out = pd.DataFrame(
        {
            "date": df["date"].dt.strftime("%Y-%m-%d"),
            "value": df["value"],
            "index": "SOI",
        }
    )
    out = out.sort_values("date").reset_index(drop=True)
    return out


def parse_co2_mlo(raw_path: Path) -> pd.DataFrame:
    """Parse the NOAA GML Mauna Loa monthly CO2 text file.

    Source format (comment lines start with '#')::

        year month decimal_date  average  deseasonalized  ndays  sdev  unc

    We use `average` (monthly mean mole fraction, ppm) as the primary value,
    replacing the -99.99 missing-value sentinel with NaN and dropping it.
    """
    with open(raw_path, "r", encoding="utf-8", errors="ignore") as fh:
        content = fh.read()

    data_lines = [ln for ln in content.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if not data_lines:
        raise ValueError(f"No data lines found in CO2 file {raw_path}")

    buf = io.StringIO("\n".join(data_lines))
    df = pd.read_csv(
        buf,
        sep=r"\s+",
        engine="python",
        header=None,
        names=["year", "month", "decimal_date", "average", "deseasonalized", "ndays", "sdev", "unc"],
    )
    df["average"] = pd.to_numeric(df["average"], errors="coerce")
    df = df[df["average"] > 0]  # drops -99.99 missing sentinel
    df["date"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=1))

    out = pd.DataFrame(
        {
            "date": df["date"].dt.strftime("%Y-%m-%d"),
            "value": df["average"],
            "index": "CO2_MLO",
        }
    )
    out = out.sort_values("date").reset_index(drop=True)
    return out


def _is_number(token: str) -> bool:
    try:
        float(token)
        return True
    except ValueError:
        return False


PARSERS: Dict[str, Callable[[Path], pd.DataFrame]] = {
    "ENSO": parse_enso_oni,
    "IOD": parse_iod_dmi,
    "SOI": parse_soi,
    "CO2": parse_co2_mlo,
}


# --------------------------------------------------------------------------- #
# Cleaning / standardization
# --------------------------------------------------------------------------- #

def clean_and_filter(df: pd.DataFrame, start_year: int, end_year: int) -> pd.DataFrame:
    """Standardize dtypes and restrict a parsed index DataFrame to the configured
    [start_year, end_year] window (inclusive).

    Raises:
        ValueError: if no rows remain after filtering (e.g. bad date range).
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])
    df = df.drop_duplicates(subset=["date"], keep="last")

    mask = (df["date"].dt.year >= start_year) & (df["date"].dt.year <= end_year)
    filtered = df.loc[mask].sort_values("date").reset_index(drop=True)

    if filtered.empty:
        raise ValueError(
            f"No records remain for years {start_year}-{end_year} after filtering "
            f"(available range: {df['date'].min()} to {df['date'].max()})"
        )

    filtered["date"] = filtered["date"].dt.strftime("%Y-%m-%d")
    return filtered[["date", "value", "index"]]


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #

def build_metadata(
    index_name: str,
    source_url: str,
    raw_path: Path,
    cleaned_path: Path,
    df: pd.DataFrame,
    start_year: int,
    end_year: int,
) -> Dict[str, Any]:
    """Assemble a metadata.json payload describing this index's collection run."""
    return {
        "index": index_name,
        "description": {
            "ENSO": "Oceanic Nino Index (ONI) / Nino 3.4 sea surface temperature anomaly",
            "IOD": "Indian Ocean Dipole / Dipole Mode Index (DMI)",
            "SOI": "Southern Oscillation Index",
            "CO2": "Atmospheric CO2 concentration, Mauna Loa Observatory (monthly mean, ppm)",
        }[index_name],
        "source_url": source_url,
        "source_agency": {
            "ENSO": "NOAA Climate Prediction Center (CPC)",
            "IOD": "NOAA Physical Sciences Laboratory (PSL)",
            "SOI": "NOAA Climate Prediction Center (CPC)",
            "CO2": "NOAA Global Monitoring Laboratory (GML)",
        }[index_name],
        "license": "Public domain (U.S. Government work)",
        "raw_file": str(raw_path),
        "raw_file_sha256": file_checksum(raw_path),
        "cleaned_file": str(cleaned_path),
        "cleaned_file_sha256": file_checksum(cleaned_path) if cleaned_path.exists() else None,
        "requested_time_period": {"start_year": start_year, "end_year": end_year},
        "actual_time_period": {
            "start_date": df["date"].min() if not df.empty else None,
            "end_date": df["date"].max() if not df.empty else None,
        },
        "record_count": int(len(df)),
        "temporal_resolution": "monthly",
        "columns": list(df.columns),
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "collector": COLLECTOR_NAME,
        "collector_version": "1.0.0",
    }


def write_metadata(metadata: Dict[str, Any], index_dir: Path) -> Path:
    """Write metadata.json for an index, merging with any prior run history."""
    metadata_path = index_dir / "metadata.json"
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
# Per-index orchestration
# --------------------------------------------------------------------------- #

def collect_index(index_name: str, cfg: ClimateIndexConfig) -> bool:
    """Run the full download -> validate -> parse -> clean -> save -> metadata
    pipeline for a single climate index.

    Returns:
        True on success, False if this index's collection failed (logged, not raised),
        so a single index failure does not abort the whole run.
    """
    index_dir = cfg.base_dir / index_name
    raw_dir = index_dir / "raw"
    cleaned_dir = index_dir / "cleaned"
    logs_dir = index_dir / "logs"
    for d in (raw_dir, cleaned_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)

    logger = setup_logger(index_name, logs_dir)
    source_url = cfg.source_urls.get(index_name, SOURCE_URLS[index_name])
    raw_filename = Path(source_url).name or f"{index_name.lower()}_raw.txt"
    raw_path = raw_dir / raw_filename
    cleaned_path = cleaned_dir / f"{index_name.lower()}_{cfg.start_year}_{cfg.end_year}.csv"

    logger.info("=== Starting collection for %s ===", index_name)
    logger.info("Source: %s", source_url)
    logger.info("Requested period: %d-%d", cfg.start_year, cfg.end_year)

    if cleaned_path.exists() and not cfg.force:
        logger.info("Cleaned output already exists, skipping (use --force to re-run): %s", cleaned_path)
        return True

    try:
        download_raw_file(source_url, raw_path, cfg, logger, force=cfg.force)
        validate_raw_file(raw_path)

        parser = PARSERS[index_name]
        parsed_df = parser(raw_path)
        logger.info("Parsed %d raw records for %s", len(parsed_df), index_name)

        cleaned_df = clean_and_filter(parsed_df, cfg.start_year, cfg.end_year)
        logger.info(
            "Filtered to %d records within %d-%d", len(cleaned_df), cfg.start_year, cfg.end_year
        )

        cleaned_df.to_csv(cleaned_path, index=False)
        logger.info("Wrote cleaned CSV -> %s", cleaned_path)

        metadata = build_metadata(
            index_name, source_url, raw_path, cleaned_path, cleaned_df, cfg.start_year, cfg.end_year
        )
        metadata_path = write_metadata(metadata, index_dir)
        logger.info("Wrote metadata -> %s", metadata_path)

        logger.info("=== Completed %s successfully ===", index_name)
        return True

    except Exception as exc:  # noqa: BLE001 - top-level guard so one index can't kill the run
        logger.error("Collection failed for %s: %s", index_name, exc, exc_info=True)
        return False


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def run(cfg: ClimateIndexConfig) -> Dict[str, bool]:
    """Run collection for every configured index, with a progress bar.

    Returns:
        Mapping of index_name -> success flag.
    """
    results: Dict[str, bool] = {}
    for index_name in tqdm(cfg.indices, desc="Climate indices", unit="index"):
        results[index_name] = collect_index(index_name, cfg)
    return results


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect global climate index datasets.")
    parser.add_argument(
        "--index",
        choices=INDEX_NAMES,
        action="append",
        dest="indices",
        help="Restrict collection to specific index/indices (repeatable). Default: all configured.",
    )
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

    if args.indices:
        cfg.indices = args.indices
    cfg.force = args.force

    print(f"[{COLLECTOR_NAME}] Collecting: {cfg.indices} for {cfg.start_year}-{cfg.end_year}")
    results = run(cfg)

    failed = [name for name, ok in results.items() if not ok]
    if failed:
        print(f"[{COLLECTOR_NAME}] Completed with failures: {failed}", file=sys.stderr)
        return 1

    print(f"[{COLLECTOR_NAME}] All indices collected successfully: {list(results.keys())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())