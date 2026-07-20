"""
utils/http_client.py
─────────────────────
Builds a requests.Session pre-configured with:
  - Retry on network errors and specific HTTP status codes
  - Exponential backoff between retries
  - Default timeout (applied per-request via the session)
  - User-Agent header

Every collector calls build_session() rather than creating raw requests.Session().
"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.config_loader import get_config


def build_session(extra_headers: dict[str, str] | None = None) -> requests.Session:
    """
    Return a requests.Session configured with retry + backoff from config.

    Parameters
    ----------
    extra_headers : dict, optional
        Additional headers (e.g. Authorization tokens) to merge into the session.

    Returns
    -------
    requests.Session
    """
    cfg  = get_config()
    http = cfg["http"]

    retry_strategy = Retry(
        total             = http["max_retries"],
        backoff_factor    = http["backoff_factor"],
        status_forcelist  = http.get("retry_on_status", [429, 500, 502, 503, 504]),
        allowed_methods   = ["GET", "POST"],
        raise_on_status   = False,
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://",  adapter)

    session.headers.update({
        "User-Agent": "WeatherDataProject/1.0 (Research; Mandi-HP)",
        "Accept":     "application/json",
    })

    if extra_headers:
        session.headers.update(extra_headers)

    return session


def get_timeout() -> int:
    """Return the configured HTTP timeout in seconds."""
    return get_config()["http"]["timeout_seconds"]
