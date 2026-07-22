"""
app/api/v1/routers/prediction_router.py
────────────────────────────────────────
Real prediction endpoints using trained models and live Open-Meteo features.
Bypasses DB to serve live inferences directly to the frontend.
"""

import os
from pathlib import Path
from fastapi import APIRouter
import joblib
import pandas as pd
import numpy as np

from app.integrations.weather.open_meteo_extended import OpenMeteoExtendedProvider
from app.ml.inference.rainfall_lstm_live import predict_rainfall_lstm

router = APIRouter()
provider = OpenMeteoExtendedProvider()

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
MODELS_DIR = BASE_DIR / "ml_models"

# Load sklearn models if they exist (safe fallback if not trained yet)
models = {}
for m_name in ["xgboost", "lightgbm", "randomforest"]:
    m_path = MODELS_DIR / f"rainfall_{m_name}.pkl"
    if m_path.exists():
        models[m_name] = joblib.load(m_path)


def _get_risk_level(rain_pred: float, hazard_type: str) -> str:
    if hazard_type == "flood":
        if rain_pred > 20: return "severe"
        if rain_pred > 10: return "high"
        if rain_pred > 4: return "moderate"
        return "low"
    elif hazard_type == "cloudburst":
        if rain_pred > 30: return "severe"
        if rain_pred > 15: return "high"
        if rain_pred > 8: return "moderate"
        return "low"
    return "low"


async def _run_prediction_for_hazard_lstm(hazard: str):
    """Live prediction using the trained LSTM (best-performing model: R2=0.479)."""
    predictions = []

    for dist in ["Mandi", "Kullu", "Chamba"]:
        try:
            lstm_result = await predict_rainfall_lstm(dist)
            pred_rain = lstm_result["precipitation_mm"]
            model_used = "lstm_v1_live"
            confidence = 85
        except Exception as exc:
            # Fallback to sklearn model or heuristic if LSTM pipeline fails
            # (e.g. Open-Meteo API hiccup, insufficient history)
            model = models.get("lightgbm") or models.get("xgboost")
            data = await provider.fetch_current_and_forecast(dist)
            current = data["current"]
            if model:
                features = pd.DataFrame([{
                    'temperature_2m': current["temperature"],
                    'relative_humidity_2m': current["humidity"],
                    'surface_pressure': current["pressure"],
                    'cloud_cover': current["cloudCover"],
                    'wind_speed_10m': current["windSpeed"],
                    'hour': 12, 'day_of_year': 200, 'month': 7,
                    'temp_lag1': current["temperature"],
                    'humidity_lag1': current["humidity"],
                    'precip_lag1': current["rainfall"],
                    'precip_roll_3h': current["rainfall"] * 3
                }])
                pred_rain = max(0, float(model.predict(features)[0]))
                model_used = "lightgbm_fallback"
                confidence = 60
            else:
                pred_rain = current["rainfall"] * 1.2
                model_used = "heuristic_fallback"
                confidence = 40
            print(f"[WARN] LSTM prediction failed for {dist}: {exc}. Used {model_used}.")

        prob = min(100, int((pred_rain / 50) * 100))

        predictions.append({
            "hazard": hazard,
            "district": dist,
            "probability": prob,
            "risk": _get_risk_level(pred_rain, hazard),
            "predicted_rainfall_mm": pred_rain,
            "model": model_used,
            "confidence": confidence,
            "horizon_hours": 24,
        })

    return {"data": predictions}


@router.get("/flood")
async def get_flood_predictions():
    return await _run_prediction_for_hazard_lstm("flood")


@router.get("/cloudburst")
async def get_cloudburst_predictions():
    return await _run_prediction_for_hazard_lstm("cloudburst")


@router.get("/rainfall/forecast")
async def get_rainfall_forecast():
    # Simple pass-through of Open-Meteo 7-day forecast
    data = await provider.fetch_current_and_forecast("Mandi")
    return {"data": data["forecast_7d"]}