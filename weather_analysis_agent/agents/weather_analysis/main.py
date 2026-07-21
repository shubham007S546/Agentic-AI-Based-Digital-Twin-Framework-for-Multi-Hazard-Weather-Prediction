"""
FastAPI entrypoint for the Weather Analysis Agent (Agent 2 of 8).

Run with:
    uvicorn agents.weather_analysis.main:app --reload --port 8001

Endpoint (matches the architecture diagram):
    GET /api/v1/weather/forecast
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .graph import weather_analysis_graph
from .logging_config import get_logger
from .schemas import WeatherRequest, WeatherResponse

logger = get_logger(__name__)

app = FastAPI(
    title="Weather Analysis Agent",
    description="Agent 2 of 8 -- fetches, analyzes, and summarizes real-time and forecast weather conditions.",
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


@app.get("/api/v1/weather/forecast", response_model=WeatherResponse)
def forecast(
    location: str,
    latitude: float | None = None,
    longitude: float | None = None,
    forecast_hours: int = 24,
) -> WeatherResponse:
    try:
        request = WeatherRequest(location=location, latitude=latitude, longitude=longitude,
                                  forecast_hours=forecast_hours)
        initial_state = {"request": request.model_dump()}
        final_state = weather_analysis_graph.invoke(initial_state)
        return WeatherResponse(**final_state["response"])
    except Exception as exc:
        logger.exception("Weather analysis run failed")
        raise HTTPException(status_code=500, detail=str(exc))
