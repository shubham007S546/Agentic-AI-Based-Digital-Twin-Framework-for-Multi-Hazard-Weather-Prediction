"""Generates the human-readable summary sentence for the weather response.
Uses Groq if GROQ_API_KEY is set (richer, more natural phrasing); otherwise
falls back to a deterministic template -- both are honest about what data
is real vs. unavailable, never inventing numbers for stubbed sources."""

from __future__ import annotations

from typing import Any, Dict, List

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)


def _template_summary(location: str, current: Dict[str, Any], anomalies: List[str], sources: List[str]) -> str:
    parts = [f"Current conditions in {location}:"]
    if current.get("temperature") is not None:
        parts.append(f"{current['temperature']}°C")
    if current.get("humidity") is not None:
        parts.append(f"{current['humidity']}% humidity")
    if current.get("rainfall") is not None:
        parts.append(f"{current['rainfall']}mm rainfall")
    if current.get("wind_speed") is not None:
        parts.append(f"{current['wind_speed']}km/h wind")
    summary = ", ".join(parts) + "."
    if anomalies:
        summary += " Anomalies: " + "; ".join(anomalies) + "."
    if sources:
        summary += f" Sources: {', '.join(sources)}."
    return summary


def generate_summary(location: str, current: Dict[str, Any], forecast: List[Dict[str, Any]],
                      anomalies: List[str], sources: List[str]) -> str:
    if not settings.has_llm_key:
        return _template_summary(location, current, anomalies, sources)

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_groq import ChatGroq

        chat = ChatGroq(model=settings.groq_model, api_key=settings.groq_api_key, temperature=0.2)
        system = (
            "You summarize weather data for a disaster early-warning system in Himachal Pradesh. "
            "Write 1-3 concise sentences. Never invent numbers not present in the data given."
        )
        user = (
            f"Location: {location}\nCurrent: {current}\nForecast (next few hours): {forecast[:6]}\n"
            f"Anomalies detected: {anomalies}\nData sources used: {sources}"
        )
        result = chat.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return result.content
    except Exception as exc:
        logger.warning("LLM summary generation failed (%s); falling back to template.", exc)
        return _template_summary(location, current, anomalies, sources)
