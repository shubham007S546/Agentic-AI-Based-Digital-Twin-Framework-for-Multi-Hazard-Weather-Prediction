"""
era5_land_collector.py
=======================

Production collector for ERA5-Land daily hydrology variables over the
Himachal Climate Digital Twin's active districts (Mandi, Kullu, Chamba),
wired directly to `config/config.yaml`.

Data source
-----------
Copernicus Climate Data Store (CDS) dataset:
    "derived-era5-land-daily-statistics"

`config.yaml`'s `digital_twin_sources.era5_land` block points at the raw
hourly dataset (`reanalysis-era5-land`), which is the underlying source.
This collector intentionally requests the CDS-native **daily** aggregation
of that same underlying data instead of pulling 24x the hourly volume and
aggregating client-side -- it produces the same "ERA5-Land daily" record
the project needs, with correct handling of accumulated fields (runoff,
snowmelt, evaporation) that CDS performs server-side. If you need raw
hourly files instead, override `dataset` in `digital_twin_sources.era5_land`
and adapt `build_request` / `process_year_for_district` accordingly.

One CDS request is submitted per district per year **per variable** to stay
within the CDS per-request cost/size limits. Each variable's NetCDF is
downloaded separately and the files are merged in memory before processing
and saving. This is transparent to all downstream code -- the merged dataset
looks identical to what a single combined request would have returned.

Variables (task-defined default, overridable via config)
----------------------------------------------------------
    - volumetric_soil_water_layer_1
    - snow_depth
    - snowmelt
    - surface_runoff
    - total_evaporation
    - skin_temperature
    - soil_temperature_level_1

Config sections this script reads
-----------------------------------
    project              (start_year, end_year)
    spatial               (crs)
    districts             (per-district boundary geojson + lat/lon)
    active_districts
    processing             (clip_to_boundary, save_bbox)
    paths.root             (digital_twin, logs, metadata)
    paths.hydrology        (root)
    api_keys.cds_api_key   (read directly as a literal value from config.yaml)
    http                   (timeout_seconds, max_retries, backoff_factor)
    download               (overwrite, resume_incomplete, workers, parallel_downloads)
    output                 (formats.table, processed_format, compression, encoding, overwrite_processed)
    logging                (level, format, date_format, console, save_log, global_log_dir, rotation)
    cache                  (enabled, folder)
    validation             (required_env_vars, fail_on_missing_dirs, create_missing_dirs, min_disk_space_gb)

Note: there is no dedicated top-level `era5_land:` block in config.yaml
(unlike `census:`), so district-specific behaviour is driven by the
top-level `districts` / `active_districts` blocks, and dataset/variable
choices by `digital_twin_sources.era5_land`.

Usage
-----
    python collectors/era5_land_collector.py
    python collectors/era5_land_collector.py --config config/config.yaml
    python collectors/era5_land_collector.py --year 2020
    python collectors/era5_land_collector.py --district mandi
    python collectors/era5_land_collector.py --force
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import logging.handlers
import os
import random
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import xarray as xr
import yaml
from tqdm import tqdm

try:
    import cdsapi
except ImportError:  # pragma: no cover
    cdsapi = None

try:
    import geopandas as gpd
except ImportError:  # pragma: no cover
    gpd = None

try:
    import shapely
    from shapely.geometry import Point
    from shapely.geometry.base import BaseGeometry
except ImportError:  # pragma: no cover
    shapely = None
    Point = None
    BaseGeometry = None


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

DEFAULT_VARIABLES: List[str] = [
    "volumetric_soil_water_layer_1",
    "snow_depth",
    "snowmelt",
    "surface_runoff",
    "total_evaporation",
    "skin_temperature",
    "soil_temperature_level_1",
]

CDS_DATASET = "derived-era5-land-daily-statistics"
DAILY_STATISTIC = "daily_mean"
DAILY_TIME_ZONE = "utc+00:00"
DAILY_FREQUENCY = "1_hourly"
DEFAULT_CDS_URL = "https://cds.climate.copernicus.eu/api"

ENV_PLACEHOLDER_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
MALFORMED_PLACEHOLDER_RE = re.compile(r"^\$\{(.+)\}$")


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #

class ConfigError(RuntimeError):
    """Raised when required configuration or environment setup is invalid."""


class AuthenticationError(ConfigError):
    """Raised when the CDS API rejects our credentials (HTTP 401 / true 403-auth).

    This is not a transient error, so it should never trigger the normal
    per-job retry loop -- retrying with the same bad credentials just
    wastes time and API quota. Callers should stop the whole run instead.

    Note: CDS also returns HTTP 403 for *cost/size limit* errors
    ("Your request is too large, please reduce your selection").  Those
    are NOT authentication failures and must NOT raise this exception --
    they are handled upstream by submitting one variable per request
    instead of all variables in a single request.
    """


def _is_auth_error(exc: Exception) -> bool:
    """Detect whether an exception from cdsapi represents a true auth failure.

    CDS returns HTTP 403 for two distinct reasons:
      1. Real authentication / authorisation failure: the key is wrong,
         expired, or the user hasn't accepted the dataset licence.
      2. Cost / size limit exceeded: "Your request is too large, please
         reduce your selection." / "cost limits exceeded".

    Only case (1) is an AuthenticationError.  Case (2) is a recoverable
    request-size problem that is handled by the per-variable splitting
    logic in ``download_year``; it must NOT be reported as an auth error.

    Args:
        exc: The exception raised by ``client.retrieve(...)``.

    Returns:
        True only if the error is a genuine credential/licence rejection
        (HTTP 401, or a 403 whose message text is specifically about
        authentication, *not* about request size or cost limits).
    """
    msg = str(exc).lower()

    # Cost / size limit 403s -- these are NOT auth errors.
    cost_limit_markers = [
        "cost limits exceeded",
        "your request is too large",
        "please reduce your selection",
        "quota exceeded",
    ]
    if any(m in msg for m in cost_limit_markers):
        return False

    # True auth / licence failures.
    auth_markers = [
        "401",
        "unauthorized",
        "authentication failed",
        "operation not allowed",
        # Only flag 403 when it is NOT a cost-limit error (already excluded above).
        "403",
    ]
    return any(m in msg for m in auth_markers)


def _is_queue_throttle_error(exc: Exception) -> bool:
    """Detect whether a CDS exception is a transient queue-throttling rejection.

    CDS returns HTTP 400 "Bad Request" with a message like:
        "The job has been rejected. Number queued requests for this dataset
        is temporarily limited. Please configure your scripts accordingly."

    This is a transient server-side rate limit -- the job was not accepted
    because the account already has too many requests queued.  It is safe
    to wait and retry; it is NOT an auth error and NOT a request-size error.

    Args:
        exc: The exception raised by ``client.retrieve(...)``.

    Returns:
        True if the error is a queue-throttling rejection.
    """
    msg = str(exc).lower()
    markers = [
        "number queued requests",
        "temporarily limited",
        "job has been rejected",
    ]
    return any(m in msg for m in markers)


# --------------------------------------------------------------------------- #
# Config dataclasses
# --------------------------------------------------------------------------- #

@dataclass
class DistrictInfo:
    """A single district's identity and boundary reference."""

    key: str
    display_name: str
    boundary_path: Path
    latitude: float
    longitude: float


@dataclass
class CollectorConfig:
    """Fully resolved runtime configuration for the ERA5-Land collector."""

    project_root: Path

    # CDS auth
    cds_key: str
    cds_url: str

    # Domain
    variables: List[str]
    dataset_enabled: bool
    start_year: int
    end_year: int
    crs: str

    # Districts / spatial
    districts: Dict[str, DistrictInfo]
    active_districts: List[str]
    clip_to_boundary: bool
    save_bbox: bool
    buffer_deg: float

    # Paths
    raw_dir: Path
    cleaned_dir: Path
    era5_land_root: Path
    log_dir: Path

    # HTTP / retry
    http_timeout_seconds: int
    http_max_retries: int
    http_backoff_factor: float

    # Download behaviour
    download_overwrite: bool
    resume_incomplete: bool
    parallel_downloads: bool
    workers: int
    # Minimum seconds to wait between successive CDS retrieve() submissions.
    # CDS enforces a per-account concurrent-queued-request limit; submitting
    # jobs too quickly fills the queue and triggers HTTP 400 "Number queued
    # requests for this dataset is temporarily limited."  A small delay
    # (default 5 s) keeps the submission rate well under that threshold.
    # Configurable via download.cds_submit_delay_seconds in config.yaml.
    cds_submit_delay_seconds: float

    # Output
    table_format: str
    compression: str
    encoding: str
    overwrite_processed: bool

    # Logging
    log_level: str
    log_format: str
    log_date_format: str
    log_console: bool
    log_save: bool
    log_rotate_max_bytes: int
    log_rotate_backup_count: int

    # Cache
    cache_enabled: bool
    cache_folder: Path

    # Validation
    fail_on_missing_dirs: bool
    create_missing_dirs: bool
    min_disk_space_gb: float

    @property
    def metadata_path(self) -> Path:
        return self.era5_land_root / "metadata.json"

    @property
    def bbox_path(self) -> Path:
        return self.era5_land_root / "bbox.json"


# --------------------------------------------------------------------------- #
# Env / config resolution helpers
# --------------------------------------------------------------------------- #

def _resolve_env_placeholder(raw_value: Optional[str], label: str) -> str:
    """Resolve a config value that may be an '${ENV_VAR}' placeholder.

    Supports three cases for `raw_value`:
      1. A proper placeholder, e.g. "${CDS_API_KEY}" -> resolved from a real
         OS environment variable, if one happens to be exported (no .env
         file is read by this collector).
      2. A malformed placeholder where a real secret was pasted directly
         inside the template braces by mistake, e.g.
         "${b7fea9da-1b9c-4760-a159-eef0a23b3b16}" (hyphens are never valid
         in an environment variable name, so this can't be case 1) -> the
         inner value is used literally, with a warning, since editing
         config.yaml to remove the braces is easy to forget.
      3. A plain literal value with no braces at all, e.g.
         "b7fea9da-1b9c-4760-a159-eef0a23b3b16" -> used as-is. This is the
         recommended (and only officially supported) way to store the CDS
         key: directly in config.yaml.

    Args:
        raw_value: The raw string from config.yaml.
        label: Human-readable label for error/warning messages (e.g. 'api_keys.cds_api_key').

    Returns:
        The resolved literal value.

    Raises:
        ConfigError: If the value is missing, or a well-formed placeholder
            references an env var that isn't set.
    """
    if not raw_value:
        raise ConfigError(f"Missing value for '{label}' in config.yaml.")

    raw_value = str(raw_value).strip()

    match = ENV_PLACEHOLDER_RE.match(raw_value)
    if match:
        env_name = match.group(1)
        resolved = os.environ.get(env_name)
        if not resolved:
            raise ConfigError(
                f"'{label}' references environment variable '{env_name}', which "
                f"is not set. This collector reads credentials from config.yaml "
                f"only (no .env file support) -- put the real value directly in "
                f"config.yaml instead of a '${{...}}' placeholder."
            )
        return resolved

    malformed = MALFORMED_PLACEHOLDER_RE.match(raw_value)
    if malformed:
        inner_value = malformed.group(1)
        print(
            f"WARNING: '{label}' in config.yaml looks like "
            f"'${{...}}' but its contents aren't a valid environment variable "
            f"name -- this usually means an actual key/token was pasted inside "
            f"the template braces by mistake. Using the inner value literally "
            f"this run. To silence this warning, edit config.yaml so the line reads:\n"
            f"    {label.split('.')[-1]}: \"{inner_value}\"\n"
            f"(i.e. remove the surrounding '${{' and '}}').",
            file=sys.stderr,
        )
        return inner_value

    return raw_value


def _resolve_path(project_root: Path, path_str: str) -> Path:
    """Resolve a config path string against the project root."""
    p = Path(path_str)
    return p if p.is_absolute() else (project_root / p)


def load_config(config_path: Path) -> CollectorConfig:
    """Load and validate all settings this collector needs from config.yaml.

    Args:
        config_path: Path to the project's config.yaml file.

    Returns:
        A populated CollectorConfig instance.

    Raises:
        ConfigError: If required keys are missing or invalid.
    """
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as fh:
        cfg: Dict[str, Any] = yaml.safe_load(fh) or {}

    project_root = config_path.resolve().parent.parent

    # --- CDS auth --------------------------------------------------------
    # Read directly from config.yaml. No .env file is loaded by this
    # collector -- if api_keys.cds_api_key is a literal value (the
    # recommended setup), it is used as-is.
    api_keys = cfg.get("api_keys", {}) or {}
    cds_key = _resolve_env_placeholder(api_keys.get("cds_api_key"), "api_keys.cds_api_key")
    cds_url = str(cfg.get("cds_api_url", DEFAULT_CDS_URL))

    # --- Domain / dataset --------------------------------------------------
    project_cfg = cfg.get("project", {}) or {}
    era5_land_src = (cfg.get("digital_twin_sources", {}) or {}).get("era5_land", {}) or {}
    configured_vars = era5_land_src.get("variables")
    variables = list(configured_vars) if configured_vars else list(DEFAULT_VARIABLES)
    if configured_vars and set(configured_vars) != set(DEFAULT_VARIABLES):
        logging.getLogger("era5_land_collector").debug(
            "digital_twin_sources.era5_land.variables differs from the task's "
            "default variable set; using the config-supplied list: %s", variables
        )

    # --- Spatial / districts ------------------------------------------------
    spatial_cfg = cfg.get("spatial", {}) or {}
    crs = spatial_cfg.get("crs", "EPSG:4326")

    districts_cfg = cfg.get("districts", {}) or {}
    active_district_keys = cfg.get("active_districts") or list(districts_cfg.keys())

    districts: Dict[str, DistrictInfo] = {}
    for key in active_district_keys:
        entry = districts_cfg.get(key)
        if not entry:
            raise ConfigError(f"active_districts references unknown district '{key}'.")
        boundary_rel = entry.get("boundary")
        if not boundary_rel:
            raise ConfigError(f"districts.{key} is missing a 'boundary' path.")
        districts[key] = DistrictInfo(
            key=key,
            display_name=key.replace("_", " ").title(),
            boundary_path=_resolve_path(project_root, boundary_rel),
            latitude=float(entry.get("latitude", 0.0)),
            longitude=float(entry.get("longitude", 0.0)),
        )

    processing_cfg = cfg.get("processing", {}) or {}
    clip_to_boundary = bool(processing_cfg.get("clip_to_boundary", True))
    save_bbox = bool(processing_cfg.get("save_bbox", True))

    # --- Paths --------------------------------------------------------------
    paths_cfg = cfg.get("paths", {}) or {}
    root_cfg = paths_cfg.get("root", {}) or {}
    hydrology_cfg = paths_cfg.get("hydrology", {}) or {}

    hydrology_root = _resolve_path(project_root, hydrology_cfg.get("root", "digital_twin/hydrology"))
    era5_land_root = hydrology_root / "ERA5_Land"
    raw_dir = era5_land_root / "raw"
    cleaned_dir = era5_land_root / "cleaned"
    log_dir = _resolve_path(project_root, root_cfg.get("logs", "logs"))

    # --- HTTP / retry ---------------------------------------------------------
    http_cfg = cfg.get("http", {}) or {}

    # --- Download behaviour ----------------------------------------------------
    download_cfg = cfg.get("download", {}) or {}

    # --- Output ------------------------------------------------------------------
    output_cfg = cfg.get("output", {}) or {}
    formats_cfg = output_cfg.get("formats", {}) or {}

    # --- Logging -----------------------------------------------------------------
    logging_cfg = cfg.get("logging", {}) or {}

    # --- Cache -------------------------------------------------------------------
    cache_cfg = cfg.get("cache", {}) or {}

    # --- Validation ---------------------------------------------------------------
    validation_cfg = cfg.get("validation", {}) or {}

    return CollectorConfig(
        project_root=project_root,
        cds_key=cds_key,
        cds_url=cds_url,
        variables=variables,
        dataset_enabled=bool(era5_land_src.get("enabled", True)),
        start_year=int(project_cfg.get("start_year", 2005)),
        end_year=int(project_cfg.get("end_year", 2025)),
        crs=crs,
        districts=districts,
        active_districts=list(active_district_keys),
        clip_to_boundary=clip_to_boundary,
        save_bbox=save_bbox,
        buffer_deg=float(processing_cfg.get("buffer_deg", 0.1)),
        raw_dir=raw_dir,
        cleaned_dir=cleaned_dir,
        era5_land_root=era5_land_root,
        log_dir=log_dir,
        http_timeout_seconds=int(http_cfg.get("timeout_seconds", 120)),
        http_max_retries=int(http_cfg.get("max_retries", 5)),
        http_backoff_factor=float(http_cfg.get("backoff_factor", 2.0)),
        download_overwrite=bool(download_cfg.get("overwrite", False)),
        resume_incomplete=bool(download_cfg.get("resume_incomplete", True)),
        parallel_downloads=bool(download_cfg.get("parallel_downloads", False)),
        workers=int(download_cfg.get("workers", 4)),
        cds_submit_delay_seconds=float(download_cfg.get("cds_submit_delay_seconds", 15.0)),
        table_format=str(formats_cfg.get("table", "Parquet")).lower(),
        compression=str(output_cfg.get("compression", "snappy")),
        encoding=str(output_cfg.get("encoding", "utf-8")),
        overwrite_processed=bool(output_cfg.get("overwrite_processed", False)),
        log_level=str(logging_cfg.get("level", "INFO")),
        log_format=str(logging_cfg.get(
            "format", "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )),
        log_date_format=str(logging_cfg.get("date_format", "%Y-%m-%d %H:%M:%S")),
        log_console=bool(logging_cfg.get("console", True)),
        log_save=bool(logging_cfg.get("save_log", True)),
        log_rotate_max_bytes=int(logging_cfg.get("rotate_max_bytes", 10_485_760)),
        log_rotate_backup_count=int(logging_cfg.get("rotate_backup_count", 5)),
        cache_enabled=bool(cache_cfg.get("enabled", True)),
        cache_folder=_resolve_path(project_root, cache_cfg.get("folder", ".cache")),
        fail_on_missing_dirs=bool(validation_cfg.get("fail_on_missing_dirs", True)),
        create_missing_dirs=bool(validation_cfg.get("create_missing_dirs", True)),
        min_disk_space_gb=float(validation_cfg.get("min_disk_space_gb", 5)),
    )


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #

def setup_logging(cfg: CollectorConfig) -> logging.Logger:
    """Configure logging per the config.yaml `logging:` block.

    Args:
        cfg: Resolved collector configuration.

    Returns:
        Configured logger instance for this collector.
    """
    logger = logging.getLogger("era5_land_collector")
    logger.setLevel(getattr(logging, cfg.log_level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    fmt = logging.Formatter(cfg.log_format, datefmt=cfg.log_date_format)

    if cfg.log_console:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(fmt)
        logger.addHandler(stream_handler)

    if cfg.log_save:
        cfg.log_dir.mkdir(parents=True, exist_ok=True)
        log_file = cfg.log_dir / "era5_land_collector.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=cfg.log_rotate_max_bytes,
            backupCount=cfg.log_rotate_backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
        logger.info("Logging to %s (rotating, max_bytes=%d, backups=%d)",
                    log_file, cfg.log_rotate_max_bytes, cfg.log_rotate_backup_count)

    return logger


# --------------------------------------------------------------------------- #
# Environment / pre-flight validation
# --------------------------------------------------------------------------- #

def validate_environment(cfg: CollectorConfig, logger: logging.Logger) -> None:
    """Fail fast on missing dependencies, directories, or disk space.

    Args:
        cfg: Resolved collector configuration.
        logger: Logger for status messages.

    Raises:
        ConfigError: If a hard requirement (dependency, directory, disk space) fails.
    """
    if cdsapi is None:
        raise ConfigError(
            "The 'cdsapi' package is not installed. Install it with "
            "'pip install cdsapi --break-system-packages'."
        )
    if gpd is None:
        raise ConfigError(
            "The 'geopandas' package is not installed. Install it with "
            "'pip install geopandas --break-system-packages'."
        )
    if shapely is None:
        raise ConfigError(
            "The 'shapely' package is not installed. Install it with "
            "'pip install shapely --break-system-packages'."
        )

    required_dirs = [cfg.raw_dir, cfg.cleaned_dir, cfg.log_dir]
    if cfg.cache_enabled:
        required_dirs.append(cfg.cache_folder)

    for directory in required_dirs:
        if directory.exists():
            continue
        if cfg.create_missing_dirs:
            directory.mkdir(parents=True, exist_ok=True)
            logger.info("Created missing directory: %s", directory)
        elif cfg.fail_on_missing_dirs:
            raise ConfigError(f"Required directory does not exist: {directory}")

    for district in cfg.districts.values():
        if not district.boundary_path.exists():
            raise ConfigError(
                f"Boundary file for district '{district.key}' not found: "
                f"{district.boundary_path}"
            )

    free_gb = shutil.disk_usage(cfg.project_root).free / (1024 ** 3)
    if free_gb < cfg.min_disk_space_gb:
        raise ConfigError(
            f"Only {free_gb:.2f} GB free at {cfg.project_root}, below the configured "
            f"minimum of {cfg.min_disk_space_gb} GB (validation.min_disk_space_gb)."
        )
    logger.info("Pre-flight checks passed. Free disk space: %.2f GB", free_gb)


# --------------------------------------------------------------------------- #
# Spatial domain
# --------------------------------------------------------------------------- #

def load_district_boundaries(cfg: CollectorConfig, logger: logging.Logger) -> "gpd.GeoDataFrame":
    """Load and union each active district's boundary geometry.

    Args:
        cfg: Resolved collector configuration.
        logger: Logger for status messages.

    Returns:
        GeoDataFrame indexed by district key, one row per district,
        reprojected to `cfg.crs`.
    """
    rows = []
    for key, district in cfg.districts.items():
        gdf = gpd.read_file(district.boundary_path)
        if gdf.crs is None:
            logger.warning(
                "Boundary file for '%s' has no CRS set; assuming %s.", key, cfg.crs
            )
            gdf.set_crs(cfg.crs, inplace=True)
        elif str(gdf.crs) != cfg.crs:
            gdf = gdf.to_crs(cfg.crs)

        geometry = gdf.union_all() if hasattr(gdf, "union_all") else gdf.unary_union
        rows.append({"district": key, "display_name": district.display_name, "geometry": geometry})

    combined = gpd.GeoDataFrame(rows, geometry="geometry", crs=cfg.crs).set_index("district")
    logger.info("Loaded boundaries for %d districts: %s", len(combined), list(combined.index))
    return combined


def compute_combined_bbox(
    districts_gdf: "gpd.GeoDataFrame", buffer_deg: float
) -> Tuple[float, float, float, float]:
    """Compute a single buffered bounding box covering all district geometries.

    Retained for informational purposes in bbox.json only -- actual CDS
    download requests are submitted per district (see
    `compute_district_download_area`), not against this combined extent.

    Args:
        districts_gdf: GeoDataFrame of district geometries.
        buffer_deg: Degrees of padding to add on every side.

    Returns:
        Tuple of (north, west, south, east) for the CDS API 'area' parameter.
    """
    minx, miny, maxx, maxy = districts_gdf.total_bounds
    return (maxy + buffer_deg, minx - buffer_deg, miny - buffer_deg, maxx + buffer_deg)


def compute_district_download_area(
    row: "gpd.GeoSeries", buffer_deg: float
) -> Tuple[float, float, float, float]:
    """Compute a single district's buffered bounding box for the CDS 'area' parameter.

    Each CDS request is submitted per district per year per variable, using
    that district's own bbox rather than one combined bbox for every district.

    Args:
        row: A single row from the districts GeoDataFrame (must have `.geometry`).
        buffer_deg: Degrees of padding to add on every side.

    Returns:
        Tuple of (north, west, south, east) for the CDS API 'area' parameter.
    """
    minx, miny, maxx, maxy = row.geometry.bounds
    return (maxy + buffer_deg, minx - buffer_deg, miny - buffer_deg, maxx + buffer_deg)


def compute_per_district_bboxes(districts_gdf: "gpd.GeoDataFrame") -> Dict[str, Dict[str, float]]:
    """Compute each district's unbuffered bounding box (for metadata/QA).

    Args:
        districts_gdf: GeoDataFrame of district geometries.

    Returns:
        Mapping of district key -> {north, south, east, west}.
    """
    result = {}
    for key, row in districts_gdf.iterrows():
        minx, miny, maxx, maxy = row.geometry.bounds
        result[key] = {"north": maxy, "south": miny, "west": minx, "east": maxx}
    return result


def save_bbox_metadata(
    cfg: CollectorConfig,
    combined_area: Tuple[float, float, float, float],
    per_district: Dict[str, Dict[str, float]],
    per_district_download_areas: Dict[str, Dict[str, float]],
) -> None:
    """Persist the derived bounding boxes to disk.

    Args:
        cfg: Resolved collector configuration.
        combined_area: (north, west, south, east) spanning every district --
            informational only, not used for any actual download.
        per_district: Per-district unbuffered bounding boxes.
        per_district_download_areas: Per-district buffered bounding boxes
            actually used for each district's CDS 'area' parameter.
    """
    if not cfg.save_bbox:
        return
    payload = {
        "crs": cfg.crs,
        "buffer_deg": cfg.buffer_deg,
        "combined_download_area": {
            "north": combined_area[0], "west": combined_area[1],
            "south": combined_area[2], "east": combined_area[3],
        },
        "combined_area_note": (
            "Informational only -- one CDS request is submitted per district "
            "per year per variable, each using 'district_download_areas' below, "
            "not this combined extent."
        ),
        "district_download_areas": per_district_download_areas,
        "districts": per_district,
        "generated_at": datetime.now().isoformat(),
    }
    cfg.era5_land_root.mkdir(parents=True, exist_ok=True)
    with open(cfg.bbox_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def build_polygon_mask(lat: np.ndarray, lon: np.ndarray, geometry: "BaseGeometry") -> np.ndarray:
    """Build a boolean grid mask of which (lat, lon) cells fall inside a geometry.

    Args:
        lat: 1D array of latitude coordinates.
        lon: 1D array of longitude coordinates.
        geometry: Shapely polygon/multipolygon to test containment against.

    Returns:
        2D boolean array of shape (len(lat), len(lon)); True where inside geometry.
    """
    lon_grid, lat_grid = np.meshgrid(lon, lat)
    try:
        points = shapely.points(lon_grid.ravel(), lat_grid.ravel())
        flags = shapely.contains(geometry, points)
    except AttributeError:
        # Fallback for shapely < 2.0 (no vectorized ufuncs).
        flags = np.array(
            [geometry.contains(Point(x, y)) for x, y in zip(lon_grid.ravel(), lat_grid.ravel())]
        )
    return flags.reshape(lat_grid.shape)


def clip_dataset_to_geometry(ds: xr.Dataset, geometry: "BaseGeometry", lat_dim: str, lon_dim: str) -> xr.Dataset:
    """Mask an xarray Dataset to grid cells inside a given geometry.

    Args:
        ds: Source dataset with lat/lon dimensions.
        geometry: Shapely polygon/multipolygon boundary.
        lat_dim: Name of the latitude dimension in `ds`.
        lon_dim: Name of the longitude dimension in `ds`.

    Returns:
        A new Dataset with cells outside `geometry` set to NaN.
    """
    mask = build_polygon_mask(ds[lat_dim].values, ds[lon_dim].values, geometry)
    mask_da = xr.DataArray(mask, dims=(lat_dim, lon_dim),
                            coords={lat_dim: ds[lat_dim], lon_dim: ds[lon_dim]})
    return ds.where(mask_da)


def detect_dim_names(ds: xr.Dataset) -> Tuple[str, str, str]:
    """Detect the (time, latitude, longitude) dimension names used by a dataset.

    Args:
        ds: Source dataset.

    Returns:
        Tuple of (time_dim, lat_dim, lon_dim).

    Raises:
        ValueError: If a required dimension cannot be identified.
    """
    time_candidates = ["valid_time", "time"]
    lat_candidates = ["latitude", "lat"]
    lon_candidates = ["longitude", "lon"]

    def _pick(candidates: List[str], kind: str) -> str:
        for c in candidates:
            if c in ds.dims or c in ds.coords:
                return c
        raise ValueError(f"Could not find a {kind} dimension among {candidates} in dataset dims {list(ds.dims)}.")

    return _pick(time_candidates, "time"), _pick(lat_candidates, "latitude"), _pick(lon_candidates, "longitude")


# --------------------------------------------------------------------------- #
# CDS client / download
# --------------------------------------------------------------------------- #

def init_cds_client(cfg: CollectorConfig, logger: logging.Logger) -> "cdsapi.Client":
    """Initialize an authenticated CDS API client using the official cdsapi package.

    Args:
        cfg: Resolved collector configuration.
        logger: Logger for status messages.

    Returns:
        Authenticated cdsapi.Client instance.
    """
    logger.info("Initializing CDS API client (url=%s)", cfg.cds_url)
    return cdsapi.Client(url=cfg.cds_url, key=cfg.cds_key, quiet=True,
                          timeout=cfg.http_timeout_seconds)


def build_request(variable: str, year: int, area: Tuple[float, float, float, float]) -> Dict[str, Any]:
    """Build the CDS API request payload for one variable / district / year.

    Requests are split to one variable per call to stay within the CDS
    per-request cost and size limits.  The request format mirrors exactly
    what the CDS website's "API request" tab generates for the
    ``derived-era5-land-daily-statistics`` dataset.

    Args:
        variable: A single ERA5-Land variable short name (e.g. "snow_depth").
        year: Calendar year to download.
        area: (north, west, south, east) bounding box for a single district.

    Returns:
        Request dictionary for ``cdsapi.Client.retrieve``.
    """
    return {
        "variable": [variable],
        "year": str(year),
        "month": [f"{m:02d}" for m in range(1, 13)],
        "day": [f"{d:02d}" for d in range(1, 32)],
        "daily_statistic": DAILY_STATISTIC,
        "time_zone": DAILY_TIME_ZONE,
        "frequency": DAILY_FREQUENCY,
        "area": list(area),
        "data_format": "netcdf",
    }


def _var_tmp_path(tmp_dir: Path, stem: str, variable: str) -> Path:
    """Return the temp path used for a single-variable part file.

    Args:
        tmp_dir: Directory to place the part file in.
        stem: Base file stem (district + year identifier).
        variable: ERA5-Land variable name.

    Returns:
        Path like ``<tmp_dir>/<stem>.<variable>.part.nc``.
    """
    safe_var = variable.replace(" ", "_")
    return tmp_dir / f"{stem}.{safe_var}.part.nc"


def validate_netcdf(file_path: Path, logger: logging.Logger) -> bool:
    """Validate that a NetCDF file opens correctly and has usable data.

    Args:
        file_path: Path to the NetCDF file.
        logger: Logger for diagnostic messages.

    Returns:
        True if the file is structurally valid, False otherwise.
    """
    if not file_path.exists() or file_path.stat().st_size == 0:
        return False
    try:
        with xr.open_dataset(file_path) as ds:
            if len(ds.data_vars) == 0:
                logger.warning("Validation failed for %s: no data variables.", file_path)
                return False
            _time_dim, _lat_dim, _lon_dim = detect_dim_names(ds)
            for var in ds.data_vars:
                if ds[var].isnull().all():
                    logger.warning("Validation warning for %s: '%s' is all-NaN.", file_path, var)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Validation failed for %s: could not open (%s).", file_path, exc)
        return False


def compute_checksum(file_path: Path) -> str:
    """Compute the SHA-256 checksum of a file.

    Args:
        file_path: Path to the file.

    Returns:
        Hex-encoded SHA-256 digest.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _download_single_variable(
    client: "cdsapi.Client",
    cfg: CollectorConfig,
    district_key: str,
    year: int,
    variable: str,
    area: Tuple[float, float, float, float],
    tmp_dir: Path,
    stem: str,
    logger: logging.Logger,
) -> Path:
    """Download a single ERA5-Land variable for one district-year, with retries.

    Submits one CDS request containing only ``variable`` (a single-element
    list) to stay within the CDS per-request cost/size limits.  The
    downloaded file is written to a ``.part.nc`` temp path inside
    ``tmp_dir`` and returned on success.

    Args:
        client: Authenticated CDS API client.
        cfg: Resolved collector configuration.
        district_key: District this request covers (for log messages).
        year: Calendar year to download (for log messages).
        variable: Single ERA5-Land variable name to request.
        area: This district's bounding box (north, west, south, east).
        tmp_dir: Directory to place the downloaded part file in.
        stem: Base file stem shared across all variables for this district-year.
        logger: Logger for status messages.

    Returns:
        Path to the validated ``.part.nc`` file.

    Raises:
        AuthenticationError: On HTTP 401 / genuine 403-auth failure -- the
            caller should abort the entire run, not just this variable.
        RuntimeError: If all retry attempts are exhausted without success.
    """
    tmp_path = _var_tmp_path(tmp_dir, stem, variable)
    request = build_request(variable, year, area)

    for attempt in range(1, cfg.http_max_retries + 1):
        # Pace submissions to stay under the CDS concurrent-queue limit.
        # The delay is applied before every attempt (including the first)
        # so that back-to-back variable requests within one district-year
        # are also spread out -- each variable is a separate queued job.
        if cfg.cds_submit_delay_seconds > 0:
            logger.debug(
                "[%s/%s] Variable '%s': waiting %.1f s before submission...",
                district_key, year, variable, cfg.cds_submit_delay_seconds,
            )
            time.sleep(cfg.cds_submit_delay_seconds)

        try:
            logger.info(
                "[%s/%s] Requesting variable '%s' (attempt %d/%d)...",
                district_key, year, variable, attempt, cfg.http_max_retries,
            )
            client.retrieve(CDS_DATASET, request, str(tmp_path))

            if not validate_netcdf(tmp_path, logger):
                raise ValueError(
                    f"Downloaded file for variable '{variable}' failed validation."
                )

            logger.info(
                "[%s/%s] Variable '%s' downloaded OK -> %s",
                district_key, year, variable, tmp_path.name,
            )
            return tmp_path

        except Exception as exc:  # noqa: BLE001
            tmp_path.unlink(missing_ok=True)

            if _is_auth_error(exc):
                logger.error(
                    "[%s/%s] Authentication rejected by CDS for variable '%s': %s",
                    district_key, year, variable, exc,
                )
                raise AuthenticationError(
                    "CDS API rejected your credentials (401/403 Unauthorized). This is "
                    "not a transient network issue, so retrying will not help. Check that: "
                    "(1) api_keys.cds_api_key in config.yaml is your current CDS "
                    "Personal Access Token from https://cds.climate.copernicus.eu/profile "
                    "with no extra quotes/spaces/newlines, and "
                    "(2) you have accepted the license terms for the "
                    f"'{CDS_DATASET}' dataset at "
                    f"https://cds.climate.copernicus.eu/datasets/{CDS_DATASET} "
                    "(License tab -> 'Accept terms')."
                ) from exc

            if _is_queue_throttle_error(exc):
                # The CDS queue is globally saturated -- many users are hitting
                # the same dataset simultaneously. This is a transient server-side
                # condition; the only correct response is to wait and retry.
                # Queue throttle hits do NOT count against cfg.http_max_retries
                # (reserved for real network/download failures); we keep retrying
                # until the server accepts the job.
                #
                # Exponential backoff + full jitter: sessions waiting simultaneously
                # will wake at different random times so they do not all hammer the
                # server again at the same instant.
                #   base  = min(60 * 2^(hit_count - 1), 300)   -> 60 s .. 300 s
                #   sleep = uniform(base / 2, base)             -> full jitter
                _q_key = f"_qhits_{id(cfg)}_{district_key}_{year}_{variable}"
                _queue_hits = getattr(_download_single_variable, _q_key, 0) + 1
                setattr(_download_single_variable, _q_key, _queue_hits)
                base = min(60.0 * (2 ** (_queue_hits - 1)), 300.0)
                sleep_time = random.uniform(base * 0.5, base)
                logger.warning(
                    "[%s/%s] Variable '%s': CDS server queue globally congested "
                    "(hit #%d -- not counted against the %d-attempt limit). "
                    "Waiting %.0f s with jitter before retrying...",
                    district_key, year, variable,
                    _queue_hits, cfg.http_max_retries, sleep_time,
                )
                time.sleep(sleep_time)
                continue  # retry without consuming an attempt

            logger.error(
                "[%s/%s] Variable '%s', attempt %d/%d failed: %s",
                district_key, year, variable, attempt, cfg.http_max_retries, exc,
            )
            if attempt < cfg.http_max_retries:
                sleep_time = cfg.http_backoff_factor ** attempt
                logger.info(
                    "[%s/%s] Variable '%s': retrying in %.1f seconds...",
                    district_key, year, variable, sleep_time,
                )
                time.sleep(sleep_time)
            else:
                raise RuntimeError(
                    f"All {cfg.http_max_retries} download attempts failed for "
                    f"variable '{variable}' ({district_key}/{year})."
                ) from exc

    # Unreachable, but satisfies type checkers.
    raise RuntimeError(f"Unexpected exit from retry loop for variable '{variable}'.")


def download_year(
    client: "cdsapi.Client",
    cfg: CollectorConfig,
    district_key: str,
    year: int,
    area: Tuple[float, float, float, float],
    output_path: Path,
    logger: logging.Logger,
) -> bool:
    """Download one district-year of ERA5-Land daily data, with retries and resume support.

    CDS imposes a per-request cost/size limit that is easily exceeded when
    requesting all 7 variables at once for a full year.  This function
    works around that limit by submitting **one CDS request per variable**,
    collecting the individual single-variable NetCDF files, merging them
    in memory with ``xarray.merge``, and writing the merged dataset to
    ``output_path``.  The merged file is structurally identical to what a
    single combined request would have returned, so all downstream
    processing code is unaffected.

    Args:
        client: Authenticated CDS API client.
        cfg: Resolved collector configuration.
        district_key: District this request covers.
        year: Calendar year to download.
        area: This district's bounding box (north, west, south, east).
        output_path: Destination NetCDF path for the merged dataset.
        logger: Logger for status messages.

    Returns:
        True on success (including "already valid, skipped"), False otherwise.
    """
    if not cfg.download_overwrite and cfg.resume_incomplete:
        if output_path.exists() and validate_netcdf(output_path, logger):
            logger.info("[%s/%s] Raw file already valid, skipping download.", district_key, year)
            return True

    tmp_dir = cfg.cache_folder if cfg.cache_enabled else output_path.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)
    stem = output_path.stem  # e.g. "era5_land_daily_mandi_2020"

    part_paths: List[Path] = []
    try:
        for variable in cfg.variables:
            part_path = _download_single_variable(
                client, cfg, district_key, year, variable, area, tmp_dir, stem, logger,
            )
            part_paths.append(part_path)

        # Merge all single-variable datasets into one before saving.
        logger.info(
            "[%s/%s] Merging %d variable file(s) into combined dataset...",
            district_key, year, len(part_paths),
        )
        datasets = [xr.open_dataset(p) for p in part_paths]
        try:
            merged = xr.merge(datasets, compat="override", join="outer")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            merged.to_netcdf(output_path)
        finally:
            for ds in datasets:
                ds.close()

        if not validate_netcdf(output_path, logger):
            raise ValueError("Merged output file failed post-merge validation.")

        logger.info("[%s/%s] Download + merge successful -> %s", district_key, year, output_path)
        return True

    except AuthenticationError:
        raise  # Propagate immediately -- do not swallow auth failures.

    except Exception as exc:  # noqa: BLE001
        logger.error("[%s/%s] Download failed: %s", district_key, year, exc)
        output_path.unlink(missing_ok=True)
        return False

    finally:
        # Always clean up per-variable temp files, whether we succeeded or not.
        for p in part_paths:
            p.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Processing: NetCDF -> tidy district dataframes
# --------------------------------------------------------------------------- #

def process_year_for_district(
    nc_path: Path,
    districts_gdf: "gpd.GeoDataFrame",
    district_key: str,
    clip_to_boundary: bool,
    logger: logging.Logger,
) -> pd.DataFrame:
    """Convert one district's yearly ERA5-Land NetCDF into a tidy daily dataframe.

    The raw NetCDF passed in already covers only this district's own
    (buffered) bounding box, since each CDS request is submitted per
    district per year. When `clip_to_boundary` is True, grid cells outside
    the district's actual polygon (as opposed to its rectangular bounding
    box) are masked to NaN before computing statistics, so the buffer
    padding used for the download doesn't leak into the results.

    Args:
        nc_path: Path to the raw NetCDF file for one district-year.
        districts_gdf: GeoDataFrame of all district geometries (indexed by key).
        district_key: The district this NetCDF belongs to.
        clip_to_boundary: Whether to mask cells outside the district polygon.
        logger: Logger for diagnostic messages.

    Returns:
        Long-format DataFrame with columns: date, district, and
        `{variable}_mean` / `_min` / `_max` per requested variable.
    """
    with xr.open_dataset(nc_path) as ds:
        time_dim, lat_dim, lon_dim = detect_dim_names(ds)
        dates = pd.to_datetime(ds[time_dim].values)
        variables = list(ds.data_vars)

        sub_ds = ds
        if clip_to_boundary:
            geometry = districts_gdf.loc[district_key].geometry
            sub_ds = clip_dataset_to_geometry(ds, geometry, lat_dim, lon_dim)

        records: Dict[str, Any] = {}
        for var in variables:
            da = sub_ds[var]
            spatial_dims = [d for d in da.dims if d != time_dim]
            records[f"{var}_mean"] = da.mean(dim=spatial_dims, skipna=True).values
            records[f"{var}_min"] = da.min(dim=spatial_dims, skipna=True).values
            records[f"{var}_max"] = da.max(dim=spatial_dims, skipna=True).values

        frame = pd.DataFrame(records)
        frame.insert(0, "date", dates)
        frame.insert(1, "district", district_key)

    missing = [v for v in DEFAULT_VARIABLES if f"{v}_mean" not in frame.columns]
    if missing:
        logger.warning("Processed file %s is missing expected variables: %s", nc_path.name, missing)

    return frame.sort_values("date").reset_index(drop=True)


def save_processed(
    df: pd.DataFrame, cfg: CollectorConfig, district_key: str, year: int, force: bool, logger: logging.Logger
) -> Tuple[Optional[Path], Optional[Path]]:
    """Persist a processed dataframe to CSV and/or Parquet per config settings.

    Args:
        df: Processed daily dataframe for one district-year.
        cfg: Resolved collector configuration.
        district_key: District this dataframe covers (used in the filename).
        year: Calendar year (used in the filename).
        force: If True, overwrite existing processed files regardless of config.
        logger: Logger for status messages.

    Returns:
        Tuple of (csv_path, parquet_path); either may be None if skipped/failed.
    """
    cfg.cleaned_dir.mkdir(parents=True, exist_ok=True)
    csv_path = cfg.cleaned_dir / f"era5_land_daily_{district_key}_{year}.csv"
    parquet_path = cfg.cleaned_dir / f"era5_land_daily_{district_key}_{year}.parquet"

    write_allowed = force or cfg.overwrite_processed or not (csv_path.exists() and parquet_path.exists())
    if not write_allowed:
        logger.info("[%s/%s] Processed files already exist and overwrite_processed=false, skipping.",
                    district_key, year)
        return csv_path, parquet_path

    df.to_csv(csv_path, index=False, encoding=cfg.encoding)

    result_parquet: Optional[Path] = parquet_path
    try:
        df.to_parquet(parquet_path, index=False, compression=cfg.compression)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[%s/%s] Could not write parquet (%s); CSV was still written.", district_key, year, exc)
        result_parquet = None

    logger.info("[%s/%s] Processed data saved -> %s", district_key, year, csv_path)
    return csv_path, result_parquet


# --------------------------------------------------------------------------- #
# Metadata / resume support
# --------------------------------------------------------------------------- #

def _metadata_key(district: str, year: int) -> str:
    """Build the compound 'district:year' key used in metadata.json."""
    return f"{district}:{year}"


def load_metadata(metadata_path: Path) -> Dict[str, Any]:
    """Load metadata.json, returning a default structure if absent/corrupt."""
    if metadata_path.exists():
        try:
            with open(metadata_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError:
            pass
    return {"dataset": CDS_DATASET, "years": {}, "last_updated": None}


def update_metadata(
    metadata_path: Path,
    district: str,
    year: int,
    status: str,
    raw_path: Optional[Path] = None,
    csv_path: Optional[Path] = None,
    parquet_path: Optional[Path] = None,
) -> None:
    """Record the outcome of processing one district-year into metadata.json.

    Args:
        metadata_path: Path to metadata.json.
        district: District key processed.
        year: Calendar year processed.
        status: One of "completed", "failed", "skipped".
        raw_path: Path to the raw NetCDF file, if produced.
        csv_path: Path to the processed CSV file, if produced.
        parquet_path: Path to the processed Parquet file, if produced.
    """
    metadata = load_metadata(metadata_path)
    entry: Dict[str, Any] = {
        "district": district,
        "year": year,
        "status": status,
        "updated_at": datetime.now().isoformat(),
    }

    if raw_path and raw_path.exists():
        entry["raw_file"] = str(raw_path)
        entry["raw_checksum_sha256"] = compute_checksum(raw_path)
        entry["raw_size_bytes"] = raw_path.stat().st_size
    if csv_path and csv_path.exists():
        entry["cleaned_csv"] = str(csv_path)
    if parquet_path and parquet_path.exists():
        entry["cleaned_parquet"] = str(parquet_path)

    metadata.setdefault("years", {})[_metadata_key(district, year)] = entry
    metadata["last_updated"] = datetime.now().isoformat()
    metadata["dataset"] = CDS_DATASET

    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metadata_path, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)


def district_year_already_completed(metadata_path: Path, district: str, year: int) -> bool:
    """Check whether a district-year is already marked 'completed' in metadata.json."""
    metadata = load_metadata(metadata_path)
    entry = metadata.get("years", {}).get(_metadata_key(district, year))
    return bool(entry and entry.get("status") == "completed")


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def _process_single_district_year(
    client: "cdsapi.Client",
    cfg: CollectorConfig,
    districts_gdf: "gpd.GeoDataFrame",
    district_key: str,
    area: Tuple[float, float, float, float],
    year: int,
    force: bool,
    logger: logging.Logger,
) -> str:
    """Run download + process + save + metadata-update for a single district-year.

    Returns:
        One of "completed", "failed", "skipped".
    """
    if not force and cfg.resume_incomplete and district_year_already_completed(cfg.metadata_path, district_key, year):
        logger.info("[%s/%s] Already completed per metadata.json, skipping (use --force to redo).",
                    district_key, year)
        return "skipped"

    raw_path = cfg.raw_dir / f"era5_land_daily_{district_key}_{year}.nc"
    ok = download_year(client, cfg, district_key, year, area, raw_path, logger)
    if not ok:
        update_metadata(cfg.metadata_path, district_key, year, status="failed", raw_path=raw_path)
        return "failed"

    try:
        df = process_year_for_district(raw_path, districts_gdf, district_key, cfg.clip_to_boundary, logger)
        csv_path, parquet_path = save_processed(df, cfg, district_key, year, force, logger)
        update_metadata(cfg.metadata_path, district_key, year, status="completed",
                         raw_path=raw_path, csv_path=csv_path, parquet_path=parquet_path)
        return "completed"
    except Exception as exc:  # noqa: BLE001
        logger.error("[%s/%s] Processing failed: %s", district_key, year, exc)
        update_metadata(cfg.metadata_path, district_key, year, status="failed", raw_path=raw_path)
        return "failed"


def collect_era5_land(
    cfg: CollectorConfig,
    logger: logging.Logger,
    force: bool = False,
    only_year: Optional[int] = None,
    only_district: Optional[str] = None,
) -> None:
    """Run the full ERA5-Land collection pipeline: one CDS request per district per year per variable.

    Args:
        cfg: Resolved collector configuration.
        logger: Logger for status messages.
        force: If True, re-download/reprocess even if already completed.
        only_year: If set, restrict the run to a single calendar year.
        only_district: If set, restrict the run to a single district.
    """
    if not cfg.dataset_enabled:
        logger.info("digital_twin_sources.era5_land.enabled is false; exiting.")
        return

    validate_environment(cfg, logger)

    districts_gdf = load_district_boundaries(cfg, logger)

    # Combined bbox is informational only (saved to bbox.json for QA) --
    # actual CDS requests below are submitted per district per variable,
    # each using its own buffered bbox via compute_district_download_area.
    combined_area = compute_combined_bbox(districts_gdf, cfg.buffer_deg)
    per_district_bboxes = compute_per_district_bboxes(districts_gdf)
    per_district_download_areas = {
        key: dict(zip(("north", "west", "south", "east"),
                      compute_district_download_area(row, cfg.buffer_deg)))
        for key, row in districts_gdf.iterrows()
    }
    save_bbox_metadata(cfg, combined_area, per_district_bboxes, per_district_download_areas)

    client = init_cds_client(cfg, logger)
    years = [only_year] if only_year else list(range(cfg.start_year, cfg.end_year + 1))
    district_keys = [only_district] if only_district else list(districts_gdf.index)

    jobs = [(d, y) for d in district_keys for y in years]
    logger.info(
        "Starting ERA5-Land collection: %d district(s) x %d year(s) = %d job(s), "
        "%d CDS request(s) per job (one per variable). "
        "Districts=%s, years=%d-%d, variables=%s",
        len(district_keys), len(years), len(jobs), len(cfg.variables),
        district_keys, years[0], years[-1], cfg.variables,
    )

    results = {"completed": 0, "failed": 0, "skipped": 0}

    # CDS enforces a strict per-account concurrent-queued-request limit.
    # Each district-year job submits len(cfg.variables) separate CDS requests
    # in sequence, so running N parallel workers floods the queue with
    # N × len(variables) simultaneous submissions and triggers HTTP 400
    # "Number queued requests for this dataset is temporarily limited."
    #
    # For this reason CDS collection is ALWAYS run sequentially -- one
    # district-year at a time, one variable at a time within that job.
    # The download.parallel_downloads and download.workers config keys are
    # intentionally ignored here; parallel mode is left in the config schema
    # so other collectors that don't share this constraint can still use it.
    if cfg.parallel_downloads:
        logger.warning(
            "download.parallel_downloads=true is set in config.yaml, but ERA5-Land "
            "collection runs sequentially regardless. CDS enforces a per-account "
            "concurrent-queue limit: submitting %d variables × multiple district-years "
            "in parallel saturates that limit and causes HTTP 400 queue rejections. "
            "Sequential submission with a %.0f s inter-request delay "
            "(download.cds_submit_delay_seconds) is used instead.",
            len(cfg.variables), cfg.cds_submit_delay_seconds,
        )

    for district_key, year in tqdm(jobs, desc="ERA5-Land district-years", unit="job"):
        area = compute_district_download_area(districts_gdf.loc[district_key], cfg.buffer_deg)
        status = _process_single_district_year(
            client, cfg, districts_gdf, district_key, area, year, force, logger
        )
        results[status] += 1

    logger.info(
        "ERA5-Land collection complete. Completed=%d, Failed=%d, Skipped=%d",
        results["completed"], results["failed"], results["skipped"],
    )
    if results["failed"]:
        logger.warning(
            "%d job(s) failed. Re-run the script (resume is automatic) to retry them.",
            results["failed"],
        )


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="ERA5-Land daily hydrology collector.")
    parser.add_argument("--config", type=Path, default=Path("config/config.yaml"),
                         help="Path to config.yaml (default: config/config.yaml)")
    parser.add_argument("--year", type=int, default=None,
                         help="Restrict the run to a single calendar year.")
    parser.add_argument("--district", type=str, default=None,
                         help="Restrict the run to a single district (e.g. 'mandi').")
    parser.add_argument("--force", action="store_true",
                         help="Re-download and reprocess district-years even if already completed.")
    return parser.parse_args()


def main() -> None:
    """Script entry point."""
    args = parse_args()

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    logger = setup_logging(cfg)

    try:
        collect_era5_land(cfg, logger, force=args.force, only_year=args.year, only_district=args.district)
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user. Progress so far is saved; re-run to resume.")
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unhandled error during collection: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()