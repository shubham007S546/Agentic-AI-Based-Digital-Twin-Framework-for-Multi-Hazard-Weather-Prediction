"""
app/schemas/alert.py
────────────────────
Pydantic schemas for the Alert and Early Warning domain.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import AlertSeverity, AlertStatus, District, HazardType


class AlertCreateRequest(BaseModel):
    district: District
    hazard_type: HazardType
    severity: AlertSeverity
    title: str = Field(..., max_length=255)
    description: str
    
    # Context regarding what triggered the alert (e.g., prediction ID, simulation ID)
    source_context: dict[str, Any] = Field(default_factory=dict)
    
    # E.g., evacuation routes, emergency contacts
    recommended_actions: dict[str, Any] = Field(default_factory=dict)


class AlertUpdateRequest(BaseModel):
    status: AlertStatus
    resolution_notes: str | None = None


class AlertResponse(BaseModel):
    id: uuid.UUID
    district: District
    hazard_type: HazardType
    severity: AlertSeverity
    status: AlertStatus
    
    title: str
    description: str
    source_context: dict[str, Any]
    recommended_actions: dict[str, Any]
    resolution_notes: str | None
    
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
