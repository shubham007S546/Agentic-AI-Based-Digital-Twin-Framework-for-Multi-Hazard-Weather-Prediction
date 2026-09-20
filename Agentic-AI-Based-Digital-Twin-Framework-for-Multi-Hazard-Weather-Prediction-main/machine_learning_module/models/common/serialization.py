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
        import sys, os
        resolved = Path(path).resolve()
        p_str = str(resolved)
        parent_str = str(resolved.parent)
        if sys.platform == "win32" and not p_str.startswith("\\\\?\\"):
            os.makedirs(f"\\\\?\\{parent_str}", exist_ok=True)
            target_path = f"\\\\?\\{p_str}"
        else:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            target_path = p_str

        joblib.dump(obj, target_path)
        if metadata is not None:
            meta_path = target_path + ".meta.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, default=str)
    except Exception as exc:
        raise SerializationError(f"Failed to save artifact to {path}: {exc}") from exc


def load_artifact(path: str) -> Any:
    """Load a joblib-serialized object from `path`."""
    import sys, os
    resolved = Path(path).resolve()
    p_str = str(resolved)
    target_path = f"\\\\?\\{p_str}" if (sys.platform == "win32" and not p_str.startswith("\\\\?\\")) else p_str
    if not os.path.exists(target_path):
        raise SerializationError(f"Artifact not found: {path}")
    try:
        return joblib.load(target_path)
    except Exception as exc:
        raise SerializationError(f"Failed to load artifact from {path}: {exc}") from exc


def load_metadata(path: str) -> Optional[dict]:
    """Load the metadata JSON that accompanies a saved artifact, if present."""
    import sys, os
    resolved = Path(path).resolve()
    p_str = str(resolved)
    meta_str = (f"\\\\?\\{p_str}" if (sys.platform == "win32" and not p_str.startswith("\\\\?\\")) else p_str) + ".meta.json"
    if not os.path.exists(meta_str):
        return None
    with open(meta_str, "r", encoding="utf-8") as f:
        return json.load(f)
