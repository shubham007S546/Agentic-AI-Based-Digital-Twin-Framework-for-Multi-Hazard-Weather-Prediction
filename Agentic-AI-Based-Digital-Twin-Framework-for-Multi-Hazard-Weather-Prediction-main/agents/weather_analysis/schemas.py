"""Request/response schemas for the Weather Analysis Agent."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field


class WeatherRequest(BaseModel):
    """Matches the diagram's 'Input from Orchestrator': location, date/time
    range, required parameters, preferred sources, resolution/forecast horizon."""

    location: str = Field(..., description="District/place name, e.g. 'Mandi'")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    forecast_hours: int = Field(24, description="How many hours ahead to forecast.")
    required_parameters: List[str] = Field(
        default_factory=lambda: ["temperature", "humidity", "rainfall", "wind_speed", "pressure", "cloud_cover"]
    )
    preferred_sources: List[str] = Field(
        default_factory=lambda: ["open_meteo", "imd", "era5", "nasa_gpm"]
    )


class CurrentConditions(BaseModel):
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    rainfall: Optional[float] = None
    wind_speed: Optional[float] = None
    pressure: Optional[float] = None
    cloud_cover: Optional[float] = None


class ForecastPoint(BaseModel):
    time: str
    rainfall: Optional[float] = None
    temp_max: Optional[float] = None
    temp_min: Optional[float] = None
    condition: Optional[str] = None


class WeatherResponse(BaseModel):
    """Matches the diagram's 'Output to Orchestrator' / example response."""

    location: str
    timestamp: str
    current: CurrentConditions
    forecast: List[ForecastPoint]
    anomalies: List[str]
    sources: List[str]
    confidence: float
    summary: str
    cached: bool = False


class WeatherAnalysisState(TypedDict, total=False):
    """Internal state threaded through the LangGraph workflow."""

    request: Dict[str, Any]
    cache_key: str
    cache_hit: bool

    provider_results: Dict[str, Dict[str, Any]]
    provider_errors: List[str]

    cleaned: Dict[str, Any]
    aggregated: Dict[str, Any]
    anomalies: List[str]
    confidence: float

    response: Dict[str, Any]
