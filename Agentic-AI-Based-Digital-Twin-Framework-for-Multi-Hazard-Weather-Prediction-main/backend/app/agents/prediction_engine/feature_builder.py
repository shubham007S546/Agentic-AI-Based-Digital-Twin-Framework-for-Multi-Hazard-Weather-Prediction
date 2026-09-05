"""
Builds the 35 model-input features from raw hourly weather readings, then
applies the same standardization your training pipeline used (via
scaler_params.csv), so the feature vector this agent produces matches the
scale your model was actually trained on.

Read the "IMPORTANT" note in schemas.py before trusting this for anything
beyond pipeline testing -- several formulas here are best-effort
reconstructions from column names, not copied from your real
final_preprocessing.py (which I haven't seen the body of).
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from .logging_config import get_logger
from .schemas import FEATURE_COLUMNS, RawHourlyReading

logger = get_logger(__name__)

_EPS = 1e-6


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _season_index(month: int) -> int:
    """Best-effort season encoding (0=winter, 1=summer, 2=monsoon,
    3=post-monsoon/autumn) for Himachal Pradesh. VERIFY against your real
    final_preprocessing.py -- this is a reasonable guess, not a copy."""
    if month in (12, 1, 2):
        return 0  # winter
    if month in (3, 4, 5):
        return 1  # summer / pre-monsoon
    if month in (6, 7, 8, 9):
        return 2  # monsoon
    return 3  # post-monsoon (Oct, Nov)


def _is_monsoon(month: int) -> int:
    """June-September, standard Indian monsoon window. VERIFY against your
    real preprocessing if it uses a different cutoff (e.g. mid-June)."""
    return 1 if month in (6, 7, 8, 9) else 0


def build_raw_features(history: List[RawHourlyReading], target_timestamp: str) -> Dict[str, float]:
    """
    `history` must be sorted oldest -> newest, with the LAST reading being
    the one to predict from (i.e. the most recent observation at or before
    target_timestamp). Needs at least 72 hourly readings for the 72h rolling
    window to be meaningful -- fewer than that still works, just with a
    shorter effective window (logged as a warning by the caller).
    """
    if not history:
        raise ValueError("history must contain at least one reading.")

    df = pd.DataFrame([h.model_dump() for h in history])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    latest = df.iloc[-1]
    target_dt = _parse_ts(target_timestamp)

    # rolling sums of precipitation over the trailing N hours (inclusive of latest)
    precip = df["precipitation_openmeteo"]
    rolling_precip_3h = precip.tail(3).sum()
    rolling_precip_6h = precip.tail(6).sum()
    rolling_precip_24h = precip.tail(24).sum()
    rolling_precip_72h = precip.tail(72).sum()

    def _lag(hours: int) -> float:
        idx = len(df) - 1 - hours
        return float(precip.iloc[idx]) if idx >= 0 else 0.0

    precip_lag_1h = _lag(1)
    precip_lag_3h = _lag(3)
    precip_lag_6h = _lag(6)

    # precip_acceleration: change in short-window rolling sum vs. one step
    # earlier -- a proxy for "is rainfall intensifying right now". Best-effort;
    # verify definition against your real preprocessing.
    if len(df) >= 4:
        prev_rolling_3h = precip.iloc[-4:-1].sum()
        precip_acceleration = float(rolling_precip_3h - prev_rolling_3h)
    else:
        precip_acceleration = 0.0

    temp_dewpoint_spread = float(latest["temperature_2m"] - latest["dewpoint_2m"])
    wind_gust_ratio = float(latest["wind_gusts_10m"] / (latest["wind_speed_10m"] + _EPS))
    humidity_cape_interact = float(latest["relative_humidity"] * latest["cape"])
    rolling_ratio_3_24 = float(rolling_precip_3h / (rolling_precip_24h + _EPS))

    wind_dir_rad = math.radians(float(latest["wind_direction_10m"]))
    wind_u_10m = float(-latest["wind_speed_10m"] * math.sin(wind_dir_rad))
    wind_v_10m = float(-latest["wind_speed_10m"] * math.cos(wind_dir_rad))

    hour = target_dt.hour
    month = target_dt.month
    day_of_year = target_dt.timetuple().tm_yday

    features = {
        "temperature_2m": float(latest["temperature_2m"]),
        "dewpoint_2m": float(latest["dewpoint_2m"]),
        "relative_humidity": float(latest["relative_humidity"]),
        "surface_pressure": float(latest["surface_pressure"]),
        "wind_speed_10m": float(latest["wind_speed_10m"]),
        "wind_direction_10m": float(latest["wind_direction_10m"]),
        "wind_gusts_10m": float(latest["wind_gusts_10m"]),
        "wind_u_10m": wind_u_10m,
        "wind_v_10m": wind_v_10m,
        "cloud_cover": float(latest["cloud_cover"]),
        "cape": float(latest["cape"]),
        "precipitation_openmeteo": float(latest["precipitation_openmeteo"]),
        "rain_openmeteo": float(latest["rain_openmeteo"]),
        "snowfall": float(latest["snowfall"]),
        "rolling_precip_3h": float(rolling_precip_3h),
        "rolling_precip_6h": float(rolling_precip_6h),
        "rolling_precip_24h": float(rolling_precip_24h),
        "rolling_precip_72h": float(rolling_precip_72h),
        "precip_lag_1h": precip_lag_1h,
        "precip_lag_3h": precip_lag_3h,
        "precip_lag_6h": precip_lag_6h,
        "temp_dewpoint_spread": temp_dewpoint_spread,
        "wind_gust_ratio": wind_gust_ratio,
        "precip_acceleration": precip_acceleration,
        "humidity_cape_interact": humidity_cape_interact,
        "rolling_ratio_3_24": rolling_ratio_3_24,
        "hour_sin": math.sin(2 * math.pi * hour / 24),
        "hour_cos": math.cos(2 * math.pi * hour / 24),
        "month_sin": math.sin(2 * math.pi * month / 12),
        "month_cos": math.cos(2 * math.pi * month / 12),
        "hour": float(hour),
        "month": float(month),
        "day_of_year": float(day_of_year),
        "season": float(_season_index(month)),
        "is_monsoon": float(_is_monsoon(month)),
    }

    missing = set(FEATURE_COLUMNS) - set(features)
    if missing:
        raise RuntimeError(f"Internal error: missing features {missing}")

    return features


def load_scaler_params(scaler_params_path: str) -> Optional[pd.DataFrame]:
    """Expects a CSV with columns like ['feature', 'mean', 'std'] -- adjust
    the column names below if your actual scaler_params.csv uses different
    ones (I inferred the shape from final_preprocessing.py's docstring,
    haven't seen the real file)."""
    try:
        df = pd.read_csv(scaler_params_path)
        return df.set_index(df.columns[0])
    except Exception as exc:
        logger.warning("Could not load scaler_params from %s: %s", scaler_params_path, exc)
        return None


def apply_scaling(features: Dict[str, float], scaler_df: Optional[pd.DataFrame]) -> Dict[str, float]:
    if scaler_df is None:
        return features
    scaled = dict(features)
    for feature_name, value in features.items():
        if feature_name in scaler_df.index:
            row = scaler_df.loc[feature_name]
            mean = float(row.get("mean", 0.0))
            std = float(row.get("std", 1.0)) or 1.0
            scaled[feature_name] = (value - mean) / std
    return scaled


def build_feature_vector(
    history: List[RawHourlyReading], target_timestamp: str, scaler_df: Optional[pd.DataFrame] = None
) -> Dict[str, float]:
    raw = build_raw_features(history, target_timestamp)
    return apply_scaling(raw, scaler_df)
