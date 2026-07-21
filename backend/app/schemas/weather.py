"""
app/schemas/weather.py
──────────────────────
Pydantic schemas for Weather data.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import District, WeatherQuality, WeatherSource


class WeatherObservationResponse(BaseModel):
    """Schema for returning a weather observation to the client."""
    
    id: uuid.UUID
    district: District
    source: WeatherSource
    timestamp: datetime
    
    temperature_2m: float | None = Field(None, description="Temperature in Celsius")
    relative_humidity_2m: float | None = Field(None, description="Relative humidity %")
    surface_pressure: float | None = Field(None, description="Surface pressure in hPa")
    wind_speed_10m: float | None = Field(None, description="Wind speed km/h")
    wind_direction_10m: float | None = Field(None, description="Wind direction degrees")
    precipitation: float | None = Field(None, description="Precipitation in mm")
    cloud_cover: float | None = Field(None, description="Cloud cover %")
    soil_moisture: float | None = Field(None, description="Soil moisture m3/m3")
    
    quality_flag: WeatherQuality
    
    model_config = ConfigDict(from_attributes=True)
