"""Model artifact (de)serialization, using joblib for estimator objects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import joblib

from .exceptions import SerializationError


def save_artifact(obj: Any, path: str, metadata: Optional[dict] = None) -> None:
    """
    Save a fitted estimator (or any picklable object) to `path` via joblib.
    If `metadata` is given, it is written alongside as `<path>.meta.json`.
    """
    try:
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(obj, out_path)
        if metadata is not None:
            meta_path = out_path.with_suffix(out_path.suffix + ".meta.json")
            with open(meta_path, "w") as f:
                json.dump(metadata, f, indent=2, default=str)
    except Exception as exc:
        raise SerializationError(f"Failed to save artifact to {path}: {exc}") from exc


def load_artifact(path: str) -> Any:
    """Load a joblib-serialized object from `path`."""
    p = Path(path)
    if not p.exists():
        raise SerializationError(f"Artifact not found: {path}")
    try:
        return joblib.load(p)
    except Exception as exc:
        raise SerializationError(f"Failed to load artifact from {path}: {exc}") from exc


def load_metadata(path: str) -> Optional[dict]:
    """Load the metadata JSON that accompanies a saved artifact, if present."""
    p = Path(path)
    meta_path = p.with_suffix(p.suffix + ".meta.json")
    if not meta_path.exists():
        return None
    with open(meta_path, "r") as f:
        return json.load(f)
