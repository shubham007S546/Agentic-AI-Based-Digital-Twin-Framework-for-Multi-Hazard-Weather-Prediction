"""
FastAPI entrypoint for the Alert & Risk Assessment Agent (Agent 4 of 8).

Run with:
    uvicorn agents.alert_risk.main:app --reload --port 8003

Endpoints (matching the architecture diagram):
    POST /api/v1/alerts/generate
    GET  /api/v1/alerts/current
    GET  /api/v1/alerts/history
    POST /api/v1/notifications/send
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .escalation import _send_notification_stub
from .graph import alert_graph
from .logging_config import get_logger
from .schemas import AlertRequest, AlertResult
from .storage import alert_store

logger = get_logger(__name__)

app = FastAPI(
    title="Alert & Risk Assessment Agent",
    description="Agent 4 of 8 -- real-time hazard detection and risk assessment for early warning and decision support.",
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


@app.post("/api/v1/alerts/generate", response_model=AlertResult)
def generate(request: AlertRequest) -> AlertResult:
    try:
        payload = request.model_dump()
        payload.setdefault("target_timestamp", datetime.now(timezone.utc).isoformat())
        initial_state = {"request": payload, "errors": []}
        final_state = alert_graph.invoke(initial_state)
        return AlertResult(**final_state["alert"])
    except Exception as exc:
        logger.exception("Alert generation failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/alerts/current")
def current_alerts(limit: int = 10) -> list:
    return alert_store.list_recent(limit)


@app.get("/api/v1/alerts/history")
def alert_history(limit: int = 50) -> list:
    return alert_store.list_recent(limit)


@app.get("/api/v1/alerts/{alert_id}")
def get_alert(alert_id: str) -> dict:
    record = alert_store.get(alert_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return record


@app.post("/api/v1/notifications/send")
def send_notification(alert_id: str, channel: str = "email") -> dict:
    alert = alert_store.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return _send_notification_stub(channel, alert)
