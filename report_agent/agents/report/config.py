"""
Environment-driven configuration for the Report Generation Agent.

Nothing is strictly required -- report generation (PDF/Excel/JSON/charts)
works with zero external dependencies. Set the other agents' URLs to pull
in real data instead of running reports off caller-supplied data alone.
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
    # Sibling agents this one aggregates data from.
    weather_agent_url: str = os.getenv("WEATHER_AGENT_URL", "http://localhost:8001")
    prediction_agent_url: str = os.getenv("PREDICTION_AGENT_URL", "http://localhost:8002")
    alert_agent_url: str = os.getenv("ALERT_AGENT_URL", "http://localhost:8003")
    digital_twin_agent_url: str = os.getenv("DIGITAL_TWIN_AGENT_URL", "http://localhost:8004")
    agent_request_timeout_seconds: float = float(os.getenv("AGENT_REQUEST_TIMEOUT_SECONDS", "20"))

    reports_output_dir: str = os.getenv("REPORTS_OUTPUT_DIR", "reports_output")
    report_log_path: str = os.getenv("REPORT_LOG_PATH", "logs/reports.jsonl")

    redis_url: str = os.getenv("REDIS_URL", "")
    log_dir: str = os.getenv("REPORT_AGENT_LOG_DIR", "logs")

    # Optional -- richer LLM-generated narrative insights instead of the
    # rule-based templates.
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    @property
    def has_redis(self) -> bool:
        return bool(self.redis_url)

    @property
    def has_llm_key(self) -> bool:
        return bool(self.groq_api_key)


settings = Settings()
