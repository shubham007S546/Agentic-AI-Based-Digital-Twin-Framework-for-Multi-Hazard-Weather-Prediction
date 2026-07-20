"""
Flood/Hydrological Model, matching the diagram's "Hydrological Model
(Rainfall->Runoff)" and "Flood Inundation Model (Depth->Extent)" boxes.

Uses the **Rational Method** (Q = C * I * A / 360 in metric units: Q in
m3/s, C dimensionless runoff coefficient, I in mm/hr, A in km2) for peak
discharge -- a real, standard, widely-taught hydrology formula (see any
civil/hydrology engineering textbook, e.g. ASCE Manual 37), appropriate for
small-to-medium mountainous catchments like Mandi/Kullu/Chamba's.

The affected-area / max-water-depth estimate that follows is a
**simplified planning-level heuristic** based on how much peak discharge
exceeds assumed channel capacity -- NOT a substitute for real 2D hydraulic
modeling (HEC-RAS, LISFLOOD-FP, etc.), which needs real channel geometry
and a DEM to do properly. Treat these two numbers as illustrative severity
indicators, not survey-grade flood maps.
"""

from __future__ import annotations

from typing import Any, Dict

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)


def run_flood_model(
    rainfall_mm: float,
    duration_hours: float,
    catchment_area_km2: float,
    runoff_coefficient: float,
    channel_capacity_m3s: float,
    boundary_area_km2: float,
) -> Dict[str, Any]:
    assumptions = [
        f"Rational Method (Q=C*I*A/360): C={runoff_coefficient} (default, not calibrated for this catchment)",
        f"Catchment area={catchment_area_km2}km2 (default estimate unless overridden by a real DEM-derived value)",
        f"Assumed channel capacity={channel_capacity_m3s}m3/s (default, not from real channel geometry)",
        "Affected-area/water-depth are a simplified severity heuristic, NOT 2D hydraulic modeling output.",
    ]

    intensity_mm_hr = rainfall_mm / max(duration_hours, 0.1)
    peak_discharge = runoff_coefficient * intensity_mm_hr * catchment_area_km2 / 360.0
    exceeded = peak_discharge > channel_capacity_m3s

    if exceeded:
        excess_ratio = (peak_discharge - channel_capacity_m3s) / channel_capacity_m3s
    else:
        excess_ratio = 0.0

    # simplified severity heuristic -- see docstring
    affected_area = min(boundary_area_km2 * 0.08 * (1 + excess_ratio), boundary_area_km2) if exceeded else 0.0
    max_water_depth = round(min(0.3 + excess_ratio * 2.5, 6.0), 2) if exceeded else 0.0

    result = {
        "method": "Rational Method (simplified)",
        "peak_discharge_m3s": round(peak_discharge, 2),
        "channel_capacity_m3s": channel_capacity_m3s,
        "channel_capacity_exceeded": exceeded,
        "affected_area_sq_km": round(affected_area, 2),
        "max_water_depth_m": max_water_depth,
        "assumptions": assumptions,
    }
    logger.info("Flood model: intensity=%.1fmm/hr peak_Q=%.2fm3/s exceeded=%s",
                intensity_mm_hr, peak_discharge, exceeded)
    return result
