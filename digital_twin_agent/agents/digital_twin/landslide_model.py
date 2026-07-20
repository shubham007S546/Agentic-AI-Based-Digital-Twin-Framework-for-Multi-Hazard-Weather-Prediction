"""
Landslide Model, matching the diagram's "Landslide Model (Slope
Stability<->Failure Probability)" box.

Uses **Caine's (1980) global rainfall intensity-duration threshold**:
    I = 14.82 * D^-0.39   (I in mm/hr, D in hours)
one of the most widely-cited landslide-triggering rainfall thresholds in
the literature. It's a *global* threshold, not calibrated specifically for
the Himalaya -- regional studies (e.g. for the Himalayan arc) generally
find LOWER, more conservative thresholds than Caine's global curve, so
treat "not exceeded" here as "not exceeded relative to a global average,"
not "safe." Replace `caine_coefficient`/`caine_exponent` in config.py with
a regionally-calibrated threshold if/when you have one.
"""

from __future__ import annotations

from typing import Any, Dict

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)

_SLOPE_MULTIPLIER = {"gentle": 0.7, "moderate": 1.0, "steep": 1.2}


def run_landslide_model(rainfall_mm: float, duration_hours: float, slope_class: str = None) -> Dict[str, Any]:
    slope_class = slope_class or settings.default_slope_class
    slope_multiplier = _SLOPE_MULTIPLIER.get(slope_class, 1.0)

    intensity_mm_hr = rainfall_mm / max(duration_hours, 0.1)
    threshold_mm_hr = settings.caine_coefficient * (duration_hours ** settings.caine_exponent)

    raw_ratio = (intensity_mm_hr / threshold_mm_hr) * slope_multiplier
    susceptibility_score = round(min(raw_ratio / 1.5, 1.0), 3)  # saturates at 1.0 when 50% over threshold
    exceeded = intensity_mm_hr * slope_multiplier > threshold_mm_hr

    assumptions = [
        f"Caine (1980) global threshold: I=14.82*D^-0.39 -- NOT regionally calibrated for Himachal Pradesh",
        f"slope_class={slope_class} (default assumption unless a real DEM-derived slope class is supplied)",
        "Regional Himalayan studies generally find lower/more conservative thresholds than the global curve.",
    ]

    result = {
        "method": "Caine (1980) rainfall intensity-duration threshold",
        "rainfall_intensity_mm_hr": round(intensity_mm_hr, 2),
        "threshold_intensity_mm_hr": round(threshold_mm_hr, 2),
        "threshold_exceeded": exceeded,
        "susceptibility_score": susceptibility_score,
        "slope_class": slope_class,
        "assumptions": assumptions,
    }
    logger.info("Landslide model: intensity=%.2fmm/hr threshold=%.2fmm/hr exceeded=%s score=%.3f",
                intensity_mm_hr, threshold_mm_hr, exceeded, susceptibility_score)
    return result
