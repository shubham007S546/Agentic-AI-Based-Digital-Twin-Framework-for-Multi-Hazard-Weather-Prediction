"""
backend/app/agents/tools/alert_tools.py
──────────────────────────────────────
Tools for evaluating thresholds, cascading warnings, and calculating compound multi-hazard indices.
"""

from __future__ import annotations

from typing import Any
from app.agents.tools.base_tool import BaseAgentTool, ToolParameter
from app.core.enums import AlertSeverity, HazardType, RiskLevel


class CheckHazardThresholdTool(BaseAgentTool):
    """Tool to test observation/forecast values against NDMA / IMD thresholds."""

    def __init__(self) -> None:
        super().__init__(
            name="check_hazard_threshold",
            description="Evaluates whether weather parameters exceed IMD warning thresholds for Himachal Pradesh.",
            parameters=[
                ToolParameter(name="hazard_type", type="string", description="Type of hazard: RAINFALL, CLOUDBURST, etc."),
                ToolParameter(name="value", type="number", description="Measured or predicted hazard intensity"),
            ],
        )

    async def execute(self, hazard_type: str, value: float) -> dict[str, Any]:
        ht = hazard_type.upper()
        severity = AlertSeverity.INFO
        risk_level = RiskLevel.LOW

        if ht in ("RAINFALL", "PRECIPITATION"):
            # IMD thresholds for 24h rainfall (mm)
            if value >= 204.5:
                severity = AlertSeverity.EMERGENCY
                risk_level = RiskLevel.EXTREME
            elif value >= 115.6:
                severity = AlertSeverity.WARNING
                risk_level = RiskLevel.HIGH
            elif value >= 64.5:
                severity = AlertSeverity.ADVISORY
                risk_level = RiskLevel.MEDIUM
        elif ht == "CLOUDBURST":
            # Cloudburst: rainfall rate >= 100mm/h or high probability
            if value >= 0.8 or value >= 100.0:
                severity = AlertSeverity.EMERGENCY
                risk_level = RiskLevel.EXTREME
            elif value >= 0.5 or value >= 50.0:
                severity = AlertSeverity.WARNING
                risk_level = RiskLevel.HIGH
        elif ht == "LANDSLIDE":
            if value >= 0.75:
                severity = AlertSeverity.WARNING
                risk_level = RiskLevel.HIGH

        return {
            "hazard_type": ht,
            "value": value,
            "severity": severity.name,
            "risk_level": risk_level.name,
            "is_breached": severity != AlertSeverity.INFO,
        }


class AssessCompoundRiskTool(BaseAgentTool):
    """Tool to evaluate compound risk when multiple hazards co-occur in the same district."""

    def __init__(self) -> None:
        super().__init__(
            name="assess_compound_risk",
            description="Computes compounded multi-hazard index for overlapping hazards.",
            parameters=[
                ToolParameter(name="active_hazards", type="array", description="List of active hazard types in district"),
                ToolParameter(name="soil_saturation", type="number", description="Current soil moisture fraction (0.0 - 1.0)", default=0.5),
            ],
        )

    async def execute(self, active_hazards: list[str], soil_saturation: float = 0.5) -> dict[str, Any]:
        hazards = {h.upper() for h in active_hazards}
        elevated_level = "LOW"

        if "CLOUDBURST" in hazards and ("LANDSLIDE" in hazards or "FLASH_FLOOD" in hazards):
            elevated_level = "EXTREME"
        elif "RAINFALL" in hazards and "LANDSLIDE" in hazards:
            elevated_level = "VERY_HIGH" if soil_saturation > 0.8 else "HIGH"
        elif len(hazards) >= 2:
            elevated_level = "HIGH"
        elif len(hazards) == 1:
            elevated_level = "MEDIUM"

        return {
            "compounded_risk": elevated_level,
            "hazards_present": list(hazards),
            "soil_saturation": soil_saturation,
            "evacuation_recommended": elevated_level in ("VERY_HIGH", "EXTREME"),
        }
