"""
app/integrations/weather/base.py
─────────────────────────────────
Base interface for all weather data providers.
"""

from abc import ABC, abstractmethod
from typing import Any

from app.core.enums import District, WeatherSource


class IWeatherProvider(ABC):
    """
    Abstract interface for fetching weather data.
    Every integration (IMD, NASA, Open-Meteo) must implement this.
    """

    @property
    @abstractmethod
    def source_name(self) -> WeatherSource:
        """The enum identifier for this source."""
        pass

    @abstractmethod
    async def fetch_current_weather(self, district: District) -> dict[str, Any]:
        """
        Fetch the latest current weather for a district.
        Must return a standardized dictionary matching the WeatherObservation model schema.
        """
        pass

    @abstractmethod
    async def fetch_historical_weather(self, district: District, start_date: str, end_date: str) -> list[dict[str, Any]]:
        """
        Fetch historical data for a date range.
        Returns a list of standardized dictionaries.
        """
        pass
