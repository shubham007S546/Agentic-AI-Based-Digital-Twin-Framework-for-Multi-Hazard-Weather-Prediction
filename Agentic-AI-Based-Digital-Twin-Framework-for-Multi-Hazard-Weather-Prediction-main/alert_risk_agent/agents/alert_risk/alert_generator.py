"""
Alert Generator, matching the diagram's "Generate Alert" step and its
example output shape (alert_id, type, severity, region, risk_score,
probability, valid_from/to, description, recommended_actions).

Uses Groq for a richer natural-language description + recommended actions
if GROQ_API_KEY is set; otherwise falls back to a deterministic template.
Either way, recommended_actions always includes the rule-based defaults for
the given hazard+severity -- the LLM (if used) only adds to/rephrases them,
never replaces the safety-relevant defaults.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from .config import settings
from .logging_config import get_logger
from .schemas import SEVERITY_DESCRIPTIONS

logger = get_logger(__name__)

_DEFAULT_ACTIONS = {
    "red": [
        "Avoid travel near rivers, streams, and known landslide-prone slopes.",
        "Move to higher ground or a safer location if in a low-lying or flood-prone area.",
        "Follow local disaster authority instructions immediately.",
    ],
    "orange": [
        "Avoid unnecessary travel near rivers, streams, and steep slopes.",
        "Stay alert and follow local advisories closely.",
        "Prepare an emergency kit and know your nearest safe location.",
    ],
    "yellow": [
        "Stay updated on the forecast and local advisories.",
        "Avoid non-essential travel in low-lying or landslide-prone areas if conditions worsen.",
    ],
    "green": [
        "No immediate action needed -- continue normal activity.",
    ],
}

_HORIZON_HOURS = {"now": 1, "1h": 1, "6h": 6, "24h": 24, "72h": 72, "7d": 168}


def _validity_window(horizon: str) -> tuple:
    now = datetime.now(timezone.utc)
    hours = _HORIZON_HOURS.get(horizon, 24)
    return now.isoformat(), (now + timedelta(hours=hours)).isoformat()


def _template_description(hazard_type: str, location: str, severity: str,
                           risk_score: float, probability: Any) -> str:
    prob_str = f" (probability {probability:.2f})" if isinstance(probability, (int, float)) else ""
    return (
        f"{SEVERITY_DESCRIPTIONS[severity]} {hazard_type.capitalize()} risk assessed for {location} "
        f"with a composite risk score of {risk_score:.2f}{prob_str}."
    )


def _llm_description(hazard_type: str, location: str, severity: str, risk_score: float,
                      probability: Any, contributing_factors: Dict[str, float]) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_groq import ChatGroq

    chat = ChatGroq(model=settings.groq_model, api_key=settings.groq_api_key, temperature=0.2)
    system = (
        "You write short, clear disaster-alert descriptions for the public in Himachal Pradesh, India. "
        "2-3 sentences. State the hazard, severity, and location plainly. Do not invent numbers beyond "
        "what's given. Do not be alarmist beyond what the severity level warrants."
    )
    user = (
        f"Hazard: {hazard_type}\nLocation: {location}\nSeverity: {severity}\n"
        f"Risk score: {risk_score}\nProbability: {probability}\nContributing factors: {contributing_factors}"
    )
    try:
        result = chat.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return result.content.strip()
    except Exception as exc:
        logger.warning("LLM description generation failed, using template: %s", exc)
        return _template_description(hazard_type, location, severity, risk_score, probability)


def generate_alert(
    hazard_type: str, location: str, region: str, severity: str, risk_score: float,
    probability: Any, horizon: str, contributing_factors: Dict[str, float],
) -> Dict[str, Any]:
    valid_from, valid_to = _validity_window(horizon)

    if settings.has_llm_key:
        description = _llm_description(hazard_type, location, severity, risk_score, probability, contributing_factors)
    else:
        description = _template_description(hazard_type, location, severity, risk_score, probability)

    alert_id = f"ALRT-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{uuid.uuid4().hex[:6].upper()}"

    return {
        "alert_id": alert_id,
        "type": hazard_type.capitalize(),
        "severity": severity.capitalize(),
        "region": region,
        "risk_score": risk_score,
        "probability": probability,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "description": description,
        "recommended_actions": list(_DEFAULT_ACTIONS[severity]),
    }
