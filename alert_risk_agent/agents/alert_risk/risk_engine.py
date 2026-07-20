"""
Rule Engine + composite risk scoring, matching the diagram's "Rule Engine
(Thresholds & Rules)" and "Assess Risk" step. Fully real and deterministic --
no ML risk model exists yet (the diagram's "ML Risk Model (Trained Models)"
box is future work: train a classifier on historical alert-outcome labels
once you have them, then blend its output in here alongside these rules).

Scoring is a transparent weighted sum, not a black box -- every factor's
contribution is returned in `contributing_factors` so an alert's score is
always explainable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)

_WEIGHT_PREDICTION = 0.5
_WEIGHT_EXTREME_EVENT_BONUS = 0.2
_WEIGHT_WEATHER_ANOMALIES = 0.2
_WEIGHT_EXTERNAL_REPORTS = 0.1


def _severity_from_score(score: float, prediction_forces_floor: bool) -> str:
    if score >= settings.red_threshold:
        severity = "red"
    elif score >= settings.orange_threshold:
        severity = "orange"
    elif score >= settings.yellow_threshold:
        severity = "yellow"
    else:
        severity = "green"

    if prediction_forces_floor and severity in ("green", "yellow"):
        severity = "orange"
    return severity


def assess_risk(
    hazard_type: str,
    prediction: Dict[str, Any],
    weather: Dict[str, Any],
    external_feeds: Dict[str, Any],
) -> Tuple[Dict[str, float], str, float]:
    """Returns (contributing_factors, severity, data_completeness)."""
    factors: Dict[str, float] = {}
    real_sources = 0
    intended_sources = 3  # prediction, weather, external_feeds

    prediction_forces_floor = False

    if prediction.get("status") == "ok":
        real_sources += 1
        if hazard_type == "rainfall" and prediction.get("prediction") is not None:
            predicted_mm = float(prediction["prediction"])
            factors["rainfall_prediction"] = min(predicted_mm / settings.cloudburst_mm_floor, 1.0) * _WEIGHT_PREDICTION
            if predicted_mm >= settings.cloudburst_mm_floor:
                prediction_forces_floor = True
        elif prediction.get("probability") is not None:
            probability = float(prediction["probability"])
            factors[f"{hazard_type}_probability"] = probability * _WEIGHT_PREDICTION
            if probability >= 0.7:
                prediction_forces_floor = True

        if prediction.get("is_extreme_event"):
            factors["extreme_event_bonus"] = _WEIGHT_EXTREME_EVENT_BONUS
            prediction_forces_floor = True
    else:
        factors["rainfall_prediction"] = 0.0

    anomalies: List[str] = weather.get("anomalies", []) if isinstance(weather, dict) else []
    if weather.get("status") != "error" and "anomalies" in weather:
        real_sources += 1
    if anomalies:
        factors["weather_anomalies"] = min(len(anomalies) * 0.1, 1.0) * _WEIGHT_WEATHER_ANOMALIES

    reliefweb = external_feeds.get("reliefweb", {}) if external_feeds else {}
    if reliefweb.get("status") == "ok":
        real_sources += 1
        if reliefweb.get("reports"):
            factors["recent_external_reports"] = _WEIGHT_EXTERNAL_REPORTS

    score = round(min(sum(factors.values()), 1.0), 3)
    severity = _severity_from_score(score, prediction_forces_floor)
    data_completeness = round(real_sources / intended_sources, 2)

    logger.info("Risk assessment: hazard=%s score=%.3f severity=%s completeness=%.2f",
                hazard_type, score, severity, data_completeness)
    return factors, severity, data_completeness
