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
    """Calls Agent 3's POST /api/v1/models/{hazard}/predict or falls back to in-process prediction graph."""
    if not history:
        return {"status": "unavailable", "note": "No history supplied; cannot request a real prediction."}

    url = f"{settings.prediction_agent_url}/api/v1/models/{hazard_type}/predict"
    payload = {
        "hazard_type": hazard_type, "location": location,
        "target_timestamp": target_timestamp, "horizon": horizon, "history": history,
    }
    # 1. Try HTTP microservice with quick timeout
    try:
        with httpx.Client(timeout=min(2.0, settings.agent_request_timeout_seconds)) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.debug("Prediction Agent HTTP unavailable (%s), trying in-process graph", exc)

    # 2. In-process LangGraph fallback
    try:
        from agents.prediction.graph import prediction_graph
        state = {"request": payload, "errors": []}
        result = prediction_graph.invoke(state)
        pred_res = result.get("result", {})
        return {
            "status": pred_res.get("status", "ok"),
            "source": "in_process_prediction_graph",
            "prediction_id": pred_res.get("prediction_id"),
            "prediction": pred_res.get("prediction", 0.0),
            "hazard_type": hazard_type,
            "probability": pred_res.get("probability", 0.0),
            "notes": pred_res.get("notes", []),
        }
    except Exception as in_err:
        logger.warning("Prediction in-process graph fallback failed: %s", in_err)
        return {"status": "error", "note": f"Prediction Agent unavailable: {in_err}"}


def fetch_weather(location: str, latitude: Optional[float], longitude: Optional[float],
                   forecast_hours: int = 24) -> Dict[str, Any]:
    """Calls Agent 2's GET /api/v1/weather/forecast or falls back to in-process weather graph."""
    url = f"{settings.weather_agent_url}/api/v1/weather/forecast"
    params = {"location": location, "forecast_hours": forecast_hours}
    if latitude is not None:
        params["latitude"] = latitude
    if longitude is not None:
        params["longitude"] = longitude

    # 1. Try HTTP microservice with quick timeout
    try:
        with httpx.Client(timeout=min(2.0, settings.agent_request_timeout_seconds)) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.debug("Weather Agent HTTP unavailable (%s), trying in-process graph", exc)

    # 2. In-process LangGraph fallback
    try:
        from agents.weather_analysis.graph import weather_analysis_graph
        state = {"request": {"location": location, "latitude": latitude, "longitude": longitude, "forecast_hours": forecast_hours}}
        result = weather_analysis_graph.invoke(state)
        resp = result.get("response", {})
        if resp:
            return resp
    except Exception as in_err:
        logger.warning("Weather in-process graph fallback failed: %s", in_err)

    return {"status": "error", "note": "Weather Agent unavailable via HTTP and in-process"}
