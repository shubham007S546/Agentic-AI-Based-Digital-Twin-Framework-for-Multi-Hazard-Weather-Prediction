"""
Environment-driven configuration for the Weather Analysis Agent.

All optional -- the agent runs with sensible defaults and no API keys,
since Open-Meteo (its only "live" provider) needs none.

REDIS_URL                 e.g. "redis://localhost:6379/0". If unset, the
                           result cache is kept in-process instead.
WEATHER_CACHE_TTL_SECONDS  Defaults to 1800 (30 min) -- matches the
                           diagram's "results cached for 10-30 minutes".
OPEN_METEO_FORECAST_URL    Defaults to the public Open-Meteo endpoint your
                           config.yaml already uses.
WEATHER_AGENT_LOG_DIR      Defaults to "logs".
GROQ_API_KEY / GROQ_MODEL  Optional -- only used to turn the structured
                           summary into an extra natural-language sentence.
                           Falls back to a templated summary without it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _load_dotenv_if_present() -> None:
    try:
        from pathlib import Path
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent / ".env")
    except ImportError:
        pass


_load_dotenv_if_present()


@dataclass
class Settings:
    redis_url: str = os.getenv("REDIS_URL", "")
    cache_ttl_seconds: int = int(os.getenv("WEATHER_CACHE_TTL_SECONDS", "1800"))
    open_meteo_forecast_url: str = os.getenv(
        "OPEN_METEO_FORECAST_URL", "https://api.open-meteo.com/v1/forecast"
    )
    log_dir: str = os.getenv("WEATHER_AGENT_LOG_DIR", "logs")
    http_timeout_seconds: float = float(os.getenv("WEATHER_HTTP_TIMEOUT_SECONDS", "15"))

    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    @property
    def has_redis(self) -> bool:
        return bool(self.redis_url)

    @property
    def has_llm_key(self) -> bool:
        return bool(self.groq_api_key)


settings = Settings()
