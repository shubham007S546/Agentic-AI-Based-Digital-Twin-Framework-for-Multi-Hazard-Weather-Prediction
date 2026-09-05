"""
app/schemas/report.py
──────────────────────
Pydantic schemas for automated Reports.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import District


class ReportCreateRequest(BaseModel):
    title: str = Field(..., max_length=255)
    report_type: str = Field(..., max_length=50) # e.g. DAILY_BRIEFING, ANOMALY_REPORT
    district: District | None = None
    
    # Metadata for the report content parameters
    parameters: dict[str, str | float | int] = Field(default_factory=dict)


class ReportResponse(BaseModel):
    id: uuid.UUID
    title: str
    report_type: str
    district: District | None
    
    file_url: str | None
    generated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
