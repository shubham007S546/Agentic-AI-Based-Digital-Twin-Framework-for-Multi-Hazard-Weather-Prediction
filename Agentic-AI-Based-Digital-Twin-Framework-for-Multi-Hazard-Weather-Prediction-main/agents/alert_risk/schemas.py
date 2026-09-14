"""Request/response schemas for the Alert & Risk Assessment Agent."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field

SEVERITY_LEVELS = ["green", "yellow", "orange", "red"]

SEVERITY_DESCRIPTIONS = {
    "red": "Severe threat to life & critical infrastructure. Immediate action required.",
    "orange": "High probability & potential impact. Prepare & act.",
    "yellow": "Possible impact. Stay updated.",
    "green": "No immediate threat. Normal monitoring.",
}


class AlertRequest(BaseModel):
    location: str = Field(..., description="e.g. 'Mandi, Himachal Pradesh'")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    district: Optional[str] = None
    hazard_types: List[str] = Field(
        default_factory=lambda: ["rainfall", "cloudburst", "landslide", "flood"]
    )
    horizon: str = Field("24h", description="e.g. 'now', '6h', '24h', '72h'")

    # If the caller (e.g. the Orchestrator, or a test) already has fresh
    # prediction/weather data, it can pass it directly here instead of this
    # agent calling out to Agent 2/Agent 3 itself. Either path works --
    # see clients.py.
    prediction_override: Optional[Dict[str, Any]] = None
    weather_override: Optional[Dict[str, Any]] = None

    notify: bool = Field(True, description="Whether to attempt notification/escalation for this alert.")
    user_role: Optional[str] = None  # e.g. "citizen", "disaster_officer" -- affects notification routing


class RiskAssessment(BaseModel):
    risk_score: float          # 0-1 composite score
    severity: str               # "red" | "orange" | "yellow" | "green"
    contributing_factors: Dict[str, float]   # factor name -> its contribution to risk_score
    data_completeness: float    # 0-1, how much of the intended input data was actually real vs. stubbed/missing


class ImpactAssessment(BaseModel):
    status: str  # "ok" | "stub"
    affected_population_estimate: Optional[int] = None
    critical_infrastructure_at_risk: List[str] = Field(default_factory=list)
    note: Optional[str] = None


class NotificationResult(BaseModel):
    channel: str
    status: str  # "sent" | "stub" | "error" | "skipped"
    note: Optional[str] = None


class AlertResult(BaseModel):
    alert_id: str
    type: str                       # hazard type this alert is for, e.g. "Cloudburst"
    severity: str                    # "Red" | "Orange" | "Yellow" | "Green"
    region: str
    risk_score: float
    probability: Optional[float] = None
    valid_from: str
    valid_to: str
    description: str
    recommended_actions: List[str]
    impact: ImpactAssessment
    escalated: bool
    notifications: List[NotificationResult]
    data_sources_used: List[str]
    notes: List[str] = Field(default_factory=list)


class AlertState(TypedDict, total=False):
    request: Dict[str, Any]
    predictions: Dict[str, Any]
    weather: Dict[str, Any]
    external_feeds: Dict[str, Any]
    data_sources_used: List[str]
    triggers: List[Dict[str, Any]]
    risk_assessment: Dict[str, Any]
    impact_assessment: Dict[str, Any]
    alert: Dict[str, Any]
    notifications: List[Dict[str, Any]]
    errors: List[str]
