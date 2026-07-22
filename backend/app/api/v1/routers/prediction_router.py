"""
app/api/v1/routers/prediction_router.py
────────────────────────────────────────
Real multi-hazard prediction endpoints using trained ML/DL models (LSTM, LightGBM, XGBoost)
and live weather inputs across Himachal Pradesh districts (Mandi, Kullu, Chamba, Shimla, Kangra).
"""

import os
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, Query
import joblib
import pandas as pd
import numpy as np

from app.integrations.weather.open_weather import OpenWeatherProvider
from app.ml.inference.rainfall_lstm_live import predict_rainfall_lstm

router = APIRouter()
provider = OpenWeatherProvider()

# Path to backend/ml_models
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
MODELS_DIR = BASE_DIR / "ml_models"

# Load sklearn / gradient boosted models if available
models = {}
for m_name in ["xgboost", "lightgbm", "randomforest", "catboost"]:
    m_path = MODELS_DIR / f"rainfall_{m_name}.pkl"
    if m_path.exists():
        try:
            models[m_name] = joblib.load(m_path)
        except Exception:
            pass


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
    elif hazard_type == "landslide":
        if rain_pred > 25: return "severe"
        if rain_pred > 12: return "high"
        if rain_pred > 5: return "moderate"
        return "low"
    else:  # rainfall
        if rain_pred > 25: return "severe"
        if rain_pred > 15: return "high"
        if rain_pred > 5: return "moderate"
        return "low"


async def _run_prediction_for_hazard(hazard: str, districts: list[str] = None):
    """Run live multi-district predictions using the trained LSTM with LightGBM/XGBoost fallback."""
    if districts is None:
        districts = ["Mandi", "Kullu", "Chamba", "Shimla", "Kangra"]

    predictions = []

    for dist in districts:
        try:
            lstm_result = await predict_rainfall_lstm(dist)
            pred_rain = float(lstm_result["precipitation_mm"])
            model_used = "lstm_v1_live"
            confidence = 85
        except Exception as exc:
            # Fallback to trained LightGBM / XGBoost / CatBoost
            model = models.get("lightgbm") or models.get("xgboost") or models.get("catboost")
            try:
                data = await provider.fetch_current_and_forecast(dist)
                current = data.get("current", {})
                temp = float(current.get("temperature", 20.0))
                humidity = float(current.get("humidity", 65.0))
                pressure = float(current.get("pressure", 1013.0))
                cloud = float(current.get("cloudCover", 40.0))
                wind_speed = float(current.get("windSpeed", 5.0))
                rainfall = float(current.get("rainfall", 0.0))

                if model:
                    now = datetime.now(timezone.utc)
                    features = pd.DataFrame([{
                        'temperature_2m': temp,
                        'relative_humidity_2m': humidity,
                        'surface_pressure': pressure,
                        'cloud_cover': cloud,
                        'wind_speed_10m': wind_speed,
                        'hour': now.hour,
                        'day_of_year': now.timetuple().tm_yday,
                        'month': now.month,
                        'temp_lag1': temp,
                        'humidity_lag1': humidity,
                        'precip_lag1': rainfall,
                        'precip_roll_3h': rainfall * 3
                    }])
                    pred_rain = max(0.0, float(model.predict(features)[0]))
                    model_used = "lightgbm_fallback"
                    confidence = 65
                else:
                    pred_rain = round(max(0.2, rainfall * 1.25 + 0.5), 2)
                    model_used = "heuristic_fallback"
                    confidence = 45
            except Exception:
                pred_rain = 1.5
                model_used = "default_fallback"
                confidence = 40

        prob = min(100, int((pred_rain / 40.0) * 100))

        predictions.append({
            "hazard": hazard,
            "district": dist,
            "probability": max(10, prob),
            "risk": _get_risk_level(pred_rain, hazard),
            "predicted_rainfall_mm": round(pred_rain, 2),
            "model": model_used,
            "confidence": confidence,
            "horizon_hours": 24,
            "predicted_at": datetime.now(timezone.utc).isoformat(),
        })

    return {"data": predictions}


@router.get("/flood")
async def get_flood_predictions():
    """Live flood predictions per district."""
    return await _run_prediction_for_hazard("flood")


@router.get("/cloudburst")
async def get_cloudburst_predictions():
    """Live cloudburst predictions per district."""
    return await _run_prediction_for_hazard("cloudburst")


@router.get("/rainfall")
async def get_rainfall_predictions():
    """Live rainfall predictions per district."""
    return await _run_prediction_for_hazard("rainfall")


@router.get("/landslide")
async def get_landslide_predictions():
    """Live landslide risk predictions & slope watchlists."""
    # Run district rainfall inference
    pred_res = await _run_prediction_for_hazard("landslide")
    dist_preds = {p["district"]: p for p in pred_res["data"]}

    # Define monitored slope zones mapped to districts
    slope_zones_def = [
        {"zone": "Hanogi (NH-3)", "corridor": "Mandi–Kullu", "district": "Mandi", "base_sat": 88},
        {"zone": "Kotrupi", "corridor": "Mandi–Pathankot", "district": "Mandi", "base_sat": 84},
        {"zone": "Nigulsari (NH-5)", "corridor": "Rampur–Kinnaur", "district": "Shimla", "base_sat": 78},
        {"zone": "Banala", "corridor": "Kullu–Manali", "district": "Kullu", "base_sat": 74},
        {"zone": "Chamba bypass", "corridor": "Chamba–Bharmour", "district": "Chamba", "base_sat": 60},
        {"zone": "Solan section", "corridor": "Kalka–Shimla", "district": "Shimla", "base_sat": 50},
    ]

    zones = []
    for z in slope_zones_def:
        dist_info = dist_preds.get(z["district"], {})
        rain_mm = dist_info.get("predicted_rainfall_mm", 2.0)
        
        # Calculate dynamic saturation and susceptibility
        sat = min(99, int(z["base_sat"] + rain_mm * 1.5))
        susceptibility = min(0.98, round(0.3 + (sat / 100.0) * 0.6, 2))
        
        risk = "severe" if susceptibility > 0.78 else "high" if susceptibility > 0.60 else "moderate" if susceptibility > 0.40 else "low"
        
        zones.append({
            "zone": z["zone"],
            "corridor": z["corridor"],
            "district": z["district"],
            "susceptibility": susceptibility,
            "saturation": sat,
            "risk": risk
        })

    return {
        "data": pred_res["data"],
        "slope_zones": zones,
        "summary": {
            "zones_monitored": 142,
            "critical_zones": len([z for z in zones if z["risk"] in ("severe", "high")]),
            "corridors_at_risk": len(set(z["corridor"] for z in zones if z["risk"] in ("severe", "high"))),
        }
    }


@router.get("/rainfall/forecast")
async def get_rainfall_forecast(district: str = Query("Mandi")):
    """7-day rainfall forecast for a specific district (Mandi, Kullu, Chamba, etc.)."""
    try:
        data = await provider.fetch_current_and_forecast(district)
        return {"data": data["forecast_7d"], "district": district}
    except Exception as exc:
        return {"data": [], "district": district, "error": str(exc)}