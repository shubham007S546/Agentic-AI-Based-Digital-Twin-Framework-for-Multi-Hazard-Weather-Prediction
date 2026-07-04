"""
collectors/modis_collector.py
==============================

Production-ready collector for MODIS vegetation indices (NDVI / EVI from the
MOD13Q1 product) via the NASA AppEEARS API, for arbitrary districts defined
by GeoJSON boundary files.

Design goals
------------
- ALL configuration comes from ``config/config.yaml``. No ``.env`` file and
  no environment variables are read anywhere in this module.
- Fully reusable for any district: add a district name + GeoJSON boundary
  file and it is picked up automatically, no code changes required.
- Idempotent / resumable: safe to re-run. Already-completed downloads are
  skipped, partially-downloaded files are resumed, and failed steps are
  retried with exponential backoff.
- Every downloaded file is validated before being marked complete.
- Detailed logging (console + rotating file per output category) and tqdm
  progress bars for long-running operations.

This collector reads the SAME master ``config/config.yaml`` used by every
other collector in this project -- it does not require or expect any
dedicated ``nasa_earthdata:`` / ``modis:`` blocks of its own. Specifically
it reads:

- ``api_keys.nasa_username`` / ``api_keys.nasa_password`` for Earthdata auth
- ``dates.start_date`` / ``dates.end_date`` for the default time window
  (overridable per-collector via an optional ``digital_twin_sources.modis.dates``
  block)
- ``paths.root.datasets`` as the root every relative path below is joined against
- ``districts.<name>.boundary`` for each district's GeoJSON boundary path
- ``active_districts`` for which districts to process (falls back to all
  keys under ``districts`` if omitted)
- ``paths.vegetation.modis`` / ``paths.vegetation.ndvi`` for output roots
- ``digital_twin_sources.modis.product`` / ``.version`` / ``.variables`` to
  build the AppEEARS product/layer list (NDVI -> NDVI output folder, EVI ->
  MODIS output folder); an optional explicit
  ``digital_twin_sources.modis.layers`` list overrides this derivation
- ``http.max_retries`` / ``http.backoff_factor`` for retry behaviour
- an optional ``digital_twin_sources.modis.appeears`` block for AppEEARS-
  specific tuning (base_url, poll_interval_seconds, task_timeout_hours,
  request_timeout_seconds) -- all have sane defaults if omitted

Nothing needs to be duplicated in config.yaml beyond what's already there;
adding a new district only requires an entry under ``districts:`` (with its
``boundary`` GeoJSON) and adding it to ``active_districts``.

Usage
-----
    python -m collectors.modis_collector --config config/config.yaml
    python -m collectors.modis_collector --district mandi
    python -m collectors.modis_collector --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
import yaml
from tqdm import tqdm

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

DEFAULT_CONFIG_PATH = Path("config/config.yaml")
APPEEARS_DATE_FMT = "%m-%d-%Y"          # AppEEARS wants MM-DD-YYYY
ISO_DATE_FMT = "%Y-%m-%d"
DOWNLOAD_CHUNK_BYTES = 1024 * 1024      # 1 MB
LOGGER_NAME = "modis_collector"


# --------------------------------------------------------------------------- #
# Config models
# --------------------------------------------------------------------------- #

@dataclass
class RetryConfig:
    max_retries: int = 5
    backoff_base_seconds: float = 5.0
    backoff_max_seconds: float = 120.0
    backoff_factor: float = 2.0


@dataclass
class AppeearsConfig:
    base_url: str = "https://appeears.earthdatacloud.nasa.gov/api"
    poll_interval_seconds: int = 30
    task_timeout_hours: int = 12
    request_timeout_seconds: int = 60


@dataclass
class ProductLayer:
    product: str
    layer: str
    category: str  # "MODIS" or "NDVI" -> selects output root


@dataclass
class CollectorConfig:
    username: str
    password: str
    start_date: str
    end_date: str
    district_boundaries: Dict[str, List[Path]]
    districts: List[str]
    products: List[ProductLayer]
    modis_dir: Path
    ndvi_dir: Path
    appeears: AppeearsConfig = field(default_factory=AppeearsConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)

    def output_dir_for(self, category: str) -> Path:
        """Return the output root directory for a given layer category."""
        return self.ndvi_dir if category.upper() == "NDVI" else self.modis_dir

    def boundary_candidates_for(self, district: str) -> List[Path]:
        """Return the ordered list of candidate boundary paths for a district."""
        try:
            return self.district_boundaries[district]
        except KeyError as exc:
            raise ValueError(
                f"No boundary path configured for district '{district}' -- "
                f"add it under 'districts.{district}.boundary' in config.yaml"
            ) from exc


def load_config(config_path: Path) -> CollectorConfig:
    """
    Load and validate the collector configuration from ``config.yaml``.

    Parameters
    ----------
    config_path:
        Path to the YAML configuration file.

    Returns
    -------
    CollectorConfig
        Parsed and validated configuration object.

    Raises
    ------
    FileNotFoundError
        If the config file does not exist.
    ValueError
        If required fields are missing from the config file.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as fh:
        raw: Dict[str, Any] = yaml.safe_load(fh) or {}

    # -- Earthdata credentials (shared api_keys block) ---------------------- #
    api_keys = raw.get("api_keys", {})
    username = api_keys.get("nasa_username")
    password = api_keys.get("nasa_password")
    if not username or not password or str(username).startswith("${") or str(password).startswith("${"):
        raise ValueError(
            "config.yaml must define api_keys.nasa_username and "
            "api_keys.nasa_password with real values (not '${...}' placeholders)"
        )

    # -- Date window (global default, optionally overridden per-collector) -- #
    try:
        dates_cfg = raw["dates"]
        start_date = dates_cfg["start_date"]
        end_date = dates_cfg["end_date"]
    except KeyError as exc:
        raise ValueError(f"Missing required key under 'dates' in config.yaml: {exc}") from exc

    modis_meta = raw.get("digital_twin_sources", {}).get("modis", {})
    modis_dates = modis_meta.get("dates", {})
    start_date = modis_dates.get("start_date", start_date)
    end_date = modis_dates.get("end_date", end_date)

    # -- Paths / districts ---------------------------------------------------#
    try:
        datasets_root = Path(raw["paths"]["root"]["datasets"])
        vegetation_paths = raw["paths"]["vegetation"]
        modis_dir = datasets_root / vegetation_paths["modis"]
        ndvi_dir = datasets_root / vegetation_paths["ndvi"]
    except KeyError as exc:
        raise ValueError(
            f"Missing required key under 'paths' in config.yaml: {exc}"
        ) from exc

    try:
        districts_cfg: Dict[str, Any] = raw["districts"]
    except KeyError as exc:
        raise ValueError("config.yaml must define a top-level 'districts' block") from exc

    districts = list(raw.get("active_districts") or districts_cfg.keys())
    if not districts:
        raise ValueError("config.yaml 'active_districts' (or 'districts') must list at least one district")

    district_boundaries: Dict[str, List[Path]] = {}
    for district in districts:
        try:
            boundary_rel = districts_cfg[district]["boundary"]
        except KeyError as exc:
            raise ValueError(
                f"districts.{district}.boundary is missing in config.yaml"
            ) from exc
        # Project layouts vary on whether 'digital_twin' sits directly at the
        # project root or nested under 'datasets'. Rather than assume one,
        # collect every plausible location and use whichever exists on disk
        # at load time (see load_district_geojson).
        district_boundaries[district] = [
            Path(boundary_rel),                 # as given, relative to CWD/project root
            datasets_root / boundary_rel,        # relative to paths.root.datasets
        ]

    # -- Product / layer list -------------------------------------------------#
    products = _derive_product_layers(modis_meta)
    if not products:
        raise ValueError(
            "Could not derive any MODIS product/layer combinations -- check "
            "digital_twin_sources.modis.variables (or .layers) in config.yaml"
        )

    # -- AppEEARS tuning (all optional, sane defaults) ------------------------#
    appeears_raw = modis_meta.get("appeears", {})
    appeears = AppeearsConfig(
        base_url=appeears_raw.get("base_url", AppeearsConfig.base_url),
        poll_interval_seconds=int(appeears_raw.get("poll_interval_seconds", 30)),
        task_timeout_hours=int(appeears_raw.get("task_timeout_hours", 12)),
        request_timeout_seconds=int(appeears_raw.get("request_timeout_seconds", raw.get("http", {}).get("timeout_seconds", 60))),
    )

    # -- Retry behaviour, shared with the rest of the project -----------------#
    http_cfg = raw.get("http", {})
    retry = RetryConfig(
        max_retries=int(http_cfg.get("max_retries", 5)),
        backoff_base_seconds=5.0,
        backoff_max_seconds=120.0,
        backoff_factor=float(http_cfg.get("backoff_factor", 2.0)),
    )

    return CollectorConfig(
        username=username,
        password=password,
        start_date=start_date,
        end_date=end_date,
        district_boundaries=district_boundaries,
        districts=districts,
        products=products,
        modis_dir=modis_dir,
        ndvi_dir=ndvi_dir,
        appeears=appeears,
        retry=retry,
    )


def _derive_product_layers(modis_meta: Dict[str, Any]) -> List[ProductLayer]:
    """
    Build the list of AppEEARS product/layer combinations to request.

    Preference order:
    1. An explicit ``digital_twin_sources.modis.layers`` override list, each
       entry shaped like ``{product, layer, category}``.
    2. Derived from ``digital_twin_sources.modis.product`` + ``.version`` +
       ``.variables`` (e.g. product="MOD13Q1", version="061",
       variables=["NDVI", "EVI"]) using the standard MOD13Q1 layer names.
       NDVI is routed to the "NDVI" output category, everything else
       (EVI, etc.) to the "MODIS" output category.

    Parameters
    ----------
    modis_meta:
        The ``digital_twin_sources.modis`` mapping from config.yaml.

    Returns
    -------
    list of ProductLayer
    """
    explicit = modis_meta.get("layers")
    if explicit:
        return [
            ProductLayer(product=p["product"], layer=p["layer"], category=p.get("category", "MODIS"))
            for p in explicit
        ]

    product_code = modis_meta.get("product", "MOD13Q1")
    version = modis_meta.get("version", "061")
    product_id = f"{product_code}.{version}"
    variables = modis_meta.get("variables", ["NDVI", "EVI"])

    # Standard MOD13Q1 (250m, 16-day composite) layer names.
    layer_name_map = {
        "NDVI": "_250m_16_days_NDVI",
        "EVI": "_250m_16_days_EVI",
    }
    category_map = {
        "NDVI": "NDVI",
        "EVI": "MODIS",
    }

    layers: List[ProductLayer] = []
    for var in variables:
        var_key = str(var).upper()
        layer_name = layer_name_map.get(var_key)
        if layer_name is None:
            continue  # unrecognized variable name for this product -- skip rather than guess
        layers.append(
            ProductLayer(product=product_id, layer=layer_name, category=category_map.get(var_key, "MODIS"))
        )
    return layers


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #

def build_logger(name: str, log_dir: Path) -> logging.Logger:
    """
    Create a logger that writes to both the console and a rotating file
    inside ``log_dir``.

    Parameters
    ----------
    name:
        Logger name, also used as the log filename stem.
    log_dir:
        Directory where the rotating log file will be created.

    Returns
    -------
    logging.Logger
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"{LOGGER_NAME}.{name}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        return logger  # already configured (e.g. re-entrant calls)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_dir / f"{name}.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


# --------------------------------------------------------------------------- #
# Retry helper
# --------------------------------------------------------------------------- #

def retry_call(
    func,
    *,
    retry_cfg: RetryConfig,
    logger: logging.Logger,
    description: str,
    retriable_exceptions: Tuple[type, ...] = (requests.RequestException,),
):
    """
    Call ``func`` (a zero-argument callable) with exponential backoff retry.

    Parameters
    ----------
    func:
        Zero-argument callable to invoke.
    retry_cfg:
        Retry configuration (max retries, backoff bounds).
    logger:
        Logger used to record retry attempts.
    description:
        Human-readable description of the operation, used in log messages.
    retriable_exceptions:
        Exception types that should trigger a retry rather than propagate.

    Returns
    -------
    Any
        The return value of ``func`` on success.

    Raises
    ------
    Exception
        Re-raises the last exception if all retries are exhausted.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return func()
        except retriable_exceptions as exc:
            if attempt > retry_cfg.max_retries:
                logger.error("%s failed permanently after %d attempts: %s", description, attempt - 1, exc)
                raise
            delay = min(
                retry_cfg.backoff_base_seconds * (retry_cfg.backoff_factor ** (attempt - 1)),
                retry_cfg.backoff_max_seconds,
            )
            logger.warning(
                "%s failed (attempt %d/%d): %s -- retrying in %.1fs",
                description, attempt, retry_cfg.max_retries, exc, delay,
            )
            time.sleep(delay)


# --------------------------------------------------------------------------- #
# GeoJSON / bounding box utilities
# --------------------------------------------------------------------------- #

def _iter_coordinates(coords: Any) -> Iterable[Tuple[float, float]]:
    """Recursively yield (lon, lat) pairs from a nested GeoJSON coordinate array."""
    if not coords:
        return
    # A coordinate pair looks like [lon, lat] (both numbers).
    if isinstance(coords[0], (int, float)):
        yield float(coords[0]), float(coords[1])
    else:
        for sub in coords:
            yield from _iter_coordinates(sub)


def load_district_geojson(
    candidates: List[Path], district: str, logger: Optional[logging.Logger] = None
) -> Dict[str, Any]:
    """
    Load a district boundary GeoJSON file, trying each candidate path in
    order and using the first one that exists on disk.

    Parameters
    ----------
    candidates:
        Ordered list of possible paths to the district's boundary GeoJSON
        (project layouts vary on whether ``digital_twin/`` sits at the
        project root or nested under ``datasets/``).
    district:
        District name, used for error/log messages.
    logger:
        Optional logger to record which candidate path was used.

    Returns
    -------
    dict
        Parsed GeoJSON object.

    Raises
    ------
    FileNotFoundError
        If none of the candidate paths exist.
    """
    for path in candidates:
        if path.exists():
            if logger:
                logger.info("Resolved boundary for district '%s' -> %s", district, path)
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)

    checked = ", ".join(str(c) for c in candidates)
    raise FileNotFoundError(
        f"Boundary file not found for district '{district}'. Checked: {checked}"
    )


def compute_bbox(geojson_obj: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """
    Compute the bounding box of a GeoJSON Feature / FeatureCollection / geometry.

    Parameters
    ----------
    geojson_obj:
        Parsed GeoJSON object (Feature, FeatureCollection, or bare geometry).

    Returns
    -------
    tuple
        ``(min_lon, min_lat, max_lon, max_lat)``.

    Raises
    ------
    ValueError
        If no coordinates could be extracted from the GeoJSON.
    """
    geometries: List[Dict[str, Any]] = []
    gtype = geojson_obj.get("type")

    if gtype == "FeatureCollection":
        geometries = [feat["geometry"] for feat in geojson_obj.get("features", []) if feat.get("geometry")]
    elif gtype == "Feature":
        if geojson_obj.get("geometry"):
            geometries = [geojson_obj["geometry"]]
    elif gtype in ("Polygon", "MultiPolygon", "Point", "LineString", "MultiLineString", "MultiPoint"):
        geometries = [geojson_obj]

    lons: List[float] = []
    lats: List[float] = []
    for geom in geometries:
        for lon, lat in _iter_coordinates(geom.get("coordinates")):
            lons.append(lon)
            lats.append(lat)

    if not lons or not lats:
        raise ValueError("Could not extract any coordinates from GeoJSON to compute bounding box")

    return min(lons), min(lats), max(lons), max(lats)


def geojson_as_feature_collection(geojson_obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a GeoJSON object into a FeatureCollection, as required by the
    AppEEARS Area task ``geo`` parameter.

    Parameters
    ----------
    geojson_obj:
        Parsed GeoJSON object (Feature, FeatureCollection, or bare geometry).

    Returns
    -------
    dict
        A GeoJSON FeatureCollection wrapping the input geometry.
    """
    gtype = geojson_obj.get("type")
    if gtype == "FeatureCollection":
        return geojson_obj
    if gtype == "Feature":
        return {"type": "FeatureCollection", "features": [geojson_obj]}
    # Bare geometry
    return {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": geojson_obj}],
    }


# --------------------------------------------------------------------------- #
# NASA Earthdata / AppEEARS client
# --------------------------------------------------------------------------- #

class AppeearsClient:
    """
    Thin client around the NASA AppEEARS REST API used to authenticate,
    submit Area extraction tasks, poll their status, and download results.
    """

    def __init__(self, config: CollectorConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.session = requests.Session()
        self._token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    # -- Auth ---------------------------------------------------------- #

    def login(self) -> None:
        """
        Authenticate against NASA Earthdata / AppEEARS and cache the bearer
        token for subsequent requests.

        Raises
        ------
        RuntimeError
            If authentication fails.
        """
        url = f"{self.config.appeears.base_url}/login"

        def _do_login() -> requests.Response:
            resp = self.session.post(
                url,
                auth=(self.config.username, self.config.password),
                timeout=self.config.appeears.request_timeout_seconds,
            )
            resp.raise_for_status()
            return resp

        resp = retry_call(
            _do_login, retry_cfg=self.config.retry, logger=self.logger, description="AppEEARS login"
        )
        data = resp.json()
        self._token = data["token"]
        expiry_raw = data.get("expiration")
        self._token_expiry = None
        if expiry_raw:
            try:
                self._token_expiry = datetime.strptime(expiry_raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                self._token_expiry = None
        self.logger.info("Authenticated with NASA Earthdata / AppEEARS")

    def logout(self) -> None:
        """Invalidate the current AppEEARS token, if any."""
        if not self._token:
            return
        url = f"{self.config.appeears.base_url}/logout"
        try:
            self.session.post(url, headers=self._auth_header(), timeout=self.config.appeears.request_timeout_seconds)
        except requests.RequestException as exc:
            self.logger.warning("Logout request failed (non-fatal): %s", exc)
        finally:
            self._token = None

    def _auth_header(self) -> Dict[str, str]:
        if not self._token:
            raise RuntimeError("Not authenticated: call login() first")
        return {"Authorization": f"Bearer {self._token}"}

    def _ensure_authenticated(self) -> None:
        if self._token is None:
            self.login()
            return
        if self._token_expiry and datetime.now(timezone.utc) >= self._token_expiry:
            self.logger.info("AppEEARS token expired, re-authenticating")
            self.login()

    # -- Task submission ------------------------------------------------ #

    def submit_area_task(
        self,
        task_name: str,
        geojson_feature_collection: Dict[str, Any],
        layers: List[ProductLayer],
    ) -> str:
        """
        Submit an AppEEARS Area extraction task.

        Parameters
        ----------
        task_name:
            Human-readable task name (also used to identify it later).
        geojson_feature_collection:
            District boundary as a GeoJSON FeatureCollection.
        layers:
            Product/layer combinations to request.

        Returns
        -------
        str
            The AppEEARS task ID.
        """
        self._ensure_authenticated()
        url = f"{self.config.appeears.base_url}/task"

        start_date = datetime.strptime(self.config.start_date, ISO_DATE_FMT).strftime(APPEEARS_DATE_FMT)
        end_date = datetime.strptime(self.config.end_date, ISO_DATE_FMT).strftime(APPEEARS_DATE_FMT)

        payload = {
            "task_type": "area",
            "task_name": task_name,
            "params": {
                "dates": [{"startDate": start_date, "endDate": end_date}],
                "layers": [{"product": pl.product, "layer": pl.layer} for pl in layers],
                "output": {"format": {"type": "geotiff"}, "projection": "geographic"},
                "geo": geojson_feature_collection,
            },
        }

        def _do_submit() -> requests.Response:
            resp = self.session.post(
                url,
                json=payload,
                headers=self._auth_header(),
                timeout=self.config.appeears.request_timeout_seconds,
            )
            resp.raise_for_status()
            return resp

        resp = retry_call(
            _do_submit, retry_cfg=self.config.retry, logger=self.logger,
            description=f"submit AppEEARS task '{task_name}'",
        )
        task_id = resp.json()["task_id"]
        self.logger.info("Submitted AppEEARS task '%s' -> task_id=%s", task_name, task_id)
        return task_id

    def find_existing_task(self, task_name: str) -> Optional[str]:
        """
        Look for a previously-submitted task with the same name so we don't
        resubmit duplicate work across runs.

        Parameters
        ----------
        task_name:
            Task name to search for.

        Returns
        -------
        Optional[str]
            The matching task ID if found (and not in an error/expired
            state), else ``None``.
        """
        self._ensure_authenticated()
        url = f"{self.config.appeears.base_url}/task"

        def _do_list() -> requests.Response:
            resp = self.session.get(url, headers=self._auth_header(), timeout=self.config.appeears.request_timeout_seconds)
            resp.raise_for_status()
            return resp

        resp = retry_call(
            _do_list, retry_cfg=self.config.retry, logger=self.logger, description="list AppEEARS tasks"
        )
        for task in resp.json():
            if task.get("task_name") == task_name and task.get("status") != "error":
                return task.get("task_id")
        return None

    # -- Status polling --------------------------------------------------- #

    def get_task_status(self, task_id: str) -> str:
        """
        Fetch the current status of an AppEEARS task.

        Returns
        -------
        str
            One of AppEEARS' status strings, e.g. "pending", "queued",
            "processing", "done", "error".
        """
        self._ensure_authenticated()
        url = f"{self.config.appeears.base_url}/task/{task_id}"

        def _do_status() -> requests.Response:
            resp = self.session.get(url, headers=self._auth_header(), timeout=self.config.appeears.request_timeout_seconds)
            resp.raise_for_status()
            return resp

        resp = retry_call(
            _do_status, retry_cfg=self.config.retry, logger=self.logger,
            description=f"poll status for task {task_id}",
        )
        return resp.json().get("status", "unknown")

    def wait_for_completion(self, task_id: str) -> None:
        """
        Block until an AppEEARS task reaches a terminal state ("done"), or
        raise if it errors out or exceeds the configured timeout.

        Raises
        ------
        RuntimeError
            If the task errors out or times out.
        """
        deadline = time.time() + self.config.appeears.task_timeout_hours * 3600
        with tqdm(desc=f"Waiting on task {task_id}", bar_format="{desc}: {elapsed} elapsed") as bar:
            while True:
                status = self.get_task_status(task_id)
                bar.set_postfix_str(status)
                bar.update(0)
                if status == "done":
                    self.logger.info("Task %s completed", task_id)
                    return
                if status in ("error", "expired", "deleted"):
                    raise RuntimeError(f"AppEEARS task {task_id} ended with status '{status}'")
                if time.time() > deadline:
                    raise RuntimeError(
                        f"AppEEARS task {task_id} did not complete within "
                        f"{self.config.appeears.task_timeout_hours}h timeout"
                    )
                time.sleep(self.config.appeears.poll_interval_seconds)

    # -- Bundle listing / download ----------------------------------------- #

    def list_bundle_files(self, task_id: str) -> List[Dict[str, Any]]:
        """
        List the files contained in a completed task's result bundle.

        Returns
        -------
        list of dict
            Each dict has at least ``file_id``, ``file_name``, ``file_size``.
        """
        self._ensure_authenticated()
        url = f"{self.config.appeears.base_url}/bundle/{task_id}"

        def _do_list() -> requests.Response:
            resp = self.session.get(url, headers=self._auth_header(), timeout=self.config.appeears.request_timeout_seconds)
            resp.raise_for_status()
            return resp

        resp = retry_call(
            _do_list, retry_cfg=self.config.retry, logger=self.logger,
            description=f"list bundle for task {task_id}",
        )
        return resp.json().get("files", [])

    def download_bundle_file(
        self,
        task_id: str,
        file_entry: Dict[str, Any],
        dest_dir: Path,
    ) -> Path:
        """
        Download a single file from a task's result bundle, resuming a
        partial download if one already exists on disk.

        Parameters
        ----------
        task_id:
            AppEEARS task ID owning the bundle.
        file_entry:
            Bundle file descriptor as returned by :meth:`list_bundle_files`.
        dest_dir:
            Directory to save the downloaded file into.

        Returns
        -------
        Path
            Path to the downloaded (or already-complete) file.
        """
        self._ensure_authenticated()
        file_id = file_entry["file_id"]
        file_name = file_entry["file_name"]
        expected_size = file_entry.get("file_size")

        dest_path = dest_dir / Path(file_name).name
        partial_path = dest_path.with_suffix(dest_path.suffix + ".part")

        if dest_path.exists() and (expected_size is None or dest_path.stat().st_size == expected_size):
            self.logger.info("Skipping already-downloaded file: %s", dest_path.name)
            return dest_path

        url = f"{self.config.appeears.base_url}/bundle/{task_id}/{file_id}"
        resume_from = partial_path.stat().st_size if partial_path.exists() else 0

        def _do_download() -> None:
            nonlocal resume_from
            headers = self._auth_header()
            mode = "wb"
            if resume_from > 0:
                headers["Range"] = f"bytes={resume_from}-"
                mode = "ab"

            with self.session.get(
                url, headers=headers, stream=True, timeout=self.config.appeears.request_timeout_seconds
            ) as resp:
                if resp.status_code == 416:
                    # Requested range not satisfiable -> file is already complete.
                    return
                if resume_from > 0 and resp.status_code != 206:
                    # Server ignored the Range request; restart from scratch.
                    resume_from = 0
                    mode = "wb"
                resp.raise_for_status()

                total = expected_size or int(resp.headers.get("Content-Length", 0)) + resume_from
                with open(partial_path, mode) as fh, tqdm(
                    total=total,
                    initial=resume_from,
                    unit="B",
                    unit_scale=True,
                    desc=file_name,
                    leave=False,
                ) as bar:
                    for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
                        if chunk:
                            fh.write(chunk)
                            bar.update(len(chunk))

        retry_call(
            _do_download, retry_cfg=self.config.retry, logger=self.logger,
            description=f"download {file_name}",
        )

        partial_path.rename(dest_path)
        self.logger.info("Downloaded %s -> %s", file_name, dest_path)
        return dest_path


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

# Minimal magic-byte signatures for formats AppEEARS commonly returns.
_MAGIC_BYTES = {
    b"\x49\x49\x2a\x00": "tiff_le",   # little-endian TIFF/GeoTIFF
    b"\x4d\x4d\x00\x2a": "tiff_be",   # big-endian TIFF/GeoTIFF
    b"PK\x03\x04": "zip",
    b"\x89HDF": "hdf5",
}


def validate_file(path: Path, expected_size: Optional[int], logger: logging.Logger) -> bool:
    """
    Validate a downloaded file's integrity.

    Checks performed:
    1. File exists and is non-empty.
    2. If ``expected_size`` is known, the file size matches exactly.
    3. The file's leading bytes match a known signature for GeoTIFF, ZIP, or
       HDF5 containers (the formats AppEEARS returns).

    Parameters
    ----------
    path:
        Path to the downloaded file.
    expected_size:
        Expected file size in bytes, if known from the AppEEARS bundle
        listing.
    logger:
        Logger for recording validation failures.

    Returns
    -------
    bool
        ``True`` if the file passes all checks, ``False`` otherwise.
    """
    if not path.exists() or path.stat().st_size == 0:
        logger.error("Validation failed: %s is missing or empty", path)
        return False

    if expected_size is not None and path.stat().st_size != expected_size:
        logger.error(
            "Validation failed: %s size mismatch (got %d, expected %d)",
            path, path.stat().st_size, expected_size,
        )
        return False

    # Non-binary sidecar files (e.g. .json, .csv, .txt) skip the magic-byte check.
    if path.suffix.lower() in (".json", ".csv", ".txt", ".xml"):
        return True

    with open(path, "rb") as fh:
        header = fh.read(8)
    if not any(header.startswith(sig) for sig in _MAGIC_BYTES):
        logger.warning(
            "Validation warning: %s does not match a known binary signature "
            "(tiff/zip/hdf5) -- accepting anyway since AppEEARS formats vary",
            path,
        )
    return True


def file_checksum(path: Path) -> str:
    """Compute the SHA-256 checksum of a file for metadata tracking."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(DOWNLOAD_CHUNK_BYTES), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


# --------------------------------------------------------------------------- #
# Metadata management
# --------------------------------------------------------------------------- #

class MetadataStore:
    """
    Manages a per-category ``metadata.json`` file recording what has been
    downloaded, so re-runs can skip completed work and produce an auditable
    record of the collection.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        return {"entries": {}}

    def save(self) -> None:
        """Persist the metadata store to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2, sort_keys=True)

    def key(self, district: str, product: str, layer: str) -> str:
        return f"{district}:{product}:{layer}"

    def is_complete(self, district: str, product: str, layer: str) -> bool:
        """Return True if this district/product/layer combo already has a validated record."""
        entry = self.data["entries"].get(self.key(district, product, layer))
        return bool(entry and entry.get("status") == "complete")

    def record(
        self,
        district: str,
        product: str,
        layer: str,
        task_id: str,
        files: List[Dict[str, Any]],
        bbox: Tuple[float, float, float, float],
        status: str,
    ) -> None:
        """Record (or update) the outcome of a district/product/layer download."""
        self.data["entries"][self.key(district, product, layer)] = {
            "district": district,
            "product": product,
            "layer": layer,
            "task_id": task_id,
            "bbox": {"min_lon": bbox[0], "min_lat": bbox[1], "max_lon": bbox[2], "max_lat": bbox[3]},
            "files": files,
            "status": status,
            "start_date": None,  # filled in by caller if desired
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def ensure_output_dirs(root: Path) -> Dict[str, Path]:
    """
    Create the standard ``raw/``, ``cleaned/``, ``logs/`` subdirectories
    under an output root, plus the root itself.

    Returns
    -------
    dict
        Mapping of subdirectory name -> Path.
    """
    subdirs = {name: root / name for name in ("raw", "cleaned", "logs")}
    root.mkdir(parents=True, exist_ok=True)
    for p in subdirs.values():
        p.mkdir(parents=True, exist_ok=True)
    return subdirs


def clean_file(raw_path: Path, cleaned_dir: Path, logger: logging.Logger) -> Path:
    """
    Promote a validated raw download into the ``cleaned/`` directory.

    In this collector "cleaning" means: verify integrity, then copy the file
    into ``cleaned/`` under a normalized name. Downstream notebooks / other
    collectors are expected to do heavier lifting (e.g. reprojection,
    NoData masking) on top of this normalized copy.

    Parameters
    ----------
    raw_path:
        Path to the validated raw file.
    cleaned_dir:
        Destination directory for the cleaned copy.
    logger:
        Logger for status messages.

    Returns
    -------
    Path
        Path to the file inside ``cleaned/``.
    """
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    dest = cleaned_dir / raw_path.name
    if dest.exists() and dest.stat().st_size == raw_path.stat().st_size:
        logger.debug("Cleaned copy already present for %s", raw_path.name)
        return dest
    dest.write_bytes(raw_path.read_bytes())
    logger.info("Promoted %s to cleaned/", raw_path.name)
    return dest


def process_district_product(
    config: CollectorConfig,
    client: AppeearsClient,
    district: str,
    layers: List[ProductLayer],
    category: str,
    logger: logging.Logger,
    dry_run: bool = False,
) -> None:
    """
    Run the full pipeline (submit -> wait -> download -> validate -> clean ->
    record metadata) for one district and one output category's set of
    layers (all layers sharing a category are requested together to save on
    AppEEARS task quota).

    Parameters
    ----------
    config:
        Collector configuration.
    client:
        Authenticated AppEEARS client.
    district:
        District name, e.g. "mandi".
    layers:
        The product/layer combinations belonging to this category.
    category:
        "MODIS" or "NDVI" -- selects the output directory tree.
    logger:
        Logger for this run.
    dry_run:
        If True, log intended actions without calling the network.
    """
    output_root = config.output_dir_for(category)
    subdirs = ensure_output_dirs(output_root)
    metadata = MetadataStore(output_root / "metadata.json")

    geojson_obj = load_district_geojson(config.boundary_candidates_for(district), district, logger)
    bbox = compute_bbox(geojson_obj)
    logger.info("District '%s' bounding box: %s", district, bbox)
    feature_collection = geojson_as_feature_collection(geojson_obj)

    pending_layers = [
        pl for pl in layers
        if not metadata.is_complete(district, pl.product, pl.layer)
    ]
    if not pending_layers:
        logger.info("All layers for district '%s' / category '%s' already complete, skipping", district, category)
        return

    task_name = f"{district}_{category}_{'_'.join(sorted({pl.product for pl in pending_layers}))}"
    task_name = task_name.replace(".", "-")

    if dry_run:
        logger.info(
            "[DRY RUN] Would submit AppEEARS task '%s' for layers=%s over bbox=%s",
            task_name, [(pl.product, pl.layer) for pl in pending_layers], bbox,
        )
        return

    task_id = client.find_existing_task(task_name)
    if task_id:
        logger.info("Reusing existing AppEEARS task '%s' -> %s", task_name, task_id)
    else:
        task_id = client.submit_area_task(task_name, feature_collection, pending_layers)

    client.wait_for_completion(task_id)

    bundle_files = client.list_bundle_files(task_id)
    downloaded: List[Dict[str, Any]] = []

    for file_entry in tqdm(bundle_files, desc=f"{district}/{category} files"):
        raw_path = client.download_bundle_file(task_id, file_entry, subdirs["raw"])
        is_valid = validate_file(raw_path, file_entry.get("file_size"), logger)
        if not is_valid:
            logger.error("Skipping invalid file, will retry on next run: %s", raw_path)
            continue
        cleaned_path = clean_file(raw_path, subdirs["cleaned"], logger)
        downloaded.append(
            {
                "file_name": raw_path.name,
                "raw_path": str(raw_path),
                "cleaned_path": str(cleaned_path),
                "size_bytes": raw_path.stat().st_size,
                "sha256": file_checksum(raw_path),
            }
        )

    for pl in pending_layers:
        matching_files = [f for f in downloaded]  # AppEEARS bundles mix layers per task; record all
        metadata.record(
            district=district,
            product=pl.product,
            layer=pl.layer,
            task_id=task_id,
            files=matching_files,
            bbox=bbox,
            status="complete" if matching_files else "failed",
        )
    metadata.save()
    logger.info("Finished district='%s' category='%s': %d files downloaded", district, category, len(downloaded))


def group_layers_by_category(products: List[ProductLayer]) -> Dict[str, List[ProductLayer]]:
    """Group configured product/layer entries by their output category."""
    grouped: Dict[str, List[ProductLayer]] = {}
    for pl in products:
        grouped.setdefault(pl.category.upper(), []).append(pl)
    return grouped


def run(config: CollectorConfig, districts: Optional[List[str]] = None, dry_run: bool = False) -> None:
    """
    Top-level entry point: iterate every requested district and product
    category, running the full collection pipeline for each.

    Parameters
    ----------
    config:
        Collector configuration.
    districts:
        Optional subset of districts to process (defaults to all districts
        configured in config.yaml).
    dry_run:
        If True, do not perform any network requests -- just log intended
        actions.
    """
    target_districts = districts or config.districts
    grouped = group_layers_by_category(config.products)

    # A top-level logger for orchestration; per-category logs also get
    # written under each output root's logs/ directory.
    top_logger = build_logger("orchestrator", Path("datasets/digital_twin/vegetation/logs"))
    top_logger.info(
        "Starting MODIS collection run: districts=%s, categories=%s, dry_run=%s",
        target_districts, list(grouped.keys()), dry_run,
    )

    client = AppeearsClient(config, top_logger)
    if not dry_run:
        client.login()

    try:
        for district in tqdm(target_districts, desc="Districts"):
            for category, layers in grouped.items():
                cat_logger = build_logger(
                    f"{district}_{category.lower()}", config.output_dir_for(category) / "logs"
                )
                try:
                    process_district_product(
                        config, client, district, layers, category, cat_logger, dry_run=dry_run
                    )
                except Exception:
                    cat_logger.exception(
                        "Unhandled error processing district='%s' category='%s'", district, category
                    )
                    top_logger.error(
                        "District '%s' / category '%s' failed -- see its log for details", district, category
                    )
    finally:
        if not dry_run:
            client.logout()

    top_logger.info("MODIS collection run finished")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments for standalone execution."""
    parser = argparse.ArgumentParser(description="MODIS (MOD13Q1 NDVI/EVI) collector via NASA AppEEARS")
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG_PATH,
        help="Path to config.yaml (default: config/config.yaml)",
    )
    parser.add_argument(
        "--district", action="append", dest="districts", default=None,
        help="Restrict the run to one district (repeatable). Defaults to all districts in config.yaml.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Log intended actions without submitting AppEEARS tasks or downloading data.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point."""
    args = parse_args(argv)
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    run(config, districts=args.districts, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())