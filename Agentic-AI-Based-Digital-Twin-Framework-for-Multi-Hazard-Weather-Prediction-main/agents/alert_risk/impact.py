"""
Impact Analyzer, matching the diagram's "Evaluate Impact" step and "Impact
Model (Exposure & Vulnerability)" box. Stubbed -- population density,
infrastructure exposure (roads/bridges/hospitals/schools), and vulnerable-
group data aren't wired into a live queryable source in this project yet
(your census_collector.py downloads static PDFs/CSVs per district, not a
queryable API; infrastructure_collector.py pulls OpenStreetMap layers to
files, same situation).

TODO once you have these as structured, queryable data (e.g. loaded into
PostgreSQL/PostGIS): replace `assess_impact` with a real spatial query --
population within N km of the predicted-impact area, critical
infrastructure (hospitals, bridges, schools) within that radius, etc.
"""

from __future__ import annotations

from typing import Any, Dict

from .logging_config import get_logger

logger = get_logger(__name__)


def assess_impact(location: str, district: str, severity: str) -> Dict[str, Any]:
    logger.info("assess_impact called for location=%s severity=%s (STUB)", location, severity)
    return {
        "status": "stub",
        "affected_population_estimate": None,
        "critical_infrastructure_at_risk": [],
        "note": (
            "Population/infrastructure exposure data not yet wired to a queryable source "
            "(census_collector.py / infrastructure_collector.py currently produce static "
            "files, not a live spatial-query API). Wire this to PostGIS once that data is "
            "loaded, keyed by district/severity/predicted-impact radius."
        ),
    }
