"""
collectors/census_collector.py
================================

Production-ready collector for publicly available Census of India data
(District Census Handbook / village & district level tables) for the
districts of a state-level "Weather / Digital-Twin" data pipeline.

The collector is fully **data-driven**: districts, search pages, known
direct-download links, retry policy, and output paths are all read from
``config/config.yaml``. Adding a new district (e.g. "Shimla") requires
only:

    1. Dropping a ``shimla_district.geojson`` file into the boundaries
       directory.
    2. Adding a ``shimla:`` block under ``census.districts`` in
       ``config.yaml``.

No code changes are required.

Run::

    python collectors/census_collector.py --config config/config.yaml
    python collectors/census_collector.py --district mandi --force

Author: Weather Data Project
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import urllib3
import yaml
from bs4 import BeautifulSoup

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - tqdm is a soft dependency
    def tqdm(iterable=None, **kwargs):  # type: ignore
        """Fallback no-op progress bar if tqdm isn't installed."""
        return iterable if iterable is not None else _DummyBar()

    class _DummyBar:
        def update(self, *_args, **_kwargs):
            pass

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

# --------------------------------------------------------------------------- #
# Constants & defaults
# --------------------------------------------------------------------------- #

DEFAULT_BASE_DIR = "datasets/digital_twin/population/Census"
DEFAULT_BOUNDARIES_DIR = "datasets/digital_twin/metadata/boundaries"
DEFAULT_FILE_TYPES = (".xls", ".xlsx", ".csv", ".pdf", ".zip")
DEFAULT_KEYWORDS = ("census", "dchb", "village", "district", "population", "2011")
DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 2.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; WeatherDataProjectBot/1.0; "
    "+https://example.org/bot)"
)
DEFAULT_VERIFY_SSL = True

logger = logging.getLogger("census_collector")


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #

@dataclass
class DistrictSpec:
    """Everything the collector needs to know about a single district."""

    name: str
    boundary_file: str
    search_urls: List[str] = field(default_factory=list)
    known_files: List[Dict[str, str]] = field(default_factory=list)
    census_code: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DownloadResult:
    """Outcome of a single file download attempt."""

    url: str
    district: str
    filename: str
    local_path: Optional[Path]
    success: bool
    file_size: Optional[int] = None
    error: Optional[str] = None
    description: str = ""


# --------------------------------------------------------------------------- #
# Logging setup
# --------------------------------------------------------------------------- #

def setup_logging(logs_dir: Path) -> None:
    """Configure root logger with console + rotating file handlers."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "census_collector.log"

    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)

    file_handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    logger.addHandler(console)
    logger.addHandler(file_handler)
    logger.debug("Logging initialised -> %s", log_path)


# --------------------------------------------------------------------------- #
# 1. load_config
# --------------------------------------------------------------------------- #

def load_config(config_path: str) -> Dict[str, Any]:
    """Load and normalise the census section of ``config.yaml``."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw_config = yaml.safe_load(fh) or {}

    census_cfg = raw_config.get("census", {}) or {}
    request_cfg = census_cfg.get("request", {}) or {}

    merged = {
        "base_dir": census_cfg.get("base_dir", DEFAULT_BASE_DIR),
        "boundaries_dir": census_cfg.get("boundaries_dir", DEFAULT_BOUNDARIES_DIR),
        "file_types": tuple(census_cfg.get("file_types", DEFAULT_FILE_TYPES)),
        "keywords": tuple(k.lower() for k in census_cfg.get("keywords", DEFAULT_KEYWORDS)),
        "districts": census_cfg.get("districts", {}) or {},
        "request": {
            "timeout": request_cfg.get("timeout", DEFAULT_TIMEOUT),
            "retries": request_cfg.get("retries", DEFAULT_RETRIES),
            "backoff_factor": request_cfg.get("backoff_factor", DEFAULT_BACKOFF),
            "user_agent": request_cfg.get("user_agent", DEFAULT_USER_AGENT),
            "verify_ssl": request_cfg.get("verify_ssl", DEFAULT_VERIFY_SSL),
        },
    }

    if not merged["request"]["verify_ssl"]:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        logger.warning(
            "SSL verification is DISABLED for census requests (request.verify_ssl: "
            "false in config.yaml). Only use this for known trusted government "
            "domains with certificate-chain issues -- never for arbitrary URLs."
        )

    if not merged["districts"]:
        logger.warning(
            "No 'census.districts' block found in %s -- falling back to "
            "auto-detecting districts from the boundaries directory.",
            config_path,
        )

    logger.info("Configuration loaded from %s", config_path)
    return merged


# --------------------------------------------------------------------------- #
# 2. load_boundaries
# --------------------------------------------------------------------------- #

def load_boundaries(config: Dict[str, Any]) -> List[DistrictSpec]:
    """Build a :class:`DistrictSpec` for every configured/discovered district."""
    boundaries_dir = Path(config["boundaries_dir"])
    districts_cfg: Dict[str, Any] = config["districts"]
    specs: List[DistrictSpec] = []

    if not districts_cfg:
        if not boundaries_dir.exists():
            logger.error("Boundaries directory does not exist: %s", boundaries_dir)
            return specs
        for geo_file in sorted(boundaries_dir.glob("*_district.geojson")):
            name = geo_file.stem.replace("_district", "")
            districts_cfg[name] = {"boundary_file": geo_file.name}

    for name, dcfg in districts_cfg.items():
        boundary_file = dcfg.get("boundary_file", f"{name}_district.geojson")
        boundary_path = boundaries_dir / boundary_file
        properties: Dict[str, Any] = {}
        census_code: Optional[str] = None

        if boundary_path.exists():
            try:
                with boundary_path.open("r", encoding="utf-8") as fh:
                    geo = json.load(fh)
                features = geo.get("features", [])
                if features:
                    properties = features[0].get("properties", {}) or {}
                    for key in (
                        "censuscode", "census_code", "district_c", "distcode",
                        "dtcode11", "DISTRICT_C", "district_code",
                    ):
                        if key in properties and properties[key]:
                            census_code = str(properties[key])
                            break
                logger.info(
                    "Loaded boundary for '%s' (%d feature(s)) from %s",
                    name, len(features), boundary_path,
                )
            except (json.JSONDecodeError, OSError) as exc:
                logger.error("Failed to parse boundary file %s: %s", boundary_path, exc)
        else:
            logger.warning(
                "Boundary file missing for district '%s': %s (continuing anyway)",
                name, boundary_path,
            )

        specs.append(
            DistrictSpec(
                name=name,
                boundary_file=boundary_file,
                search_urls=list(dcfg.get("search_urls", []) or []),
                known_files=list(dcfg.get("known_files", []) or []),
                census_code=census_code,
                properties=properties,
            )
        )

    logger.info("Prepared %d district specification(s): %s",
                len(specs), ", ".join(s.name for s in specs))
    return specs


# --------------------------------------------------------------------------- #
# HTTP session helper
# --------------------------------------------------------------------------- #

def _build_session(config: Dict[str, Any]) -> requests.Session:
    """Create a requests.Session with a standard User-Agent header."""
    session = requests.Session()
    session.headers.update({"User-Agent": config["request"]["user_agent"]})
    return session


def _request_with_retries(
    session: requests.Session,
    url: str,
    config: Dict[str, Any],
    stream: bool = False,
) -> Optional[requests.Response]:
    """GET a URL with exponential-backoff retries."""
    retries = config["request"]["retries"]
    timeout = config["request"]["timeout"]
    backoff = config["request"]["backoff_factor"]
    verify = config["request"]["verify_ssl"]

    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=timeout, stream=stream, verify=verify)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            logger.warning(
                "Attempt %d/%d failed for %s: %s", attempt, retries, url, exc
            )
            if attempt < retries:
                sleep_for = backoff ** attempt
                time.sleep(sleep_for)
    logger.error("All %d attempt(s) failed for %s", retries, url)
    return None


# --------------------------------------------------------------------------- #
# 3. discover_sources
# --------------------------------------------------------------------------- #

def discover_sources(
    district: DistrictSpec, config: Dict[str, Any], session: requests.Session
) -> List[Tuple[str, str, str]]:
    """Discover downloadable Census file URLs for a district."""
    discovered: Dict[str, Tuple[str, str]] = {}

    for entry in district.known_files:
        url = entry.get("url")
        if not url:
            continue
        filename = entry.get("filename") or Path(urlparse(url).path).name or "download"
        description = entry.get("description", filename)
        discovered[url] = (filename, description)

    file_types = config["file_types"]
    keywords = config["keywords"]

    for search_url in district.search_urls:
        logger.info("Scanning '%s' for downloadable Census files ...", search_url)
        resp = _request_with_retries(session, search_url, config)
        if resp is None:
            logger.error(
                "Could not reach search URL for district '%s': %s",
                district.name, search_url,
            )
            continue

        try:
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to parse HTML from %s: %s", search_url, exc)
            continue

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            full_url = urljoin(search_url, href)
            lower_href = href.lower()
            link_text = anchor.get_text(strip=True).lower()

            matches_ext = any(lower_href.endswith(ext) for ext in file_types)
            matches_keyword = any(
                kw in lower_href or kw in link_text or kw in district.name.lower()
                for kw in keywords
            )

            if matches_ext and (matches_keyword or district.name.lower() in lower_href):
                filename = Path(urlparse(full_url).path).name or f"{district.name}_file"
                description = anchor.get_text(strip=True) or filename
                discovered.setdefault(full_url, (filename, description))

    results = [(url, fname, desc) for url, (fname, desc) in discovered.items()]
    logger.info(
        "Discovered %d candidate file(s) for district '%s'",
        len(results), district.name,
    )
    return results


# --------------------------------------------------------------------------- #
# 4. download_files
# --------------------------------------------------------------------------- #

def download_files(
    district: DistrictSpec,
    sources: List[Tuple[str, str, str]],
    raw_dir: Path,
    config: Dict[str, Any],
    session: requests.Session,
    force: bool = False,
) -> List[DownloadResult]:
    """Download each discovered source file, skipping existing/valid files."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    results: List[DownloadResult] = []

    if not sources:
        logger.warning(
            "No sources to download for district '%s'. "
            "Add 'search_urls' or 'known_files' in config.yaml.",
            district.name,
        )
        return results

    for url, filename, description in tqdm(
        sources, desc=f"Downloading [{district.name}]", unit="file"
    ):
        safe_name = f"{district.name}_{filename}"
        local_path = raw_dir / safe_name

        if local_path.exists() and local_path.stat().st_size > 0 and not force:
            logger.info("Skipping existing file: %s", local_path)
            results.append(
                DownloadResult(
                    url=url, district=district.name, filename=safe_name,
                    local_path=local_path, success=True,
                    file_size=local_path.stat().st_size, description=description,
                )
            )
            continue

        resp = _request_with_retries(session, url, config, stream=True)
        if resp is None:
            results.append(
                DownloadResult(
                    url=url, district=district.name, filename=safe_name,
                    local_path=None, success=False,
                    error="Download failed after retries", description=description,
                )
            )
            continue

        try:
            total = int(resp.headers.get("content-length", 0))
            with open(local_path, "wb") as fh, tqdm(
                total=total or None, unit="B", unit_scale=True,
                desc=safe_name, leave=False,
            ) as bar:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
                        bar.update(len(chunk))

            size = local_path.stat().st_size
            logger.info("Downloaded %s (%d bytes) -> %s", url, size, local_path)
            results.append(
                DownloadResult(
                    url=url, district=district.name, filename=safe_name,
                    local_path=local_path, success=True,
                    file_size=size, description=description,
                )
            )
        except OSError as exc:
            logger.error("Failed to write file %s: %s", local_path, exc)
            results.append(
                DownloadResult(
                    url=url, district=district.name, filename=safe_name,
                    local_path=None, success=False, error=str(exc),
                    description=description,
                )
            )

    return results


# --------------------------------------------------------------------------- #
# validate_dataset
# --------------------------------------------------------------------------- #

def validate_dataset(path: Path, min_size_bytes: int = 100) -> bool:
    """Sanity-check a downloaded/extracted file."""
    if not path.exists():
        logger.error("Validation failed: file does not exist: %s", path)
        return False

    size = path.stat().st_size
    if size < min_size_bytes:
        logger.error(
            "Validation failed: %s is suspiciously small (%d bytes)", path, size
        )
        return False

    suffix = path.suffix.lower()
    try:
        if suffix == ".zip":
            with zipfile.ZipFile(path) as zf:
                bad_file = zf.testzip()
                if bad_file is not None:
                    logger.error("Corrupt member '%s' inside zip %s", bad_file, path)
                    return False
        elif suffix in (".xls", ".xlsx"):
            pd.ExcelFile(path)
        elif suffix == ".csv":
            pd.read_csv(path, nrows=5)
    except Exception as exc:
        logger.error("Validation failed for %s: %s", path, exc)
        return False

    logger.debug("Validated OK: %s (%d bytes)", path, size)
    return True


# --------------------------------------------------------------------------- #
# 5. extract_tables
# --------------------------------------------------------------------------- #

def extract_tables(
    download: DownloadResult, extract_dir: Path
) -> List[pd.DataFrame]:
    """Extract tabular data from a downloaded file into a list of DataFrames."""
    if not download.success or download.local_path is None:
        return []

    path = download.local_path
    suffix = path.suffix.lower()
    frames: List[pd.DataFrame] = []

    try:
        if suffix == ".csv":
            df = pd.read_csv(path)
            df["_source_file"] = path.name
            frames.append(df)

        elif suffix in (".xls", ".xlsx"):
            sheets = pd.read_excel(path, sheet_name=None)
            for sheet_name, df in sheets.items():
                if df is None or df.empty:
                    continue
                df["_source_sheet"] = sheet_name
                df["_source_file"] = path.name
                frames.append(df)

        elif suffix == ".zip":
            extract_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(path) as zf:
                zf.extractall(extract_dir)
                for member in zf.namelist():
                    member_path = extract_dir / member
                    if member_path.is_file() and member_path.suffix.lower() in (
                        ".csv", ".xls", ".xlsx"
                    ):
                        fake_result = DownloadResult(
                            url=download.url, district=download.district,
                            filename=member_path.name, local_path=member_path,
                            success=True, file_size=member_path.stat().st_size,
                        )
                        frames.extend(extract_tables(fake_result, extract_dir))

        elif suffix == ".pdf":
            try:
                import pdfplumber  # optional dependency
            except ImportError:
                logger.warning(
                    "pdfplumber not installed -- skipping table extraction "
                    "for PDF %s. Install with `pip install pdfplumber` to "
                    "enable this.", path,
                )
                return []
            with pdfplumber.open(path) as pdf_doc:
                for page_num, page in enumerate(pdf_doc.pages, start=1):
                    for table in page.extract_tables():
                        if not table or len(table) < 2:
                            continue
                        df = pd.DataFrame(table[1:], columns=table[0])
                        df["_source_page"] = page_num
                        df["_source_file"] = path.name
                        frames.append(df)
        else:
            logger.warning("Unsupported file type for extraction: %s", path)

    except Exception as exc:
        logger.error("Failed to extract tables from %s: %s", path, exc)
        return []

    logger.info("Extracted %d table(s) from %s", len(frames), path.name)
    return frames


# --------------------------------------------------------------------------- #
# 6. clean_data
# --------------------------------------------------------------------------- #

_COLUMN_RENAME_MAP = {
    "district": "district_name",
    "district_name": "district_name",
    "name": "village_name",
    "village_name": "village_name",
    "town_village_name": "village_name",
    "total_population": "total_population",
    "tot_p": "total_population",
    "tot_m": "male_population",
    "tot_f": "female_population",
    "male": "male_population",
    "female": "female_population",
    "no_hh": "households",
    "households": "households",
    "no_of_household": "households",
    "p_lit": "literates",
    "literates": "literates",
    "p_sc": "sc_population",
    "sc_population": "sc_population",
    "p_st": "st_population",
    "st_population": "st_population",
    "tot_workers": "total_workers",
    "main_workers": "main_workers",
    "marginal_workers": "marginal_workers",
    "non_workers": "non_workers",
    "area_sq_km": "area_sq_km",
    "area": "area_sq_km",
    "village_code": "village_code",
    "location_code": "village_code",
    "census_code": "census_code",
    "dist_code": "district_code",
    "distcode": "district_code",
}

_NUMERIC_HINTS = (
    "population", "households", "literates", "workers", "area",
    "density", "code",
)


def _normalise_column_name(col: Any) -> str:
    """Lowercase, strip, and replace spaces/punctuation with underscores."""
    text = str(col).strip().lower()
    for ch in (" ", "-", "/", "(", ")", "."):
        text = text.replace(ch, "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


def _dedupe_columns(columns: List[str]) -> List[str]:
    """Make a list of column names unique, preserving order.

    Census PDF tables extracted via ``pdfplumber`` routinely have blank,
    ``None``, or repeated header cells (merged header rows, multi-line
    headers split across cells, etc.). After :func:`_normalise_column_name`
    several of these can collapse onto the same string (e.g. two blank
    headers both becoming ``""``, or two raw columns both mapping to
    ``"district_name"`` via ``_COLUMN_RENAME_MAP``). A DataFrame with
    duplicate column labels breaks downstream: assigning a new column
    (``df["x"] = ...``), selecting a single column, and -- critically --
    ``pd.concat()`` all internally reindex columns, and pandas raises
    ``"Reindexing only valid with uniquely valued Index objects"`` the
    moment it tries to do that against a non-unique column index.

    This assigns a numeric suffix to every repeat occurrence of a name
    (first occurrence keeps the bare name), so no DataFrame we build ever
    has duplicate column labels.

    Args:
        columns: Raw (already-normalised) column names, in order.

    Returns:
        A same-length list of guaranteed-unique column names.
    """
    seen: Dict[str, int] = {}
    deduped: List[str] = []
    for col in columns:
        base = col if col else "unnamed"
        if base not in seen:
            seen[base] = 0
            deduped.append(base)
        else:
            seen[base] += 1
            deduped.append(f"{base}_{seen[base]}")
    return deduped


def clean_data(
    frames: List[pd.DataFrame], district: DistrictSpec
) -> Optional[pd.DataFrame]:
    """Normalise, tag, and concatenate raw extracted tables.

    - Lower-cases / snake-cases column names.
    - Maps common Census column spelling variants onto a canonical schema
      (see ``_COLUMN_RENAME_MAP``).
    - Deduplicates column labels so every frame has a unique column index
      before it's touched further (see :func:`_dedupe_columns`) -- this is
      what makes the later ``pd.concat`` safe.
    - Coerces population/household/area-like columns to numeric.
    - Derives ``population_density`` when both population and area exist.
    - Stamps every row with the district name and census code.

    Args:
        frames: Raw DataFrames from :func:`extract_tables`.
        district: The district these frames belong to.

    Returns:
        A single cleaned DataFrame, or ``None`` if there was nothing to clean.
    """
    if not frames:
        logger.warning("No frames to clean for district '%s'", district.name)
        return None

    cleaned_frames: List[pd.DataFrame] = []

    for raw_df in frames:
        df = raw_df.copy()

        # Step 1: normalise raw header text (may still collide, e.g. two
        # blank/merged header cells both becoming "").
        df.columns = [_normalise_column_name(c) for c in df.columns]

        # Step 2: dedupe *before* renaming. If we deduped only after the
        # rename below, two already-duplicate raw columns would still be
        # ambiguous when the rename dict looks them up (dict keys can't
        # carry duplicates, but the DataFrame's column index still can).
        df.columns = _dedupe_columns(list(df.columns))

        df = df.rename(columns={
            c: _COLUMN_RENAME_MAP[c] for c in df.columns if c in _COLUMN_RENAME_MAP
        })

        # Step 3: dedupe *again* after renaming. The rename map itself can
        # introduce fresh collisions -- e.g. a table with both a "district"
        # and a "district_name" column both map to canonical
        # "district_name", or two distinct raw headers ("no_hh" and
        # "households") both map onto "households".
        df.columns = _dedupe_columns(list(df.columns))

        # Drop fully-empty rows/columns produced by header/footer artifacts.
        df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")

        for col in df.columns:
            if any(hint in col for hint in _NUMERIC_HINTS):
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace(",", "", regex=False),
                    errors="coerce",
                )

        df["district_name"] = district.name.title()
        if district.census_code:
            df["census_code"] = district.census_code

        if "total_population" in df.columns and "area_sq_km" in df.columns:
            with pd.option_context("mode.use_inf_as_na", True):
                df["population_density"] = (
                    df["total_population"] / df["area_sq_km"]
                ).round(2)

        cleaned_frames.append(df)

    combined = pd.concat(cleaned_frames, ignore_index=True, sort=False)
    combined = combined.drop_duplicates()
    logger.info(
        "Cleaned data for '%s': %d rows, %d columns",
        district.name, len(combined), len(combined.columns),
    )
    return combined


# --------------------------------------------------------------------------- #
# 7. save_metadata
# --------------------------------------------------------------------------- #

def save_metadata(
    metadata_path: Path,
    entries: List[Dict[str, Any]],
) -> None:
    """Persist (append/merge) dataset metadata entries to ``metadata.json``."""
    existing: List[Dict[str, Any]] = []
    if metadata_path.exists():
        try:
            with metadata_path.open("r", encoding="utf-8") as fh:
                existing = json.load(fh)
            if not isinstance(existing, list):
                existing = []
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read existing metadata.json (%s); recreating.", exc)
            existing = []

    by_key = {e.get("file_name"): e for e in existing if "file_name" in e}
    for entry in entries:
        by_key[entry["file_name"]] = entry

    merged = list(by_key.values())
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with metadata_path.open("w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2, ensure_ascii=False, default=str)

    logger.info("Metadata saved: %s (%d total entries)", metadata_path, len(merged))


def _make_metadata_entry(
    download: DownloadResult,
    cleaned_df: Optional[pd.DataFrame],
    cleaned_file: Optional[Path],
) -> Dict[str, Any]:
    """Build a single metadata.json record for one downloaded/cleaned file."""
    return {
        "dataset_name": download.description or download.filename,
        "source_url": download.url,
        "download_date": datetime.now(timezone.utc).isoformat(),
        "district": download.district.title(),
        "file_name": download.filename,
        "file_format": Path(download.filename).suffix.lstrip(".").lower(),
        "file_size_bytes": download.file_size,
        "num_records": int(len(cleaned_df)) if cleaned_df is not None else None,
        "cleaned_file": str(cleaned_file) if cleaned_file else None,
        "last_updated": None,
        "checksum_sha256": (
            _sha256(download.local_path) if download.local_path else None
        ),
        "status": "success" if download.success else "failed",
        "error": download.error,
    }


def _sha256(path: Path, chunk_size: int = 65536) -> Optional[str]:
    """Compute the SHA-256 checksum of a file, or None if it can't be read."""
    if not path or not path.exists():
        return None
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(chunk_size), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def process_district(
    district: DistrictSpec,
    dirs: Dict[str, Path],
    config: Dict[str, Any],
    session: requests.Session,
    force: bool,
) -> List[Dict[str, Any]]:
    """Run the full discover -> download -> extract -> clean pipeline for one district."""
    logger.info("=" * 70)
    logger.info("Processing district: %s", district.name.upper())
    logger.info("=" * 70)

    metadata_entries: List[Dict[str, Any]] = []

    try:
        sources = discover_sources(district, config, session)
    except Exception as exc:
        logger.error(
            "discover_sources failed for '%s': %s -- skipping district.",
            district.name, exc,
        )
        return metadata_entries

    if not sources:
        logger.warning(
            "No Census sources available for district '%s'. "
            "Official data may be unpublished/unreachable. Continuing "
            "with remaining districts.", district.name,
        )
        return metadata_entries

    downloads = download_files(
        district, sources, dirs["raw"], config, session, force=force
    )

    for dl in downloads:
        if not dl.success or dl.local_path is None:
            logger.error(
                "Download failed for %s (%s): %s", dl.filename, dl.url, dl.error
            )
            metadata_entries.append(_make_metadata_entry(dl, None, None))
            continue

        if not validate_dataset(dl.local_path):
            logger.error("Validation failed for downloaded file: %s", dl.local_path)
            dl.success = False
            dl.error = "Failed post-download validation"
            metadata_entries.append(_make_metadata_entry(dl, None, None))
            continue

        try:
            frames = extract_tables(dl, dirs["extract"])
            cleaned_df = clean_data(frames, district) if frames else None
        except Exception as exc:
            logger.error(
                "extract/clean failed for %s: %s", dl.local_path, exc
            )
            metadata_entries.append(_make_metadata_entry(dl, None, None))
            continue

        cleaned_file: Optional[Path] = None
        if cleaned_df is not None and not cleaned_df.empty:
            stem = Path(dl.filename).stem
            csv_path = dirs["cleaned"] / f"{stem}.csv"
            cleaned_df.to_csv(csv_path, index=False)
            cleaned_file = csv_path
            try:
                parquet_path = dirs["cleaned"] / f"{stem}.parquet"
                cleaned_df.to_parquet(parquet_path, index=False)
            except (ImportError, ValueError) as exc:
                logger.warning(
                    "Parquet write skipped for %s (install 'pyarrow' to "
                    "enable): %s", stem, exc,
                )
            logger.info("Saved cleaned dataset: %s", csv_path)
        else:
            logger.warning(
                "No tabular data could be cleaned from %s", dl.local_path
            )

        metadata_entries.append(_make_metadata_entry(dl, cleaned_df, cleaned_file))

    return metadata_entries


def build_dirs(base_dir: Path) -> Dict[str, Path]:
    """Create and return the standard Census output directory layout."""
    dirs = {
        "raw": base_dir / "raw",
        "cleaned": base_dir / "cleaned",
        "logs": base_dir / "logs",
        "extract": base_dir / "raw" / "_extracted",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Collect public Census of India data for configured districts."
    )
    parser.add_argument(
        "--config", default="config/config.yaml",
        help="Path to config.yaml (default: config/config.yaml)",
    )
    parser.add_argument(
        "--district", default=None,
        help="Process only this district (name must match config/boundary key).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-download files even if they already exist locally.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point: orchestrates the full multi-district Census collection run."""
    args = parse_args(argv)

    try:
        config = load_config(args.config)
    except (FileNotFoundError, yaml.YAMLError) as exc:
        print(f"FATAL: could not load config '{args.config}': {exc}", file=sys.stderr)
        return 1

    base_dir = Path(config["base_dir"])
    dirs = build_dirs(base_dir)
    setup_logging(dirs["logs"])

    logger.info("Census collector starting run at %s", datetime.now().isoformat())

    districts = load_boundaries(config)
    if args.district:
        districts = [d for d in districts if d.name.lower() == args.district.lower()]
        if not districts:
            logger.error("Requested district '%s' not found in config/boundaries.", args.district)
            return 1

    session = _build_session(config)
    all_metadata: List[Dict[str, Any]] = []

    for district in districts:
        try:
            entries = process_district(district, dirs, config, session, force=args.force)
            all_metadata.extend(entries)
        except Exception as exc:  # noqa: BLE001 - top-level safety net
            logger.error(
                "Unexpected error processing district '%s': %s. "
                "Continuing with remaining districts.", district.name, exc,
                exc_info=True,
            )
            continue

    save_metadata(base_dir / "metadata.json", all_metadata)

    ok = sum(1 for e in all_metadata if e.get("status") == "success")
    fail = len(all_metadata) - ok
    logger.info(
        "Run complete: %d succeeded, %d failed, %d district(s) processed.",
        ok, fail, len(districts),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())