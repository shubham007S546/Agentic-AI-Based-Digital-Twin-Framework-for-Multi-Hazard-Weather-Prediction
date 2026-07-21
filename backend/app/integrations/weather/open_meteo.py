"""
app/integrations/weather/open_meteo.py
──────────────────────────────────────
Open-Meteo API integration.

Design decisions:
  • Uses httpx.AsyncClient for non-blocking HTTP requests.
  • Maps district coordinates to latitude/longitude.
  • Translates Open-Meteo JSON into our standard WeatherObservation schema.
"""

from typing import Any

import httpx
import structlog

from app.core.enums import District, WeatherSource
from app.exceptions.domain import WeatherSourceUnavailableError
from app.integrations.weather.base import IWeatherProvider

logger = structlog.get_logger(__name__)

# Hardcoded coordinates for the 3 target districts in Himachal Pradesh
_DISTRICT_COORDINATES = {
    District.MANDI: {"lat": 31.5892, "lon": 76.9182},
    District.KULLU: {"lat": 31.9578, "lon": 77.1095},
    District.CHAMBA: {"lat": 32.5534, "lon": 76.1258},
}


class OpenMeteoProvider(IWeatherProvider):
    def __init__(self):
        self.base_url = "https://api.open-meteo.com/v1/forecast"

    @property
    def source_name(self) -> WeatherSource:
        return WeatherSource.OPEN_METEO

    async def fetch_current_weather(self, district: District) -> dict[str, Any]:
        coords = _DISTRICT_COORDINATES.get(district)
        if not coords:
            raise ValueError(f"Coordinates not found for district {district}")

        params = {
            "latitude": coords["lat"],
            "longitude": coords["lon"],
            "current": "temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,wind_direction_10m,precipitation,cloud_cover",
            "timezone": "Asia/Kolkata",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.base_url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()

                current = data.get("current", {})
                
                # Standardize to our internal schema
                return {
                    "temperature_2m": current.get("temperature_2m"),
                    "relative_humidity_2m": current.get("relative_humidity_2m"),
                    "surface_pressure": current.get("surface_pressure"),
                    "wind_speed_10m": current.get("wind_speed_10m"),
                    "wind_direction_10m": current.get("wind_direction_10m"),
                    "precipitation": current.get("precipitation"),
                    "cloud_cover": current.get("cloud_cover"),
                    "raw_data": data,
                }
        except httpx.HTTPError as exc:
            logger.error("Open-Meteo API request failed", error=str(exc))
            raise WeatherSourceUnavailableError("Open-Meteo", "Failed to fetch weather data") from exc

    async def fetch_historical_weather(self, district: District, start_date: str, end_date: str) -> list[dict[str, Any]]:
        # Open-Meteo historical API uses a different endpoint (archive-api.open-meteo.com)
        # Simplified for now
        raise NotImplementedError("Historical fetch not yet implemented for Open-Meteo")
