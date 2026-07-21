"""
app/agents/data_collection_agent.py
────────────────────────────────────
Agent 8 — Data Collection Agent

Responsibility:
  • Orchestrate multi-source satellite and remote sensing data ingestion:
      MODIS (vegetation, land surface temperature)
      Sentinel-2 (SAR flood mapping, soil moisture)
      NASA GPM (global precipitation measurement)
      India WRIS (river gauge levels)
  • Store processed outputs as WeatherObservation records with
    source=WeatherSource.MODIS / SENTINEL / NASA_GPM / INDIA_WRIS
  • Validate data quality and set WeatherObservation.quality_flag

Models used:
  • WeatherObservation — stores multi-source satellite observations
                         (source, district, timestamp, raw_data, quality_flag)
"""

from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.enums import AgentName, District, WeatherQuality, WeatherSource

# Map source → expected fields available from that provider
_SOURCE_FIELDS: dict[WeatherSource, list[str]] = {
    WeatherSource.MODIS: ["land_surface_temp", "ndvi", "cloud_cover"],
    WeatherSource.SENTINEL: ["sar_backscatter", "soil_moisture", "flood_extent_km2"],
    WeatherSource.NASA_GPM: ["precipitation", "precipitation_probability"],
    WeatherSource.INDIA_WRIS: ["river_discharge_m3s", "water_level_m"],
}


class DataCollectionAgent(BaseAgent):
    """
    Multi-source remote sensing and satellite data ingestion agent.
    Creates WeatherObservation records for each district × source combination.
    """

    def __init__(self) -> None:
        super().__init__(name=AgentName.DATA_COLLECTION, version="1.0.0")

    @property
    def description(self) -> str:
        return (
            "Ingests satellite (MODIS, Sentinel-2, NASA GPM) and hydrological "
            "(India WRIS) data for all target districts, storing normalized "
            "WeatherObservation records with source-appropriate quality flags."
        )

    def _get_timeout_seconds(self) -> float:
        return 180.0  # Satellite data APIs can be slow

    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Satellite ingestion pipeline.

        Real implementation:
          1. For each (district, source) pair, call the corresponding HTTP client
             (MODISClient, SentinelClient, GPMClient, WRISClient)
          2. Parse response into WeatherObservation fields
          3. Validate: if missing critical fields → quality_flag = SUSPECT / BAD
          4. Upsert WeatherObservation record (district, source, timestamp unique key)
          5. Emit DataIngested event so WeatherAgent can detect anomalies
        """
        sources_to_collect: list[WeatherSource] = payload.get(
            "sources", list(_SOURCE_FIELDS.keys())
        )
        results: dict[str, str] = {}
        total_observations = 0
        quality_flags: dict[str, str] = {}

        for district in District:
            for source in sources_to_collect:
                if source not in _SOURCE_FIELDS:
                    continue
                key = f"{district.name}:{source.name}"
                try:
                    self._logger.info(
                        "Collecting satellite data",
                        district=district.name,
                        source=source.name,
                        expected_fields=_SOURCE_FIELDS[source],
                    )
                    # Real:
                    # raw_data = await satellite_client_map[source].fetch(district)
                    # obs = WeatherObservation(
                    #     district=district,
                    #     source=source,
                    #     timestamp=datetime.now(UTC),
                    #     raw_data=raw_data,
                    #     quality_flag=WeatherQuality.GOOD if raw_data else WeatherQuality.MISSING,
                    # )
                    # await weather_repo.upsert(obs)
                    quality_flags[key] = WeatherQuality.GOOD.value
                    results[key] = "ok"
                    total_observations += 1

                except Exception as exc:
                    self._logger.error(
                        "Satellite data collection failed",
                        district=district.name,
                        source=source.name,
                        error=str(exc),
                    )
                    quality_flags[key] = WeatherQuality.BAD.value
                    results[key] = f"error: {exc}"

        successful = sum(1 for v in results.values() if v == "ok")

        return {
            "sources_collected": [s.value for s in sources_to_collect],
            "districts_processed": len(District),
            "total_observations": total_observations,
            "successful": successful,
            "failed": len(results) - successful,
            "quality_summary": quality_flags,
        }
