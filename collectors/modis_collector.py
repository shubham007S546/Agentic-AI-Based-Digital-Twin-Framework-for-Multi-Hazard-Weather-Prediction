"""
collectors/modis_collector.py
==============================

Production-ready collector for MODIS vegetation indices (NDVI / EVI from the
MOD13Q1 product) via the NASA AppEEARS API, for arbitrary districts defined
by GeoJSON boundary files.
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

DEFAULT_CONFIG_PATH = Path("config/config.yaml")
APPEEARS_DATE_FMT = "%m-%d-%Y"
ISO_DATE_FMT = "%Y-%m-%d"
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
LOGGER_NAME = "modis_collector"


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
    category: str


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
    logs_root: Path
    appeears: AppeearsConfig = field(default_factory=AppeearsConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)

    def output_dir_for(self, category: str) -> Path:
        return self.ndvi_dir if category.upper() == "NDVI" else self.modis_dir

    def boundary_candidates_for(self, district: str) -> List[Path]:
        try:
            return self.district_boundaries[district]
        except KeyError as exc:
            raise ValueError(
                f"No boundary path configured for district '{district}' -- "
                f"add it under 'districts.{district}.boundary' in config.yaml"
            ) from exc


def load_config(config_path: Path) -> CollectorConfig:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as fh:
        raw: Dict[str, Any] = yaml.safe_load(fh) or {}

    # -- Earthdata credentials ------------------------------------------- #
    api_keys = raw.get("api_keys", {})
    username = api_keys.get("nasa_username")
    password = api_keys.get("nasa_password")
    if not username or not password or str(username).startswith("${") or str(password).startswith("${"):
        raise ValueError(
            "config.yaml must define api_keys.nasa_username and "
            "api_keys.nasa_password with real values (not '${...}' placeholders)"
        )

    # -- Date window ------------------------------------------------------ #
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

    # -- Paths -------------------------------------------------------------#
    # IMPORTANT: paths.root.datasets ("datasets") is ONLY the root for
    # Stage-1 raw weather pulls (paths.weather.*). Every digital-twin domain
    # path (paths.vegetation.*, paths.disaster_history.*, paths.terrain.*,
    # etc.) is already a full path relative to the PROJECT ROOT -- it must
    # NOT be joined under datasets_root, or you get a bogus
    # "datasets/digital_twin/vegetation/MODIS" directory instead of the real
    # "digital_twin/vegetation/MODIS".
    try:
        vegetation_paths = raw["paths"]["vegetation"]
        modis_dir = Path(vegetation_paths["modis"])
        ndvi_dir = Path(vegetation_paths["ndvi"])
    except KeyError as exc:
        raise ValueError(
            f"Missing required key under 'paths.vegetation' in config.yaml: {exc}"
        ) from exc

    logs_root = Path(raw.get("paths", {}).get("root", {}).get("logs", "logs"))

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
        # districts.<name>.boundary is already project-root-relative
        # (e.g. "digital_twin/metadata/boundaries/mandi_district.geojson").
        # Try it as-is first (relative to CWD, which should be the project
        # root when you run `python -m collectors.modis_collector`), then
        # fall back to resolving relative to paths.root.digital_twin in case
        # the script is ever launched from a different working directory.
        digital_twin_root = Path(raw.get("paths", {}).get("root", {}).get("digital_twin", "digital_twin"))
        candidates = [Path(boundary_rel)]
        # boundary_rel typically starts with "digital_twin/..." already; if
        # someone points digital_twin_root somewhere else, this second
        # candidate covers that case without double-prefixing.
        if not str(boundary_rel).replace("\\", "/").startswith(str(digital_twin_root).replace("\\", "/") + "/"):
            candidates.append(digital_twin_root.parent / boundary_rel)
        district_boundaries[district] = candidates

    # -- Product / layer list ----------------------------------------------#
    products = _derive_product_layers(modis_meta)
    if not products:
        raise ValueError(
            "Could not derive any MODIS product/layer combinations -- check "
            "digital_twin_sources.modis.variables (or .layers) in config.yaml"
        )

    # -- AppEEARS tuning ------------------------------------------------------#
    appeears_raw = modis_meta.get("appeears", {})
    appeears = AppeearsConfig(
        base_url=appeears_raw.get("base_url", AppeearsConfig.base_url),
        poll_interval_seconds=int(appeears_raw.get("poll_interval_seconds", 30)),
        task_timeout_hours=int(appeears_raw.get("task_timeout_hours", 12)),
        request_timeout_seconds=int(appeears_raw.get("request_timeout_seconds", raw.get("http", {}).get("timeout_seconds", 60))),
    )

    # -- Retry behaviour -------------------------------------------------------#
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
        logs_root=logs_root,
        appeears=appeears,
        retry=retry,
    )


def _derive_product_layers(modis_meta: Dict[str, Any]) -> List[ProductLayer]:
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
            continue
        layers.append(
            ProductLayer(product=product_id, layer=layer_name, category=category_map.get(var_key, "MODIS"))
        )
    return layers


def build_logger(name: str, log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"{LOGGER_NAME}.{name}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        return logger

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


def retry_call(
    func,
    *,
    retry_cfg: RetryConfig,
    logger: logging.Logger,
    description: str,
    retriable_exceptions: Tuple[type, ...] = (requests.RequestException,),
):
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


def _iter_coordinates(coords: Any) -> Iterable[Tuple[float, float]]:
    if not coords:
        return
    if isinstance(coords[0], (int, float)):
        yield float(coords[0]), float(coords[1])
    else:
        for sub in coords:
            yield from _iter_coordinates(sub)


def load_district_geojson(
    candidates: List[Path], district: str, logger: Optional[logging.Logger] = None
) -> Dict[str, Any]:
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
    gtype = geojson_obj.get("type")
    if gtype == "FeatureCollection":
        return geojson_obj
    if gtype == "Feature":
        return {"type": "FeatureCollection", "features": [geojson_obj]}
    return {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": geojson_obj}],
    }


class AppeearsClient:
    def __init__(self, config: CollectorConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.session = requests.Session()
        self._token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    def login(self) -> None:
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

    def submit_area_task(
        self,
        task_name: str,
        geojson_feature_collection: Dict[str, Any],
        layers: List[ProductLayer],
    ) -> str:
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

    def get_task_status(self, task_id: str) -> str:
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

    def list_bundle_files(self, task_id: str) -> List[Dict[str, Any]]:
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
        self._ensure_authenticated()
        file_id = file_entry["file_id"]
        file_name = file_entry["file_name"]
        expected_size = file_entry.get("file_size")
        s3_url = file_entry.get("s3_url")
        # AppEEARS sometimes returns this as a raw "s3://bucket/key" URI
        # rather than a presigned https:// URL. `requests` has no adapter
        # for the s3:// scheme (that needs boto3), so only trust it when
        # it's actually fetchable over plain HTTP(S) -- otherwise fall back
        # to the authenticated bundle endpoint below.
        if s3_url and not s3_url.lower().startswith(("http://", "https://")):
            self.logger.debug(
                "Ignoring non-HTTP s3_url for %s (%s); using authenticated endpoint instead",
                file_name, s3_url,
            )
            s3_url = None

        dest_path = dest_dir / Path(file_name).name
        partial_path = dest_path.with_suffix(dest_path.suffix + ".part")

        if dest_path.exists() and (expected_size is None or dest_path.stat().st_size == expected_size):
            self.logger.info("Skipping already-downloaded file: %s", dest_path.name)
            return dest_path

        resume_from = partial_path.stat().st_size if partial_path.exists() else 0

        def _do_download() -> None:
            nonlocal resume_from
            # Prefer the presigned S3 URL when AppEEARS provides one directly
            # in the bundle listing: it's a plain unauthenticated GET, fewer
            # hops, and immune to the Earthdata bearer token expiring
            # mid-download on long multi-file runs.
            if s3_url:
                url = s3_url
                headers: Dict[str, str] = {}
            else:
                url = f"{self.config.appeears.base_url}/bundle/{task_id}/{file_id}"
                headers = self._auth_header()

            mode = "wb"
            if resume_from > 0:
                headers["Range"] = f"bytes={resume_from}-"
                mode = "ab"

            with self.session.get(
                url, headers=headers, stream=True, timeout=self.config.appeears.request_timeout_seconds
            ) as resp:
                if resp.status_code == 416:
                    return
                if resume_from > 0 and resp.status_code != 206:
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


_MAGIC_BYTES = {
    b"\x49\x49\x2a\x00": "tiff_le",
    b"\x4d\x4d\x00\x2a": "tiff_be",
    b"PK\x03\x04": "zip",
    b"\x89HDF": "hdf5",
}


def validate_file(path: Path, expected_size: Optional[int], logger: logging.Logger) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        logger.error("Validation failed: %s is missing or empty", path)
        return False

    if expected_size is not None and path.stat().st_size != expected_size:
        logger.error(
            "Validation failed: %s size mismatch (got %d, expected %d)",
            path, path.stat().st_size, expected_size,
        )
        return False

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
    sha256 = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(DOWNLOAD_CHUNK_BYTES), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


class MetadataStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        return {"entries": {}}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2, sort_keys=True)

    def key(self, district: str, product: str, layer: str) -> str:
        return f"{district}:{product}:{layer}"

    def is_complete(self, district: str, product: str, layer: str) -> bool:
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
        self.data["entries"][self.key(district, product, layer)] = {
            "district": district,
            "product": product,
            "layer": layer,
            "task_id": task_id,
            "bbox": {"min_lon": bbox[0], "min_lat": bbox[1], "max_lon": bbox[2], "max_lat": bbox[3]},
            "files": files,
            "status": status,
            "start_date": None,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }


def ensure_output_dirs(root: Path) -> Dict[str, Path]:
    subdirs = {name: root / name for name in ("raw", "cleaned", "logs")}
    root.mkdir(parents=True, exist_ok=True)
    for p in subdirs.values():
        p.mkdir(parents=True, exist_ok=True)
    return subdirs


def clean_file(raw_path: Path, cleaned_dir: Path, logger: logging.Logger) -> Path:
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
            "[DRY RUN] Would submit AppEEARS task '%s' for layers=%s over bbox=%s output_dir=%s",
            task_name, [(pl.product, pl.layer) for pl in pending_layers], bbox, output_root,
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
        matching_files = [f for f in downloaded]
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
    grouped: Dict[str, List[ProductLayer]] = {}
    for pl in products:
        grouped.setdefault(pl.category.upper(), []).append(pl)
    return grouped


def run(config: CollectorConfig, districts: Optional[List[str]] = None, dry_run: bool = False) -> None:
    target_districts = districts or config.districts
    grouped = group_layers_by_category(config.products)

    # Was hardcoded to a literal "datasets/digital_twin/vegetation/logs"
    # string before -- now derived from config.yaml's paths.root.logs, so it
    # actually lands next to your other collectors' logs regardless of CWD.
    top_logger = build_logger("orchestrator", config.logs_root / "vegetation")
    top_logger.info(
        "Starting MODIS collection run: districts=%s, categories=%s, dry_run=%s",
        target_districts, list(grouped.keys()), dry_run,
    )
    top_logger.info("MODIS output dirs -> MODIS: %s | NDVI: %s", config.modis_dir, config.ndvi_dir)

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


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
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