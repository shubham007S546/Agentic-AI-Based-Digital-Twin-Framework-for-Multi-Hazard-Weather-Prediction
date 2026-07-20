"""
FastAPI entrypoint for the Digital Twin Agent (Agent 5 of 8).

Run with:
    uvicorn agents.digital_twin.main:app --reload --port 8004

Endpoints (matching the architecture diagram):
    POST /api/v1/digital-twin/scenario
    GET  /api/v1/digital-twin/layers
    GET  /api/v1/digital-twin/scenario/{scenario_id}
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .graph import digital_twin_graph
from .logging_config import get_logger
from .schemas import ScenarioRequest, ScenarioResponse
from .storage import twin_state_store
from .twin_state import load_twin_state

logger = get_logger(__name__)

app = FastAPI(
    title="Digital Twin Agent",
    description="Agent 5 of 8 -- geospatial simulation & scenario analysis (flood/landslide what-if modeling).",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/v1/digital-twin/scenario", response_model=ScenarioResponse)
def run_scenario(request: ScenarioRequest) -> ScenarioResponse:
    try:
        initial_state = {"request": request.model_dump(), "errors": []}
        final_state = digital_twin_graph.invoke(initial_state)
        return ScenarioResponse(**final_state["response"])
    except Exception as exc:
        logger.exception("Scenario simulation failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/digital-twin/layers")
def get_layers(district: str) -> dict:
    twin = load_twin_state(district)
    return {"district": district, "layers": twin["layers"], "boundary_area_km2": twin["boundary_area_km2"]}


@app.get("/api/v1/digital-twin/scenario/{scenario_id}")
def get_scenario(scenario_id: str) -> dict:
    record = twin_state_store.get(scenario_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    return record


@app.get("/api/v1/digital-twin/scenarios/recent")
def recent_scenarios(limit: int = 20) -> list:
    return twin_state_store.list_recent(limit)
