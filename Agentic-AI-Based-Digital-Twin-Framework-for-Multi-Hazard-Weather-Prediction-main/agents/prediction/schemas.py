"""
Request/response schemas, plus the feature-schema constants this agent was
built against.

IMPORTANT -- read before trusting real predictions
----------------------------------------------------
FEATURE_COLUMNS below is reconstructed from the column names/values you
showed me from your actual `ml_ready/X_train.csv` (35 columns, z-scored).
`feature_builder.py` computes each of these from raw hourly weather
readings using standard definitions (rolling sums, lags, cyclical time
encoding, etc.) -- but I have NOT seen your actual `final_preprocessing.py`
feature-engineering code, only its docstring/header. So treat
`feature_builder.py` as a **best-effort reconstruction**: verify each
formula against your real preprocessing code before trusting predictions
for anything beyond testing the pipeline end-to-end. Where I had to guess
(e.g. `precip_acceleration`, `season` encoding, `is_monsoon` month range),
it's flagged with a comment in feature_builder.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field

# Exact column order your model was trained on (from your X_train.csv).
FEATURE_COLUMNS: List[str] = [
    "temperature_2m", "dewpoint_2m", "relative_humidity", "surface_pressure",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "wind_u_10m", "wind_v_10m",
    "cloud_cover", "cape", "precipitation_openmeteo", "rain_openmeteo", "snowfall",
    "rolling_precip_3h", "rolling_precip_6h", "rolling_precip_24h", "rolling_precip_72h",
    "precip_lag_1h", "precip_lag_3h", "precip_lag_6h",
    "temp_dewpoint_spread", "wind_gust_ratio", "precip_acceleration",
    "humidity_cape_interact", "rolling_ratio_3_24",
    "hour_sin", "hour_cos", "month_sin", "month_cos",
    "hour", "month", "day_of_year", "season", "is_monsoon",
]

# Raw hourly reading fields feature_builder.py needs to derive the above.
RAW_READING_FIELDS: List[str] = [
    "timestamp", "temperature_2m", "dewpoint_2m", "relative_humidity",
    "surface_pressure", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
    "cloud_cover", "cape", "precipitation_openmeteo", "rain_openmeteo", "snowfall",
]


class RawHourlyReading(BaseModel):
    """One hour of raw (unscaled) observed/forecast weather -- e.g. from the
    Weather Analysis Agent, or IMD/ERA5/OpenMeteo directly."""

    timestamp: str  # ISO8601
    temperature_2m: float
    dewpoint_2m: float
    relative_humidity: float
    surface_pressure: float
    wind_speed_10m: float
    wind_direction_10m: float
    wind_gusts_10m: float
    cloud_cover: float
    cape: float
    precipitation_openmeteo: float
    rain_openmeteo: float
    snowfall: float = 0.0


class PredictionRequest(BaseModel):
    hazard_type: str = Field(..., description="'rainfall' | 'cloudburst' | 'landslide'")
    location: str = Field(..., description="e.g. 'Mandi, Himachal Pradesh'")
    target_timestamp: str = Field(..., description="ISO8601 timestamp being predicted for")
    horizon: str = Field("24h", description="e.g. '1h', '6h', '24h', '72h', '7d'")
    # Provide at least `sequence_length` hours of history (most recent last),
    # ending at or before target_timestamp, so rolling/lag features can be computed.
    history: List[RawHourlyReading] = Field(default_factory=list)


class PredictionResult(BaseModel):
    hazard: str
    location: str
    unit: Optional[str] = None
    timestamp: str
    horizon: str
    prediction: Optional[float] = None
    probability: Optional[float] = None
    confidence: float
    is_extreme_event: bool
    model: Dict[str, Any]
    explanation_url: Optional[str] = None
    status: str  # "ok" | "stub" | "error"
    notes: List[str] = Field(default_factory=list)


class PredictionState(TypedDict, total=False):
    request: Dict[str, Any]
    features: Dict[str, float]
    feature_warnings: List[str]
    model_info: Dict[str, Any]
    raw_prediction: Dict[str, Any]
    result: Dict[str, Any]
    errors: List[str]
