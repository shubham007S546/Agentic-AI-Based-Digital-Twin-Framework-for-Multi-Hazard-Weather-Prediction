"""
Real HTTP integration with Agents 2-5, matching the diagram's "Internal
APIs" box (predictions, alerts, weather history, digital-twin metrics,
infrastructure). Degrades gracefully (honestly reported, not fabricated)
if any agent isn't running -- a report built from partial data is still
useful, and `data_completeness` in the response tells you how partial.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)


def fetch_weather(district: str, forecast_hours: int = 24) -> Dict[str, Any]:
    url = f"{settings.weather_agent_url}/api/v1/weather/forecast"
    try:
        with httpx.Client(timeout=settings.agent_request_timeout_seconds) as client:
            resp = client.get(url, params={"location": district, "forecast_hours": forecast_hours})
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("Weather Agent unavailable for %s: %s", district, exc)
        return {"status": "error", "note": str(exc)}


def fetch_prediction(district: str, hazard_type: str, history: Optional[list] = None) -> Dict[str, Any]:
    if not history:
        return {"status": "unavailable", "note": "No history supplied; cannot request a real prediction."}
    url = f"{settings.prediction_agent_url}/api/v1/models/{hazard_type}/predict"
    payload = {"hazard_type": hazard_type, "location": district, "target_timestamp": "", "horizon": "24h",
               "history": history}
    try:
        with httpx.Client(timeout=settings.agent_request_timeout_seconds) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("Prediction Agent unavailable for %s/%s: %s", district, hazard_type, exc)
        return {"status": "error", "note": str(exc)}


def fetch_recent_alerts(limit: int = 20) -> Dict[str, Any]:
    url = f"{settings.alert_agent_url}/api/v1/alerts/current"
    try:
        with httpx.Client(timeout=settings.agent_request_timeout_seconds) as client:
            resp = client.get(url, params={"limit": limit})
            resp.raise_for_status()
            return {"status": "ok", "alerts": resp.json()}
    except Exception as exc:
        logger.warning("Alert Agent unavailable: %s", exc)
        return {"status": "error", "note": str(exc), "alerts": []}


def fetch_digital_twin_scenario(district: str, rainfall_mm: float) -> Dict[str, Any]:
    url = f"{settings.digital_twin_agent_url}/api/v1/digital-twin/scenario"
    payload = {"district": district, "rainfall_mm": rainfall_mm, "duration_hours": 24,
               "hazard_types": ["flood", "landslide"]}
    try:
        with httpx.Client(timeout=settings.agent_request_timeout_seconds) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("Digital Twin Agent unavailable for %s: %s", district, exc)
        return {"status": "error", "note": str(exc)}
