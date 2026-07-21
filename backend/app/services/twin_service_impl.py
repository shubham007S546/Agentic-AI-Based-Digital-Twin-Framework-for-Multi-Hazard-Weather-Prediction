"""
app/services/twin_service_impl.py
─────────────────────────────────
Digital Twin Service Implementation.
Coordinates TwinState snapshots and simulation runs.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Optional

import structlog

from app.core.enums import District, SimulationStatus
from app.exceptions.base import AppException
from app.models.digital_twin import Simulation, TwinState
from app.repositories.interfaces.twin_repo import ITwinRepository
from app.services.interfaces.twin_service import ITwinService
from app.services.interfaces.weather_service import IWeatherService
from app.schemas.digital_twin import SimulationCreateRequest

logger = structlog.get_logger(__name__)


class TwinServiceImpl(ITwinService):
    def __init__(
        self,
        twin_repo: ITwinRepository,
        weather_service: IWeatherService,
    ):
        self.twin_repo = twin_repo
        self.weather_service = weather_service

    async def get_current_state(self, district: District) -> TwinState:
        state = await self.twin_repo.get_latest_state(district)
        if not state:
            logger.info("No twin state found, triggering initial sync", district=district.name)
            state = await self.synchronize_state(district)
        return state

    async def synchronize_state(self, district: District) -> TwinState:
        """
        Builds a new TwinState snapshot by querying the latest weather data.
        """
        # Fetch current real-world weather data for the district
        # If none exists, this will trigger a live API poll inside WeatherService
        obs = await self.weather_service.get_latest_observation(district)

        weather_state = {
            "temperature_2m": obs.temperature_2m if obs else 20.0,
            "precipitation_mm": obs.precipitation if obs else 0.0,
            "humidity_percent": obs.relative_humidity_2m if obs else 50.0,
            "wind_speed_kmh": obs.wind_speed_10m if obs else 5.0,
            "soil_moisture": obs.soil_moisture_0_to_7cm if obs else 0.3,
        }

        # Stubs for other domains (to be populated by real agents/collectors later)
        hydrological_state = {"river_level_m": 2.5, "discharge_m3s": 120.0}
        geological_state = {"slope_stability_index": 0.85}
        infrastructure_state = {"road_network_status": "OPEN", "power_grid_load": 0.7}

        state = TwinState(
            district=district,
            weather_state=weather_state,
            hydrological_state=hydrological_state,
            geological_state=geological_state,
            infrastructure_state=infrastructure_state,
        )

        return await self.twin_repo.create_state(state)

    async def create_simulation(
        self, request: SimulationCreateRequest, created_by: Optional[uuid.UUID]
    ) -> Simulation:
        
        # Ensure a baseline state exists
        baseline_state = await self.get_current_state(request.district)

        simulation = Simulation(
            name=request.name,
            description=request.description,
            created_by=created_by,
            district=request.district,
            status=SimulationStatus.PENDING,
            baseline_state_id=baseline_state.id,
            scenario_parameters=request.scenario_parameters,
        )

        return await self.twin_repo.create_simulation(simulation)

    async def run_simulation(self, simulation_id: uuid.UUID) -> Simulation:
        simulation = await self.twin_repo.get_simulation(simulation_id)
        if not simulation:
            raise AppException(f"Simulation not found: {simulation_id}")

        if simulation.status != SimulationStatus.PENDING:
            raise AppException(f"Cannot run simulation with status {simulation.status.name}")

        simulation.status = SimulationStatus.RUNNING
        simulation.started_at = datetime.now(UTC)
        await self.twin_repo.update_simulation(simulation)

        try:
            # --- Stub for actual ML / physics simulation engine ---
            logger.info("Executing simulation", simulation_id=str(simulation.id))
            await asyncio.sleep(2)  # Simulate compute time
            
            # Extract scenario parameters
            params = simulation.scenario_parameters
            precip_multiplier = params.get("precipitation_multiplier", 1.0)
            
            # Dummy logic: heavy rain = flood risk
            results = {
                "projected_river_level_m": 2.5 + (1.5 * precip_multiplier),
                "landslide_probability": min(1.0, 0.2 * precip_multiplier),
                "infrastructure_impact": "SEVERE" if precip_multiplier >= 3.0 else "NOMINAL",
            }
            
            simulation.simulation_results = results
            simulation.status = SimulationStatus.COMPLETED
            
        except Exception as exc:
            logger.error("Simulation failed", error=str(exc))
            simulation.status = SimulationStatus.FAILED
            simulation.error_message = str(exc)
            
        finally:
            simulation.completed_at = datetime.now(UTC)
            await self.twin_repo.update_simulation(simulation)

        return simulation
