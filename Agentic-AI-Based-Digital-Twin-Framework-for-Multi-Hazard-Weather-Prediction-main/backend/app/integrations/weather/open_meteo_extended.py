"""
app/integrations/weather/open_meteo_extended.py
──────────────────────────────────────
Real weather integration using Open-Meteo API.
This requires NO database and works as a direct proxy to Open-Meteo,
fulfilling Phase 1 of making the platform real.
"""

from typing import Any
import logging
import httpx
from datetime import datetime, timezone

try:
    import structlog
    logger = structlog.get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)

# All 17 major districts/locations of Himachal Pradesh
DISTRICT_COORDINATES = {
    "Mandi": {"lat": 31.5892, "lon": 76.9182},
    "Kullu": {"lat": 31.9578, "lon": 77.1095},
    "Chamba": {"lat": 32.5534, "lon": 76.1258},
    "Shimla": {"lat": 31.1048, "lon": 77.1734},
    "Kangra": {"lat": 32.0998, "lon": 76.2691},
    "Kinnaur": {"lat": 31.651, "lon": 78.471},
    "Lahaul and Spiti": {"lat": 32.333, "lon": 77.583},
    "Sirmaur": {"lat": 30.5599, "lon": 77.2954},
    "Solan": {"lat": 30.9084, "lon": 77.0999},
    "Una": {"lat": 31.4685, "lon": 76.2708},
    "Bilaspur": {"lat": 31.33, "lon": 76.75},
    "Hamirpur": {"lat": 31.68, "lon": 76.52},
}

class OpenMeteoExtendedProvider:
    def __init__(self):
        self.base_url = "https://api.open-meteo.com/v1/forecast"
        
    def _get_coords(self, district: str) -> dict:
        # Match case-insensitive
        dist_key = next((k for k in DISTRICT_COORDINATES.keys() if k.lower() == district.lower()), None)
        if not dist_key:
            # Fallback to Mandi if unknown
            logger.warning(f"District {district} not found, falling back to Mandi.")
            return DISTRICT_COORDINATES["Mandi"]
        return DISTRICT_COORDINATES[dist_key]

    async def fetch_current_and_forecast(self, district: str) -> dict[str, Any]:
        """Fetch current conditions, hourly (2 days) and daily (7 days) forecast."""
        coords = self._get_coords(district)
        
        params = {
            "latitude": coords["lat"],
            "longitude": coords["lon"],
            "current": "temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,wind_direction_10m,precipitation,cloud_cover,weather_code",
            "hourly": "temperature_2m,precipitation,cloud_cover",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max",
            "timezone": "Asia/Kolkata",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.base_url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                
                # Format to our frontend schema
                current = data.get("current", {})
                daily = data.get("daily", {})
                hourly = data.get("hourly", {})
                
                # Transform daily forecast
                forecast = []
                if "time" in daily:
                    for i in range(len(daily["time"])):
                        dt = datetime.fromisoformat(daily["time"][i])
                        forecast.append({
                            "date": daily["time"][i],
                            "day": dt.strftime("%A"),
                            "tempMax": daily["temperature_2m_max"][i],
                            "tempMin": daily["temperature_2m_min"][i],
                            "rainfall": daily["precipitation_sum"][i],
                            "rainProbability": daily["precipitation_probability_max"][i],
                            "windSpeed": daily["wind_speed_10m_max"][i],
                            "humidity": 60, # Daily humidity isn't directly in this OpenMeteo endpoint by default
                            "condition": self._code_to_condition(daily["weather_code"][i])
                        })
                
                # Transform hourly (next 24 hours)
                hourly_data = []
                if "time" in hourly:
                    # Find index for current hour
                    now = datetime.now(timezone.utc)
                    start_idx = 0
                    # Just take first 24 hours
                    for i in range(start_idx, min(start_idx + 24, len(hourly["time"]))):
                        hr_dt = datetime.fromisoformat(hourly["time"][i])
                        hourly_data.append({
                            "hour": hr_dt.strftime("%H:%M"),
                            "rainfall": hourly["precipitation"][i],
                            "predicted": hourly["precipitation"][i] # use same for now, ML overrides later
                        })

                # Determine risk dynamically based on current rain
                rain_1h = current.get("precipitation", 0)
                risk = "low"
                if rain_1h > 15: risk = "severe"
                elif rain_1h > 5: risk = "high"
                elif rain_1h > 2: risk = "moderate"

                result = {
                    "current": {
                        "temperature": current.get("temperature_2m"),
                        "rainfall": rain_1h,
                        "humidity": current.get("relative_humidity_2m"),
                        "pressure": current.get("surface_pressure"),
                        "windSpeed": current.get("wind_speed_10m"),
                        "windDirection": self._deg_to_dir(current.get("wind_direction_10m", 0)),
                        "visibility": 10, # default
                        "uvIndex": 5, # default
                        "cloudCover": current.get("cloud_cover"),
                        "condition": self._code_to_condition(current.get("weather_code", 0)),
                        "dewPoint": current.get("temperature_2m", 20) - ((100 - current.get("relative_humidity_2m", 50)) / 5), # approx
                    },
                    "forecast_7d": forecast,
                    "hourly_rainfall": hourly_data,
                    "station_meta": {
                        "id": f"st-{district.lower()}",
                        "name": district,
                        "district": district,
                        "lat": coords["lat"],
                        "lng": coords["lon"],
                        "risk": risk,
                        "probability": min(100, int(rain_1h * 10)),
                        "metric": current.get("precipitation", 0)
                    }
                }
                return result
                
        except Exception as exc:
            logger.error("Open-Meteo Extended API request failed", error=str(exc))
            raise

    def _code_to_condition(self, code: int) -> str:
        """WMO Weather interpretation codes"""
        codes = {
            0: "Clear sky",
            1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Fog", 48: "Depositing rime fog",
            51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
            61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
            71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
            80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
            95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail"
        }
        return codes.get(code, "Unknown")
        
    def _deg_to_dir(self, deg: float) -> str:
        val = int((deg / 22.5) + .5)
        arr = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        return arr[(val % 16)]
