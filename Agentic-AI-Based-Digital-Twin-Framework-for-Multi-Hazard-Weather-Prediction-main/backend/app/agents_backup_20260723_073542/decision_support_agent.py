"""
app/agents/decision_support_agent.py
──────────────────────────────────────
Agent 11 — Decision Support Agent

Responsibility:
  • Synthesise intelligence from DisasterIntelligenceAgent, PredictionAgent,
    and TwinState into actionable decision briefs for government authorities
    and disaster officers
  • Apply SDMA (State Disaster Management Authority) standard response protocols
    mapped to risk levels from RiskLevel enum
  • Generate an Alert Bulletin Report (ReportType.ALERT_BULLETIN) and cascade
    to ReportAgent for upload

Models used:
  • TwinState          — current district state snapshot for context
  • Alert              — active alerts to include in the decision brief
  • PredictionRequest  — highest-confidence predictions per hazard
  • Report             — output report record (type=ALERT_BULLETIN)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.enums import (
    AgentName,
    AgentTrigger,
    AlertSeverity,
    District,
    HazardType,
    ReportType,
    RiskLevel,
)

# SDMA response protocol mapping: risk level → recommended actions
_RESPONSE_PROTOCOLS: dict[RiskLevel, list[str]] = {
    RiskLevel.NEGLIGIBLE: ["Routine monitoring"],
    RiskLevel.LOW: ["Enhanced monitoring every 30 min", "Alert district administration"],
    RiskLevel.MODERATE: [
        "Activate district EOC standby",
        "Pre-position NDRF teams",
        "Issue public advisory",
    ],
    RiskLevel.HIGH: [
        "Activate district EOC",
        "Deploy NDRF teams",
        "Evacuate high-risk zones",
        "Coordinate with HPSDMA",
        "Issue RED alert bulletin",
    ],
    RiskLevel.VERY_HIGH: [
        "Full EOC activation",
        "Multi-district NDRF deployment",
        "Mandatory evacuation of vulnerable zones",
        "Coordinate with Army / ITBP",
        "State-level alert",
    ],
    RiskLevel.EXTREME: [
        "Declare disaster emergency",
        "NDMA coordination",
        "Mass evacuation",
        "National-level emergency declared",
        "Media broadcast — all channels",
    ],
}


class DecisionSupportAgent(BaseAgent):
    """
    Decision synthesis agent for government authorities.
    Maps compound risk intelligence into SDMA protocol recommendations.
    """

    def __init__(self) -> None:
        super().__init__(name=AgentName.DECISION_SUPPORT, version="1.0.0")

    @property
    def description(self) -> str:
        return (
            "Synthesises TwinState, active Alert, and PredictionRequest data into "
            "structured decision briefs with SDMA response protocol recommendations. "
            "Generates Alert Bulletin reports and cascades to ReportAgent."
        )

    def _get_timeout_seconds(self) -> float:
        return 120.0

    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Decision brief generation pipeline.

        Payload expects:
          - district_risk_report: dict from DisasterIntelligenceAgent
          - active_alerts: list of Alert dicts
          - twin_states: dict of district → TwinState snapshot

        Real implementation:
          1. For each district, read compound_risk_level from district_risk_report
          2. Map risk level to SDMA protocols via _RESPONSE_PROTOCOLS
          3. Include active Alert list, latest TwinState snapshot, and top predictions
          4. Build structured brief dict per district
          5. Cascade to ReportAgent with ReportType.ALERT_BULLETIN
          6. Cascade to NotificationAgent for disaster officer delivery
        """
        district_risk: dict[str, Any] = payload.get("district_risk_report", {})
        active_alerts: list[dict] = payload.get("active_alerts", [])
        twin_states: dict[str, Any] = payload.get("twin_states", {})
        generated_at = datetime.now(UTC).isoformat()

        decision_briefs: list[dict] = []
        escalation_needed = False

        for district in District:
            risk_info = district_risk.get(district.value, {})
            raw_risk_level = risk_info.get("compound_risk_level", RiskLevel.LOW.value)

            # Safely parse risk level
            try:
                risk_level = RiskLevel(raw_risk_level)
            except ValueError:
                risk_level = RiskLevel.LOW

            protocols = _RESPONSE_PROTOCOLS.get(risk_level, [])
            district_alerts = [
                a for a in active_alerts if a.get("district") == district.value
            ]

            brief = {
                "district": district.value,
                "generated_at": generated_at,
                "risk_level": risk_level.value,
                "active_hazards": risk_info.get("active_hazards", []),
                "alert_count": len(district_alerts),
                "sdma_protocols": protocols,
                "twin_state_available": district.value in twin_states,
                "recommended_actions": protocols,
            }
            decision_briefs.append(brief)

            if risk_level in (RiskLevel.HIGH, RiskLevel.VERY_HIGH, RiskLevel.EXTREME):
                escalation_needed = True
                self._logger.warning(
                    "High-risk decision brief generated",
                    district=district.name,
                    risk_level=risk_level.value,
                    protocols=protocols,
                )

        # Cascade to ReportAgent for bulletin generation
        # Real: await agent_manager.execute(
        #     AgentName.REPORT_GENERATOR,
        #     payload={"report_type": ReportType.ALERT_BULLETIN.value, "briefs": decision_briefs},
        #     trigger=AgentTrigger.CASCADE,
        # )
        # If escalation needed → also cascade to NotificationAgent

        return {
            "generated_at": generated_at,
            "districts_briefed": len(decision_briefs),
            "escalation_needed": escalation_needed,
            "report_type": ReportType.ALERT_BULLETIN.value,
            "decision_briefs": decision_briefs,
        }
