"""
app/agents/digital_twin_agent.py
──────────────────────────────────
Agent 6 — Digital Twin Synchronisation Agent

Responsibility:
  • Sync the latest WeatherObservation and prediction data into TwinState
  • Mark previous TwinState records as is_latest=False before inserting a new one
  • Trigger SimulationAgent when scenario_parameters are provided in payload

Models used:
  • TwinState   — district-level state snapshot (weather, hydrology, geology, infra)
  • Simulation  — what-if scenario runs keyed to a baseline TwinState
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.enums import (
    AgentName,
    AgentTrigger,
    District,
    RiskLevel,
    SimulationStatus,
    WeatherSource,
)


class DigitalTwinAgent(BaseAgent):
    """
    Maintains real-time synchronisation of the district Digital Twin state
    from the latest WeatherObservation observations and ML prediction results.
    """

    def __init__(self) -> None:
        super().__init__(name=AgentName.DIGITAL_TWIN, version="1.0.0")

    @property
    def description(self) -> str:
        return (
            "Syncs the latest weather, hydrological, geological, and infrastructure "
            "readings into TwinState for each district, keeping the digital twin "
            "current for simulation and risk-assessment queries."
        )

    def _get_timeout_seconds(self) -> float:
        return 120.0

    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        State synchronisation pipeline.

        Real implementation:
          1. For each district, fetch the latest WeatherObservation from DB
          2. Fetch latest PredictionRequest results (rainfall, landslide, flood)
          3. Build a new TwinState record:
               district=district,
               timestamp=datetime.now(UTC),
               weather_state={temperature_2m, precipitation, humidity, ...},
               hydrological_state={soil_moisture, river_level, flood_index},
               geological_state={landslide_risk_score, slope_saturation},
               infrastructure_state={road_closure_risk, bridge_risk},
               is_latest=True
          4. Set previous TwinState.is_latest = False for this district
          5. If payload contains "scenario_parameters", create a Simulation record
             with status=QUEUED and cascade to SimulationAgent
        """
        synced_districts: list[str] = []
        simulations_queued: int = 0
        scenario_parameters: dict = payload.get("scenario_parameters", {})
        sync_timestamp = datetime.now(UTC).isoformat()

        for district in District:
            try:
                # Real: latest_obs = await weather_repo.get_latest(district)
                # Real: latest_preds = await prediction_repo.get_latest_per_hazard(district)
                # Build TwinState from obs + preds, then save to DB

                twin_state_snapshot = {
                    "district": district.value,
                    "timestamp": sync_timestamp,
                    "weather_state": {
                        "source": WeatherSource.OPEN_METEO.value,
                        "temperature_2m": None,       # from WeatherObservation
                        "precipitation": None,
                        "relative_humidity_2m": None,
                        "cloud_cover": None,
                        "wind_speed_10m": None,
                    },
                    "hydrological_state": {
                        "soil_moisture": None,         # from WeatherObservation.soil_moisture
                        "flood_risk_index": None,      # from PredictionRequest result
                        "river_discharge_m3s": None,   # from HydrologicalAgent
                    },
                    "geological_state": {
                        "landslide_risk_score": None,  # from PredictionRequest result
                        "slope_saturation_index": None,
                    },
                    "infrastructure_state": {
                        "road_closure_risk": RiskLevel.LOW.value,
                        "bridge_stress_index": 0.0,
                    },
                    "is_latest": True,
                }

                self._logger.info(
                    "TwinState synced",
                    district=district.name,
                    timestamp=sync_timestamp,
                )
                synced_districts.append(district.value)

            except Exception as exc:
                self._logger.error(
                    "TwinState sync failed",
                    district=district.name,
                    error=str(exc),
                )

        # If caller provided scenario parameters, queue a simulation
        if scenario_parameters:
            self._logger.info(
                "Queuing simulation",
                scenario_parameters=scenario_parameters,
                trigger=AgentTrigger.CASCADE.value,
            )
            # Real: sim = Simulation(scenario_parameters=scenario_parameters,
            #                        status=SimulationStatus.QUEUED, ...)
            #       await simulation_repo.create(sim)
            #       await agent_manager.execute(AgentName.MONITORING, payload={...}, trigger=AgentTrigger.CASCADE)
            simulations_queued = 1

        return {
            "districts_synced": len(synced_districts),
            "synced": synced_districts,
            "sync_timestamp": sync_timestamp,
            "simulations_queued": simulations_queued,
        }
