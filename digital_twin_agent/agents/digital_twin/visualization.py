"""
Visualize Outputs, matching the diagram's "Visualize & Map" step. This
produces a **simplified structured summary** (risk color, affected area,
key numbers) suitable for a frontend to render as a simple map overlay or
dashboard card -- NOT the full 3D/4D Cesium/Three.js visualization the
diagram's "Technologies Used" box describes (Cesium.js/Three.js, Xarray for
4D time-slider). That's real future frontend work once this agent has a
real DEM + flood-extent polygon to actually render.
"""

from __future__ import annotations

from typing import Any, Dict

_RISK_COLORS = {"Low": "#2ecc71", "Moderate": "#f1c40f", "High": "#e67e22", "Extreme": "#e74c3c"}


def build_visualization(district: str, risk_level: str, flood: Dict[str, Any], landslide: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "simplified_2d_summary",
        "note": "Structured summary only -- not a rendered 3D/4D map. Wire a real DEM + flood-extent "
                "polygon through Cesium.js/deck.gl on the frontend for the diagram's full visualization.",
        "district": district,
        "risk_level": risk_level,
        "color": _RISK_COLORS.get(risk_level, "#95a5a6"),
        "flood_summary": {
            "affected_area_sq_km": flood.get("affected_area_sq_km") if flood else None,
            "max_water_depth_m": flood.get("max_water_depth_m") if flood else None,
        } if flood else None,
        "landslide_summary": {
            "susceptibility_score": landslide.get("susceptibility_score") if landslide else None,
        } if landslide else None,
    }
