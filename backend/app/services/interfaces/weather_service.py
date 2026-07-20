"""
app/services/interfaces/weather_service.py
──────────────────────────────────────────
Interface for the Weather service.
"""

from abc import ABC, abstractmethod

from app.core.enums import District
from app.models.weather import WeatherObservation


class IWeatherService(ABC):
    """Abstract interface for Weather business logic."""

    @abstractmethod
    async def get_latest_observation(self, district: District) -> WeatherObservation:
        """Fetch the most recent weather observation for a district."""
        pass

    @abstractmethod
    async def get_recent_observations(self, district: District, limit: int = 10) -> list[WeatherObservation]:
        """Fetch recent weather observations for a district."""
        pass

    @abstractmethod
    async def ingest_current_weather(self, district: District) -> list[WeatherObservation]:
        """
        Trigger an ingestion from all configured providers for a district.
        Returns the newly created observation records.
        """
        pass
