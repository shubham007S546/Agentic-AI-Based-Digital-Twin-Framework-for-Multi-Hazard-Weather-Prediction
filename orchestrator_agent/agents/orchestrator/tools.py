"""
Tool registry the Orchestrator calls out to. Each function here stands in
for one of Agents 2-8 in the diagram, using the exact endpoint shape shown
there, so wiring in the real agent later is a drop-in replacement: swap the
stub body for an actual HTTP call (or in-process import, if that agent ends
up living in this same codebase) without touching graph.py at all.

Every stub returns "status": "stub" so responses generated from stub data
are honestly labelled -- never presented as if they were real predictions.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict

from .logging_config import get_logger

logger = get_logger(__name__)


def weather_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 2: Weather Analysis Agent.
    Real endpoint (per architecture diagram): GET /api/v1/weather/forecast
    TODO: replace this stub with an HTTP call (or direct import) once
    Agent 2 exists, e.g.:
        resp = httpx.get(f"{WEATHER_AGENT_URL}/api/v1/weather/forecast", params=params)
        return resp.json()
    """
    logger.info("weather_tool called with params=%s (STUB)", params)
    return {
        "status": "stub",
        "note": "Agent 2 (Weather Analysis Agent) not yet implemented.",
        "location": params.get("location", "Mandi"),
        "forecast": "unavailable (stub)",
    }


def prediction_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 3: Prediction Agent.
    Real endpoint: POST /api/v1/prediction/rainfall
    TODO: replace with a call into machine_learning_module's saved model,
    e.g. loading the log1p LightGBM artifact via BasePredictor and running
    .predict_dataframe() on the relevant feature row for this location/date.
    """
    logger.info("prediction_tool called with params=%s (STUB)", params)
    return {
        "status": "stub",
        "note": "Agent 3 (Prediction Agent) not yet implemented -- wire this to "
                "machine_learning_module/models/.../predict.py.",
        "location": params.get("location", "Mandi"),
        "rainfall_probability": None,
        "predicted_mm": None,
    }


def alert_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 4: Alert & Risk Agent.
    Real endpoint: GET /api/v1/alerts/current
    TODO: replace with a call to your alert/risk-level service.
    """
    logger.info("alert_tool called with params=%s (STUB)", params)
    return {
        "status": "stub",
        "note": "Agent 4 (Alert & Risk Agent) not yet implemented.",
        "location": params.get("location", "Mandi"),
        "alert_level": "unknown",
    }


def digital_twin_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 5: Digital Twin Agent.
    Real endpoint: POST /api/v1/digital-twin/query
    TODO: replace with a call into your digital_twin/ simulation service.
    """
    logger.info("digital_twin_tool called with params=%s (STUB)", params)
    return {
        "status": "stub",
        "note": "Agent 5 (Digital Twin Agent) not yet implemented.",
        "query": params.get("query", ""),
        "simulation_result": None,
    }


def data_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 6: Data Quality Agent (dataset/historical-data access).
    Real endpoint: GET /api/v1/datasets/search
    TODO: replace with a call into your dataset/historical-data store.
    """
    logger.info("data_tool called with params=%s (STUB)", params)
    return {
        "status": "stub",
        "note": "Agent 6 (Data Quality Agent) not yet implemented.",
        "query": params.get("query", ""),
        "records": [],
    }


def rag_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 7: Report/RAG Agent -- research docs, guidelines.
    Real endpoint: POST /api/v1/rag/search
    TODO: you already have a hybrid FAISS+BM25+RRF+CrossEncoder RAG system --
    wire this directly to that pipeline's query function instead of an HTTP
    call, since it's likely in the same Python environment.
    """
    logger.info("rag_tool called with params=%s (STUB)", params)
    return {
        "status": "stub",
        "note": "Agent 7 (Report/RAG Agent) not yet wired -- connect to your "
                "existing FAISS+BM25+RRF+CrossEncoder RAG pipeline here.",
        "query": params.get("query", ""),
        "documents": [],
    }


def notification_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 8: Assistant/Notification Agent.
    Real endpoint: POST /api/v1/notifications/send
    TODO: replace with a call to your email/SMS/push notification service.
    """
    logger.info("notification_tool called with params=%s (STUB)", params)
    return {
        "status": "stub",
        "note": "Agent 8 (Assistant Agent) not yet implemented.",
        "channel": params.get("channel", "unspecified"),
        "sent": False,
    }


TOOL_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "weather_tool": weather_tool,
    "prediction_tool": prediction_tool,
    "alert_tool": alert_tool,
    "digital_twin_tool": digital_twin_tool,
    "data_tool": data_tool,
    "rag_tool": rag_tool,
    "notification_tool": notification_tool,
}


def call_tool(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke a tool by name, catching and labelling any failure so one
    broken tool never crashes the whole orchestrator run."""
    if tool_name not in TOOL_REGISTRY:
        return {"status": "error", "note": f"Unknown tool: {tool_name!r}"}
    start = time.monotonic()
    try:
        result = TOOL_REGISTRY[tool_name](params)
        result.setdefault("status", "ok")
        return result
    except Exception as exc:
        logger.exception("Tool %s failed", tool_name)
        return {"status": "error", "note": str(exc)}
    finally:
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info("Tool %s took %.1fms", tool_name, elapsed_ms)
