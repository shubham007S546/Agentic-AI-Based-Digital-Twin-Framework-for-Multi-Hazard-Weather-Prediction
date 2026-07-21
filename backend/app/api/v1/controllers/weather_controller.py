"""
app/api/v1/controllers/weather_controller.py
────────────────────────────────────────────
Weather Controller class.
"""

from typing import Annotated

from fastapi import Depends

from app.core.enums import District
from app.dependencies.services import get_weather_service
from app.services.interfaces.weather_service import IWeatherService


class WeatherController:
    """Controller for weather endpoints."""

    def __init__(
        self,
        weather_service: Annotated[IWeatherService, Depends(get_weather_service)],
    ):
        self.weather_service = weather_service

    async def get_current_weather(self, district: District):
        return await self.weather_service.get_latest_observation(district)

    async def get_recent_weather(self, district: District, limit: int):
        return await self.weather_service.get_recent_observations(district, limit)

    async def force_ingest(self, district: District):
        return await self.weather_service.ingest_current_weather(district)
