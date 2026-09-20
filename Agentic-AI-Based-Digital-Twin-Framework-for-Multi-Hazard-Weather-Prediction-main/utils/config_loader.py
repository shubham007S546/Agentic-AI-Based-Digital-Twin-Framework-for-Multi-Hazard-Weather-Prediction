"""
utils/config_loader.py
──────────────────────
Unified configuration and source path loader.
Reads config/config.yaml and config/data_sources.yaml.
Provides robust project-relative path resolution using pathlib.Path.
Never crashes on missing legacy keys; guarantees directory existence.
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

# Project root = parent of the utils/ directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
DATA_SOURCES_PATH = PROJECT_ROOT / "config" / "data_sources.yaml"


class ConfigError(Exception):
    """Raised when config is missing critical required settings."""


@lru_cache(maxsize=1)
def get_config() -> Dict[str, Any]:
    """
    Load, validate, and return master config as a dict. Cached per process.
    """
    if not CONFIG_PATH.exists():
        raise ConfigError(f"Master config file not found at: {CONFIG_PATH}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    if not cfg:
        raise ConfigError(f"Config file is empty: {CONFIG_PATH}")

    _validate(cfg)
    return cfg


@lru_cache(maxsize=1)
def get_data_sources_registry() -> Dict[str, Any]:
    """
    Load data sources registry defining all 13 environmental providers.
    """
    if not DATA_SOURCES_PATH.exists():
        return {}
    with open(DATA_SOURCES_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def get_project_root() -> Path:
    """Return project root directory as a pathlib.Path."""
    return PROJECT_ROOT


def to_long_path(p: Any) -> str:
    """
    Convert a path to Windows extended-length path format (\\\\?\\C:\\...)
    if running on Windows, safely bypassing the MAX_PATH (260 char) limit.
    """
    s = os.path.abspath(str(p))
    if sys.platform == "win32" and not s.startswith("\\\\?\\"):
        return f"\\\\?\\{s}"
    return s


def get_source_dir(source_key: str) -> Path:
    """
    Resolve base directory for a given environmental data source.
    Checks config paths.weather, paths.digital_twin, or sources blocks.
    Guarantees the directory exists.
    """
    cfg = get_config()

    # 1. Check sources block
    sources = cfg.get("sources", {})
    if source_key in sources:
        src = sources[source_key]
        if isinstance(src, dict) and "download_dir" in src:
            target = PROJECT_ROOT / src["download_dir"]
            target.mkdir(parents=True, exist_ok=True)
            return target

    # 2. Check paths.weather block
    weather_paths = cfg.get("paths", {}).get("weather", {})
    if source_key in weather_paths:
        target = PROJECT_ROOT / weather_paths[source_key]
        target.mkdir(parents=True, exist_ok=True)
        return target

    # 3. Check digital twin domain paths
    dt_paths = cfg.get("paths", {})
    if source_key in dt_paths:
        val = dt_paths[source_key]
        rel = val.get("root") if isinstance(val, dict) else val
        if rel:
            target = PROJECT_ROOT / rel
            target.mkdir(parents=True, exist_ok=True)
            return target

    # 4. Standard default fallback
    target = PROJECT_ROOT / "datasets" / f"source_{source_key}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_source_paths(source_key: str) -> Dict[str, Path]:
    """
    Returns standard subdirectories for a source:
      - base
      - raw
      - cleaned
      - metadata
      - logs
    Guarantees all directories exist on disk.
    """
    base = get_source_dir(source_key)
    raw = base / "raw"
    cleaned = base / "cleaned"
    metadata = base / "metadata"
    logs = base / "logs"

    for d in (base, raw, cleaned, metadata, logs):
        d.mkdir(parents=True, exist_ok=True)

    return {
        "base": base,
        "base_dir": base,
        "raw": raw,
        "raw_dir": raw,
        "cleaned": cleaned,
        "cleaned_dir": cleaned,
        "metadata": metadata,
        "metadata_dir": metadata,
        "logs": logs,
        "logs_dir": logs,
    }


def get_date_range() -> Tuple[date, date]:
    """Return (start_date, end_date) as datetime.date objects."""
    cfg = get_config()
    dates_cfg = cfg.get("dates", {})
    start_str = dates_cfg.get("start_date", "2005-01-01")
    end_str = dates_cfg.get("end_date", "2025-12-31")

    try:
        start = datetime.strptime(start_str, "%Y-%m-%d").date()
        end = datetime.strptime(end_str, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ConfigError(f"Invalid date format in config.yaml: {exc}")

    return start, end


def get_active_districts() -> List[str]:
    """Return list of active district keys (e.g. ['mandi', 'kullu', 'chamba'])."""
    cfg = get_config()
    return [d.lower() for d in cfg.get("active_districts", ["mandi", "kullu", "chamba"])]


def get_district_info(district_name: str) -> Dict[str, Any]:
    """
    Return coordinate bounds and metadata for a district.
    Handles case-insensitivity.
    """
    cfg = get_config()
    districts = cfg.get("districts", {})
    key = district_name.strip().lower()

    if key in districts:
        info = dict(districts[key])
        info["key"] = key
        return info

    # Fallback to defaults if unknown
    return {
        "key": key,
        "state": "Himachal Pradesh",
        "latitude": 31.7081,
        "longitude": 76.9318,
        "bbox": {"lat_min": 31.0, "lat_max": 33.0, "lon_min": 75.5, "lon_max": 78.0},
    }


# Alias for backward compatibility
get_district_coords = get_district_info


def _validate(cfg: Dict[str, Any]) -> None:
    """Validate core required sections in master configuration."""
    # Ensure dates are present and valid
    if "dates" in cfg:
        try:
            start = datetime.strptime(cfg["dates"]["start_date"], "%Y-%m-%d").date()
            end = datetime.strptime(cfg["dates"]["end_date"], "%Y-%m-%d").date()
            if start >= end:
                raise ConfigError(f"start_date ({start}) must precede end_date ({end})")
        except (KeyError, ValueError) as exc:
            raise ConfigError(f"Invalid date configuration: {exc}")
