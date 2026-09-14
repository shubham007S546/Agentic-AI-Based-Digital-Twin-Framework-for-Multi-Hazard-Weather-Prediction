"""Request/response schemas for the Report Generation Agent."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field

REPORT_TYPES = [
    "daily_weather", "rainfall_forecast", "multi_hazard", "district_risk",
    "infrastructure_impact", "event_summary", "seasonal_outlook", "custom",
]
REPORT_FORMATS = ["pdf", "excel", "json", "dashboard"]


class ReportRequest(BaseModel):
    report_type: str = Field(..., description=f"One of {REPORT_TYPES}")
    districts: List[str] = Field(default_factory=lambda: ["Mandi"])
    format: str = Field("pdf", description=f"One of {REPORT_FORMATS}")
    horizon: str = Field("24h", description="Forecast horizon for weather/rainfall data, e.g. '24h', '72h'.")
    include_charts: bool = True
    user_role: Optional[str] = None
    distribute: bool = False
    notification_channels: List[str] = Field(default_factory=list)

    # Optional overrides -- if the caller already has fresh data, skip
    # re-fetching from the other agents (same pattern as Agent 4).
    data_override: Optional[Dict[str, Any]] = None


class ReportSection(BaseModel):
    title: str
    kind: str  # "text" | "table" | "chart"
    content: Any


class ReportMetadata(BaseModel):
    report_id: str
    report_type: str
    format: str
    version: int
    generated_at: str
    districts: List[str]
    data_sources_used: List[str]
    data_completeness: float


class DistributionResult(BaseModel):
    channel: str
    status: str  # "sent" | "stub" | "skipped" | "error"
    note: Optional[str] = None


class ReportResult(BaseModel):
    metadata: ReportMetadata
    summary: str
    key_insights: List[str]
    sections: List[ReportSection]
    file_path: Optional[str] = None
    download_url: Optional[str] = None
    distribution: List[DistributionResult]
    notes: List[str] = Field(default_factory=list)


class ReportState(TypedDict, total=False):
    request: Dict[str, Any]
    collected_data: Dict[str, Any]
    data_sources_used: List[str]
    data_completeness: float
    analysis: Dict[str, Any]
    insights: List[str]
    sections: List[Dict[str, Any]]
    summary: str
    report_id: str
    version: int
    file_path: Optional[str]
    metadata: Dict[str, Any]
    distribution: List[Dict[str, Any]]
    result: Dict[str, Any]
    errors: List[str]
