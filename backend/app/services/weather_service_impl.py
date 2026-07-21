"""
app/services/weather_service_impl.py
────────────────────────────────────
Implementation of IWeatherService.
"""

from datetime import UTC, datetime
from typing import Sequence

import structlog

from app.core.enums import District, WeatherQuality
from app.exceptions.domain import ResourceNotFoundError
from app.integrations.weather.base import IWeatherProvider
from app.models.weather import WeatherObservation
from app.repositories.interfaces.weather_repo import IWeatherRepository
from app.services.interfaces.weather_service import IWeatherService

logger = structlog.get_logger(__name__)


class WeatherServiceImpl(IWeatherService):
    def __init__(
        self,
        weather_repo: IWeatherRepository,
        providers: Sequence[IWeatherProvider],
    ):
        self.weather_repo = weather_repo
        self.providers = providers

    async def get_latest_observation(self, district: District) -> WeatherObservation:
        obs = await self.weather_repo.get_latest_by_district(district)
        if not obs:
            raise ResourceNotFoundError(f"No weather observations found for {district.name}")
        return obs

    async def get_recent_observations(self, district: District, limit: int = 10) -> list[WeatherObservation]:
        return await self.weather_repo.get_recent_by_district(district, limit=limit)

    async def ingest_current_weather(self, district: District) -> list[WeatherObservation]:
        """
        Polls all registered providers for current weather, stores the results in the DB.
        """
        created_observations: list[WeatherObservation] = []
        now = datetime.now(UTC)

        for provider in self.providers:
            try:
                data = await provider.fetch_current_weather(district)
                
                obs = WeatherObservation(
                    district=district,
                    source=provider.source_name,
                    timestamp=now,
                    temperature_2m=data.get("temperature_2m"),
                    relative_humidity_2m=data.get("relative_humidity_2m"),
                    surface_pressure=data.get("surface_pressure"),
                    wind_speed_10m=data.get("wind_speed_10m"),
                    wind_direction_10m=data.get("wind_direction_10m"),
                    precipitation=data.get("precipitation"),
                    cloud_cover=data.get("cloud_cover"),
                    soil_moisture=data.get("soil_moisture"),
                    quality_flag=WeatherQuality.GOOD,
                    raw_data=data.get("raw_data"),
                )
                
                # Add to DB
                saved_obs = await self.weather_repo.create(obs)
                created_observations.append(saved_obs)
                
                logger.info(
                    "Weather data ingested",
                    district=district.name,
                    source=provider.source_name.name,
                )
                
            except Exception as exc:
                # Log but continue with other providers (fault tolerance)
                logger.error(
                    "Failed to ingest weather data from provider",
                    district=district.name,
                    source=provider.source_name.name,
                    error=str(exc),
                )

        return created_observations
