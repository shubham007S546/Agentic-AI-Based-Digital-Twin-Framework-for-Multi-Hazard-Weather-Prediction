"""
app/repositories/interfaces/weather_repo.py
───────────────────────────────────────────
Interface for the Weather Observation repository.
"""

from abc import ABC, abstractmethod
from typing import Optional
import uuid

from app.core.enums import District
from app.models.weather import WeatherObservation


class IWeatherRepository(ABC):
    """Abstract interface for Weather Observation data access."""

    @abstractmethod
    async def create(self, observation: WeatherObservation) -> WeatherObservation:
        """Save a new weather observation to the database."""
        pass

    @abstractmethod
    async def get_latest_by_district(self, district: District) -> Optional[WeatherObservation]:
        """Fetch the most recent weather observation for a specific district."""
        pass
        
    @abstractmethod
    async def get_recent_by_district(self, district: District, limit: int = 10) -> list[WeatherObservation]:
        """Fetch a list of recent weather observations for a district."""
        pass
