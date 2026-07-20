"""
app/schemas/prediction.py
─────────────────────────
Pydantic schemas for ML predictions.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.core.enums import District, HazardType, PredictionStatus, PredictionType


class PredictionRunRequest(BaseModel):
    """Payload to trigger a new prediction manually."""
    
    district: District
    hazard_type: HazardType
    prediction_type: PredictionType = PredictionType.ONLINE
    
    # Optional manual overrides. If omitted, the service will fetch 
    # the latest weather data from the DB for the district.
    features: dict[str, Any] | None = None


class PredictionResponse(BaseModel):
    """API response for a prediction log."""
    
    id: uuid.UUID
    triggered_by: str
    model_name: str
    model_version: str
    
    district: District
    hazard_type: HazardType
    prediction_type: PredictionType
    status: PredictionStatus
    
    input_features: dict[str, Any]
    prediction_result: dict[str, Any] | None
    
    confidence: float | None
    inference_time_ms: float | None
    error_message: str | None
    
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class BatchPredictionRunRequest(BaseModel):
    """Payload to trigger multiple predictions in a single batch request."""
    
    requests: list[PredictionRunRequest]


class BatchPredictionResponse(BaseModel):
    """API response for a batch prediction execution."""
    
    predictions: list[PredictionResponse]

