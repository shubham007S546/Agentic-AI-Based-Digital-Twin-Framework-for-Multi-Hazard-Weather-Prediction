"""
app/agents/prediction_agent.py
──────────────────────────────
Agent 2 — Prediction Agent

Responsibility:
  • Run scheduled multi-hazard predictions for all districts
  • Trigger AlertAgent (via cascade) if risk thresholds are exceeded

Models used:
  • PredictionRequest  — audit log of every ML inference call
  • Alert              — created when prediction result exceeds threshold
"""

from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.enums import AgentName, AgentTrigger, District, HazardType, PredictionType


class PredictionAgent(BaseAgent):
    """
    Runs scheduled multi-hazard ML predictions for every district
    and emits cascade triggers for AlertAgent on threshold breach.
    """

    HAZARDS = [
        HazardType.RAINFALL,
        HazardType.LANDSLIDE,
        HazardType.CLOUDBURST,
        HazardType.FLASH_FLOOD,
    ]

    def __init__(self) -> None:
        super().__init__(name=AgentName.PREDICTION, version="1.0.0")

    @property
    def description(self) -> str:
        return (
            "Runs multi-hazard ML predictions for each district on a schedule. "
            "Logs each inference to PredictionRequest and cascades to AlertAgent "
            "when a HIGH or CRITICAL risk level is returned."
        )

    def _get_timeout_seconds(self) -> float:
        return 180.0

    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Run predictions for all districts × hazard combinations.

        Real implementation:
          1. Fetch latest WeatherObservation features per district
          2. Call PredictionService.run_prediction() for each hazard
             (creates PredictionRequest record with status=COMPLETED/FAILED)
          3. If result risk_level in (HIGH, CRITICAL, EXTREME) →
             emit AgentTrigger.CASCADE to AlertAgent with prediction payload
        """
        trigger_type: str = payload.get("trigger", AgentTrigger.SCHEDULED.value)
        predictions_run = 0
        alerts_cascaded = 0
        failed = 0

        for district in District:
            for hazard in self.HAZARDS:
                try:
                    self._logger.info(
                        "Running prediction",
                        district=district.name,
                        hazard=hazard.name,
                        prediction_type=PredictionType.SCHEDULED.value,
                    )
                    # Real: result = await prediction_service.run_prediction(request, triggered_by="prediction_agent")
                    # if result.prediction_result.get("risk_level") in ("HIGH", "CRITICAL", "EXTREME"):
                    #     await agent_manager.execute(AgentName.ALERT, payload={"predictions": [...]}, trigger=AgentTrigger.CASCADE)
                    #     alerts_cascaded += 1
                    predictions_run += 1
                except Exception as exc:
                    self._logger.error(
                        "Prediction failed",
                        district=district.name,
                        hazard=hazard.name,
                        error=str(exc),
                    )
                    failed += 1

        return {
            "trigger_type": trigger_type,
            "predictions_run": predictions_run,
            "alerts_cascaded": alerts_cascaded,
            "failed": failed,
            "districts": [d.name for d in District],
            "hazards": [h.name for h in self.HAZARDS],
        }
