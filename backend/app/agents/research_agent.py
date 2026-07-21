"""
app/agents/research_agent.py
────────────────────────────
Agent 9 — Research & Analytics Agent

Responsibility:
  • Export curated datasets from WeatherObservation and PredictionRequest
    tables for academic / research consumption
  • Compute seasonal climate indices (SPI, SPEI, AMI) from historical records
  • Generate Research Export reports (CSV / XLSX / JSON) and upload to MinIO

Models used:
  • WeatherObservation  — primary historical time-series data source
  • PredictionRequest   — ML model output history (confidence, inference_time_ms)
  • Report              — stores export metadata and MinIO URL
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.enums import AgentName, District, ReportFormat, ReportType


# Climate indices that can be computed from WeatherObservation.precipitation
_COMPUTABLE_INDICES = ["SPI-1", "SPI-3", "SPI-6", "SPEI-3", "AMI"]


class ResearchAgent(BaseAgent):
    """
    Academic data export and climate index computation agent.
    Serves research workflows and ML model retraining pipelines.
    """

    def __init__(self) -> None:
        super().__init__(name=AgentName.RESEARCH, version="1.0.0")

    @property
    def description(self) -> str:
        return (
            "Exports curated WeatherObservation and PredictionRequest datasets "
            "for research use, computes climate indices (SPI, SPEI, AMI), "
            "and generates XLSX/CSV/JSON exports stored in MinIO."
        )

    def _get_timeout_seconds(self) -> float:
        return 600.0  # Large dataset exports can be slow

    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Research data pipeline.

        Real implementation:
          1. Parse date_range from payload (default: last 365 days)
          2. Query WeatherObservation for all districts in date_range
          3. Compute climate indices using scipy / statsmodels
          4. Build DataFrame → export as CSV/XLSX/JSON
          5. Upload to MinIO and create Report(type=RESEARCH_EXPORT) record
          6. Return export metadata
        """
        district_filter: str | None = payload.get("district")
        date_from: str = payload.get("date_from", "")
        date_to: str = payload.get("date_to", datetime.now(UTC).date().isoformat())
        export_format: str = payload.get("format", ReportFormat.CSV.value)
        indices: list[str] = payload.get("indices", _COMPUTABLE_INDICES[:3])

        target_districts = (
            [district_filter]
            if district_filter
            else [d.value for d in District]
        )

        self._logger.info(
            "Starting research data export",
            districts=target_districts,
            date_range=f"{date_from} → {date_to}",
            format=export_format,
            indices=indices,
        )

        computed_indices: dict[str, Any] = {}
        for idx in indices:
            for district in target_districts:
                key = f"{district}:{idx}"
                # Real: value = await climate_index_service.compute(district, idx, date_from, date_to)
                computed_indices[key] = None  # placeholder until real computation

        export_url = (
            f"s3://weather-research/exports/"
            f"{'_'.join(target_districts)}_{date_to}_research_export.{export_format.lower()}"
        )

        # Real:
        # df = await weather_repo.export_dataframe(districts=target_districts, from_date=date_from, to_date=date_to)
        # await minio_client.upload(df.to_csv(), export_url)
        # await report_repo.create(Report(type=ReportType.RESEARCH_EXPORT, storage_url=export_url))

        return {
            "status": "exported",
            "districts": target_districts,
            "date_range": {"from": date_from, "to": date_to},
            "export_format": export_format,
            "export_url": export_url,
            "climate_indices_computed": list(computed_indices.keys()),
            "report_type": ReportType.RESEARCH_EXPORT.value,
        }
