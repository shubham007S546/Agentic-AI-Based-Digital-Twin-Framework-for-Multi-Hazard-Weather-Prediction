"""
Weather data providers -- one function per source in the diagram.

open_meteo_provider is a REAL, working HTTP integration against the public
Open-Meteo forecast API (no key required) -- this is the only one of the
four sources that's genuinely a live, queryable real-time API; see the
module docstring in each stub below for why IMD/ERA5/NASA GPM are handled
differently.

imd_provider / era5_provider / nasa_gpm_provider are honest stubs: those
three sources in this project are archive/reanalysis datasets fetched via
heavy-auth batch collectors (collectors/imd_collector.py, era5_collector.py,
nasa_collector.py), not live per-request query APIs. Rather than pretend to
"fetch" from them per-request, each stub is documented with exactly how to
read the most recent already-collected data for a district from
datasets/source_*/cleaned/*.csv once you wire it in.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)

_OPEN_METEO_HOURLY_VARS = [
    "temperature_2m", "relative_humidity_2m", "precipitation",
    "wind_speed_10m", "surface_pressure", "cloud_cover",
]


def open_meteo_provider(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 2 tool: real-time + forecast weather from Open-Meteo.
    Real endpoint: GET https://api.open-meteo.com/v1/forecast
    (matches your config.yaml sources.openmeteo.forecast_url + variables)
    """
    latitude = params.get("latitude")
    longitude = params.get("longitude")
    forecast_hours = params.get("forecast_hours", 24)

    if latitude is None or longitude is None:
        return {"status": "error", "source": "open_meteo", "note": "latitude/longitude required."}

    query = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(_OPEN_METEO_HOURLY_VARS),
        "timezone": "Asia/Kolkata",
        "forecast_days": max(1, min(16, (forecast_hours // 24) + 1)),
    }

    start = time.monotonic()
    try:
        with httpx.Client(timeout=settings.http_timeout_seconds) as client:
            resp = client.get(settings.open_meteo_forecast_url, params=query)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Open-Meteo request failed: %s", exc)
        return {"status": "error", "source": "open_meteo", "note": str(exc)}
    finally:
        logger.info("open_meteo_provider took %.1fms", (time.monotonic() - start) * 1000)

    hourly = data.get("hourly", {})
    times: List[str] = hourly.get("time", [])
    if not times:
        return {"status": "error", "source": "open_meteo", "note": "Empty hourly response."}

    now_idx = _nearest_hour_index(times)
    end_idx = min(len(times), now_idx + forecast_hours)

    current = {
        "temperature": _safe_at(hourly.get("temperature_2m"), now_idx),
        "humidity": _safe_at(hourly.get("relative_humidity_2m"), now_idx),
        "rainfall": _safe_at(hourly.get("precipitation"), now_idx),
        "wind_speed": _safe_at(hourly.get("wind_speed_10m"), now_idx),
        "pressure": _safe_at(hourly.get("surface_pressure"), now_idx),
        "cloud_cover": _safe_at(hourly.get("cloud_cover"), now_idx),
    }

    forecast = [
        {
            "time": times[i],
            "rainfall": _safe_at(hourly.get("precipitation"), i),
            "temp_max": _safe_at(hourly.get("temperature_2m"), i),
            "temp_min": _safe_at(hourly.get("temperature_2m"), i),
            "condition": _condition_from_precip(_safe_at(hourly.get("precipitation"), i)),
        }
        for i in range(now_idx, end_idx)
    ]

    return {"status": "ok", "source": "open_meteo", "current": current, "forecast": forecast}


def _nearest_hour_index(times: List[str]) -> int:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for i, t in enumerate(times):
        try:
            parsed = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if parsed >= now:
            return i
    return 0


def _safe_at(values: Optional[List[Any]], idx: int) -> Optional[Any]:
    if values is None or idx >= len(values):
        return None
    return values[idx]


def _condition_from_precip(precip_mm: Optional[float]) -> str:
    if precip_mm is None:
        return "Unknown"
    if precip_mm <= 0:
        return "Clear"
    if precip_mm < 2.5:
        return "Light Rain"
    if precip_mm < 7.5:
        return "Moderate Rain"
    return "Heavy Rain"


def imd_provider(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 2 tool: IMD gridded rainfall.
    NOT a live query API in this project -- IMD data is collected in bulk by
    collectors/imd_collector.py into datasets/source_1_imd/cleaned/imd_<district>_<year>_cleaned.csv.
    TODO: read the most recent row for `params['location']` from that file, e.g.:
        df = pd.read_csv(f"datasets/source_1_imd/cleaned/imd_{district}_{year}_cleaned.csv")
        latest = df.iloc[-1]
    """
    logger.info("imd_provider called with params=%s (STUB)", params)
    return {"status": "stub", "source": "imd",
            "note": "IMD is a batch-collected archive in this project, not a live API. "
                    "Wire this to read datasets/source_1_imd/cleaned/*.csv instead."}


def era5_provider(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 2 tool: ERA5 reanalysis.
    NOT a live query API -- collected via collectors/era5_collector.py (Copernicus CDS)
    into datasets/source_4_era5/cleaned/era5_<district>_<yyyymm>_cleaned.csv.
    TODO: read the most recent available month's file for the requested district.
    """
    logger.info("era5_provider called with params=%s (STUB)", params)
    return {"status": "stub", "source": "era5",
            "note": "ERA5 is a batch-collected reanalysis archive in this project, not a live API. "
                    "Wire this to read datasets/source_4_era5/cleaned/*.csv instead."}


def nasa_gpm_provider(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 2 tool: NASA GPM IMERG precipitation.
    NOT a live query API -- collected via collectors/nasa_collector.py (NASA Earthdata)
    into datasets/source_2_nasa_gpm/.
    TODO: read the most recent available file for the requested district/time.
    """
    logger.info("nasa_gpm_provider called with params=%s (STUB)", params)
    return {"status": "stub", "source": "nasa_gpm",
            "note": "NASA GPM is a batch-collected archive in this project, not a live API. "
                    "Wire this to read datasets/source_2_nasa_gpm/ instead."}


def openweather_provider(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 2 tool: real-time current + forecast weather from OpenWeatherMap API.
    Uses OPENWEATHER_API_KEY from environment or settings.
    Falls back gracefully to open_meteo_provider if key is missing or request fails.
    """
    import os
    api_key = settings.openweather_api_key or os.getenv("OPENWEATHER_API_KEY", "")
    if not api_key or api_key in ("CHANGE_ME", "your_key_here"):
        logger.info("OPENWEATHER_API_KEY not configured; falling back to open_meteo_provider")
        return open_meteo_provider(params)

    latitude = params.get("latitude")
    longitude = params.get("longitude")
    if latitude is None or longitude is None:
        return {"status": "error", "source": "openweather", "note": "latitude/longitude required."}

    start = time.monotonic()
    try:
        with httpx.Client(timeout=settings.http_timeout_seconds) as client:
            resp = client.get(
                f"{settings.openweather_base_url}/weather",
                params={"lat": latitude, "lon": longitude, "appid": api_key, "units": "metric"},
            )
            if resp.status_code != 200:
                logger.warning("OpenWeather returned %s, falling back to Open-Meteo", resp.status_code)
                return open_meteo_provider(params)
            cur_data = resp.json()

            fc_resp = client.get(
                f"{settings.openweather_base_url}/forecast",
                params={"lat": latitude, "lon": longitude, "appid": api_key, "units": "metric"},
            )
            fc_data = fc_resp.json() if fc_resp.status_code == 200 else {}
    except Exception as exc:
        logger.warning("OpenWeather request failed (%s); falling back to Open-Meteo", exc)
        return open_meteo_provider(params)
    finally:
        logger.info("openweather_provider took %.1fms", (time.monotonic() - start) * 1000)

    main = cur_data.get("main", {})
    wind = cur_data.get("wind", {})
    rain = cur_data.get("rain", {})
    clouds = cur_data.get("clouds", {})
    current = {
        "temperature": main.get("temp"),
        "humidity": main.get("humidity"),
        "rainfall": float(rain.get("1h", rain.get("3h", 0.0))),
        "wind_speed": wind.get("speed"),
        "pressure": main.get("pressure"),
        "cloud_cover": clouds.get("all"),
    }

    forecast = []
    max_steps = max(1, params.get("forecast_hours", 24) // 3)
    for item in fc_data.get("list", [])[:max_steps]:
        item_main = item.get("main", {})
        item_rain = item.get("rain", {})
        forecast.append({
            "time": item.get("dt_txt"),
            "rainfall": float(item_rain.get("3h", 0.0)),
            "temp_max": item_main.get("temp_max"),
            "temp_min": item_main.get("temp_min"),
            "condition": item.get("weather", [{}])[0].get("main", "Clear"),
        })

    return {"status": "ok", "source": "openweather", "current": current, "forecast": forecast}


PROVIDER_REGISTRY = {
    "open_meteo": open_meteo_provider,
    "open_weather": openweather_provider,
    "openweather": openweather_provider,
    "imd": imd_provider,
    "era5": era5_provider,
    "nasa_gpm": nasa_gpm_provider,
}


def call_provider(name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if name not in PROVIDER_REGISTRY:
        return {"status": "error", "source": name, "note": f"Unknown provider: {name!r}"}
    try:
        return PROVIDER_REGISTRY[name](params)
    except Exception as exc:
        logger.exception("Provider %s raised an unexpected error", name)
        return {"status": "error", "source": name, "note": str(exc)}
