"""
utils/metadata_writer.py
────────────────────────
Generates and saves a metadata.json file for each data source.
Called by every collector after cleaning is complete.

Schema
------
{
  "source_name": str,
  "api_url": str,
  "download_date": str (ISO 8601),
  "download_timestamp": str,
  "config_location": { state, district, lat, lon },
  "config_date_range": { start_date, end_date },
  "num_records": int,
  "columns": [ { name, dtype, non_null_count, null_count, null_pct } ],
  "missing_values": { col: count },
  "data_types": { col: dtype_str },
  "update_frequency": str,
  "file_paths": { raw: str, cleaned: str },
  "collector_version": str
}
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from utils.config_loader import get_config


COLLECTOR_VERSION = "1.0.0"


def write_metadata(
    *,
    source_dir: Path,
    source_name: str,
    api_url: str,
    update_frequency: str,
    df_cleaned: pd.DataFrame,
    raw_file_path: Path,
    cleaned_file_path: Path,
    extra: dict[str, Any] | None = None,
) -> Path:
    """
    Build and save metadata.json for a data source.

    Parameters
    ----------
    source_dir        : Path  — root of this source (e.g. datasets/source_1_imd)
    source_name       : str   — human-readable source name
    api_url           : str   — primary endpoint or portal URL
    update_frequency  : str   — e.g. "Daily", "Monthly"
    df_cleaned        : pd.DataFrame — the cleaned dataframe
    raw_file_path     : Path  — where raw file was saved
    cleaned_file_path : Path  — where cleaned file was saved
    extra             : dict  — any source-specific extra fields

    Returns
    -------
    Path to the written metadata.json
    """
    cfg      = get_config()
    location = cfg["location"]
    dates    = cfg["dates"]
    now      = datetime.utcnow()

    # ── Column-level statistics ───────────────────────────────
    columns_info = []
    missing_values: dict[str, int] = {}
    data_types: dict[str, str]     = {}

    for col in df_cleaned.columns:
        series        = df_cleaned[col]
        null_count    = int(series.isna().sum())
        non_null      = int(series.notna().sum())
        total         = len(series)
        null_pct      = round((null_count / total * 100) if total > 0 else 0.0, 2)
        dtype_str     = str(series.dtype)

        columns_info.append({
            "name":           col,
            "dtype":          dtype_str,
            "non_null_count": non_null,
            "null_count":     null_count,
            "null_pct":       null_pct,
        })
        missing_values[col] = null_count
        data_types[col]     = dtype_str

    # ── Assemble metadata dict ────────────────────────────────
    metadata: dict[str, Any] = {
        "source_name":        source_name,
        "api_url":            api_url,
        "download_date":      now.strftime("%Y-%m-%d"),
        "download_timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "collector_version":  COLLECTOR_VERSION,
        "config_location": {
            "state":     location["state"],
            "district":  location["district"],
            "latitude":  location["latitude"],
            "longitude": location["longitude"],
        },
        "config_date_range": {
            "start_date": dates["start_date"],
            "end_date":   dates["end_date"],
        },
        "num_records":     len(df_cleaned),
        "num_columns":     len(df_cleaned.columns),
        "columns":         columns_info,
        "missing_values":  missing_values,
        "data_types":      data_types,
        "update_frequency": update_frequency,
        "file_paths": {
            "raw":     str(raw_file_path.resolve()),
            "cleaned": str(cleaned_file_path.resolve()),
        },
    }

    if extra:
        metadata["extra"] = extra

    # ── Write JSON ────────────────────────────────────────────
    out_path = source_dir / "metadata.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2, ensure_ascii=False, default=str)

    return out_path
