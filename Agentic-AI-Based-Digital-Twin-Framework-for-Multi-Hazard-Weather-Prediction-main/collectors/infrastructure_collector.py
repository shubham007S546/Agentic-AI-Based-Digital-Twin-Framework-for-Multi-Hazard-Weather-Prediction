"""
infrastructure_collector.py
=============================

Production collector for OpenStreetMap (Overpass API) infrastructure layers
over the Himachal Climate Digital Twin's active districts (Mandi, Kullu,
Chamba), wired directly to `config/config.yaml` -- architecture mirrors
`era5_land_collector.py` (same config-loading pattern, logging, retry/
backoff-with-jitter for server-side rate limiting, metadata.json shape,
and CLI flags).

Data source
-----------
OpenStreetMap data via the Overpass API. `config.yaml`'s
`digital_twin_sources.infrastructure` block is a descriptive/summary entry
(same role as `digital_twin_sources.census` relative to the real `census:`
block) -- it is not what this collector reads for its actual behaviour.

REQUIRED CONFIG ADDITION
------------------------
Exactly like `census:` is the dedicated, self-contained block that
`census_collector.py` actually reads (as documented in its own comment in
config.yaml), this collector needs an equivalent dedicated `infrastructure:`
block. It does not exist yet in the config.yaml you shared, so add this
before running:

    infrastructure:
      base_dir: "digital_twin/infrastructure"   # falls back to paths.infrastructure.root if omitted
      overpass:
        mirrors:
          - "https://overpass.private.coffee/api/interpreter"
          - "https://overpass.kumi.systems/api/interpreter"
          - "https://overpass.osm.ch/api/interpreter"
          - "https://overpass-api.de/api/interpreter"
        timeout_seconds:        180
        request_delay_seconds:  2.0   # pacing between requests (Overpass fair-use policy)
        user_agent: "Mozilla/5.0 (compatible; HimachalDigitalTwinBot/2.1; +https://example.org/bot)"
      # request/retries below are aligned with http.* -- see era5_land_collector.py's
      # own comment on this same pattern in census:
      request:
        retries:        5     # aligned with http.max_retries
        backoff_factor: 2.0   # aligned with http.backoff_factor

If this block is missing, the collector raises a ConfigError with this same
message at startup rather than failing on an unrelated KeyError deeper in
the run.

Config sections this script reads
-----------------------------------
    project                    (unused directly; kept for parity)
    spatial                     (crs)
    districts                   (per-district boundary geojson)
    active_districts
    processing                  (clip_to_boundary)
    paths.root                  (logs)
    paths.infrastructure         (root, roads, villages, schools, hospitals --
                                  bridges/power/transport/government are derived
                                  under root since config.yaml has no explicit
                                  keys for them; see resolve_category_dirs)
    infrastructure               (NEW block -- see above)
    digital_twin_sources.infrastructure  (enabled flag only)
    http                         (max_retries, backoff_factor -- aligned defaults)
    download                     (overwrite, resume_incomplete)
    output                       (formats.vector, encoding)
    logging                      (level, format, date_format, console, save_log,
                                  global_log_dir, rotation)
    cache                        (enabled, folder -- reserved for future use,
                                  e.g. caching raw Overpass JSON responses)
    validation                   (fail_on_missing_dirs, create_missing_dirs,
                                  min_disk_space_gb)

Category -> folder mapping
---------------------------
The 18 requested infrastructure categories collapse into the 8 requested
output folders as follows (folders reuse paths.infrastructure keys where
they exist -- roads/villages/schools/hospitals -- and are derived under
paths.infrastructure.root for the rest):

    Roads                                       -> Roads
    Bridges                                     -> Bridges
    Hospitals, Primary_Health_Centres            -> Hospitals
    Schools, Colleges                            -> Schools
    Police_Stations, Fire_Stations,
    Government_Offices                           -> Government
    Bus_Stops, Railway_Stations,
    Airports_Helipads                            -> Transport
    Villages, Towns                              -> Villages
    Hydropower_Stations, Dams,
    Power_Substations, Transmission_Lines        -> Power

Usage
-----
    python collectors/infrastructure_collector.py
    python collectors/infrastructure_collector.py --config config/config.yaml
    python collectors/infrastructure_collector.py --district mandi
    python collectors/infrastructure_collector.py --category Roads
    python collectors/infrastructure_collector.py --force
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import logging.handlers
import random
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
import yaml
from tqdm import tqdm

try:
    import geopandas as gpd
except ImportError:  # pragma: no cover
    gpd = None

try:
    import shapely
    from shapely.geometry import LineString, MultiPolygon, Point, Polygon
    from shapely.geometry.base import BaseGeometry
    from shapely.validation import make_valid
except ImportError:  # pragma: no cover
    shapely = None
    LineString = MultiPolygon = Point = Polygon = None
    BaseGeometry = None
    make_valid = None


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

DEFAULT_OVERPASS_MIRRORS: List[str] = [
    # overpass-api.de (and its lz4./z. subdomains, which are backend nodes of
    # the SAME operator/instance -- not independent mirrors) has been
    # returning blanket 406 Not Acceptable responses to Python/requests
    # traffic since ~June 2026 as an anti-bot measure unrelated to headers,
    # query shape, or request rate. This is a known, still-open upstream
    # issue: https://github.com/drolbr/Overpass-API/issues/791 and
    # https://community.openstreetmap.org/t/overpass-api-error-406/143198
    # -- not something fixable from the client side. Genuinely independent
    # instances (different operators) are used as the default mirror list
    # instead, with overpass-api.de kept last in case it's restored later.
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]

CATEGORY_SPECS: Dict[str, Dict[str, Any]] = {
    "Roads": {"folder": "roads", "filters": ['way["highway"]']},
    "Bridges": {"folder": "bridges", "filters": ['way["bridge"]', 'node["man_made"="bridge"]']},
    "Hospitals": {"folder": "hospitals", "filters": ['node["amenity"="hospital"]', 'way["amenity"="hospital"]']},
    "Primary_Health_Centres": {
        "folder": "hospitals",
        "filters": ['node["amenity"="clinic"]', 'way["amenity"="clinic"]', 'node["healthcare"="centre"]'],
    },
    "Schools": {"folder": "schools", "filters": ['node["amenity"="school"]', 'way["amenity"="school"]']},
    "Colleges": {"folder": "schools", "filters": ['node["amenity"="college"]', 'way["amenity"="college"]']},
    "Police_Stations": {"folder": "government", "filters": ['node["amenity"="police"]', 'way["amenity"="police"]']},
    "Fire_Stations": {
        "folder": "government",
        "filters": ['node["amenity"="fire_station"]', 'way["amenity"="fire_station"]'],
    },
    "Government_Offices": {
        "folder": "government",
        "filters": ['node["office"="government"]', 'way["office"="government"]'],
    },
    "Bus_Stops": {
        "folder": "transport",
        "filters": ['node["highway"="bus_stop"]', 'node["amenity"="bus_station"]', 'way["amenity"="bus_station"]'],
    },
    "Railway_Stations": {"folder": "transport", "filters": ['node["railway"="station"]', 'way["railway"="station"]']},
    "Airports_Helipads": {
        "folder": "transport",
        "filters": [
            'node["aeroway"="aerodrome"]', 'way["aeroway"="aerodrome"]',
            'node["aeroway"="helipad"]', 'way["aeroway"="helipad"]',
        ],
    },
    "Villages": {"folder": "villages", "filters": ['node["place"="village"]']},
    "Towns": {"folder": "villages", "filters": ['node["place"="town"]']},
    "Hydropower_Stations": {
        "folder": "power",
        "filters": [
            'node["power"="plant"]["plant:source"="hydro"]', 'way["power"="plant"]["plant:source"="hydro"]',
            'node["power"="generator"]["generator:source"="hydro"]', 'way["power"="generator"]["generator:source"="hydro"]',
        ],
    },
    "Dams": {
        "folder": "power",
        "filters": ['way["waterway"="dam"]', 'node["waterway"="dam"]', 'way["man_made"="dam"]', 'node["man_made"="dam"]'],
    },
    "Power_Substations": {"folder": "power", "filters": ['node["power"="substation"]', 'way["power"="substation"]']},
    "Transmission_Lines": {"folder": "power", "filters": ['way["power"="line"]', 'way["power"="minor_line"]']},
}

FOLDER_DISPLAY_NAMES: Dict[str, str] = {
    "roads": "Roads", "bridges": "Bridges", "hospitals": "Hospitals", "schools": "Schools",
    "villages": "Villages", "power": "Power", "transport": "Transport", "government": "Government",
}


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #

class ConfigError(RuntimeError):
    """Raised when required configuration or environment setup is invalid."""


def _is_rate_limited(exc: Exception) -> bool:
    """Detect whether an exception represents an Overpass rate-limit / server
    congestion response rather than a genuine request failure. Overpass
    returns HTTP 429 ("Too Many Requests") and HTTP 504 ("Gateway Timeout")
    for transient server-side conditions -- the same non-fatal treatment
    era5_land_collector.py gives CDS queue-throttle 400s.
    """
    msg = str(exc).lower()
    markers = ["429", "too many requests", "504", "gateway timeout", "rate limit"]
    return any(m in msg for m in markers)


def _is_non_retryable_client_error(exc: Exception) -> bool:
    """Detect a deterministic client-side rejection that retrying the exact
    same request will never fix (as opposed to 429/504, which are transient
    server load and worth waiting out).

    HTTP 406 ("Not Acceptable") from overpass-api.de is almost always the
    front-end's bot-mitigation layer rejecting requests that don't send a
    proper User-Agent/Accept header -- not a query or rate-limit problem.
    401/403/404/400 are included for the same reason: none of them change
    on retry without changing the request itself. Rather than burning the
    full retry budget with exponential backoff against a deterministic
    rejection, this lets the caller fail fast on the current mirror and
    move on to the next one immediately.

    Args:
        exc: The exception raised during the HTTP request.

    Returns:
        True if this looks like a non-transient client-side rejection.
    """
    msg = str(exc).lower()
    markers = ["406", "not acceptable", "400", "bad request", "401", "unauthorized",
               "403", "forbidden", "404", "not found"]
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


@dataclass
class CollectorConfig:
    """Fully resolved runtime configuration for the infrastructure collector."""

    project_root: Path
    crs: str

    districts: Dict[str, DistrictInfo]
    active_districts: List[str]
    clip_to_boundary: bool

    dataset_enabled: bool

    infra_root: Path
    category_dirs: Dict[str, Path]
    log_dir: Path

    overpass_mirrors: List[str]
    overpass_timeout_seconds: int
    overpass_user_agent: str
    request_delay_seconds: float

    http_max_retries: int
    http_backoff_factor: float

    download_overwrite: bool
    resume_incomplete: bool

    vector_format: str
    encoding: str

    log_level: str
    log_format: str
    log_date_format: str
    log_console: bool
    log_save: bool
    log_rotate_max_bytes: int
    log_rotate_backup_count: int

    cache_enabled: bool
    cache_folder: Path

    fail_on_missing_dirs: bool
    create_missing_dirs: bool
    min_disk_space_gb: float

    @property
    def metadata_path(self) -> Path:
        return self.infra_root / "metadata.json"


# --------------------------------------------------------------------------- #
# Config resolution
# --------------------------------------------------------------------------- #

def _resolve_path(project_root: Path, path_str: str) -> Path:
    """Resolve a config path string against the project root."""
    p = Path(path_str)
    return p if p.is_absolute() else (project_root / p)


_INFRASTRUCTURE_BLOCK_HELP = (
    "config.yaml is missing the required 'infrastructure:' block. This "
    "collector needs its own self-contained block, the same way "
    "'census:' is the dedicated block collectors/census_collector.py reads "
    "(digital_twin_sources.infrastructure is only a descriptive summary "
    "entry, same role as digital_twin_sources.census). Add:\n\n"
    "infrastructure:\n"
    "  base_dir: \"digital_twin/infrastructure\"\n"
    "  overpass:\n"
    "    mirrors:\n"
    "      - \"https://overpass.private.coffee/api/interpreter\"\n"
    "      - \"https://overpass.kumi.systems/api/interpreter\"\n"
    "      - \"https://overpass.osm.ch/api/interpreter\"\n"
    "      - \"https://overpass-api.de/api/interpreter\"\n"
    "    timeout_seconds: 180\n"
    "    request_delay_seconds: 2.0\n"
    "    user_agent: \"Mozilla/5.0 (compatible; HimachalDigitalTwinBot/2.1; "
    "+https://example.org/bot)\"\n"
    "  request:\n"
    "    retries: 5\n"
    "    backoff_factor: 2.0\n"
)

# overpass-api.de's front-end rejects requests without a proper User-Agent
# (returns 406 Not Acceptable) -- this matches the identifying string
# census_collector.py already uses for the same reason (see census.request.user_agent).
DEFAULT_OVERPASS_USER_AGENT = (
    "Mozilla/5.0 (compatible; HimachalDigitalTwinBot/2.1; +https://example.org/bot)"
)


def resolve_category_dirs(infra_root: Path, paths_infra_cfg: Dict[str, Any],
                           project_root: Path) -> Dict[str, Path]:
    """Resolve output directories for each of the 8 category folders.

    `paths.infrastructure` already defines `roads`, `villages`, `schools`,
    `hospitals` explicitly -- used as-is. It has no entries for `bridges`,
    `power`, `transport`, `government`, so those are derived as
    `<infra_root>/<TitleCaseName>`.
    """
    dirs: Dict[str, Path] = {}
    for key, display in FOLDER_DISPLAY_NAMES.items():
        if key in paths_infra_cfg:
            dirs[key] = _resolve_path(project_root, paths_infra_cfg[key])
        else:
            dirs[key] = infra_root / display
    dirs["cleaned"] = infra_root / "cleaned"
    dirs["logs"] = infra_root / "logs"
    return dirs


def load_config(config_path: Path) -> CollectorConfig:
    """Load and validate all settings this collector needs from config.yaml."""
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as fh:
        cfg: Dict[str, Any] = yaml.safe_load(fh) or {}

    project_root = config_path.resolve().parent.parent

    infra_cfg = cfg.get("infrastructure")
    if infra_cfg is None:
        raise ConfigError(_INFRASTRUCTURE_BLOCK_HELP)

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
        )

    processing_cfg = cfg.get("processing", {}) or {}
    clip_to_boundary = bool(processing_cfg.get("clip_to_boundary", True))

    dt_infra_summary = (cfg.get("digital_twin_sources", {}) or {}).get("infrastructure", {}) or {}
    dataset_enabled = bool(dt_infra_summary.get("enabled", True))

    paths_cfg = cfg.get("paths", {}) or {}
    root_cfg = paths_cfg.get("root", {}) or {}
    paths_infra_cfg = paths_cfg.get("infrastructure", {}) or {}

    base_dir_str = infra_cfg.get("base_dir") or paths_infra_cfg.get("root", "digital_twin/infrastructure")
    infra_root = _resolve_path(project_root, base_dir_str)
    category_dirs = resolve_category_dirs(infra_root, paths_infra_cfg, project_root)
    log_dir = _resolve_path(project_root, root_cfg.get("logs", "logs"))

    overpass_cfg = infra_cfg.get("overpass", {}) or {}
    overpass_mirrors = list(overpass_cfg.get("mirrors") or DEFAULT_OVERPASS_MIRRORS)
    overpass_timeout_seconds = int(overpass_cfg.get("timeout_seconds", 180))
    overpass_user_agent = str(overpass_cfg.get("user_agent", DEFAULT_OVERPASS_USER_AGENT))
    request_delay_seconds = float(overpass_cfg.get("request_delay_seconds", 2.0))

    http_cfg = cfg.get("http", {}) or {}
    request_cfg = infra_cfg.get("request", {}) or {}
    http_max_retries = int(request_cfg.get("retries", http_cfg.get("max_retries", 5)))
    http_backoff_factor = float(request_cfg.get("backoff_factor", http_cfg.get("backoff_factor", 2.0)))

    download_cfg = cfg.get("download", {}) or {}
    download_overwrite = bool(download_cfg.get("overwrite", False))
    resume_incomplete = bool(download_cfg.get("resume_incomplete", True))

    output_cfg = cfg.get("output", {}) or {}
    formats_cfg = output_cfg.get("formats", {}) or {}
    vector_format = str(formats_cfg.get("vector", "GeoJSON"))
    encoding = str(output_cfg.get("encoding", "utf-8"))

    logging_cfg = cfg.get("logging", {}) or {}
    cache_cfg = cfg.get("cache", {}) or {}
    validation_cfg = cfg.get("validation", {}) or {}

    return CollectorConfig(
        project_root=project_root,
        crs=crs,
        districts=districts,
        active_districts=list(active_district_keys),
        clip_to_boundary=clip_to_boundary,
        dataset_enabled=dataset_enabled,
        infra_root=infra_root,
        category_dirs=category_dirs,
        log_dir=log_dir,
        overpass_mirrors=overpass_mirrors,
        overpass_timeout_seconds=overpass_timeout_seconds,
        overpass_user_agent=overpass_user_agent,
        request_delay_seconds=request_delay_seconds,
        http_max_retries=http_max_retries,
        http_backoff_factor=http_backoff_factor,
        download_overwrite=download_overwrite,
        resume_incomplete=resume_incomplete,
        vector_format=vector_format,
        encoding=encoding,
        log_level=str(logging_cfg.get("level", "INFO")),
        log_format=str(logging_cfg.get("format", "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")),
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
    """Configure logging per the config.yaml `logging:` block."""
    logger = logging.getLogger("infrastructure_collector")
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
        log_file = cfg.log_dir / "infrastructure_collector.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=cfg.log_rotate_max_bytes,
            backupCount=cfg.log_rotate_backup_count, encoding="utf-8",
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
    """Fail fast on missing dependencies, directories, or disk space."""
    if gpd is None:
        raise ConfigError("The 'geopandas' package is not installed. Install with "
                           "'pip install geopandas --break-system-packages'.")
    if shapely is None:
        raise ConfigError("The 'shapely' package is not installed. Install with "
                           "'pip install shapely --break-system-packages'.")

    required_dirs = list(cfg.category_dirs.values()) + [cfg.log_dir]
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
            raise ConfigError(f"Boundary file for district '{district.key}' not found: {district.boundary_path}")

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
    """Load and union each active district's boundary geometry."""
    rows = []
    for key, district in cfg.districts.items():
        gdf = gpd.read_file(district.boundary_path)
        if gdf.crs is None:
            logger.warning("Boundary file for '%s' has no CRS set; assuming %s.", key, cfg.crs)
            gdf.set_crs(cfg.crs, inplace=True)
        elif str(gdf.crs) != cfg.crs:
            gdf = gdf.to_crs(cfg.crs)

        geometry = gdf.union_all() if hasattr(gdf, "union_all") else gdf.unary_union
        rows.append({"district": key, "display_name": district.display_name, "geometry": geometry})

    combined = gpd.GeoDataFrame(rows, geometry="geometry", crs=cfg.crs).set_index("district")
    logger.info("Loaded boundaries for %d districts: %s", len(combined), list(combined.index))
    return combined


def district_bbox(row: "gpd.GeoSeries") -> Tuple[float, float, float, float]:
    """Return (south, west, north, east) bbox for the Overpass query."""
    minx, miny, maxx, maxy = row.geometry.bounds
    return (miny, minx, maxy, maxx)


# --------------------------------------------------------------------------- #
# Overpass client
# --------------------------------------------------------------------------- #

class OverpassClient:
    """Thin client around the Overpass API with mirror fallback, retry, and
    backoff-with-jitter on rate-limit/congestion responses."""

    def __init__(self, mirrors: List[str], timeout_seconds: int, max_retries: int,
                 backoff_factor: float, request_delay_seconds: float,
                 user_agent: str, logger: logging.Logger,
                 max_rate_limit_hits_per_mirror: int = 3) -> None:
        self.mirrors = mirrors
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.request_delay_seconds = request_delay_seconds
        self.logger = logger
        # Caps how many consecutive rate-limit/timeout hits are tolerated on
        # a single mirror before giving up on it and moving to the next one.
        # Without this cap, `attempt` is decremented on every rate-limit hit
        # (see `query()` below) so the standard max_retries budget never
        # gets consumed under *persistent* 429/504s -- the loop would retry
        # the same mirror indefinitely with ever-growing backoff instead of
        # ever trying the next mirror.
        self.max_rate_limit_hits_per_mirror = max_rate_limit_hits_per_mirror
        self._rate_limit_hits: Dict[str, int] = {}
        # overpass-api.de's front-end rejects requests without a proper
        # User-Agent (406 Not Acceptable) -- requests' default UA
        # ("python-requests/x.x") gets treated as bot traffic and blocked.
        # Accept is set explicitly for the same content-negotiation reason.
        self._headers = {"User-Agent": user_agent, "Accept": "application/json"}

    def _post_once(self, url: str, query: str) -> Dict[str, Any]:
        response = requests.post(url, data={"data": query}, headers=self._headers,
                                  timeout=self.timeout_seconds)
        if response.status_code == 429:
            raise requests.HTTPError(f"429 Too Many Requests from {url}")
        if response.status_code == 504:
            raise requests.HTTPError(f"504 Gateway Timeout from {url}")
        if response.status_code == 406:
            raise requests.HTTPError(
                f"406 Not Acceptable from {url} -- the server rejected the request "
                f"headers (User-Agent/Accept), not the query itself."
            )
        response.raise_for_status()
        return response.json()

    def query(self, query_str: str, job_key: str) -> Dict[str, Any]:
        """Run an Overpass QL query, falling back across mirrors, with retry."""
        last_exc: Optional[Exception] = None
        for mirror in self.mirrors:
            attempt = 0
            while attempt < self.max_retries:
                attempt += 1
                if self.request_delay_seconds > 0:
                    time.sleep(self.request_delay_seconds)
                try:
                    return self._post_once(mirror, query_str)
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if _is_rate_limited(exc):
                        hits = self._rate_limit_hits.get(job_key, 0) + 1
                        self._rate_limit_hits[job_key] = hits
                        if hits >= self.max_rate_limit_hits_per_mirror:
                            self.logger.warning(
                                "[%s] Hit rate-limit/timeout %d times on %s. Advancing to next mirror.",
                                job_key, hits, mirror,
                            )
                            break
                        base = min(15.0 * (2 ** (hits - 1)), 120.0)
                        sleep_time = random.uniform(base * 0.5, base)
                        self.logger.warning(
                            "[%s] Overpass rate-limited on %s (hit #%d, not counted "
                            "against the %d-attempt limit): %s. Waiting %.0f s...",
                            job_key, mirror, hits, self.max_retries, exc, sleep_time,
                        )
                        time.sleep(sleep_time)
                        attempt -= 1
                        continue

                    if _is_non_retryable_client_error(exc):
                        # Deterministic rejection (bad headers, malformed
                        # request, auth) -- retrying the identical request
                        # against the same mirror will not change the
                        # outcome. Fail this mirror immediately instead of
                        # spending the full retry budget on backoff.
                        self.logger.warning(
                            "[%s] Overpass rejected the request on %s (non-retryable: %s). "
                            "Skipping remaining retries on this mirror.",
                            job_key, mirror, exc,
                        )
                        break

                    wait = self.backoff_factor ** attempt
                    self.logger.warning(
                        "[%s] Overpass request failed on %s (attempt %d/%d): %s. Retrying in %.1f s...",
                        job_key, mirror, attempt, self.max_retries, exc, wait,
                    )
                    time.sleep(wait)
            self.logger.warning("[%s] Exhausted retries on mirror %s, trying next mirror.", job_key, mirror)
        raise RuntimeError(f"Overpass query failed on all mirrors for '{job_key}': {last_exc}")


def build_overpass_query(bbox: Tuple[float, float, float, float],
                          filters: List[str], timeout_seconds: int) -> str:
    """Build an Overpass QL query for the given bbox and element filters."""
    south, west, north, east = bbox
    bbox_str = f"({south},{west},{north},{east})"
    filter_clauses = "\n  ".join(f"{f}{bbox_str};" for f in filters)
    return f"""
[out:json][timeout:{timeout_seconds}];
(
  {filter_clauses}
);
out geom;
"""


# --------------------------------------------------------------------------- #
# OSM JSON -> GeoDataFrame conversion
# --------------------------------------------------------------------------- #

def _way_geometry(element: Dict[str, Any]) -> Optional["BaseGeometry"]:
    geometry = element.get("geometry")
    if not geometry:
        return None
    coords = [(pt["lon"], pt["lat"]) for pt in geometry]
    if len(coords) < 2:
        return None
    if coords[0] == coords[-1] and len(coords) >= 4:
        try:
            return Polygon(coords)
        except Exception:
            return LineString(coords)
    return LineString(coords)


def _relation_geometry(element: Dict[str, Any]) -> Optional["BaseGeometry"]:
    """Best-effort geometry construction for relations from 'outer' member ways."""
    members = element.get("members", [])
    outer_coords: List[List[Tuple[float, float]]] = []
    for member in members:
        if member.get("role") == "outer" and member.get("geometry"):
            coords = [(pt["lon"], pt["lat"]) for pt in member["geometry"]]
            if len(coords) >= 4 and coords[0] == coords[-1]:
                outer_coords.append(coords)
    if not outer_coords:
        return None
    try:
        if len(outer_coords) == 1:
            return Polygon(outer_coords[0])
        return MultiPolygon([Polygon(c) for c in outer_coords])
    except Exception:
        return None


def osm_json_to_geodataframe(osm_json: Dict[str, Any], logger: logging.Logger,
                              crs: str) -> "gpd.GeoDataFrame":
    """Convert a raw Overpass `out geom` JSON response into a GeoDataFrame."""
    records: List[Dict[str, Any]] = []
    skipped_relations = 0

    for element in osm_json.get("elements", []):
        el_type = element.get("type")
        tags = element.get("tags", {}) or {}
        geometry: Optional["BaseGeometry"] = None

        if el_type == "node":
            lat, lon = element.get("lat"), element.get("lon")
            if lat is not None and lon is not None:
                geometry = Point(lon, lat)
        elif el_type == "way":
            geometry = _way_geometry(element)
        elif el_type == "relation":
            geometry = _relation_geometry(element)
            if geometry is None:
                skipped_relations += 1

        if geometry is None:
            continue

        records.append({
            "osm_id": element.get("id"),
            "osm_type": el_type,
            "name": tags.get("name"),
            "tags": json.dumps(tags, ensure_ascii=False),
            "geometry": geometry,
        })

    if skipped_relations:
        logger.warning("Skipped %d relation(s) with no reconstructable outer geometry.", skipped_relations)

    if not records:
        return gpd.GeoDataFrame(columns=["osm_id", "osm_type", "name", "tags", "geometry"],
                                 geometry="geometry", crs=crs)

    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=crs)
    logger.info("Parsed %d elements with geometry from Overpass response.", len(gdf))
    return gdf


# --------------------------------------------------------------------------- #
# Validation, clipping, deduplication
# --------------------------------------------------------------------------- #

def validate_geometries(gdf: "gpd.GeoDataFrame", logger: logging.Logger) -> "gpd.GeoDataFrame":
    """Drop empty/null geometries and repair invalid ones via make_valid."""
    if gdf.empty:
        return gdf

    before = len(gdf)
    gdf = gdf[~gdf.geometry.isna() & ~gdf.geometry.is_empty].copy()

    invalid_mask = ~gdf.geometry.is_valid
    if invalid_mask.any():
        gdf.loc[invalid_mask, "geometry"] = gdf.loc[invalid_mask, "geometry"].apply(
            lambda geom: make_valid(geom) if geom is not None else None
        )

    gdf = gdf[~gdf.geometry.isna() & ~gdf.geometry.is_empty & gdf.geometry.is_valid].copy()

    dropped = before - len(gdf)
    if dropped:
        logger.info("Validation dropped %d invalid/empty geometries.", dropped)
    return gdf


def deduplicate(gdf: "gpd.GeoDataFrame", logger: logging.Logger) -> "gpd.GeoDataFrame":
    """Remove duplicates by (osm_type, osm_id), then by geometry+tags hash."""
    if gdf.empty:
        return gdf

    before = len(gdf)
    gdf = gdf.drop_duplicates(subset=["osm_type", "osm_id"], keep="first")

    def _row_hash(row) -> str:
        payload = f"{row['tags']}|{row.geometry.wkt}"
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    gdf = gdf.copy()
    gdf["_dedup_hash"] = gdf.apply(_row_hash, axis=1)
    gdf = gdf.drop_duplicates(subset="_dedup_hash", keep="first").drop(columns="_dedup_hash")

    dropped = before - len(gdf)
    if dropped:
        logger.info("Deduplication removed %d duplicate features.", dropped)
    return gdf


def clip_to_boundary(gdf: "gpd.GeoDataFrame", boundary_geometry: "BaseGeometry",
                     crs: str, logger: logging.Logger) -> "gpd.GeoDataFrame":
    """Clip features to a single district's boundary polygon."""
    if gdf.empty:
        return gdf

    boundary_gdf = gpd.GeoDataFrame({"geometry": [boundary_geometry]}, crs=crs)
    before = len(gdf)
    clipped = gpd.clip(gdf, boundary_gdf)
    logger.info("Clipped to district boundary: %d -> %d features.", before, len(clipped))
    return clipped


# --------------------------------------------------------------------------- #
# Output writing
# --------------------------------------------------------------------------- #

def output_paths(category_dir: Path, district: str, category: str,
                  vector_format: str) -> Tuple[Path, Path]:
    ext = ".geojson" if vector_format.upper() == "GEOJSON" else f".{vector_format.lower()}"
    stem = f"{district}_{category}"
    return category_dir / f"{stem}{ext}", category_dir / f"{stem}.csv"


def save_outputs(gdf: "gpd.GeoDataFrame", vector_path: Path, csv_path: Path,
                  encoding: str, logger: logging.Logger) -> None:
    if vector_path.suffix.lower() == ".geojson":
        gdf.to_file(vector_path, driver="GeoJSON")
    else:
        gdf.to_file(vector_path)

    csv_df = pd.DataFrame(gdf.drop(columns="geometry"))
    csv_df["geometry_wkt"] = gdf.geometry.apply(lambda g: g.wkt if g is not None else None)
    csv_df.to_csv(csv_path, index=False, encoding=encoding)

    logger.info("Saved %d features -> %s / %s", len(gdf), vector_path.name, csv_path.name)


def write_cleaned_copy(gdf: "gpd.GeoDataFrame", cleaned_dir: Path, district: str,
                        category: str, logger: logging.Logger) -> Path:
    """Write the validated + deduplicated + clipped result to `cleaned/`."""
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    path = cleaned_dir / f"{district}_{category}_cleaned.geojson"
    gdf.to_file(path, driver="GeoJSON")
    logger.info("Wrote cleaned copy -> %s", path.name)
    return path


def compute_checksum(file_path: Path) -> str:
    """Compute the SHA-256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


# --------------------------------------------------------------------------- #
# Metadata / resume support
# --------------------------------------------------------------------------- #

def _metadata_key(district: str, category: str) -> str:
    """Build the compound 'district:category' key used in metadata.json."""
    return f"{district}:{category}"


def load_metadata(metadata_path: Path) -> Dict[str, Any]:
    """Load metadata.json, returning a default structure if absent/corrupt."""
    if metadata_path.exists():
        try:
            with open(metadata_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError:
            pass
    return {"source": "OpenStreetMap (Overpass API)", "jobs": {}, "last_updated": None}


def update_metadata(
    metadata_path: Path, district: str, category: str, status: str,
    feature_count: int = 0, vector_path: Optional[Path] = None,
    csv_path: Optional[Path] = None, cleaned_path: Optional[Path] = None,
) -> None:
    """Record the outcome of processing one district-category into metadata.json."""
    metadata = load_metadata(metadata_path)
    entry: Dict[str, Any] = {
        "district": district, "category": category, "status": status,
        "feature_count": feature_count, "updated_at": datetime.now().isoformat(),
    }

    if vector_path and vector_path.exists():
        entry["vector_file"] = str(vector_path)
        entry["vector_checksum_sha256"] = compute_checksum(vector_path)
    if csv_path and csv_path.exists():
        entry["csv_file"] = str(csv_path)
    if cleaned_path and cleaned_path.exists():
        entry["cleaned_file"] = str(cleaned_path)

    metadata.setdefault("jobs", {})[_metadata_key(district, category)] = entry
    metadata["last_updated"] = datetime.now().isoformat()

    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metadata_path, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)


def district_category_already_completed(metadata_path: Path, district: str, category: str) -> bool:
    """Check whether a district-category is already 'completed' or 'empty'."""
    metadata = load_metadata(metadata_path)
    entry = metadata.get("jobs", {}).get(_metadata_key(district, category))
    return bool(entry and entry.get("status") in ("completed", "empty"))


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def _process_single_district_category(
    client: OverpassClient, cfg: CollectorConfig, districts_gdf: "gpd.GeoDataFrame",
    district_key: str, category: str, spec: Dict[str, Any], force: bool,
    logger: logging.Logger,
) -> str:
    """Run fetch + validate + clip + save + metadata-update for one job."""
    job_key = _metadata_key(district_key, category)

    if not force and cfg.resume_incomplete and district_category_already_completed(
        cfg.metadata_path, district_key, category
    ):
        logger.info("[%s] Already completed per metadata.json, skipping (use --force to redo).", job_key)
        return "skipped"

    folder_key = spec["folder"]
    category_dir = cfg.category_dirs[folder_key]
    vector_path, csv_path = output_paths(category_dir, district_key, category, cfg.vector_format)

    if not cfg.download_overwrite and not force and vector_path.exists() and csv_path.exists():
        logger.info("[%s] Output files already exist, skipping (download.overwrite=false).", job_key)
        return "skipped"

    boundary_row = districts_gdf.loc[district_key]
    bbox = district_bbox(boundary_row)
    query_str = build_overpass_query(bbox, spec["filters"], cfg.overpass_timeout_seconds)

    try:
        osm_json = client.query(query_str, job_key)
    except Exception as exc:  # noqa: BLE001
        logger.error("[%s] Overpass fetch failed: %s", job_key, exc)
        update_metadata(cfg.metadata_path, district_key, category, status="failed")
        return "failed"

    gdf = osm_json_to_geodataframe(osm_json, logger, cfg.crs)
    if gdf.empty:
        logger.warning("[%s] No features returned from Overpass.", job_key)
        update_metadata(cfg.metadata_path, district_key, category, status="empty", feature_count=0)
        return "empty"

    gdf = validate_geometries(gdf, logger)
    gdf = deduplicate(gdf, logger)
    gdf = clip_to_boundary(gdf, boundary_row.geometry, cfg.crs, logger)

    if gdf.empty:
        logger.warning("[%s] No features remain after clipping to boundary.", job_key)
        update_metadata(cfg.metadata_path, district_key, category, status="empty", feature_count=0)
        return "empty"

    try:
        save_outputs(gdf, vector_path, csv_path, cfg.encoding, logger)
        cleaned_path = write_cleaned_copy(gdf, cfg.category_dirs["cleaned"], district_key, category, logger)
        update_metadata(
            cfg.metadata_path, district_key, category, status="completed",
            feature_count=len(gdf), vector_path=vector_path, csv_path=csv_path,
            cleaned_path=cleaned_path,
        )
        return "completed"
    except Exception as exc:  # noqa: BLE001
        logger.error("[%s] Failed to save outputs: %s", job_key, exc)
        update_metadata(cfg.metadata_path, district_key, category, status="failed")
        return "failed"


def collect_infrastructure(
    cfg: CollectorConfig, logger: logging.Logger, force: bool = False,
    only_district: Optional[str] = None, only_category: Optional[str] = None,
) -> None:
    """Run the full infrastructure collection pipeline sequentially (Overpass's
    public-server fair-use policy discourages concurrent queries from one client)."""
    if not cfg.dataset_enabled:
        logger.info("digital_twin_sources.infrastructure.enabled is false; exiting.")
        return

    validate_environment(cfg, logger)
    districts_gdf = load_district_boundaries(cfg, logger)

    client = OverpassClient(
        mirrors=cfg.overpass_mirrors, timeout_seconds=cfg.overpass_timeout_seconds,
        max_retries=cfg.http_max_retries, backoff_factor=cfg.http_backoff_factor,
        request_delay_seconds=cfg.request_delay_seconds,
        user_agent=cfg.overpass_user_agent, logger=logger,
    )

    district_keys = [only_district] if only_district else list(districts_gdf.index)
    if only_category:
        if only_category not in CATEGORY_SPECS:
            raise ConfigError(f"Unknown category '{only_category}'. Valid categories: "
                               f"{', '.join(CATEGORY_SPECS.keys())}")
        categories = [only_category]
    else:
        categories = list(CATEGORY_SPECS.keys())

    jobs = [(d, c) for d in district_keys for c in categories]
    logger.info(
        "Starting infrastructure collection: %d district(s) x %d categor(y/ies) = %d job(s). "
        "Districts=%s, categories=%s",
        len(district_keys), len(categories), len(jobs), district_keys, categories,
    )

    results = {"completed": 0, "failed": 0, "skipped": 0, "empty": 0}

    for district_key, category in tqdm(jobs, desc="Infrastructure district-categories", unit="job"):
        spec = CATEGORY_SPECS[category]
        status = _process_single_district_category(
            client, cfg, districts_gdf, district_key, category, spec, force, logger
        )
        results[status] += 1

    logger.info(
        "Infrastructure collection complete. Completed=%d, Empty=%d, Failed=%d, Skipped=%d",
        results["completed"], results["empty"], results["failed"], results["skipped"],
    )
    if results["failed"]:
        logger.warning("%d job(s) failed. Re-run the script (resume is automatic) to retry them.",
                        results["failed"])


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="OpenStreetMap infrastructure collector.")
    parser.add_argument("--config", type=Path, default=Path("config/config.yaml"),
                         help="Path to config.yaml (default: config/config.yaml)")
    parser.add_argument("--district", type=str, default=None,
                         help="Restrict the run to a single district (e.g. 'mandi').")
    parser.add_argument("--category", type=str, default=None,
                         help="Restrict the run to a single category (e.g. 'Roads').")
    parser.add_argument("--force", action="store_true",
                         help="Re-fetch and reprocess district-categories even if already completed.")
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
        collect_infrastructure(cfg, logger, force=args.force,
                                only_district=args.district, only_category=args.category)
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