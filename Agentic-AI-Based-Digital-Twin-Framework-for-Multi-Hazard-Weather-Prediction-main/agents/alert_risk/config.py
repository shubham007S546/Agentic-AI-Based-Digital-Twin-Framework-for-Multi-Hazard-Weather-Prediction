"""
Environment-driven configuration for the Alert & Risk Assessment Agent.

Nothing here is strictly required to run the agent -- it works out of the
box with rule-based risk scoring and stubbed notifications. Set
PREDICTION_AGENT_URL / WEATHER_AGENT_URL to get real predictions/weather
feeding into risk scoring instead of running on caller-supplied data alone.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


def _load_dotenv_if_present() -> None:
    try:
        from pathlib import Path
        from dotenv import load_dotenv, find_dotenv
        env_file = find_dotenv(usecwd=True)
        if env_file:
            load_dotenv(env_file)
        for parent_env in [Path(__file__).resolve().parents[2] / ".env", Path(__file__).resolve().parent / ".env"]:
            if parent_env.exists():
                load_dotenv(parent_env, override=False)
    except Exception:
        pass


_load_dotenv_if_present()


@dataclass
class Settings:
    # Sibling agents this one calls out to for real data (see clients.py).
    prediction_agent_url: str = os.getenv("PREDICTION_AGENT_URL", "http://localhost:8002")
    weather_agent_url: str = os.getenv("WEATHER_AGENT_URL", "http://localhost:8001")
    agent_request_timeout_seconds: float = float(os.getenv("AGENT_REQUEST_TIMEOUT_SECONDS", "20"))

    # ReliefWeb is a real, public, keyless-enough API (just needs an "appname"
    # string identifying your app, not a secret) -- see external_feeds.py.
    reliefweb_base_url: str = os.getenv("RELIEFWEB_BASE_URL", "https://api.reliefweb.int/v2/reports")
    reliefweb_appname: str = os.getenv("RELIEFWEB_APPNAME", "himachal-digital-twin")
    reliefweb_country_iso3: str = os.getenv("RELIEFWEB_COUNTRY_ISO3", "IND")

    # Severity thresholds on the composite 0-1 risk score. Tune these once
    # you have real historical alert outcomes to calibrate against.
    red_threshold: float = float(os.getenv("RISK_RED_THRESHOLD", "0.85"))
    orange_threshold: float = float(os.getenv("RISK_ORANGE_THRESHOLD", "0.60"))
    yellow_threshold: float = float(os.getenv("RISK_YELLOW_THRESHOLD", "0.35"))

    # Rainfall (mm) that alone forces at least Orange, regardless of composite
    # score -- matches your final_preprocessing.py's CLOUDBURST_MM concept.
    cloudburst_mm_floor: float = float(os.getenv("CLOUDBURST_MM_FLOOR", "100.0"))

    # Escalation: severities at/above this auto-escalate to authorities,
    # not just notify the requesting user.
    escalation_severity_floor: str = os.getenv("ESCALATION_SEVERITY_FLOOR", "orange")

    notification_channels: List[str] = field(
        default_factory=lambda: os.getenv("NOTIFICATION_CHANNELS", "email").split(",")
    )

    alert_log_path: str = os.getenv("ALERT_LOG_PATH", "logs/alerts.jsonl")
    redis_url: str = os.getenv("REDIS_URL", "")

    log_dir: str = os.getenv("ALERT_RISK_AGENT_LOG_DIR", "logs")

    # Optional -- richer LLM-generated alert descriptions/recommended actions.
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    # Real-time web intelligence and search feeds (Tavily & SerpAPI)
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    serpapi_api_key: str = os.getenv("SERPAPI_API_KEY", "")

    @property
    def has_redis(self) -> bool:
        return bool(self.redis_url)

    @property
    def has_llm_key(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def has_tavily(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def has_serpapi(self) -> bool:
        return bool(self.serpapi_api_key)


settings = Settings()
