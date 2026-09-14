"""
Real HTTP integration with the other running agents: this agent calls
Agent 2 (Weather Analysis) and Agent 3 (Prediction) directly over HTTP,
matching the diagram's "Prediction Outputs" and "Weather Data" boxes under
DATA SOURCES. If either agent isn't running (or the caller already passed
`prediction_override` / `weather_override` in the request), this degrades
gracefully rather than failing the whole alert -- a partial risk assessment
from whatever data IS available is still useful, and is honestly reported
as such via `data_sources_used` / `notes`.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)


def fetch_prediction(location: str, hazard_type: str, target_timestamp: str, horizon: str,
                      history: Optional[list] = None) -> Dict[str, Any]:
    """Calls Agent 3's POST /api/v1/models/{hazard}/predict.
    Requires `history` (raw hourly weather readings) -- if you don't have
    that assembled yet, this will honestly come back as an error/stub
    rather than fabricate a prediction."""
    if not history:
        return {"status": "unavailable", "note": "No history supplied; cannot request a real prediction."}

    url = f"{settings.prediction_agent_url}/api/v1/models/{hazard_type}/predict"
    payload = {
        "hazard_type": hazard_type, "location": location,
        "target_timestamp": target_timestamp, "horizon": horizon, "history": history,
    }
    try:
        with httpx.Client(timeout=settings.agent_request_timeout_seconds) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("Prediction Agent unreachable/errored for hazard=%s: %s", hazard_type, exc)
        return {"status": "error", "note": f"Prediction Agent unavailable: {exc}"}


def fetch_weather(location: str, latitude: Optional[float], longitude: Optional[float],
                   forecast_hours: int = 24) -> Dict[str, Any]:
    """Calls Agent 2's GET /api/v1/weather/forecast."""
    url = f"{settings.weather_agent_url}/api/v1/weather/forecast"
    params = {"location": location, "forecast_hours": forecast_hours}
    if latitude is not None:
        params["latitude"] = latitude
    if longitude is not None:
        params["longitude"] = longitude
    try:
        with httpx.Client(timeout=settings.agent_request_timeout_seconds) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("Weather Agent unreachable/errored for %s: %s", location, exc)
        return {"status": "error", "note": f"Weather Agent unavailable: {exc}"}
