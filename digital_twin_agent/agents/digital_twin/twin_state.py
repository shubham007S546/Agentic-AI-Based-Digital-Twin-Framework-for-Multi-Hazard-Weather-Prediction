"""
Twin State Manager, matching the diagram's "Load Twin State" step and
"Twin State Manager" component. Tries to load REAL layers from your
project's actual digital_twin/ folder structure (per your config.yaml's
`paths.*` block); falls back to documented defaults and reports honestly
via TwinLayerStatus when a layer isn't found on disk.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)


def _boundaries_dir() -> str:
    return settings.boundaries_dir or os.path.join(settings.digital_twin_dir, "metadata", "boundaries")


def _infrastructure_dir() -> str:
    return settings.infrastructure_dir or os.path.join(settings.digital_twin_dir, "infrastructure")


def load_boundary(district: str) -> Tuple[Optional[float], Dict[str, Any]]:
    """Returns (area_km2 or None, layer_status_dict). Real if the district's
    boundary GeoJSON exists on disk; otherwise honestly reports unavailable."""
    path = os.path.join(_boundaries_dir(), f"{district.lower()}_district.geojson")
    if not os.path.exists(path):
        return None, {"layer": "terrain_boundary", "status": "unavailable",
                       "detail": f"No boundary file at {path}"}
    try:
        from shapely.geometry import shape
        from shapely.ops import unary_union

        with open(path) as f:
            geojson = json.load(f)

        geoms = [shape(feat["geometry"]) for feat in geojson.get("features", [geojson])] \
            if "features" in geojson else [shape(geojson["geometry"])]
        merged = unary_union(geoms)

        # crude degrees->km2 conversion (WGS84, mid-latitude ~31°N): good
        # enough for a rough affected-area estimate, not survey-grade area.
        deg_to_km = 111.0
        area_km2 = merged.area * (deg_to_km ** 2)

        return area_km2, {"layer": "terrain_boundary", "status": "loaded", "source": path,
                           "detail": f"Approx. area {area_km2:.1f} km2 (WGS84 degree->km2 approximation)"}
    except Exception as exc:
        logger.warning("Failed to load boundary for %s: %s", district, exc)
        return None, {"layer": "terrain_boundary", "status": "unavailable", "detail": str(exc)}


def load_infrastructure_layer(district: str, layer_name: str) -> Tuple[Optional[list], Dict[str, Any]]:
    """Looks for digital_twin/infrastructure/<Layer>/<district>*.geojson.
    Returns (list of features or None, layer_status_dict)."""
    layer_dir = os.path.join(_infrastructure_dir(), layer_name)
    if not os.path.isdir(layer_dir):
        return None, {"layer": layer_name.lower(), "status": "unavailable",
                       "detail": f"No directory at {layer_dir}"}

    candidates = [f for f in os.listdir(layer_dir)
                  if district.lower() in f.lower() and f.endswith(".geojson")]
    if not candidates:
        return None, {"layer": layer_name.lower(), "status": "unavailable",
                       "detail": f"No {district} file found in {layer_dir}"}

    path = os.path.join(layer_dir, candidates[0])
    try:
        with open(path) as f:
            geojson = json.load(f)
        features = geojson.get("features", [])
        return features, {"layer": layer_name.lower(), "status": "loaded", "source": path,
                           "detail": f"{len(features)} features"}
    except Exception as exc:
        logger.warning("Failed to load %s layer for %s: %s", layer_name, district, exc)
        return None, {"layer": layer_name.lower(), "status": "unavailable", "detail": str(exc)}


def load_twin_state(district: str) -> Dict[str, Any]:
    layers: List[Dict[str, Any]] = []

    area_km2, boundary_status = load_boundary(district)
    layers.append(boundary_status)

    bridges, bridges_status = load_infrastructure_layer(district, "Bridges")
    layers.append(bridges_status)

    roads, roads_status = load_infrastructure_layer(district, "Roads")
    layers.append(roads_status)

    logger.info("Twin state for %s: %s", district,
                {l["layer"]: l["status"] for l in layers})

    return {
        "layers": layers,
        "boundary_area_km2": area_km2,
        "bridges": bridges,
        "roads": roads,
    }
