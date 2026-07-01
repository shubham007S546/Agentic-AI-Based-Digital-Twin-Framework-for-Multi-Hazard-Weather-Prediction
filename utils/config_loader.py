"""
utils/config_loader.py
──────────────────────
Loads and validates config/config.yaml.
Every collector imports get_config() from here — never reads YAML directly.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


# Project root = parent of the utils/ directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH  = PROJECT_ROOT / "config" / "config.yaml"


class ConfigError(Exception):
    """Raised when config is missing required keys or has invalid values."""


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    """
    Load, validate, and return the master config as a plain dict.
    Result is cached — file is read only once per process.
    """
    if not CONFIG_PATH.exists():
        raise ConfigError(f"Config file not found: {CONFIG_PATH}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    if not cfg:
        raise ConfigError("Config file is empty.")

    _validate(cfg)
    return cfg


def get_project_root() -> Path:
    return PROJECT_ROOT


def get_source_dir(source_key: str) -> Path:
    """
    Return the absolute Path to a source's dataset directory.
    source_key: one of imd | nasa_gpm | datagov | wris | openmeteo
    """
    cfg = get_config()
    rel_path = cfg["sources"][source_key]["download_dir"]
    return PROJECT_ROOT / rel_path


def get_date_range() -> tuple[date, date]:
    """Return (start_date, end_date) as datetime.date objects."""
    cfg = get_config()
    start = datetime.strptime(cfg["dates"]["start_date"], "%Y-%m-%d").date()
    end   = datetime.strptime(cfg["dates"]["end_date"],   "%Y-%m-%d").date()
    return start, end


# ── private ────────────────────────────────────────────────────

def _validate(cfg: dict) -> None:
    required_top = ["location", "dates", "api_keys", "http", "sources", "logging"]
    for key in required_top:
        if key not in cfg:
            raise ConfigError(f"Missing required top-level key in config: '{key}'")

    # Validate dates
    try:
        start = datetime.strptime(cfg["dates"]["start_date"], "%Y-%m-%d").date()
        end   = datetime.strptime(cfg["dates"]["end_date"],   "%Y-%m-%d").date()
    except (KeyError, ValueError) as exc:
        raise ConfigError(f"Invalid dates in config: {exc}") from exc

    if start >= end:
        raise ConfigError(f"start_date ({start}) must be before end_date ({end}).")

    # Validate location
    for field in ["state", "district", "latitude", "longitude"]:
        if field not in cfg.get("location", {}):
            raise ConfigError(f"Missing location.{field} in config.")

    # Validate HTTP settings
    http = cfg.get("http", {})
    for field in ["timeout_seconds", "max_retries", "backoff_factor"]:
        if field not in http:
            raise ConfigError(f"Missing http.{field} in config.")
