"""
The Alert & Risk Assessment Agent's LangGraph state machine -- implements
the diagram's 7-step workflow:

    1. Monitor inputs             -> monitor_inputs
    2. Detect triggers            -> detect_triggers
    3. Assess risk                -> assess_risk_node
    4. Evaluate impact            -> evaluate_impact_node
    5. Generate alert             -> generate_alert_node
    6. Notify & escalate          -> notify_and_escalate_node
    7. Log & update               -> log_and_update
"""

from __future__ import annotations

from typing import Any, Dict, List

from langgraph.graph import END, StateGraph

from . import clients, external_feeds
from .alert_generator import generate_alert
from .escalation import notify_and_escalate
from .impact import assess_impact
from .logging_config import get_logger
from .risk_engine import assess_risk
from .schemas import AlertState
from .storage import alert_store

logger = get_logger(__name__)


def monitor_inputs(state: AlertState) -> AlertState:
    request = state["request"]
    location = request["location"]
    district = request.get("district") or location.split(",")[0].strip()

    predictions: Dict[str, Any] = {}
    if request.get("prediction_override"):
        predictions = request["prediction_override"]
    else:
        # only actually fetches if the caller supplied `history` per-hazard in
        # prediction_override -- otherwise clients.fetch_prediction honestly
        # reports "unavailable" rather than fabricating a prediction (see clients.py)
        for hazard in request.get("hazard_types", ["rainfall"]):
            predictions[hazard] = clients.fetch_prediction(
                location, hazard, request.get("target_timestamp", ""), request.get("horizon", "24h"),
                history=request.get(f"{hazard}_history"),
            )

    weather = request.get("weather_override") or clients.fetch_weather(
        location, request.get("latitude"), request.get("longitude"),
    )

    feeds = external_feeds.fetch_all_external_feeds(district)

    sources_used = []
    if any(p.get("status") == "ok" for p in predictions.values()):
        sources_used.append("prediction_agent")
    if weather.get("status") != "error":
        sources_used.append("weather_agent")
    if feeds.get("reliefweb", {}).get("status") == "ok":
        sources_used.append("reliefweb")

    return {**state, "predictions": predictions, "weather": weather,
            "external_feeds": feeds, "data_sources_used": sources_used}


def detect_triggers(state: AlertState) -> AlertState:
    triggers = []
    for hazard, pred in state.get("predictions", {}).items():
        if pred.get("status") == "ok" and pred.get("is_extreme_event"):
            triggers.append({"hazard": hazard, "trigger": "extreme_event_flag"})
    for anomaly in state.get("weather", {}).get("anomalies", []) or []:
        triggers.append({"hazard": "weather", "trigger": anomaly})
    logger.info("Detected %d trigger(s): %s", len(triggers), triggers)
    return {**state, "triggers": triggers}


def assess_risk_node(state: AlertState) -> AlertState:
    request = state["request"]
    predictions = state.get("predictions", {})
    weather = state.get("weather", {})
    feeds = state.get("external_feeds", {})

    per_hazard = {}
    for hazard in request.get("hazard_types", ["rainfall"]):
        pred = predictions.get(hazard, {"status": "unavailable"})
        factors, severity, completeness = assess_risk(hazard, pred, weather, feeds)
        score = round(min(sum(factors.values()), 1.0), 3)
        per_hazard[hazard] = {
            "risk_score": score, "severity": severity, "contributing_factors": factors,
            "data_completeness": completeness, "probability": pred.get("probability"),
            "prediction": pred.get("prediction"),
        }

    # the hazard with the highest risk score drives the alert this run generates
    primary_hazard = max(per_hazard, key=lambda h: per_hazard[h]["risk_score"])
    return {**state, "risk_assessment": {"per_hazard": per_hazard, "primary_hazard": primary_hazard}}


def evaluate_impact_node(state: AlertState) -> AlertState:
    request = state["request"]
    primary_hazard = state["risk_assessment"]["primary_hazard"]
    severity = state["risk_assessment"]["per_hazard"][primary_hazard]["severity"]
    district = request.get("district") or request["location"].split(",")[0].strip()
    impact = assess_impact(request["location"], district, severity)
    return {**state, "impact_assessment": impact}


def generate_alert_node(state: AlertState) -> AlertState:
    request = state["request"]
    ra = state["risk_assessment"]
    primary_hazard = ra["primary_hazard"]
    hazard_assessment = ra["per_hazard"][primary_hazard]

    alert = generate_alert(
        hazard_type=primary_hazard,
        location=request["location"],
        region=request.get("district") or request["location"],
        severity=hazard_assessment["severity"],
        risk_score=hazard_assessment["risk_score"],
        probability=hazard_assessment.get("probability"),
        horizon=request.get("horizon", "24h"),
        contributing_factors=hazard_assessment["contributing_factors"],
    )
    alert["impact"] = state["impact_assessment"]
    alert["data_sources_used"] = state.get("data_sources_used", [])
    alert["notes"] = [
        f"data_completeness={hazard_assessment['data_completeness']}",
        *(f"trigger: {t['trigger']} ({t['hazard']})" for t in state.get("triggers", [])),
    ]
    return {**state, "alert": alert}


def notify_and_escalate_node(state: AlertState) -> AlertState:
    alert = state["alert"]
    request = state["request"]
    notifications, escalated = notify_and_escalate(alert, request.get("notify", True))
    alert["notifications"] = notifications
    alert["escalated"] = escalated
    return {**state, "alert": alert, "notifications": notifications}


def log_and_update(state: AlertState) -> AlertState:
    alert = state["alert"]
    alert_store.append(alert)
    logger.info("Logged alert %s | severity=%s | escalated=%s",
                alert["alert_id"], alert["severity"], alert.get("escalated"))
    return {**state, "alert": alert}


def build_alert_graph():
    graph = StateGraph(AlertState)

    graph.add_node("monitor_inputs", monitor_inputs)
    graph.add_node("detect_triggers", detect_triggers)
    graph.add_node("assess_risk", assess_risk_node)
    graph.add_node("evaluate_impact", evaluate_impact_node)
    graph.add_node("generate_alert", generate_alert_node)
    graph.add_node("notify_and_escalate", notify_and_escalate_node)
    graph.add_node("log_and_update", log_and_update)

    graph.set_entry_point("monitor_inputs")
    graph.add_edge("monitor_inputs", "detect_triggers")
    graph.add_edge("detect_triggers", "assess_risk")
    graph.add_edge("assess_risk", "evaluate_impact")
    graph.add_edge("evaluate_impact", "generate_alert")
    graph.add_edge("generate_alert", "notify_and_escalate")
    graph.add_edge("notify_and_escalate", "log_and_update")
    graph.add_edge("log_and_update", END)

    return graph.compile()


alert_graph = build_alert_graph()
