"""Process & Analyze, matching the diagram's "Process & Analyze" step and
"Analytics Engine" component. Fully real, deterministic computation over
whatever data was actually collected -- no fabrication, and any missing
metric is simply omitted (not guessed)."""

from __future__ import annotations

from typing import Any, Dict, List

from .logging_config import get_logger

logger = get_logger(__name__)


def analyze(per_district: Dict[str, Any], districts: List[str]) -> Dict[str, Any]:
    district_metrics = {}
    risk_scores = {}

    for district in districts:
        data = per_district.get(district, {})
        metrics: Dict[str, Any] = {}

        weather = data.get("weather", {})
        if weather.get("status") != "error" and weather.get("current"):
            metrics["current_temperature"] = weather["current"].get("temperature")
            metrics["current_humidity"] = weather["current"].get("humidity")
            metrics["current_rainfall"] = weather["current"].get("rainfall")
            metrics["anomalies"] = weather.get("anomalies", [])

        prediction = data.get("prediction", {})
        if prediction.get("status") == "ok":
            metrics["predicted_rainfall_mm"] = prediction.get("prediction")
            metrics["is_extreme_event"] = prediction.get("is_extreme_event")

        twin = data.get("digital_twin", {})
        if "risk_level" in twin:
            metrics["digital_twin_risk_level"] = twin["risk_level"]
            if twin.get("flood"):
                metrics["flood_affected_area_sq_km"] = twin["flood"].get("affected_area_sq_km")
            if twin.get("landslide"):
                metrics["landslide_susceptibility_score"] = twin["landslide"].get("susceptibility_score")
                risk_scores[district] = twin["landslide"]["susceptibility_score"]

        district_metrics[district] = metrics

    alerts = per_district.get("_alerts", {}).get("alerts", [])
    alert_summary = {
        "total_active": len(alerts),
        "by_severity": _count_by(alerts, "severity"),
    }

    trends = {}
    numeric_predictions = {d: m["predicted_rainfall_mm"] for d, m in district_metrics.items()
                            if m.get("predicted_rainfall_mm") is not None}
    if numeric_predictions:
        trends["highest_predicted_rainfall_district"] = max(numeric_predictions, key=numeric_predictions.get)
        trends["average_predicted_rainfall_mm"] = round(sum(numeric_predictions.values()) / len(numeric_predictions), 1)

    if risk_scores:
        trends["highest_risk_district"] = max(risk_scores, key=risk_scores.get)

    logger.info("Analysis complete for %s districts | alerts=%d", len(districts), len(alerts))
    return {"district_metrics": district_metrics, "alert_summary": alert_summary, "trends": trends}


def _count_by(records: List[dict], field: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for r in records:
        key = r.get(field, "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts
