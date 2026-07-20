"""
Environment-driven configuration for the Digital Twin Agent.

Nothing is strictly required -- the agent runs scenario simulations using
real hydrology/landslide formulas (see hydrology_model.py / landslide_model.py)
with reasonable defaults if your actual DEM/GeoJSON/infrastructure layers
aren't found on disk at these paths, honestly flagging when it's falling
back to defaults rather than real terrain data.
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
    digital_twin_dir: str = os.getenv("DIGITAL_TWIN_DIR", "../digital_twin")
    boundaries_dir: str = os.getenv("BOUNDARIES_DIR", "")  # resolved under digital_twin_dir if unset
    infrastructure_dir: str = os.getenv("INFRASTRUCTURE_DIR", "")  # resolved under digital_twin_dir if unset

    # Hydrology (Rational Method) defaults -- see hydrology_model.py.
    # Runoff coefficient C by land-cover class: steep forested Himalayan
    # terrain runs higher than flat cropland. These are standard textbook
    # ranges (ASCE Manual 37 / FHWA HEC-22), not measured for Mandi/Kullu/
    # Chamba specifically -- replace with calibrated values once you have
    # real gauged discharge to fit against.
    default_runoff_coefficient: float = float(os.getenv("DEFAULT_RUNOFF_COEFFICIENT", "0.55"))
    default_catchment_area_km2: float = float(os.getenv("DEFAULT_CATCHMENT_AREA_KM2", "50.0"))
    default_channel_capacity_m3s: float = float(os.getenv("DEFAULT_CHANNEL_CAPACITY_M3S", "25.0"))

    # Landslide (Caine 1980 global ID threshold: I = 14.82 * D^-0.39, mm/hr,
    # D in hours) -- a well-known, widely-cited *global* threshold, not
    # calibrated regionally for Himachal Pradesh. Regional studies generally
    # find lower, more conservative thresholds for the Himalaya; treat this
    # as a starting point, not a substitute for a locally-calibrated one.
    caine_coefficient: float = float(os.getenv("CAINE_COEFFICIENT", "14.82"))
    caine_exponent: float = float(os.getenv("CAINE_EXPONENT", "-0.39"))
    default_slope_class: str = os.getenv("DEFAULT_SLOPE_CLASS", "steep")  # gentle|moderate|steep

    redis_url: str = os.getenv("REDIS_URL", "")
    twin_state_log_path: str = os.getenv("TWIN_STATE_LOG_PATH", "logs/digital_twin_state.jsonl")
    log_dir: str = os.getenv("DIGITAL_TWIN_AGENT_LOG_DIR", "logs")

    @property
    def has_redis(self) -> bool:
        return bool(self.redis_url)


settings = Settings()
