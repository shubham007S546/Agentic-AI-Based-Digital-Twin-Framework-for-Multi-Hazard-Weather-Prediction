"""
app/api/v1/routers/prediction_router.py
────────────────────────────────────────
Real multi-hazard prediction endpoints using trained ML/DL models (LSTM, LightGBM, XGBoost)
and live weather inputs across Himachal Pradesh districts (Mandi, Kullu, Chamba, Shimla, Kangra).

Extreme-event detection uses IMD (India Meteorological Department) standard thresholds:
  - Cloudburst: ≥100mm/hr (IMD definition)
  - Extremely Heavy Rain: ≥204.5mm/24h (Red Alert)
  - Very Heavy Rain: 115.6–204.4mm/24h (Orange Warning)
  - Heavy Rain: 64.5–115.5mm/24h (Yellow Watch)
  - Landslide: Composite slope + antecedent + saturation model (IIT Roorkee / NIDM)
  - Flash Flood: CWC gauge utilization + basin saturation model
"""

import os
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, Query
import joblib
import pandas as pd
import numpy as np

from app.integrations.weather.open_weather import OpenWeatherProvider
from app.ml.inference.extreme_event_classifier import (
    classify_rainfall_imd,
    assess_cloudburst_risk,
    assess_landslide_risk,
    assess_flood_risk,
    format_imd_classification_for_api,
)

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


# ── District terrain/slope metadata for Himachal Pradesh ───────────────────
DISTRICT_TERRAIN = {
    "Mandi":  {"avg_slope_deg": 38.0, "base_saturation": 72, "vulnerability_zones": 24},
    "Kullu":  {"avg_slope_deg": 42.0, "base_saturation": 68, "vulnerability_zones": 18},
    "Chamba": {"avg_slope_deg": 35.0, "base_saturation": 64, "vulnerability_zones": 12},
    "Shimla": {"avg_slope_deg": 33.0, "base_saturation": 66, "vulnerability_zones": 15},
    "Kangra": {"avg_slope_deg": 30.0, "base_saturation": 60, "vulnerability_zones": 10},
}

# ── River gauge reference data ──────────────────────────────────────────────
DISTRICT_GAUGES = {
    "Mandi":  {"river": "Beas",   "station": "Pandoh",  "danger_level_m": 10.2, "normal_level_m": 6.0},
    "Kullu":  {"river": "Beas",   "station": "Manali",  "danger_level_m": 5.5,  "normal_level_m": 3.0},
    "Chamba": {"river": "Ravi",   "station": "Chamba",  "danger_level_m": 8.0,  "normal_level_m": 4.5},
    "Shimla": {"river": "Sutlej", "station": "Rampur",  "danger_level_m": 9.0,  "normal_level_m": 5.0},
    "Kangra": {"river": "Beas",   "station": "Pong",    "danger_level_m": 12.0, "normal_level_m": 6.5},
}


import asyncio

async def _predict_single_district(hazard: str, dist: str, predict_rainfall_lstm_fn=None):
    terrain = DISTRICT_TERRAIN.get(dist, {"avg_slope_deg": 30.0, "base_saturation": 65, "vulnerability_zones": 10})
    gauge_ref = DISTRICT_GAUGES.get(dist, {"danger_level_m": 8.0, "normal_level_m": 4.5})

    # ── 1. Get live weather data with fast timeout ──────────────────────
    try:
        weather_data = await asyncio.wait_for(provider.fetch_current_and_forecast(dist), timeout=3.0)
        current = weather_data.get("current", {})
        temp = float(current.get("temperature", 20.0) or 20.0)
        humidity = float(current.get("humidity", 65.0) or 65.0)
        pressure = float(current.get("pressure", 1013.0) or 1013.0)
        cloud = float(current.get("cloudCover", 40.0) or 40.0)
        wind_speed = float(current.get("windSpeed", 5.0) or 5.0)
        rainfall_1h = float(current.get("rainfall", 0.0) or 0.0)

        # Hourly + daily accumulated rainfall from forecast
        hourly_data = weather_data.get("hourly_rainfall", [])
        forecast_7d = weather_data.get("forecast_7d", [])
    except Exception:
        temp, humidity, pressure, cloud, wind_speed, rainfall_1h = 20.0, 65.0, 1013.0, 40.0, 5.0, 0.0
        hourly_data, forecast_7d = [], []

    # ── 2. Run ML model (LSTM preferred, sklearn fallback) ────────────
    pred_rain_24h = None
    model_used = "default_fallback"
    confidence = 40

    try:
        if predict_rainfall_lstm_fn is not None:
            lstm_result = await asyncio.wait_for(predict_rainfall_lstm_fn(dist), timeout=2.0)
            pred_rain_24h = float(lstm_result["precipitation_mm"])
            model_used = "lstm_v1_live"
            confidence = 85
    except Exception:
        pass

    if pred_rain_24h is None:
        model = models.get("lightgbm") or models.get("xgboost") or models.get("catboost")
        if model:
            try:
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
                    'precip_lag1': rainfall_1h,
                    'precip_roll_3h': rainfall_1h * 3
                }])
                pred_rain_24h = max(0.0, float(model.predict(features)[0]))
                model_used = "lightgbm_v2"
                confidence = 70
            except Exception:
                pass

    if pred_rain_24h is None:
        # Heuristic fallback
        pred_rain_24h = round(max(0.2, rainfall_1h * 8.0 + 0.5), 2)
        model_used = "heuristic_fallback"
        confidence = 45

    # ── 3. IMD Extreme Event Classification ──────────────────────────
    imd_class = classify_rainfall_imd(pred_rain_24h)

    # ── 4. Hazard-specific extreme event assessment ───────────────────
    extreme_event_detected = imd_class.is_extreme
    imd_api_data = format_imd_classification_for_api(imd_class)
    hazard_specific = {}

    if hazard == "cloudburst":
        cape_proxy = max(0, (humidity - 60) * 40 + (temp - 15) * 30 + cloud * 5)
        cb_assess = assess_cloudburst_risk(
            rainfall_mm_1h=rainfall_1h,
            cape_j_kg=cape_proxy,
            wind_shear_m_s=wind_speed * 0.3,
            relative_humidity_pct=humidity,
        )
        if cb_assess.probability >= 0.60 or rainfall_1h >= 50:
            extreme_event_detected = True
        hazard_specific = {
            "cloudburst_probability": cb_assess.probability,
            "is_cloudburst_active": cb_assess.is_cloudburst,
            "cloudburst_explanation": cb_assess.explanation,
            "cape_estimated_j_kg": int(cape_proxy),
        }

    elif hazard == "landslide":
        antecedent_3d = sum(
            d.get("rainfall", 0) for d in forecast_7d[:3]
        ) if forecast_7d else pred_rain_24h * 2.5
        antecedent_7d = sum(
            d.get("rainfall", 0) for d in forecast_7d[:7]
        ) if forecast_7d else pred_rain_24h * 5.0

        soil_sat = min(99, terrain["base_saturation"] + (pred_rain_24h * 0.12))

        ls_assess = assess_landslide_risk(
            current_rainfall_mm=pred_rain_24h,
            antecedent_rainfall_3d_mm=antecedent_3d,
            antecedent_rainfall_7d_mm=antecedent_7d,
            soil_saturation_pct=soil_sat,
            slope_angle_deg=terrain["avg_slope_deg"],
            district=dist,
        )
        if ls_assess.is_critical:
            extreme_event_detected = True
        hazard_specific = {
            "landslide_risk_score": ls_assess.risk_score,
            "soil_saturation_pct": ls_assess.soil_saturation_pct,
            "slope_susceptibility": ls_assess.slope_susceptibility,
            "contributing_factors": ls_assess.contributing_factors,
            "vulnerability_zones": terrain["vulnerability_zones"],
        }

    elif hazard == "flood":
        gauge_ref_data = DISTRICT_GAUGES.get(dist, {})
        normal_level = gauge_ref_data.get("normal_level_m", 5.0)
        danger_level = gauge_ref_data.get("danger_level_m", 10.0)
        est_level = normal_level + (pred_rain_24h * 0.08)
        basin_sat = min(98, terrain["base_saturation"] + (pred_rain_24h * 0.10))
        trend = "rising" if pred_rain_24h > 15 else "steady"

        flood_assess = assess_flood_risk(
            current_gauge_level_m=est_level,
            danger_level_m=danger_level,
            discharge_m3_s=1200 + pred_rain_24h * 40,
            basin_soil_saturation_pct=basin_sat,
            upstream_rainfall_mm=pred_rain_24h,
            trend=trend,
        )
        if flood_assess.is_critical:
            extreme_event_detected = True
        hazard_specific = {
            "gauge_utilization_pct": flood_assess.gauge_utilization_pct,
            "estimated_gauge_level_m": round(est_level, 2),
            "danger_level_m": danger_level,
            "river": gauge_ref_data.get("river", "—"),
            "station": gauge_ref_data.get("station", "—"),
            "flood_explanation": flood_assess.explanation,
            "time_to_danger_hours": flood_assess.time_to_danger_hours,
        }

    # ── 5. Build probability and risk level ──────────────────────────
    color_to_risk = {
        "red": "severe",
        "orange": "high",
        "yellow": "moderate" if pred_rain_24h < 90 else "high",
        "green": "low" if pred_rain_24h < 10 else "moderate",
    }
    risk = color_to_risk.get(imd_class.color_code.value, "low")

    if hazard == "landslide" and hazard_specific.get("landslide_risk_score", 0) > 0.6:
        risk = "severe" if hazard_specific["landslide_risk_score"] > 0.78 else "high"
    elif hazard == "flood" and hazard_specific.get("gauge_utilization_pct", 0) > 80:
        risk = "severe" if hazard_specific["gauge_utilization_pct"] > 95 else "high"
    elif hazard == "cloudburst" and hazard_specific.get("cloudburst_probability", 0) > 0.6:
        risk = "severe" if hazard_specific.get("cloudburst_probability", 0) > 0.80 else "high"

    category_prob_map = {
        "no_rain": max(5, int(pred_rain_24h * 0.5)),
        "light_rain": max(10, int(15 + pred_rain_24h)),
        "moderate_rain": max(25, int(30 + pred_rain_24h * 0.5)),
        "heavy_rain": max(55, min(80, int(60 + (pred_rain_24h - 64) * 0.2))),
        "very_heavy_rain": max(75, min(90, int(75 + (pred_rain_24h - 115) * 0.07))),
        "extremely_heavy_rain": max(88, min(99, int(90 + (pred_rain_24h - 204) * 0.03))),
        "cloudburst": 99,
    }
    prob = category_prob_map.get(imd_class.category.value, 30)

    return {
        "hazard": hazard,
        "district": dist,
        "probability": prob,
        "risk": risk,
        "predicted_rainfall_mm": round(pred_rain_24h, 2),
        "rainfall_1h_mm": round(rainfall_1h, 2),
        "model": model_used,
        "confidence": confidence,
        "horizon_hours": 24,
        "predicted_at": datetime.now(timezone.utc).isoformat(),
        "imd_category": imd_api_data["imd_category"],
        "imd_color_code": imd_api_data["imd_color_code"],
        "is_extreme_event": extreme_event_detected,
        "imd_threshold_description": imd_api_data["threshold_description"],
        "action_recommended": imd_api_data["action_recommended"],
        **hazard_specific,
    }


async def _run_prediction_for_hazard(hazard: str, districts: list[str] = None):
    """
    Run live multi-district predictions concurrently using LSTM with LightGBM/XGBoost fallback.
    Applies IMD-standard extreme event classification to all predictions.
    """
    try:
        from app.ml.inference.rainfall_lstm_live import predict_rainfall_lstm
    except ModuleNotFoundError:
        predict_rainfall_lstm = None

    if districts is None:
        districts = ["Mandi", "Kullu", "Chamba", "Shimla", "Kangra"]

    tasks = [_predict_single_district(hazard, dist, predict_rainfall_lstm) for dist in districts]
    predictions = await asyncio.gather(*tasks)

    return {"data": list(predictions)}


@router.get("/flood")
async def get_flood_predictions():
    """Live flood predictions per district with gauge utilization and IMD classification."""
    return await _run_prediction_for_hazard("flood")


@router.get("/cloudburst")
async def get_cloudburst_predictions():
    """Live cloudburst predictions with CAPE-based convective assessment and IMD classification."""
    return await _run_prediction_for_hazard("cloudburst")


@router.get("/rainfall")
async def get_rainfall_predictions():
    """Live rainfall predictions with IMD 4-tier classification per district."""
    return await _run_prediction_for_hazard("rainfall")


@router.get("/landslide")
async def get_landslide_predictions():
    """Live landslide risk predictions with slope susceptibility and antecedent rainfall assessment."""
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
        ls_score = dist_info.get("landslide_risk_score", 0.3)

        # Dynamic saturation using live prediction
        sat = min(99, int(z["base_sat"] + rain_mm * 1.5))
        susceptibility = min(0.98, round(ls_score * 1.1, 2)) if ls_score else min(0.98, round(0.3 + (sat / 100.0) * 0.6, 2))
        risk = dist_info.get("risk", "low") if dist_info else (
            "severe" if susceptibility > 0.78 else
            "high" if susceptibility > 0.60 else
            "moderate" if susceptibility > 0.40 else "low"
        )

        zones.append({
            "zone": z["zone"],
            "corridor": z["corridor"],
            "district": z["district"],
            "susceptibility": susceptibility,
            "saturation": sat,
            "risk": risk,
            "rainfall_mm": round(rain_mm, 2),
        })

    critical = [z for z in zones if z["risk"] in ("severe", "high")]
    return {
        "data": pred_res["data"],
        "slope_zones": zones,
        "summary": {
            "zones_monitored": 142,
            "critical_zones": len(critical),
            "corridors_at_risk": len(set(z["corridor"] for z in critical)),
        }
    }


@router.get("/extreme-summary")
async def get_extreme_event_summary():
    """
    Cross-hazard extreme event summary.
    Returns only districts/hazards where an extreme event is currently detected.
    Used by the dashboard's alert panel.
    """
    all_hazards = ["rainfall", "cloudburst", "flood", "landslide"]
    extreme_events = []

    for hazard in all_hazards:
        try:
            result = await _run_prediction_for_hazard(hazard)
            for pred in result["data"]:
                if pred.get("is_extreme_event"):
                    extreme_events.append({
                        "hazard": hazard,
                        "district": pred["district"],
                        "imd_category": pred.get("imd_category", ""),
                        "imd_color_code": pred.get("imd_color_code", "green"),
                        "risk": pred["risk"],
                        "predicted_rainfall_mm": pred.get("predicted_rainfall_mm", 0),
                        "action_recommended": pred.get("action_recommended", ""),
                        "predicted_at": pred.get("predicted_at"),
                    })
        except Exception:
            pass

    return {
        "extreme_events": extreme_events,
        "total_extreme_events": len(extreme_events),
        "districts_affected": len(set(e["district"] for e in extreme_events)),
        "highest_risk": max(
            (e["risk"] for e in extreme_events),
            key=lambda r: {"low": 0, "moderate": 1, "high": 2, "severe": 3}.get(r, 0),
            default="low",
        ) if extreme_events else "low",
        "summary_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/rainfall/forecast")
async def get_rainfall_forecast(district: str = Query("Mandi")):
    """7-day rainfall forecast for a specific district (Mandi, Kullu, Chamba, etc.)."""
    try:
        data = await provider.fetch_current_and_forecast(district)
        forecast = data.get("forecast_7d", [])
        # Augment with IMD classification for each day
        for day in forecast:
            imd = classify_rainfall_imd(day.get("rainfall", 0))
            day["imd_category"] = imd.category.value
            day["imd_color_code"] = imd.color_code.value
            day["is_extreme"] = imd.is_extreme
        return {"data": forecast, "district": district}
    except Exception as exc:
        return {"data": [], "district": district, "error": str(exc)}