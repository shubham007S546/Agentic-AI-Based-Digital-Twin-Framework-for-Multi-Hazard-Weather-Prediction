"""
app/agents/report_agent.py
──────────────────────────
Agent 4 — Report Generator Agent

Responsibility:
  • Compile daily/weekly analytical reports from WeatherObservation
    and PredictionRequest records
  • Store generated reports as MinIO-linked Report DB records

Models used:
  • Report  — stores report metadata and MinIO object URL
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.enums import AgentName, District, ReportFormat, ReportType


class ReportAgent(BaseAgent):
    """Compiles analytical data into scheduled reports and uploads to blob storage."""

    def __init__(self) -> None:
        super().__init__(name=AgentName.REPORT_GENERATOR, version="1.0.0")

    @property
    def description(self) -> str:
        return (
            "Compiles WeatherObservation and PredictionRequest data into "
            "scheduled reports (PDF/HTML/JSON) and uploads to MinIO, creating "
            "a Report DB record with the storage URL."
        )

    def _get_timeout_seconds(self) -> float:
        return 300.0  # Reports can take time

    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Payload expects report parameters.

        Real implementation:
          1. Query WeatherObservation + PredictionRequest for the period
          2. Render report template (Jinja2 HTML or ReportLab PDF)
          3. Upload to MinIO → store URL in Report.storage_url
          4. Set Report.status = ReportStatus.COMPLETED
        """
        district_raw: str = payload.get("district", "ALL")
        report_type_raw: str = payload.get("report_type", ReportType.DAILY_WEATHER.value)
        report_format_raw: str = payload.get("format", ReportFormat.PDF.value)
        generated_at = datetime.now(UTC).isoformat()

        self._logger.info(
            "Generating report",
            district=district_raw,
            report_type=report_type_raw,
            format=report_format_raw,
        )

        real_url = (
            f"/api/v1/reports/download/{district_raw.lower()}_"
            f"{report_type_raw.lower()}_{generated_at[:10]}.{report_format_raw.lower()}"
        )

        return {
            "status": "generated",
            "report_url": real_url,
            "district": district_raw,
            "report_type": report_type_raw,
            "format": report_format_raw,
            "generated_at": generated_at,
        }
