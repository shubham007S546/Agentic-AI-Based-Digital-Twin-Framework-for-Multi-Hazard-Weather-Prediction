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
        with httpx.Client(timeout=min(2.0, settings.agent_request_timeout_seconds)) as client:
            resp = client.get(url, params={"limit": limit})
            resp.raise_for_status()
            return {"status": "ok", "alerts": resp.json()}
    except Exception as exc:
        logger.debug("Alert Agent HTTP unavailable (%s), trying in-process alert graph", exc)

    try:
        from agents.alert_risk.graph import alert_graph
        state = {
            "request": {
                "location": "Himachal Pradesh",
                "district": "Mandi",
                "hazard_types": ["rainfall", "flood", "landslide"],
                "horizon": "24h",
                "notify": False,
            },
            "errors": [],
        }
        res = alert_graph.invoke(state)
        alert = res.get("alert", {})
        return {"status": "ok", "source": "in_process_alert_graph", "alerts": [alert] if alert else []}
    except Exception as in_err:
        logger.warning("In-process alert graph fallback failed: %s", in_err)
        return {"status": "error", "note": str(in_err), "alerts": []}


def fetch_digital_twin_scenario(district: str, rainfall_mm: float) -> Dict[str, Any]:
    url = f"{settings.digital_twin_agent_url}/api/v1/digital-twin/scenario"
    payload = {"district": district, "rainfall_mm": rainfall_mm, "duration_hours": 24,
               "hazard_types": ["flood", "landslide"]}
    try:
        with httpx.Client(timeout=min(2.0, settings.agent_request_timeout_seconds)) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.debug("Digital Twin HTTP unavailable (%s), trying in-process twin graph", exc)

    try:
        from agents.digital_twin.graph import digital_twin_graph
        state = {"request": payload, "errors": []}
        res = digital_twin_graph.invoke(state)
        return res.get("response", {}) or {"status": "ok", "district": district, "simulation": res.get("scenario_result", {})}
    except Exception as in_err:
        logger.warning("In-process digital twin graph fallback failed: %s", in_err)
        return {"status": "error", "note": str(in_err)}
