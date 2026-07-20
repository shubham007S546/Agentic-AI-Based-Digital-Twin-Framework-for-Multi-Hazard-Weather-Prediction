"""
app/agents/alert_agent.py
──────────────────────────
Agent 3 — Alert Agent

Responsibility:
  • Evaluate prediction outputs against hazard thresholds
  • Create Alert records in the database
  • Emit AlertIssued events for the NotificationAgent
"""

from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.enums import AgentName


class AlertAgent(BaseAgent):
    THRESHOLDS = {
        "precipitation_mm": 50.0,      # >50mm/hr = HIGH rainfall alert
        "risk_score": 0.65,            # >0.65 landslide risk score
        "cloudburst_probability": 0.70,
        "flood_risk_index": 0.65,
    }

    def __init__(self) -> None:
        super().__init__(name=AgentName.ALERT, version="1.0.0")

    @property
    def description(self) -> str:
        return "Evaluates prediction results against configurable thresholds and generates disaster alerts."

    def _get_timeout_seconds(self) -> float:
        return 60.0

    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Payload expects: {"predictions": [{hazard, district, result}]}
        Creates Alert DB records for any exceeding threshold.
        """
        predictions = payload.get("predictions", [])
        alerts_issued = 0

        for pred in predictions:
            result = pred.get("result", {})

            if self._exceeds_threshold(result):
                alerts_issued += 1
                self._logger.warning(
                    "Threshold exceeded — alert issued",
                    district=pred.get("district"),
                    hazard=pred.get("hazard"),
                    result=result,
                )

        return {
            "predictions_evaluated": len(predictions),
            "alerts_issued": alerts_issued,
        }

    def _exceeds_threshold(self, result: dict[str, Any]) -> bool:
        for key, threshold in self.THRESHOLDS.items():
            value = result.get(key)
            if value is not None and float(value) >= threshold:
                return True
        return False
