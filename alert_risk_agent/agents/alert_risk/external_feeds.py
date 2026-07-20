"""
External feeds, matching the diagram's "External Feeds" box (CWC Alerts,
GSI Landslide, ReliefWeb, News/Social).

ReliefWeb is wired for real -- it's a public API (config.yaml confirms your
v2 migration notes: POST + JSON filter body, appname required but not a
secret). CWC/GSI/News don't have a confirmed public API in your project
(your own river_discharge_collector config notes CWC has no bulk
CSV/API access, only a live dashboard), so those are honestly stubbed.
"""

from __future__ import annotations

from typing import Any, Dict, List

import httpx

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)

_DISASTER_TYPES = [
    "Flood", "Flash Flood", "Landslide", "Cloudburst", "Heavy Rainfall",
    "Storm", "Lightning", "Avalanche", "Earthquake", "Drought",
]


def fetch_reliefweb_reports(limit: int = 10) -> Dict[str, Any]:
    """Real integration: POST to ReliefWeb v2 API for recent disaster
    reports affecting India, filtered to disaster types relevant here."""
    payload = {
        "filter": {
            "operator": "AND",
            "conditions": [
                {"field": "country.iso3", "value": settings.reliefweb_country_iso3},
                {"field": "disaster_type.name", "value": _DISASTER_TYPES, "operator": "OR"},
            ],
        },
        "limit": limit,
        "sort": ["date.created:desc"],
        "fields": {"include": ["title", "date.created", "country.name", "disaster_type.name", "url"]},
    }
    try:
        with httpx.Client(timeout=settings.agent_request_timeout_seconds) as client:
            resp = client.post(
                settings.reliefweb_base_url,
                params={"appname": settings.reliefweb_appname},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        reports = [
            {
                "title": item.get("fields", {}).get("title"),
                "date": item.get("fields", {}).get("date", {}).get("created"),
                "disaster_types": [d.get("name") for d in item.get("fields", {}).get("disaster_type", [])],
                "url": item.get("fields", {}).get("url"),
            }
            for item in data.get("data", [])
        ]
        return {"status": "ok", "source": "reliefweb", "reports": reports}
    except Exception as exc:
        logger.warning("ReliefWeb fetch failed: %s", exc)
        return {"status": "error", "source": "reliefweb", "note": str(exc), "reports": []}


def fetch_cwc_alerts(district: str) -> Dict[str, Any]:
    """Stub. CWC's flood forecast system (ffs.india-water.gov.in) has no
    confirmed public bulk API -- your own river_discharge_collector config
    notes this. Would need a scraper/FFS API client (flagged as future work
    there too)."""
    logger.info("fetch_cwc_alerts called for district=%s (STUB)", district)
    return {"status": "stub", "source": "cwc", "note": "No confirmed public CWC alerts API.", "alerts": []}


def fetch_gsi_landslide(district: str) -> Dict[str, Any]:
    """Stub. Geological Survey of India landslide susceptibility data isn't
    wired into this project's collectors yet."""
    logger.info("fetch_gsi_landslide called for district=%s (STUB)", district)
    return {"status": "stub", "source": "gsi", "note": "GSI landslide feed not yet integrated.", "alerts": []}


def fetch_news_social(district: str) -> Dict[str, Any]:
    """Stub. Would need a news/social API key (e.g. NewsAPI, Twitter/X API)."""
    logger.info("fetch_news_social called for district=%s (STUB)", district)
    return {"status": "stub", "source": "news_social", "note": "No news/social API configured.", "items": []}


def fetch_all_external_feeds(district: str) -> Dict[str, Any]:
    return {
        "reliefweb": fetch_reliefweb_reports(),
        "cwc": fetch_cwc_alerts(district),
        "gsi": fetch_gsi_landslide(district),
        "news_social": fetch_news_social(district),
    }
