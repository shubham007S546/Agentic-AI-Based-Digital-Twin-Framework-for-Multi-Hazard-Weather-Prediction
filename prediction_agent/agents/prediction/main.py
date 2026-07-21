"""
FastAPI entrypoint for the Prediction Agent (Agent 3 of 8).

Run with:
    uvicorn agents.prediction.main:app --reload --port 8002

Endpoints (matching the architecture diagram):
    POST /api/v1/models/{hazard}/predict
    GET  /api/v1/models/{hazard}/info
    GET  /api/v1/predictions/{prediction_id}
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import model_registry
from .graph import prediction_graph
from .logging_config import get_logger
from .schemas import PredictionRequest, PredictionResult
from .storage import prediction_store

logger = get_logger(__name__)

app = FastAPI(
    title="Prediction Agent",
    description="Agent 3 of 8 -- ML inference & forecasting for rainfall, cloudburst, and landslide hazards.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/v1/models/{hazard}/predict", response_model=PredictionResult)
def predict(hazard: str, request: PredictionRequest) -> PredictionResult:
    if request.hazard_type != hazard:
        raise HTTPException(status_code=400, detail=f"URL hazard {hazard!r} != body hazard_type {request.hazard_type!r}")
    try:
        initial_state = {"request": request.model_dump(), "errors": []}
        final_state = prediction_graph.invoke(initial_state)
        result = final_state.get("result", {})
        if final_state.get("errors") and result.get("status") != "ok":
            result = {**result, "status": "error", "notes": final_state["errors"]}
        return PredictionResult(**result)
    except Exception as exc:
        logger.exception("Prediction run failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/models/{hazard}/info")
def model_info(hazard: str) -> dict:
    loader = {
        "rainfall": model_registry.get_rainfall_model,
        "cloudburst": model_registry.get_cloudburst_model,
        "landslide": model_registry.get_landslide_model,
    }.get(hazard)
    if loader is None:
        raise HTTPException(status_code=404, detail=f"Unknown hazard: {hazard!r}")
    model = loader()
    if model is None:
        return {"hazard": hazard, "loaded": False, "note": f"No {hazard} model configured."}
    return {"hazard": hazard, "loaded": True, **model.info()}


@app.get("/api/v1/predictions/{prediction_id}")
def get_prediction(prediction_id: str) -> dict:
    record = prediction_store.get(prediction_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Prediction not found.")
    return record
