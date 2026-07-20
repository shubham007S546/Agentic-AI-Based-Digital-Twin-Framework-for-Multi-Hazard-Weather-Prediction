"""
The Digital Twin Agent's LangGraph state machine -- implements the
diagram's 7-step workflow (combined into 5 nodes for a cleaner state
machine; each still corresponds 1:1 to a diagram step):

    1. Receive request           -> (entry, see main.py)
    2. Load twin state            -> load_state
    3. Prepare simulation inputs  -> prepare_inputs
    4. Run simulation             -> run_simulation
    5. Analyze results            -> (part of run_simulation)
    6. Visualize & map            -> visualize
    7. Update twin state           -> update_and_finalize
"""

from __future__ import annotations

from typing import Any, Dict

from langgraph.graph import END, StateGraph

from .config import settings
from .hydrology_model import run_flood_model
from .impact_model import assess_impact
from .landslide_model import run_landslide_model
from .logging_config import get_logger
from .schemas import TwinState
from .storage import twin_state_store
from .twin_state import load_twin_state
from .visualization import build_visualization

logger = get_logger(__name__)


def load_state(state: TwinState) -> TwinState:
    request = state["request"]
    twin = load_twin_state(request["district"])
    return {**state, "layers": twin["layers"], "boundary_area_km2": twin["boundary_area_km2"],
            "bridges": twin["bridges"], "roads": twin["roads"]}


def prepare_inputs(state: TwinState) -> TwinState:
    request = state["request"]
    boundary_area = state.get("boundary_area_km2")

    inputs = {
        "rainfall_mm": request["rainfall_mm"],
        "duration_hours": request.get("duration_hours", 24.0),
        "catchment_area_km2": request.get("catchment_area_km2") or settings.default_catchment_area_km2,
        "runoff_coefficient": request.get("runoff_coefficient") or settings.default_runoff_coefficient,
        "channel_capacity_m3s": settings.default_channel_capacity_m3s,
        "boundary_area_km2": boundary_area or settings.default_catchment_area_km2,
    }
    logger.info("Prepared simulation inputs for %s: %s", request["district"], inputs)
    return {**state, "simulation_inputs": inputs}


def run_simulation(state: TwinState) -> TwinState:
    request = state["request"]
    inputs = state["simulation_inputs"]
    hazard_types = request.get("hazard_types", ["flood", "landslide"])

    flood_result = None
    if "flood" in hazard_types:
        flood_result = run_flood_model(
            rainfall_mm=inputs["rainfall_mm"], duration_hours=inputs["duration_hours"],
            catchment_area_km2=inputs["catchment_area_km2"], runoff_coefficient=inputs["runoff_coefficient"],
            channel_capacity_m3s=inputs["channel_capacity_m3s"], boundary_area_km2=inputs["boundary_area_km2"],
        )

    landslide_result = None
    if "landslide" in hazard_types:
        landslide_result = run_landslide_model(inputs["rainfall_mm"], inputs["duration_hours"])

    flood_severity = 0.0
    if flood_result and flood_result["channel_capacity_exceeded"]:
        flood_severity = min(
            (flood_result["peak_discharge_m3s"] - flood_result["channel_capacity_m3s"])
            / flood_result["channel_capacity_m3s"], 1.0,
        )
    landslide_severity = landslide_result["susceptibility_score"] if landslide_result else 0.0
    composite_severity = max(flood_severity, landslide_severity)

    if composite_severity >= 0.75:
        risk_level = "Extreme"
    elif composite_severity >= 0.5:
        risk_level = "High"
    elif composite_severity >= 0.25:
        risk_level = "Moderate"
    else:
        risk_level = "Low"

    impact_result = assess_impact(state.get("bridges"), state.get("roads"), composite_severity)

    return {**state, "flood_result": flood_result, "landslide_result": landslide_result,
            "impact_result": impact_result, "risk_level": risk_level, "composite_severity": composite_severity}


def visualize(state: TwinState) -> TwinState:
    request = state["request"]
    visualization = build_visualization(
        request["district"], state["risk_level"], state.get("flood_result"), state.get("landslide_result"),
    )
    return {**state, "visualization": visualization}


def update_and_finalize(state: TwinState) -> TwinState:
    request = state["request"]
    response = {
        "district": request["district"],
        "rainfall_mm": request["rainfall_mm"],
        "duration_hours": request.get("duration_hours", 24.0),
        "risk_level": state["risk_level"],
        "flood": state.get("flood_result"),
        "landslide": state.get("landslide_result"),
        "impact": state["impact_result"],
        "layers_used": state["layers"],
        "visualization": state["visualization"],
        "notes": [f"composite_severity={state['composite_severity']:.2f}"],
    }
    scenario_id = twin_state_store.save(response)
    response["scenario_id"] = scenario_id

    logger.info("Scenario %s complete for %s | risk_level=%s", scenario_id, request["district"], state["risk_level"])
    return {**state, "response": response}


def build_digital_twin_graph():
    graph = StateGraph(TwinState)

    graph.add_node("load_state", load_state)
    graph.add_node("prepare_inputs", prepare_inputs)
    graph.add_node("run_simulation", run_simulation)
    graph.add_node("visualize", visualize)
    graph.add_node("update_and_finalize", update_and_finalize)

    graph.set_entry_point("load_state")
    graph.add_edge("load_state", "prepare_inputs")
    graph.add_edge("prepare_inputs", "run_simulation")
    graph.add_edge("run_simulation", "visualize")
    graph.add_edge("visualize", "update_and_finalize")
    graph.add_edge("update_and_finalize", END)

    return graph.compile()


digital_twin_graph = build_digital_twin_graph()
