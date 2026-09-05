"""
backend/app/ml/inference/rainfall_lstm_live.py
────────────────────────────────────────────────────────────────────
Live inference wrapper for the trained LSTM rainfall model
(machine_learning_module/artifacts/deep_learning/dl_lstm_v1/model.joblib).

Pipeline:
  1. Fetch ~120 hours of hourly weather from Open-Meteo's FORECAST API
     (api.open-meteo.com/v1/forecast, with past_days=5) — this endpoint,
     unlike the ERA5 archive API, supports `cape`, which the model needs.
  2. Rename/derive columns to match training column names exactly.
  3. Engineer the same 44 FEATURE_COLS used in final_preprocessing.py
     (rolling windows, lags, trend/change features, antecedent-condition
     features, 5 engineered interaction features, cyclic + calendar time
     features).
  4. Scale continuous columns using the EXACT mean/std saved in
     ml_ready/scaler_params.csv (never refit live — must match training).
  5. Take the last 24 rows (sequence_length=24) and run them through the
     trained DeepLearningModel (LSTM) via BasePredictor.from_artifact.

ASSUMPTIONS (verify against your actual final_preprocessing.py and correct
if these don't match — search for "season" / "is_monsoon" / how rolling
features are computed if unsure):
  - Rolling/lag features are computed on `precipitation_openmeteo`.
  - is_monsoon = 1 if month in [6,7,8,9] else 0.
  - season: 0=Winter(Dec-Feb) 1=Summer(Mar-May) 2=Monsoon(Jun-Sep) 3=PostMonsoon(Oct-Nov)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd

# ── Make the machine_learning_module package importable ────────────────
BACKEND_APP_DIR = Path(__file__).resolve().parent.parent.parent  # backend/app
PROJECT_ROOT = BACKEND_APP_DIR.parent.parent  # Weather_Data_Project root
ML_MODULE_DIR = PROJECT_ROOT / "machine_learning_module"
sys.path.insert(0, str(ML_MODULE_DIR))

from models.common.base_model import BasePredictor  # noqa: E402
from models.deep_learning.config import DeepLearningConfig  # noqa: E402
from models.deep_learning.model import DeepLearningModel  # noqa: E402

MODEL_PATH = ML_MODULE_DIR / "artifacts" / "deep_learning" / "dl_lstm_v1" / "model.joblib"
SCALER_PARAMS_PATH = PROJECT_ROOT / "ml_ready" / "scaler_params.csv"

SEQUENCE_LENGTH = 24
# Need enough history before the 24-row sequence to compute rolling_precip_72h
# (72h window) + lag_72h + change features. 72 + 24 + small buffer.
HOURS_NEEDED = 72 + SEQUENCE_LENGTH + 6

DISTRICT_COORDINATES = {
    "Mandi": {"lat": 31.5892, "lon": 76.9182},
    "Kullu": {"lat": 31.9578, "lon": 77.1095},
    "Chamba": {"lat": 32.5534, "lon": 76.1258},
    "Shimla": {"lat": 31.1048, "lon": 77.1734},
    "Kangra": {"lat": 32.0998, "lon": 76.2691},
}

FEATURE_COLS = [
    "temperature_2m", "dewpoint_2m", "relative_humidity", "surface_pressure",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "wind_u_10m",
    "wind_v_10m", "cloud_cover", "cape",
    "precipitation_openmeteo", "rain_openmeteo", "snowfall",
    "rolling_precip_3h", "rolling_precip_6h", "rolling_precip_24h", "rolling_precip_72h",
    "precip_lag_1h", "precip_lag_3h", "precip_lag_6h", "precip_lag_12h",
    "precip_lag_24h", "precip_lag_48h", "precip_lag_72h",
    "pressure_change_1h", "pressure_change_3h", "pressure_change_6h",
    "temp_change_1h", "temp_change_3h", "temp_change_6h",
    "dewpoint_change_1h", "dewpoint_change_3h",
    "consecutive_rain_hours", "dry_spell_hours",
    "temp_dewpoint_spread", "wind_gust_ratio", "precip_acceleration",
    "humidity_cape_interact", "rolling_ratio_3_24",
    "hour_sin", "hour_cos", "month_sin", "month_cos",
    "hour", "month", "day_of_year", "season", "is_monsoon",
    "week_of_year", "day_of_week", "is_weekend",
]

DO_NOT_SCALE = {
    "hour_sin", "hour_cos", "month_sin", "month_cos",
    "hour", "month", "day_of_year", "season", "is_monsoon",
    "wind_direction_10m", "week_of_year", "day_of_week", "is_weekend",
}


# ══════════════════════════════════════════════════════════
#  STEP 1: FETCH LIVE HOURLY DATA (forecast API — supports cape + past_days)
# ══════════════════════════════════════════════════════════

async def fetch_recent_hourly(district: str, hours_back: int = HOURS_NEEDED) -> pd.DataFrame:
    coords = DISTRICT_COORDINATES[district]
    past_days = max(1, (hours_back // 24) + 2)  # buffer

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": coords["lat"],
        "longitude": coords["lon"],
        "past_days": past_days,
        "forecast_days": 1,
        "hourly": ",".join([
            "temperature_2m", "dewpoint_2m", "relative_humidity_2m",
            "surface_pressure", "wind_speed_10m", "wind_direction_10m",
            "wind_gusts_10m", "cloud_cover", "cape",
            "precipitation", "rain", "snowfall",
        ]),
        "timezone": "UTC",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()

    hourly = data.get("hourly", {})
    df = pd.DataFrame(hourly)
    df["time"] = pd.to_datetime(df["time"])

    # Rename to match training column names exactly
    df = df.rename(columns={
        "relative_humidity_2m": "relative_humidity",
        "precipitation": "precipitation_openmeteo",
        "rain": "rain_openmeteo",
    })

    # Keep only rows up to "now" (drop the forecast_days=1 future rows we don't need)
    now = pd.Timestamp.utcnow().tz_localize(None)
    df = df[df["time"] <= now].reset_index(drop=True)

    # Trim to exactly the trailing `hours_back` hours
    df = df.tail(hours_back).reset_index(drop=True)

    return df


# ══════════════════════════════════════════════════════════
#  STEP 2: DERIVE wind_u / wind_v (trigonometry, same as final_preprocessing.py Step 7B)
# ══════════════════════════════════════════════════════════

def derive_wind_components(df: pd.DataFrame) -> pd.DataFrame:
    speed = df["wind_speed_10m"]
    direction_rad = np.deg2rad(df["wind_direction_10m"])
    df["wind_u_10m"] = -speed * np.sin(direction_rad)
    df["wind_v_10m"] = -speed * np.cos(direction_rad)
    return df


# ══════════════════════════════════════════════════════════
#  STEP 3: ENGINEER ALL 44 FEATURES (mirrors final_preprocessing.py)
# ══════════════════════════════════════════════════════════

def engineer_all_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    precip_col = "precipitation_openmeteo"

    # ---- Rolling windows ----
    df["rolling_precip_3h"] = df[precip_col].rolling(3, min_periods=1).sum()
    df["rolling_precip_6h"] = df[precip_col].rolling(6, min_periods=1).sum()
    df["rolling_precip_24h"] = df[precip_col].rolling(24, min_periods=1).sum()
    df["rolling_precip_72h"] = df[precip_col].rolling(72, min_periods=1).sum()

    # ---- Lags ----
    for h in [1, 3, 6, 12, 24, 48, 72]:
        df[f"precip_lag_{h}h"] = df[precip_col].shift(h).fillna(0.0)

    # ---- Pressure / temp / dewpoint change ----
    for h in [1, 3, 6]:
        df[f"pressure_change_{h}h"] = df["surface_pressure"].diff(h).fillna(0.0)
        df[f"temp_change_{h}h"] = df["temperature_2m"].diff(h).fillna(0.0)
    for h in [1, 3]:
        df[f"dewpoint_change_{h}h"] = df["dewpoint_2m"].diff(h).fillna(0.0)

    # ---- Antecedent-condition features (based on precip_lag_1h only) ----
    wet = (df["precip_lag_1h"] > 0).astype(int)
    consec = wet.groupby((wet != wet.shift()).cumsum()).cumsum() * wet
    df["consecutive_rain_hours"] = consec

    dry = (df["precip_lag_1h"] <= 0).astype(int)
    dry_run = dry.groupby((dry != dry.shift()).cumsum()).cumsum() * dry
    df["dry_spell_hours"] = dry_run

    # ---- 5 engineered interaction features ----
    df["temp_dewpoint_spread"] = (df["temperature_2m"] - df["dewpoint_2m"]).clip(lower=0)
    df["wind_gust_ratio"] = (df["wind_gusts_10m"] / (df["wind_speed_10m"] + 0.1)).clip(upper=20)
    df["precip_acceleration"] = df["precip_lag_1h"] - df["precip_lag_3h"]
    df["humidity_cape_interact"] = (df["relative_humidity"] / 100.0) * df["cape"]
    df["rolling_ratio_3_24"] = (df["rolling_precip_3h"] / (df["rolling_precip_24h"] + 0.1)).clip(upper=10)

    # ---- Cyclic + calendar time features ----
    df["hour"] = df["time"].dt.hour
    df["month"] = df["time"].dt.month
    df["day_of_year"] = df["time"].dt.dayofyear
    df["week_of_year"] = df["time"].dt.isocalendar().week.astype(int)
    df["day_of_week"] = df["time"].dt.dayofweek
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    df["is_monsoon"] = df["month"].isin([6, 7, 8, 9]).astype(int)

    def _season(m: int) -> int:
        if m in (12, 1, 2):
            return 0  # Winter
        if m in (3, 4, 5):
            return 1  # Summer
        if m in (6, 7, 8, 9):
            return 2  # Monsoon
        return 3  # Post-monsoon (10, 11)

    df["season"] = df["month"].apply(_season)

    return df


# ══════════════════════════════════════════════════════════
#  STEP 4: SCALE using saved scaler params (NEVER refit live)
# ══════════════════════════════════════════════════════════

_scaler_params: pd.DataFrame | None = None


def _load_scaler_params() -> pd.DataFrame:
    global _scaler_params
    if _scaler_params is None:
        _scaler_params = pd.read_csv(SCALER_PARAMS_PATH).set_index("feature")
    return _scaler_params


def scale_features(df: pd.DataFrame) -> pd.DataFrame:
    params = _load_scaler_params()
    df = df.copy()
    for feat in FEATURE_COLS:
        if feat in DO_NOT_SCALE or feat not in df.columns:
            continue
        if feat not in params.index:
            continue
        mean = params.loc[feat, "mean"]
        std = params.loc[feat, "std"]
        df[feat] = (df[feat] - mean) / (std if std != 0 else 1.0)
    return df


# ══════════════════════════════════════════════════════════
#  STEP 5: FULL PIPELINE + LSTM PREDICTION
# ══════════════════════════════════════════════════════════

_predictor: BasePredictor | None = None


def _get_predictor() -> BasePredictor:
    global _predictor
    if _predictor is None:
        config = DeepLearningConfig(
            task_type="regression",
            data_dir=str(PROJECT_ROOT / "ml_ready"),
            target_column="imd_rainfall_mm",
            experiment_name="dl_lstm_v1",
            architecture="lstm",
            sequence_length=SEQUENCE_LENGTH,
            hidden_size=64,
            num_layers=2,
            dropout=0.2,
            device="cpu",
        )
        _predictor = BasePredictor.from_artifact(DeepLearningModel, config, str(MODEL_PATH))
    return _predictor


async def predict_rainfall_lstm(district: str) -> dict[str, Any]:
    """
    Full live pipeline: fetch -> engineer -> scale -> predict.
    Returns a dict with predicted_mm and metadata.
    """
    raw = await fetch_recent_hourly(district)
    raw = derive_wind_components(raw)
    engineered = engineer_all_features(raw)

    missing = [c for c in FEATURE_COLS if c not in engineered.columns]
    if missing:
        raise ValueError(f"Missing engineered feature columns: {missing}")

    scaled = scale_features(engineered)

    # Take the last SEQUENCE_LENGTH rows in the exact FEATURE_COLS order
    X = scaled[FEATURE_COLS].tail(SEQUENCE_LENGTH).reset_index(drop=True)

    if len(X) < SEQUENCE_LENGTH:
        raise ValueError(
            f"Only {len(X)} hourly rows available, need {SEQUENCE_LENGTH}. "
            "Open-Meteo may not have returned enough history."
        )

    predictor = _get_predictor()
    result_df = predictor.predict_dataframe(X)
    # predict_dataframe likely returns one row per input row; the model
    # was trained to predict the NEXT hour from the trailing 24h window,
    # so take the last prediction row.
    predicted_mm = float(result_df.iloc[-1, 0])
    predicted_mm = max(0.0, predicted_mm)

    return {
        "precipitation_mm": round(predicted_mm, 2),
        "risk_level": "HIGH" if predicted_mm > 50 else "MEDIUM" if predicted_mm > 20 else "LOW",
        "model": "lstm_v1_live",
        "district": district,
    }
