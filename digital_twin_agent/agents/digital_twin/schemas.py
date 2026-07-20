"""Request/response schemas for the Digital Twin Agent."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field


class ScenarioRequest(BaseModel):
    district: str = Field(..., description="e.g. 'Mandi', 'Kullu', 'Chamba'")
    rainfall_mm: float = Field(..., description="Total rainfall for the scenario window, e.g. 150 for '150mm in 24h'")
    duration_hours: float = Field(24.0, description="Duration the rainfall_mm falls over.")
    hazard_types: List[str] = Field(default_factory=lambda: ["flood", "landslide"])
    catchment_area_km2: Optional[float] = Field(
        None, description="Override the default catchment area for this district if you have a real DEM-derived value."
    )
    runoff_coefficient: Optional[float] = Field(
        None, description="Override the default runoff coefficient if calibrated for this district."
    )


class TwinLayerStatus(BaseModel):
    layer: str
    status: str  # "loaded" | "default" | "unavailable"
    source: Optional[str] = None
    detail: Optional[str] = None


class FloodResult(BaseModel):
    method: str
    peak_discharge_m3s: float
    channel_capacity_m3s: float
    channel_capacity_exceeded: bool
    affected_area_sq_km: float
    max_water_depth_m: float
    assumptions: List[str]


class LandslideResult(BaseModel):
    method: str
    rainfall_intensity_mm_hr: float
    threshold_intensity_mm_hr: float
    threshold_exceeded: bool
    susceptibility_score: float  # 0-1
    slope_class: str
    assumptions: List[str]


class ImpactResult(BaseModel):
    status: str  # "ok" | "stub"
    bridges_at_risk: Optional[int] = None
    roads_at_risk: Optional[int] = None
    population_at_risk: Optional[int] = None
    note: Optional[str] = None


class ScenarioResponse(BaseModel):
    scenario_id: Optional[str] = None
    district: str
    rainfall_mm: float
    duration_hours: float
    risk_level: str  # "Low" | "Moderate" | "High" | "Extreme"
    flood: Optional[FloodResult] = None
    landslide: Optional[LandslideResult] = None
    impact: ImpactResult
    layers_used: List[TwinLayerStatus]
    visualization: Dict[str, Any]
    notes: List[str] = Field(default_factory=list)


class TwinState(TypedDict, total=False):
    request: Dict[str, Any]
    layers: List[Dict[str, Any]]
    boundary_area_km2: Optional[float]
    bridges: Optional[List[dict]]
    roads: Optional[List[dict]]
    simulation_inputs: Dict[str, Any]
    flood_result: Dict[str, Any]
    landslide_result: Dict[str, Any]
    impact_result: Dict[str, Any]
    risk_level: str
    composite_severity: float
    visualization: Dict[str, Any]
    response: Dict[str, Any]
    errors: List[str]
