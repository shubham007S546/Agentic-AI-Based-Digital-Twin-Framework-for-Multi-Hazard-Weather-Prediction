"""
Environment-driven configuration for the Orchestrator Agent.

Required
--------
GROQ_API_KEY        Your Groq API key (https://console.groq.com). If unset,
                     the agent falls back to a rule-based stand-in for the LLM
                     so the whole pipeline is still runnable/testable without
                     a key -- see llm.py for what that fallback actually does
                     (it is NOT a substitute for real intent understanding,
                     just enough to keep the graph wired end-to-end).

Optional
--------
GROQ_MODEL           Defaults to "llama-3.3-70b-versatile".
REDIS_URL            e.g. "redis://localhost:6379/0". If unset, conversation
                     memory is kept in-process (a plain dict) instead --
                     fine for local dev / a single-process deployment, but
                     it will NOT persist across restarts or scale across
                     multiple orchestrator instances.
ORCHESTRATOR_LOG_DIR  Defaults to "logs".
MAX_HISTORY_TURNS     Defaults to 10 (per-session turns kept for context).
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
        pass  # python-dotenv is optional; env vars can be set any other way# python-dotenv is optional; env vars can be set any other way


_load_dotenv_if_present()


@dataclass
class Settings:
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    redis_url: str = os.getenv("REDIS_URL", "")
    log_dir: str = os.getenv("ORCHESTRATOR_LOG_DIR", "logs")
    max_history_turns: int = int(os.getenv("MAX_HISTORY_TURNS", "10"))

    @property
    def has_llm_key(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def has_redis(self) -> bool:
        return bool(self.redis_url)


settings = Settings()
