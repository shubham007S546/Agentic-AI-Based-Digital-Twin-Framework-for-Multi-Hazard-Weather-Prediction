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
            logger.info("Executing simulation via ML engines", simulation_id=str(simulation.id))
            
            # Extract scenario parameters
            params = simulation.scenario_parameters or {}
            precip_mult = float(params.get("precipitation_multiplier", 1.0))
            temp_delta = float(params.get("temperature_delta", 0.0))

            from app.ml.inference.rainfall_model import RainfallPredictor
            from app.ml.inference.landslide_model import LandslidePredictor, FloodPredictor, CloudburstPredictor

            rf_predictor = RainfallPredictor()
            ls_predictor = LandslidePredictor()
            fl_predictor = FloodPredictor()
            cb_predictor = CloudburstPredictor()

            await rf_predictor.load()
            await ls_predictor.load()
            await fl_predictor.load()

            sim_features = {
                "temperature_2m": 22.0 + temp_delta,
                "relative_humidity_2m": min(100.0, 70.0 * precip_mult),
                "cloud_cover": min(100.0, 60.0 * precip_mult),
                "precipitation": 15.0 * precip_mult,
                "rolling_precip_72h": 45.0 * precip_mult,
                "soil_moisture": min(1.0, 0.45 * precip_mult),
                "slope_degrees": 32.0,
            }

            rf_res = await rf_predictor.predict(sim_features)
            ls_res = await ls_predictor.predict(sim_features)
            fl_res = await fl_predictor.predict(sim_features)
            cb_res = await cb_predictor.predict(sim_features)

            results = {
                "projected_rainfall_mm": rf_res["precipitation_mm"],
                "projected_river_level_m": round(2.1 + (fl_res["flood_risk_index"] * 3.5), 2),
                "landslide_probability": ls_res["risk_score"],
                "landslide_risk_level": ls_res["risk_level"],
                "cloudburst_probability": cb_res["cloudburst_probability"],
                "flood_risk_index": fl_res["flood_risk_index"],
                "infrastructure_impact": "CRITICAL" if ls_res["risk_score"] > 0.7 or fl_res["flood_risk_index"] > 0.7 else "MODERATE" if precip_mult > 1.5 else "NOMINAL",
                "model_ensemble": ["XGBoost_Rainfall", "Geotech_Landslide", "Catchment_Flood"]
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
