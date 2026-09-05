"""
app/agents/disaster_intelligence_agent.py
─────────────────────────────────────────
Agent 5 — Disaster Intelligence Agent

Responsibility:
  • Aggregate active Alert records across all districts
  • Compute compound multi-hazard risk scores
    (e.g., simultaneous landslide + cloudburst = EXTREME compounded risk)
  • Emit structured risk assessments for the DecisionSupportAgent

Models used:
  • Alert           — active disaster alerts per district/hazard
  • PredictionRequest — latest ML prediction results per hazard
"""

from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.enums import (
    AgentName,
    AgentTrigger,
    AlertSeverity,
    District,
    HazardType,
    RiskLevel,
)

# Compound risk matrix: hazard combinations → elevated risk level
_COMPOUND_RULES: list[tuple[set[HazardType], RiskLevel]] = [
    ({HazardType.CLOUDBURST, HazardType.LANDSLIDE}, RiskLevel.EXTREME),
    ({HazardType.CLOUDBURST, HazardType.FLASH_FLOOD}, RiskLevel.EXTREME),
    ({HazardType.RAINFALL, HazardType.LANDSLIDE}, RiskLevel.VERY_HIGH),
    ({HazardType.RAINFALL, HazardType.FLASH_FLOOD}, RiskLevel.VERY_HIGH),
]


class DisasterIntelligenceAgent(BaseAgent):
    """
    Evaluates compound multi-hazard risk by correlating active alerts
    and recent ML predictions across all target districts.
    """

    def __init__(self) -> None:
        super().__init__(name=AgentName.DISASTER_INTELLIGENCE, version="1.0.0")

    @property
    def description(self) -> str:
        return (
            "Aggregates active Alert records and PredictionRequest outputs to compute "
            "compound multi-hazard risk scores per district and emit structured "
            "intelligence reports for the DecisionSupportAgent."
        )

    def _get_timeout_seconds(self) -> float:
        return 90.0

    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Compound risk evaluation pipeline.

        Real implementation:
          1. Query Alert.objects WHERE status=ACTIVE, grouped by district
          2. Query latest PredictionRequest per district/hazard
          3. Apply _COMPOUND_RULES to elevate risk where multiple hazards coincide
          4. Build risk_report dict and emit to DecisionSupportAgent via CASCADE
        """
        # Payload may carry pre-fetched alerts from AlertAgent cascade
        active_alerts: list[dict] = payload.get("active_alerts", [])
        district_risk: dict[str, dict] = {}

        for district in District:
            district_alerts = [
                a for a in active_alerts
                if a.get("district") == district.value
            ]

            active_hazards: set[HazardType] = {
                HazardType(a["hazard_type"])
                for a in district_alerts
                if "hazard_type" in a
            }

            # Determine compound risk level
            risk_level = RiskLevel.LOW
            for hazard_set, elevated_level in _COMPOUND_RULES:
                if hazard_set.issubset(active_hazards):
                    risk_level = elevated_level
                    break

            max_severity = max(
                (a.get("severity", AlertSeverity.INFO) for a in district_alerts),
                default=AlertSeverity.INFO,
            )

            district_risk[district.value] = {
                "active_hazards": [h.value for h in active_hazards],
                "alert_count": len(district_alerts),
                "compound_risk_level": risk_level.value,
                "max_severity": (
                    max_severity.name
                    if isinstance(max_severity, AlertSeverity)
                    else str(max_severity)
                ),
            }

            self._logger.info(
                "District risk assessed",
                district=district.name,
                risk_level=risk_level.value,
                active_hazards=list(active_hazards),
            )

        high_risk_districts = [
            d for d, r in district_risk.items()
            if r["compound_risk_level"] in (RiskLevel.VERY_HIGH.value, RiskLevel.EXTREME.value)
        ]

        return {
            "districts_evaluated": len(District),
            "high_risk_districts": high_risk_districts,
            "district_risk_report": district_risk,
            "cascade_trigger": AgentTrigger.CASCADE.value if high_risk_districts else None,
        }
