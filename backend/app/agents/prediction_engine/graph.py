"""
The Prediction Agent's LangGraph state machine -- implements the diagram's
9-step workflow:

    1. Receive prediction request      (entry point, see main.py)
    2. Validate & parse input          -> validate_and_parse
    3. Gather data / build features    -> build_features
    4. Select & load model             -> select_model
    5. Run inference                   -> run_inference
    6. Post-process results            -> post_process
    7. Save & log                      -> save_and_log
    8. Return response                 (finalize, see main.py)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import pandas as pd
from langgraph.graph import END, StateGraph

from . import model_registry
from .calibration import confidence_score, is_extreme_probability, is_extreme_rainfall
from .config import settings
from .feature_builder import build_feature_vector, load_scaler_params
from .logging_config import get_logger
from .schemas import FEATURE_COLUMNS, PredictionState, RawHourlyReading
from .storage import prediction_store

logger = get_logger(__name__)

_scaler_df = None
_scaler_loaded = False


def _get_scaler():
    global _scaler_df, _scaler_loaded
    if not _scaler_loaded:
        _scaler_df = load_scaler_params(settings.scaler_params_path) if settings.has_scaler else None
        _scaler_loaded = True
    return _scaler_df


def validate_and_parse(state: PredictionState) -> PredictionState:
    request = state["request"]
    errors = []
    if request.get("hazard_type") not in ("rainfall", "cloudburst", "landslide"):
        errors.append(f"Unsupported hazard_type: {request.get('hazard_type')!r}")
    if not request.get("history"):
        errors.append("history must contain at least one raw hourly reading.")
    return {**state, "errors": errors}


def build_features(state: PredictionState) -> PredictionState:
    if state.get("errors"):
        return state

    request = state["request"]
    history = [RawHourlyReading(**h) for h in request["history"]]
    warnings = []
    if len(history) < 72:
        warnings.append(f"Only {len(history)}h of history provided; 72h+ recommended for stable rolling features.")

    try:
        features = build_feature_vector(history, request["target_timestamp"], _get_scaler())
    except Exception as exc:
        logger.exception("Feature building failed")
        return {**state, "errors": state.get("errors", []) + [f"feature_builder: {exc}"]}

    if not settings.has_scaler:
        warnings.append("SCALER_PARAMS_PATH not set -- features are UNSCALED. "
                         "Predictions will likely be wrong unless your model was trained on raw features.")

    return {**state, "features": features, "feature_warnings": warnings}


def select_model(state: PredictionState) -> PredictionState:
    if state.get("errors"):
        return state

    hazard = state["request"]["hazard_type"]
    loader = {
        "rainfall": model_registry.get_rainfall_model,
        "cloudburst": model_registry.get_cloudburst_model,
        "landslide": model_registry.get_landslide_model,
    }[hazard]
    model = loader()

    if model is None:
        return {**state, "model_info": {"loaded": False, "hazard": hazard}}
    return {**state, "model_info": {"loaded": True, "hazard": hazard, **model.info()}}


def run_inference(state: PredictionState) -> PredictionState:
    if state.get("errors"):
        return state

    model_info = state.get("model_info", {})
    hazard = state["request"]["hazard_type"]

    if not model_info.get("loaded"):
        return {**state, "raw_prediction": {
            "status": "stub",
            "note": f"No trained {hazard} model configured (set {hazard.upper()}_MODEL_PATH). "
                    f"Train one with machine_learning_module's train.py, then point this agent at the artifact.",
        }}

    loader_fn = {
        "rainfall": model_registry.get_rainfall_model,
        "cloudburst": model_registry.get_cloudburst_model,
        "landslide": model_registry.get_landslide_model,
    }[hazard]
    model = loader_fn()

    features = state["features"]
    X = pd.DataFrame([{col: features[col] for col in FEATURE_COLUMNS}])

    try:
        if hazard == "rainfall":
            pred_df = model.predictor.predict_dataframe(X)
            predicted_mm = float(pred_df["prediction"].iloc[0])
            return {**state, "raw_prediction": {"status": "ok", "predicted_mm": predicted_mm}}
        else:
            pred_df = model.predictor.predict_dataframe(X)
            probability = None
            if hasattr(model.predictor.model, "predict_proba"):
                proba = model.predictor.model.predict_proba(X)
                probability = float(proba[0][1])
            return {**state, "raw_prediction": {
                "status": "ok",
                "predicted_class": int(pred_df["prediction"].iloc[0]),
                "probability": probability,
            }}
    except Exception as exc:
        logger.exception("Inference failed for hazard=%s", hazard)
        return {**state, "raw_prediction": {"status": "error", "note": str(exc)}}


def post_process(state: PredictionState) -> PredictionState:
    if state.get("errors"):
        return state

    request = state["request"]
    raw = state.get("raw_prediction", {})
    model_info = state.get("model_info", {})
    warnings = state.get("feature_warnings", [])
    hazard = request["hazard_type"]

    n_history = len(request.get("history", []))
    conf = confidence_score(n_history, model_info.get("loaded", False), warnings)

    if raw.get("status") != "ok":
        result = {
            "hazard": hazard, "location": request["location"], "unit": None,
            "timestamp": request["target_timestamp"], "horizon": request.get("horizon", "24h"),
            "prediction": None, "probability": None, "confidence": 0.0, "is_extreme_event": False,
            "model": model_info, "explanation_url": None,
            "status": raw.get("status", "error"), "notes": warnings + [raw.get("note", "")],
        }
        return {**state, "result": result}

    if hazard == "rainfall":
        predicted_mm = raw["predicted_mm"]
        result = {
            "hazard": hazard, "location": request["location"], "unit": "mm",
            "timestamp": request["target_timestamp"], "horizon": request.get("horizon", "24h"),
            "prediction": predicted_mm, "probability": None, "confidence": conf,
            "is_extreme_event": is_extreme_rainfall(predicted_mm),
            "model": model_info, "explanation_url": None, "status": "ok", "notes": warnings,
        }
    else:
        probability = raw.get("probability")
        result = {
            "hazard": hazard, "location": request["location"], "unit": "probability",
            "timestamp": request["target_timestamp"], "horizon": request.get("horizon", "24h"),
            "prediction": raw.get("predicted_class"), "probability": probability, "confidence": conf,
            "is_extreme_event": is_extreme_probability(probability),
            "model": model_info, "explanation_url": None, "status": "ok", "notes": warnings,
        }

    return {**state, "result": result}


def save_and_log(state: PredictionState) -> PredictionState:
    result = state.get("result")
    if result is None:
        result = {
            "hazard": state["request"].get("hazard_type"), "location": state["request"].get("location"),
            "timestamp": state["request"].get("target_timestamp"), "status": "error",
            "notes": state.get("errors", []),
        }
        return {**state, "result": result}

    prediction_id = prediction_store.append(result)
    result = {**result, "prediction_id": prediction_id}
    logger.info("Saved prediction %s for hazard=%s location=%s", prediction_id,
                result.get("hazard"), result.get("location"))
    return {**state, "result": result}


def build_prediction_graph():
    graph = StateGraph(PredictionState)

    graph.add_node("validate_and_parse", validate_and_parse)
    graph.add_node("build_features", build_features)
    graph.add_node("select_model", select_model)
    graph.add_node("run_inference", run_inference)
    graph.add_node("post_process", post_process)
    graph.add_node("save_and_log", save_and_log)

    graph.set_entry_point("validate_and_parse")
    graph.add_edge("validate_and_parse", "build_features")
    graph.add_edge("build_features", "select_model")
    graph.add_edge("select_model", "run_inference")
    graph.add_edge("run_inference", "post_process")
    graph.add_edge("post_process", "save_and_log")
    graph.add_edge("save_and_log", END)

    return graph.compile()


prediction_graph = build_prediction_graph()
