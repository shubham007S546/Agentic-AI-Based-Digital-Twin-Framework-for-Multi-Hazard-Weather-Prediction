"""
app/services/twin_service_impl.py
─────────────────────────────────
Digital Twin Service Implementation.
Coordinates TwinState snapshots and simulation runs.

Integration strategy:
  1. run_simulation() tries the standalone Digital Twin Agent (port 8004)
     first, because it implements a full LangGraph 7-step workflow with
     Rational-Method hydrology and Caine-1980 landslide thresholds.
  2. If the agent is unreachable it falls back to the local ML predictors
     (RainfallPredictor, LandslidePredictor, FloodPredictor) so the service
     always returns a result even when the agent sidecar is not running.
  3. synchronize_state() likewise enriches the TwinState with data from the
     Digital Twin Agent when available.

Set DIGITAL_TWIN_AGENT_URL (default: http://localhost:8004) to point at the
running agent instance (or the Docker service name when using compose).
"""

import asyncio
import os
import uuid
from datetime import UTC, datetime
from typing import Any, Optional

import httpx
import structlog

from app.core.enums import District, SimulationStatus
from app.exceptions.base import AppException
from app.models.digital_twin import Simulation, TwinState
from app.repositories.interfaces.twin_repo import ITwinRepository
from app.services.interfaces.twin_service import ITwinService
from app.services.interfaces.weather_service import IWeatherService
from app.schemas.digital_twin import SimulationCreateRequest

logger = structlog.get_logger(__name__)

_DIGITAL_TWIN_AGENT_URL = os.getenv("DIGITAL_TWIN_AGENT_URL", "http://localhost:8004")
_AGENT_TIMEOUT = float(os.getenv("AGENT_REQUEST_TIMEOUT_SECONDS", "30"))


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
        Builds a new TwinState snapshot by querying the latest weather data,
        then enriches it with hydrological/geological data from the Digital
        Twin Agent (if reachable).
        """
        obs = await self.weather_service.get_latest_observation(district)

        weather_state = {
            "temperature_2m": obs.temperature_2m if obs else 20.0,
            "precipitation_mm": obs.precipitation if obs else 0.0,
            "humidity_percent": obs.relative_humidity_2m if obs else 50.0,
            "wind_speed_kmh": obs.wind_speed_10m if obs else 5.0,
            "soil_moisture": obs.soil_moisture_0_to_7cm if obs else 0.3,
        }

        # Default stubs — overridden by Digital Twin Agent data when available
        hydrological_state: dict[str, Any] = {"river_level_m": 2.5, "discharge_m3s": 120.0}
        geological_state: dict[str, Any] = {"slope_stability_index": 0.85}
        infrastructure_state: dict[str, Any] = {
            "road_network_status": "OPEN",
            "power_grid_load": 0.7,
        }

        # Enrich from Digital Twin Agent
        try:
            async with httpx.AsyncClient(timeout=_AGENT_TIMEOUT) as client:
                resp = await client.post(
                    f"{_DIGITAL_TWIN_AGENT_URL}/api/v1/digital-twin/scenario",
                    json={
                        "query": (
                            f"What is the current hydrological and geological state "
                            f"for district {district.name}?"
                        ),
                        "district": district.name,
                        "precipitation_mm": weather_state["precipitation_mm"],
                    },
                )
                resp.raise_for_status()
                agent_data = resp.json()
                # Merge agent data into our state dicts
                if "hydrological_state" in agent_data:
                    hydrological_state.update(agent_data["hydrological_state"])
                if "geological_state" in agent_data:
                    geological_state.update(agent_data["geological_state"])
                if "infrastructure_state" in agent_data:
                    infrastructure_state.update(agent_data["infrastructure_state"])
                logger.info(
                    "Digital Twin Agent enriched state",
                    district=district.name,
                )
        except Exception as exc:
            logger.warning(
                "Digital Twin Agent not reachable — using default stubs",
                district=district.name,
                error=str(exc),
            )

        state = TwinState(
            district=district,
            timestamp=datetime.now(UTC),
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

        results: dict[str, Any] = {}

        # ── Strategy 1: Call the standalone Digital Twin Agent ────────────────
        # The agent implements a full LangGraph workflow with Rational-Method
        # hydrology and Caine-1980 landslide thresholds — richer than our ML
        # predictor stubs.
        try:
            logger.info(
                "Calling Digital Twin Agent",
                simulation_id=str(simulation.id),
                url=_DIGITAL_TWIN_AGENT_URL,
            )
            params = simulation.scenario_parameters or {}
            precip_mult = float(params.get("precipitation_multiplier", 1.0))

            async with httpx.AsyncClient(timeout=_AGENT_TIMEOUT) as client:
                resp = await client.post(
                    f"{_DIGITAL_TWIN_AGENT_URL}/api/v1/digital-twin/scenario",
                    json={
                        "query": (
                            f"Simulate what happens to {simulation.district.name} district "
                            f"if precipitation increases by {precip_mult}x. "
                            "Include flood severity, peak discharge, landslide risk, "
                            "infrastructure impact, and recommended actions."
                        ),
                        "district": simulation.district.name,
                        **params,
                    },
                )
                resp.raise_for_status()
                agent_data = resp.json()
                results = {
                    "source": "digital_twin_agent",
                    "agent_response": agent_data.get("response", ""),
                    "flood_severity": agent_data.get("flood_severity", "unknown"),
                    "peak_discharge_m3s": agent_data.get("peak_discharge_m3s"),
                    "flood_depth_m": agent_data.get("flood_depth_m"),
                    "landslide_probability": agent_data.get("landslide_probability"),
                    "infrastructure_impact": agent_data.get("infrastructure_impact", []),
                    "population_at_risk": agent_data.get("population_at_risk", 0),
                    "recommended_actions": agent_data.get("recommended_actions", []),
                    **{k: v for k, v in agent_data.items() if k not in results},
                }
                logger.info(
                    "Digital Twin Agent simulation succeeded",
                    simulation_id=str(simulation.id),
                )

        # ── Strategy 2: Local ML predictor fallback ───────────────────────────
        except Exception as agent_exc:
            logger.warning(
                "Digital Twin Agent unavailable — falling back to local ML predictors",
                simulation_id=str(simulation.id),
                error=str(agent_exc),
            )
            try:
                params = simulation.scenario_parameters or {}
                precip_mult = float(params.get("precipitation_multiplier", 1.0))
                temp_delta = float(params.get("temperature_delta", 0.0))

                from app.ml.inference.rainfall_model import RainfallPredictor
                from app.ml.inference.landslide_model import (
                    LandslidePredictor,
                    FloodPredictor,
                    CloudburstPredictor,
                )

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
                    "source": "local_ml_predictors",
                    "projected_rainfall_mm": rf_res["precipitation_mm"],
                    "projected_river_level_m": round(
                        2.1 + (fl_res["flood_risk_index"] * 3.5), 2
                    ),
                    "landslide_probability": ls_res["risk_score"],
                    "landslide_risk_level": ls_res["risk_level"],
                    "cloudburst_probability": cb_res["cloudburst_probability"],
                    "flood_risk_index": fl_res["flood_risk_index"],
                    "infrastructure_impact": (
                        "CRITICAL"
                        if ls_res["risk_score"] > 0.7 or fl_res["flood_risk_index"] > 0.7
                        else "MODERATE" if precip_mult > 1.5
                        else "NOMINAL"
                    ),
                    "model_ensemble": [
                        "XGBoost_Rainfall",
                        "Geotech_Landslide",
                        "Catchment_Flood",
                    ],
                }
            except Exception as ml_exc:
                logger.error(
                    "Local ML predictors also failed",
                    simulation_id=str(simulation.id),
                    error=str(ml_exc),
                )
                simulation.status = SimulationStatus.FAILED
                simulation.error_message = (
                    f"Digital Twin Agent: {agent_exc}; Local ML: {ml_exc}"
                )
                simulation.completed_at = datetime.now(UTC)
                await self.twin_repo.update_simulation(simulation)
                return simulation

        simulation.simulation_results = results
        simulation.status = SimulationStatus.COMPLETED
        simulation.completed_at = datetime.now(UTC)
        await self.twin_repo.update_simulation(simulation)
        return simulation
