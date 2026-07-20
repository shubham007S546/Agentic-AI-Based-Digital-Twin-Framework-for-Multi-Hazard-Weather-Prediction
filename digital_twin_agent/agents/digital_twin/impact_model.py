"""
Impact Assessment, matching the diagram's "Analyze Results" step (affected
area, bridges/roads at risk, population at risk).

Bridges/roads counts are REAL when the corresponding GeoJSON layer was
found on disk by twin_state.py (a genuine feature count from your actual
infrastructure_collector.py output) -- scaled by how severe the flood/
landslide exceedance is, since we don't have real flood-extent polygon
intersection (that needs the DEM-based 2D hydraulic model this project
doesn't have yet). Population is always stubbed -- your census data isn't
in a queryable/spatial form yet (see Agent 4's impact.py for the same
caveat).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .logging_config import get_logger

logger = get_logger(__name__)


def assess_impact(
    bridges: Optional[List[dict]],
    roads: Optional[List[dict]],
    severity_fraction: float,  # 0-1, e.g. flood excess_ratio capped at 1, or landslide susceptibility_score
) -> Dict[str, Any]:
    if bridges is None and roads is None:
        return {
            "status": "stub",
            "bridges_at_risk": None,
            "roads_at_risk": None,
            "population_at_risk": None,
            "note": "No infrastructure layers found on disk for this district -- see twin_state.py's "
                    "expected path. Population is always stubbed (census data isn't in queryable/spatial form yet).",
        }

    bridges_at_risk = round(len(bridges) * severity_fraction) if bridges is not None else None
    roads_at_risk = round(len(roads) * severity_fraction) if roads is not None else None

    logger.info("Impact assessment: bridges_at_risk=%s roads_at_risk=%s (severity_fraction=%.2f)",
                bridges_at_risk, roads_at_risk, severity_fraction)

    return {
        "status": "ok" if (bridges is not None or roads is not None) else "stub",
        "bridges_at_risk": bridges_at_risk,
        "roads_at_risk": roads_at_risk,
        "population_at_risk": None,
        "note": "bridges/roads counts are real feature counts scaled by simulated severity, not a real "
                "spatial intersection with a flood-extent polygon. population_at_risk always stubbed "
                "(no queryable census data source yet).",
    }
