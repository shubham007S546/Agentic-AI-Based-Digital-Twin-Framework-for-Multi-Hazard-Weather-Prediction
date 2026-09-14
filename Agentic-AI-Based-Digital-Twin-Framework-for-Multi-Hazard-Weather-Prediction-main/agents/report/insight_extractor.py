"""Extract Insights, matching the diagram's "Generate Insights" step and
"Insight Extractor" component. Rule-based by default (always available,
deterministic); adds an LLM-generated narrative summary on top if
GROQ_API_KEY is set -- the rule-based insights are never replaced by the
LLM, only supplemented, so insights never depend on an API key being
present."""

from __future__ import annotations

from typing import Any, Dict, List

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)


def _rule_based_insights(analysis: Dict[str, Any], report_type: str) -> List[str]:
    insights = []
    trends = analysis.get("trends", {})
    district_metrics = analysis.get("district_metrics", {})
    alert_summary = analysis.get("alert_summary", {})

    if trends.get("highest_predicted_rainfall_district"):
        insights.append(
            f"{trends['highest_predicted_rainfall_district']} has the highest predicted rainfall "
            f"({trends.get('average_predicted_rainfall_mm', '?')}mm avg across districts)."
        )

    if trends.get("highest_risk_district"):
        insights.append(f"{trends['highest_risk_district']} shows the highest landslide susceptibility score.")

    for district, metrics in district_metrics.items():
        if metrics.get("is_extreme_event"):
            insights.append(f"{district}: prediction agent flagged an extreme rainfall event.")
        if metrics.get("anomalies"):
            insights.append(f"{district}: weather anomalies detected -- {', '.join(metrics['anomalies'])}.")
        if metrics.get("digital_twin_risk_level") in ("High", "Extreme"):
            insights.append(f"{district}: digital twin scenario risk level is {metrics['digital_twin_risk_level']}.")

    if alert_summary.get("total_active", 0) > 0:
        insights.append(f"{alert_summary['total_active']} active alert(s) across monitored districts.")

    if not insights:
        insights.append("No significant anomalies, extreme events, or elevated risk detected in available data.")

    return insights


def _llm_narrative(insights: List[str], report_type: str, districts: List[str]) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_groq import ChatGroq

    chat = ChatGroq(model=settings.groq_model, api_key=settings.groq_api_key, temperature=0.2)
    system = (
        "You write a short (3-5 sentence) executive summary for a weather/hazard report for districts "
        "in Himachal Pradesh, India, based ONLY on the bullet-point findings given. Do not invent numbers "
        "or claims beyond what's listed."
    )
    user = f"Report type: {report_type}\nDistricts: {districts}\nFindings:\n" + "\n".join(f"- {i}" for i in insights)
    try:
        result = chat.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return result.content.strip()
    except Exception as exc:
        logger.warning("LLM narrative generation failed: %s", exc)
        return " ".join(insights[:3])


def generate_insights(analysis: Dict[str, Any], report_type: str, districts: List[str]) -> Dict[str, Any]:
    insights = _rule_based_insights(analysis, report_type)
    summary = _llm_narrative(insights, report_type, districts) if settings.has_llm_key else " ".join(insights[:3])
    return {"insights": insights, "summary": summary}
