"""
app/integrations/weather/open_weather.py
──────────────────────────────────────────
Live weather integration using OpenWeather API (current weather & 5-day forecast)
with graceful automatic fallback to OpenMeteo.
"""

import os
from typing import Any
import httpx
import logging
from datetime import datetime, timezone

from app.core.config import get_settings
from app.integrations.weather.open_meteo_extended import OpenMeteoExtendedProvider, DISTRICT_COORDINATES

logger = logging.getLogger(__name__)

DEFAULT_API_KEY = "886cd33323a4600331a38bd829e16c5f"

class OpenWeatherProvider:
    def __init__(self):
        settings = get_settings()
        ws = getattr(settings, "weather_sources", None)
        self.api_key = os.getenv("OPENWEATHER_API_KEY") or (getattr(ws, "openweather_api_key", DEFAULT_API_KEY) if ws else DEFAULT_API_KEY)
        self.base_url = (getattr(ws, "openweather_base_url", "https://api.openweathermap.org/data/2.5") if ws else "https://api.openweathermap.org/data/2.5")
        self.meteo_fallback = OpenMeteoExtendedProvider()

    def _get_coords(self, district: str) -> dict:
        dist_key = next((k for k in DISTRICT_COORDINATES.keys() if k.lower() == district.lower()), None)
        if not dist_key:
            return DISTRICT_COORDINATES["Mandi"]
        return DISTRICT_COORDINATES[dist_key]

    async def fetch_current_and_forecast(self, district: str) -> dict[str, Any]:
        """
        Fetches live current weather and forecast using OpenWeather API.
        Falls back to Open-Meteo seamlessly if OpenWeather API returns an error
        (e.g., 401 key propagating/invalid, 429 limit, network error).
        """
        coords = self._get_coords(district)
        
        try:
            async with httpx.AsyncClient() as client:
                # 1. Current Weather
                cur_resp = await client.get(
                    f"{self.base_url}/weather",
                    params={
                        "lat": coords["lat"],
                        "lon": coords["lon"],
                        "appid": self.api_key,
                        "units": "metric"
                    },
                    timeout=8.0
                )

                if cur_resp.status_code != 200:
                    logger.warning(
                        "OpenWeather current weather request returned %s, falling back to Open-Meteo: %s",
                        cur_resp.status_code,
                        cur_resp.text[:200]
                    )
                    return await self.meteo_fallback.fetch_current_and_forecast(district)

                cur_data = cur_resp.json()

                # 2. 5-day / 3-hour Forecast
                fc_resp = await client.get(
                    f"{self.base_url}/forecast",
                    params={
                        "lat": coords["lat"],
                        "lon": coords["lon"],
                        "appid": self.api_key,
                        "units": "metric"
                    },
                    timeout=8.0
                )

                fc_data = fc_resp.json() if fc_resp.status_code == 200 else {}

                # Format current weather
                main = cur_data.get("main", {})
                wind = cur_data.get("wind", {})
                rain = cur_data.get("rain", {})
                weather_arr = cur_data.get("weather", [{}])
                rain_1h = float(rain.get("1h", rain.get("3h", 0.0)))
                cond = weather_arr[0].get("main", "Clear") if weather_arr else "Clear"

                current = {
                    "temperature": main.get("temp"),
                    "rainfall": rain_1h,
                    "humidity": main.get("humidity"),
                    "pressure": main.get("pressure"),
                    "windSpeed": wind.get("speed"),
                    "windDirection": self._deg_to_dir(wind.get("deg", 0)),
                    "visibility": cur_data.get("visibility", 10000) / 1000.0,
                    "uvIndex": 5,
                    "cloudCover": cur_data.get("clouds", {}).get("all", 0),
                    "condition": cond,
                    "dewPoint": round(main.get("temp", 20) - ((100 - main.get("humidity", 50)) / 5), 1),
                }

                # Transform 5-day forecast into daily & hourly lists
                forecast_7d = []
                hourly_rainfall = []
                list_items = fc_data.get("list", [])

                daily_agg = {}
                for item in list_items:
                    dt = datetime.fromtimestamp(item.get("dt", 0), tz=timezone.utc)
                    date_str = dt.strftime("%Y-%m-%d")
                    day_name = dt.strftime("%A")
                    item_temp = item.get("main", {}).get("temp", 0)
                    item_rain = float(item.get("rain", {}).get("3h", 0.0))

                    if date_str not in daily_agg:
                        daily_agg[date_str] = {
                            "date": date_str,
                            "day": day_name,
                            "tempMax": item_temp,
                            "tempMin": item_temp,
                            "rainfall": 0.0,
                            "pop": float(item.get("pop", 0) * 100),
                            "windSpeed": float(item.get("wind", {}).get("speed", 0)),
                            "condition": item.get("weather", [{}])[0].get("main", "Clear")
                        }
                    daily_agg[date_str]["tempMax"] = max(daily_agg[date_str]["tempMax"], item_temp)
                    daily_agg[date_str]["tempMin"] = min(daily_agg[date_str]["tempMin"], item_temp)
                    daily_agg[date_str]["rainfall"] += item_rain

                    if len(hourly_rainfall) < 24:
                        hourly_rainfall.append({
                            "hour": dt.strftime("%H:%M"),
                            "rainfall": round(item_rain, 2),
                            "predicted": round(item_rain * 1.1, 2)
                        })

                for d in list(daily_agg.values())[:7]:
                    forecast_7d.append({
                        "date": d["date"],
                        "day": d["day"],
                        "tempMax": round(d["tempMax"], 1),
                        "tempMin": round(d["tempMin"], 1),
                        "rainfall": round(d["rainfall"], 1),
                        "rainProbability": int(d["pop"]),
                        "windSpeed": round(d["windSpeed"], 1),
                        "humidity": main.get("humidity", 60),
                        "condition": d["condition"]
                    })

                risk = "low"
                if rain_1h > 15: risk = "severe"
                elif rain_1h > 5: risk = "high"
                elif rain_1h > 2: risk = "moderate"

                return {
                    "current": current,
                    "forecast_7d": forecast_7d,
                    "hourly_rainfall": hourly_rainfall,
                    "station_meta": {
                        "id": f"st-{district.lower()}",
                        "name": district,
                        "district": district,
                        "lat": coords["lat"],
                        "lng": coords["lon"],
                        "risk": risk,
                        "probability": min(100, int(rain_1h * 10)),
                        "metric": rain_1h
                    }
                }

        except Exception as exc:
            logger.warning("OpenWeather request failed, utilizing Open-Meteo fallback: %s", str(exc))
            return await self.meteo_fallback.fetch_current_and_forecast(district)

    def _deg_to_dir(self, deg: float) -> str:
        val = int((deg / 22.5) + .5)
        arr = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        return arr[(val % 16)]
