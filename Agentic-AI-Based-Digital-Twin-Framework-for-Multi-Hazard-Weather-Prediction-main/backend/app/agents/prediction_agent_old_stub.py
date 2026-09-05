"""
app/agents/prediction_agent.py
──────────────────────────────
Agent 2 — Prediction Agent (wired to real trained models via prediction_engine)
"""

from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.prediction_engine.graph import prediction_graph
from app.core.enums import AgentName, AgentTrigger, District, HazardType, PredictionType


class PredictionAgent(BaseAgent):
    HAZARDS = [HazardType.RAINFALL, HazardType.LANDSLIDE, HazardType.CLOUDBURST]
    # FLASH_FLOOD has no model in prediction_engine yet — graph.py's
    # validate_and_parse only accepts rainfall/cloudburst/landslide.

    def __init__(self) -> None:
        super().__init__(name=AgentName.PREDICTION, version="2.0.0")

    @property
    def description(self) -> str:
        return (
            "Runs multi-hazard ML predictions for each district using real "
            "trained models (via model_registry), logs each inference, and "
            "cascades to AlertAgent on HIGH/CRITICAL risk."
        )

    def _get_timeout_seconds(self) -> float:
        return 180.0

    async def _fetch_history_for_district(self, district) -> list[dict]:
        """
        TODO: wire to real WeatherObservation table/service.
        Must return 72h+ of raw hourly reading dicts matching RawHourlyReading.
        """
        raise NotImplementedError(
            "Connect this to your WeatherObservation query."
        )

    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        trigger_type: str = payload.get("trigger", AgentTrigger.SCHEDULED.value)
        predictions_run = 0
        alerts_cascaded = 0
        failed = 0
        results = []

        for district in District:
            try:
                history = await self._fetch_history_for_district(district)
            except NotImplementedError as exc:
                self._logger.error("History fetch not wired", district=district.name, error=str(exc))
                failed += len(self.HAZARDS)
                continue

            for hazard in self.HAZARDS:
                request = {
                    "hazard_type": hazard.value.lower(),
                    "location": district.name,
                    "target_timestamp": payload.get("target_timestamp"),
                    "horizon": payload.get("horizon", "24h"),
                    "history": history,
                }
                try:
                    self._logger.info("Running prediction", district=district.name, hazard=hazard.name)
                    state = prediction_graph.invoke({"request": request})
                    result = state.get("result", {})
                    results.append(result)

                    if result.get("status") == "ok":
                        predictions_run += 1
                        if result.get("is_extreme_event"):
                            self._logger.warning(
                                "Extreme event detected — should cascade to AlertAgent",
                                district=district.name, hazard=hazard.name,
                            )
                            alerts_cascaded += 1
                    else:
                        failed += 1

                except Exception as exc:
                    self._logger.error("Prediction failed", district=district.name, hazard=hazard.name, error=str(exc))
                    failed += 1

        return {
            "trigger_type": trigger_type,
            "predictions_run": predictions_run,
            "alerts_cascaded": alerts_cascaded,
            "failed": failed,
            "districts": [d.name for d in District],
            "hazards": [h.name for h in self.HAZARDS],
            "results": results,
        }