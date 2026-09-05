"""
Collect Data, matching the diagram's "Collect Data" step and "Data
Aggregator" component. Which agents get called depends on `report_type` --
e.g. a daily_weather report only needs Agent 2, while multi_hazard pulls
predictions + alerts too. Everything is tracked in `data_sources_used` /
`data_completeness` so the final report is honest about how much of it is
real vs. missing.
"""

from __future__ import annotations

from typing import Any, Dict, List

from . import clients
from .logging_config import get_logger

logger = get_logger(__name__)

_REPORT_TYPE_SOURCES = {
    "daily_weather": ["weather"],
    "rainfall_forecast": ["weather", "prediction"],
    "multi_hazard": ["prediction", "alerts"],
    "district_risk": ["alerts", "digital_twin"],
    "infrastructure_impact": ["digital_twin"],
    "event_summary": ["alerts", "weather"],
    "seasonal_outlook": ["weather"],
    "custom": ["weather", "prediction", "alerts", "digital_twin"],
}


def collect_data(report_type: str, districts: List[str], horizon: str,
                  data_override: Dict[str, Any] = None) -> Dict[str, Any]:
    if data_override:
        return {"per_district": data_override, "sources_used": ["data_override"],
                "completeness": 1.0, "note": "Using caller-supplied data_override."}

    needed_sources = _REPORT_TYPE_SOURCES.get(report_type, ["weather"])
    per_district: Dict[str, Dict[str, Any]] = {}
    sources_hit = set()
    total_calls, ok_calls = 0, 0

    for district in districts:
        district_data: Dict[str, Any] = {}

        if "weather" in needed_sources:
            total_calls += 1
            weather = clients.fetch_weather(district, forecast_hours=24)
            district_data["weather"] = weather
            if weather.get("status") != "error":
                ok_calls += 1
                sources_hit.add("weather_agent")

        if "prediction" in needed_sources:
            total_calls += 1
            # rainfall prediction needs history -- best-effort from weather's
            # own forecast series if we just fetched it, otherwise honestly unavailable
            history = None
            weather = district_data.get("weather", {})
            if weather.get("status") != "error" and weather.get("forecast"):
                history = [{"timestamp": p.get("time"), "rain_openmeteo": p.get("rainfall", 0.0)}
                           for p in weather["forecast"]]
            prediction = clients.fetch_prediction(district, "rainfall", history=history)
            district_data["prediction"] = prediction
            if prediction.get("status") == "ok":
                ok_calls += 1
                sources_hit.add("prediction_agent")

        if "digital_twin" in needed_sources:
            total_calls += 1
            predicted_mm = district_data.get("prediction", {}).get("prediction") or 50.0
            twin = clients.fetch_digital_twin_scenario(district, predicted_mm)
            district_data["digital_twin"] = twin
            if twin.get("status") != "error" and "risk_level" in twin:
                ok_calls += 1
                sources_hit.add("digital_twin_agent")

        per_district[district] = district_data

    if "alerts" in needed_sources:
        total_calls += 1
        alerts = clients.fetch_recent_alerts()
        per_district["_alerts"] = alerts
        if alerts.get("status") == "ok":
            ok_calls += 1
            sources_hit.add("alert_agent")

    completeness = round(ok_calls / total_calls, 2) if total_calls else 0.0
    logger.info("Collected data for %s | sources=%s | completeness=%.2f", districts, sources_hit, completeness)

    return {"per_district": per_district, "sources_used": sorted(sources_hit), "completeness": completeness}
