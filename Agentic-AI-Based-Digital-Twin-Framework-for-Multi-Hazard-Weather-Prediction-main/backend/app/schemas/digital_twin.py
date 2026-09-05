"""
app/schemas/digital_twin.py
───────────────────────────
Pydantic schemas for Digital Twin states and Simulations.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import District, SimulationStatus


# ── Twin State Schemas ────────────────────────────────────────────────────────

class TwinStateResponse(BaseModel):
    id: uuid.UUID
    district: District
    timestamp: datetime
    
    weather_state: dict[str, Any]
    hydrological_state: dict[str, Any]
    geological_state: dict[str, Any]
    infrastructure_state: dict[str, Any]
    
    is_latest: bool
    
    model_config = ConfigDict(from_attributes=True)


# ── Simulation Schemas ────────────────────────────────────────────────────────

class SimulationCreateRequest(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = Field(None, max_length=1000)
    district: District
    
    # E.g., {"precipitation_multiplier": 2.5, "temperature_offset": 5.0}
    scenario_parameters: dict[str, Any]


class SimulationResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_by: uuid.UUID | None
    district: District
    status: SimulationStatus
    
    baseline_state_id: uuid.UUID
    scenario_parameters: dict[str, Any]
    simulation_results: dict[str, Any] | None
    
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    
    model_config = ConfigDict(from_attributes=True)
