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
        headers = {
            "User-Agent": "himachal-climate-digital-twin/2.1",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=settings.agent_request_timeout_seconds) as client:
            resp = client.post(
                settings.reliefweb_base_url,
                params={"appname": settings.reliefweb_appname},
                json=payload,
                headers=headers,
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
    """Queries Tavily or SerpAPI for recent landslide and geological hazard reports for the district."""
    if settings.has_tavily:
        try:
            with httpx.Client(timeout=settings.agent_request_timeout_seconds) as client:
                resp = client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": settings.tavily_api_key,
                        "query": f"{district} Himachal Pradesh landslide risk slope failure advisory",
                        "search_depth": "basic",
                        "max_results": 4,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    alerts = [
                        {
                            "title": item.get("title"),
                            "snippet": item.get("content"),
                            "url": item.get("url"),
                            "source": "tavily_landslide",
                        }
                        for item in data.get("results", [])
                    ]
                    logger.info("Retrieved %d real landslide reports via Tavily for %s", len(alerts), district)
                    return {"status": "ok", "source": "tavily_gsi_surrogate", "alerts": alerts}
        except Exception as exc:
            logger.warning("Tavily landslide query failed for %s: %s", district, exc)

    logger.info("fetch_gsi_landslide using fallback for district=%s", district)
    return {"status": "stub", "source": "gsi", "note": "GSI direct API unavailable; Tavily fallback exhausted.", "alerts": []}


def fetch_news_social(district: str) -> Dict[str, Any]:
    """Fetches real-time disaster, weather warnings, and road blockage reports via Tavily or SerpAPI."""
    # 1. Primary: Tavily Ground Truth Search
    if settings.has_tavily:
        try:
            with httpx.Client(timeout=settings.agent_request_timeout_seconds) as client:
                resp = client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": settings.tavily_api_key,
                        "query": f"{district} Himachal Pradesh weather alert cloudburst landslide road block news",
                        "search_depth": "basic",
                        "max_results": 5,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    items = [
                        {
                            "title": item.get("title"),
                            "content": item.get("content"),
                            "url": item.get("url"),
                            "score": item.get("score"),
                            "source": "tavily_news",
                        }
                        for item in data.get("results", [])
                    ]
                    logger.info("Retrieved %d live news items via Tavily for %s", len(items), district)
                    return {"status": "ok", "source": "tavily", "items": items}
        except Exception as exc:
            logger.warning("Tavily news query failed for %s: %s", district, exc)

    # 2. Secondary: SerpAPI Google News
    if settings.has_serpapi:
        try:
            with httpx.Client(timeout=settings.agent_request_timeout_seconds) as client:
                resp = client.get(
                    "https://serpapi.com/search.json",
                    params={
                        "api_key": settings.serpapi_api_key,
                        "q": f"{district} Himachal weather alert warning",
                        "engine": "google",
                        "num": 5,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    items = [
                        {
                            "title": res.get("title"),
                            "snippet": res.get("snippet"),
                            "link": res.get("link"),
                            "source": "serpapi_news",
                        }
                        for res in data.get("organic_results", [])[:5]
                    ]
                    logger.info("Retrieved %d live news items via SerpAPI for %s", len(items), district)
                    return {"status": "ok", "source": "serpapi", "items": items}
        except Exception as exc:
            logger.warning("SerpAPI news query failed for %s: %s", district, exc)

    return {"status": "stub", "source": "news_social", "note": "No news search provider responded.", "items": []}


def fetch_all_external_feeds(district: str) -> Dict[str, Any]:
    return {
        "reliefweb": fetch_reliefweb_reports(),
        "cwc": fetch_cwc_alerts(district),
        "gsi": fetch_gsi_landslide(district),
        "news_social": fetch_news_social(district),
    }
