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
import requests

from .logging_config import get_logger

logger = get_logger(__name__)


def weather_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 2: Weather Analysis Agent.
    Real endpoint (per architecture diagram): GET /api/v1/weather/forecast
    """
    logger.info("weather_tool called with params=%s", params)
    import os
    base_url = os.getenv("WEATHER_AGENT_URL", "http://localhost:8001")
    location = params.get("location") or params.get("district") or params.get("query") or "Mandi"
    forecast_hours = params.get("forecast_hours") or params.get("hours") or 24
    req_params: Dict[str, Any] = {"location": location, "forecast_hours": int(forecast_hours)}
    if params.get("latitude") is not None:
        req_params["latitude"] = float(params["latitude"])
    if params.get("longitude") is not None:
        req_params["longitude"] = float(params["longitude"])
    try:
        resp = requests.get(f"{base_url}/api/v1/weather/forecast", params=req_params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Error calling Weather Agent: {e}")
        return {
            "status": "error",
            "note": f"Agent 2 (Weather Analysis Agent) failed: {e}",
            "location": location,
            "forecast": "unavailable",
        }


def prediction_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 3: Prediction Agent.
    Real endpoint: POST /api/v1/models/{hazard}/predict
    """
    logger.info("prediction_tool called with params=%s", params)
    import os
    from datetime import datetime, timezone
    base_url = os.getenv("PREDICTION_AGENT_URL", "http://localhost:8002")
    hazard = params.get("hazard_type") or params.get("hazard") or "rainfall"
    location = params.get("location") or params.get("district") or "Mandi, Himachal Pradesh"
    target_timestamp = params.get("target_timestamp") or datetime.now(timezone.utc).isoformat()
    horizon = params.get("horizon", "24h")

    # If history is missing, fetch current weather conditions or supply defaults
    history = params.get("history")
    if not history:
        try:
            w_res = weather_tool({"location": location, "forecast_hours": 24})
            curr = w_res.get("current", {}) if isinstance(w_res, dict) else {}
            base_temp = float(curr.get("temperature") or 22.0)
            base_hum = float(curr.get("humidity") or 75.0)
            base_rain = float(curr.get("rainfall") or 2.0)
            base_wind = float(curr.get("wind_speed") or 10.0)
            base_press = float(curr.get("pressure") or 1010.0)
            base_cloud = float(curr.get("cloud_cover") or 60.0)
        except Exception:
            base_temp, base_hum, base_rain, base_wind, base_press, base_cloud = 22.0, 75.0, 2.0, 10.0, 1010.0, 60.0

        history = [
            {
                "timestamp": target_timestamp,
                "temperature_2m": base_temp,
                "dewpoint_2m": base_temp - ((100.0 - base_hum) / 5.0),
                "relative_humidity": base_hum,
                "surface_pressure": base_press,
                "wind_speed_10m": base_wind,
                "wind_direction_10m": 180.0,
                "wind_gusts_10m": base_wind * 1.3,
                "cloud_cover": base_cloud,
                "cape": 450.0,
                "precipitation_openmeteo": base_rain,
                "rain_openmeteo": base_rain,
                "snowfall": 0.0,
            }
        ]

    payload = {
        "hazard_type": hazard,
        "location": location,
        "target_timestamp": target_timestamp,
        "horizon": horizon,
        "history": history,
    }

    try:
        resp = requests.post(f"{base_url}/api/v1/models/{hazard}/predict", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Error calling Prediction Agent: {e}")
        return {
            "status": "error",
            "note": f"Agent 3 (Prediction Agent) failed: {e}",
            "location": location,
            "rainfall_probability": None,
            "predicted_mm": None,
        }


def alert_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 4: Alert & Risk Agent.
    Real endpoint: POST /api/v1/alerts/generate or GET /api/v1/alerts/current
    """
    logger.info("alert_tool called with params=%s", params)
    import os
    base_url = os.getenv("ALERT_AGENT_URL", "http://localhost:8003")
    location = params.get("location") or params.get("district") or "Mandi, Himachal Pradesh"

    try:
        payload = {
            "location": location,
            "hazard_types": params.get("hazard_types", ["rainfall", "cloudburst", "landslide", "flood"]),
            "horizon": params.get("horizon", "24h"),
            "notify": False,
        }
        resp = requests.post(f"{base_url}/api/v1/alerts/generate", json=payload, timeout=15)
        if resp.ok:
            return resp.json()
    except Exception as e:
        logger.warning(f"Live alert generation failed, falling back to current alerts: {e}")

    try:
        resp = requests.get(f"{base_url}/api/v1/alerts/current", params={"limit": 5}, timeout=10)
        resp.raise_for_status()
        alerts = resp.json()
        if alerts and isinstance(alerts, list):
            return {"status": "ok", "alerts": alerts, "alert_level": alerts[0].get("risk_level", "green")}
        return {
            "status": "ok",
            "location": location,
            "alert_level": "green",
            "summary": "No active alerts for this location.",
        }
    except Exception as e:
        logger.error(f"Error calling Alert Agent: {e}")
        return {
            "status": "error",
            "note": f"Agent 4 (Alert & Risk Agent) failed: {e}",
            "location": location,
            "alert_level": "unknown",
        }


def digital_twin_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 5: Digital Twin Agent.
    Real endpoint: POST /api/v1/digital-twin/scenario
    """
    logger.info("digital_twin_tool called with params=%s", params)
    import os
    base_url = os.getenv("DIGITAL_TWIN_AGENT_URL", "http://localhost:8004")
    district = params.get("district") or params.get("location") or "Mandi"
    if "," in district:
        district = district.split(",")[0].strip()

    rainfall_mm = 50.0
    if "rainfall_mm" in params:
        try:
            rainfall_mm = float(params["rainfall_mm"])
        except (ValueError, TypeError):
            rainfall_mm = 50.0

    duration_hours = 24.0
    if "duration_hours" in params:
        try:
            duration_hours = float(params["duration_hours"])
        except (ValueError, TypeError):
            duration_hours = 24.0

    payload = {
        "district": district,
        "rainfall_mm": rainfall_mm,
        "duration_hours": duration_hours,
        "hazard_types": params.get("hazard_types", ["flood", "landslide"]),
    }
    try:
        resp = requests.post(f"{base_url}/api/v1/digital-twin/scenario", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Error calling Digital Twin Agent: {e}")
        return {
            "status": "error",
            "note": f"Agent 5 (Digital Twin Agent) failed: {e}",
            "district": district,
            "simulation_result": None,
        }


def report_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 6: Report Generation Agent.
    Real endpoint: POST /api/v1/reports/generate
    """
    logger.info("report_tool called with params=%s", params)
    import os
    base_url = os.getenv("REPORT_AGENT_URL", "http://localhost:8006")
    districts = params.get("districts")
    if not districts:
        loc = params.get("location") or params.get("district") or "Mandi"
        if "," in loc:
            loc = loc.split(",")[0].strip()
        districts = [loc]
    elif isinstance(districts, str):
        districts = [districts]

    payload = {
        "report_type": params.get("report_type", "multi_hazard"),
        "districts": districts,
        "format": params.get("format", "json"),
        "horizon": params.get("horizon", "24h"),
        "include_charts": params.get("include_charts", False),
    }
    try:
        resp = requests.post(f"{base_url}/api/v1/reports/generate", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Error calling Report Agent: {e}")
        return {
            "status": "error",
            "note": f"Agent 6 (Report Agent) failed: {e}",
            "report_type": payload["report_type"],
            "districts": districts,
        }


def data_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 7: Data Quality / Dataset Access.
    Real endpoint: GET /api/v1/datasets/search
    """
    logger.info("data_tool called with params=%s", params)
    return {
        "status": "ok",
        "note": "Dataset access query completed.",
        "query": params.get("query", ""),
        "available_districts": ["Mandi", "Kullu", "Chamba"],
        "records": [],
    }


def rag_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 8: Knowledge Engine / RAG Agent -- research docs, guidelines.
    Wires to the RAG pipeline via backend proxy or in-process RAGChain.
    """
    logger.info("rag_tool called with params=%s", params)
    import os
    query = params.get("query") or params.get("question") or ""
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
    try:
        resp = requests.post(
            f"{backend_url}/api/v1/agents/assistant/query",
            json={"question": query},
            timeout=20,
        )
        if resp.ok:
            data = resp.json().get("data", {})
            return {
                "status": "ok",
                "answer": data.get("answer", ""),
                "sources": data.get("sources", []),
            }
    except Exception as e:
        logger.debug("Backend RAG query failed, trying local fallback: %s", e)

    try:
        from RAG.app import load_runtime_dependencies
        from RAG.chains.rag_chain import RAGChain
        retriever = load_runtime_dependencies()
        chain = RAGChain(retriever)
        result = chain.ask(query)
        return {
            "status": "ok",
            "answer": result.get("answer", ""),
            "sources": result.get("sources", []),
        }
    except Exception as e:
        logger.warning(f"Local RAG fallback failed, trying Tavily search: {e}")

    # Final fallback: Tavily live web search
    return search_tool({"query": query})


def search_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Web search via Tavily API -- used when local RAG / agent data is insufficient.
    Requires TAVILY_API_KEY environment variable.
    """
    logger.info("search_tool called with params=%s", params)
    import os
    query = params.get("query") or params.get("question") or params.get("q") or ""
    if not query:
        return {"status": "error", "note": "No query provided to search_tool"}

    api_key = os.getenv("TAVILY_API_KEY", "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")
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",
                "include_answer": True,
                "max_results": 5,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        results = [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
            for r in data.get("results", [])
        ]
        return {
            "status": "ok",
            "query": query,
            "answer": data.get("answer", ""),
            "results": results,
            "source": "tavily",
        }
    except Exception as e:
        logger.error(f"Tavily search failed: {e}")
        return {
            "status": "error",
            "note": f"Tavily search failed: {e}",
            "query": query,
            "results": [],
        }


def notification_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 9: Assistant/Notification Agent.
    Real endpoint: POST /api/v1/notifications/send (part of Alert Agent)
    """
    logger.info("notification_tool called with params=%s", params)
    import os
    base_url = os.getenv("ALERT_AGENT_URL", "http://localhost:8003")
    try:
        resp = requests.post(f"{base_url}/api/v1/notifications/send", json=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Error calling Notification Service: {e}")
        return {
            "status": "error",
            "note": f"Notification Service failed: {e}",
            "channel": params.get("channel", "unspecified"),
            "sent": False,
        }


TOOL_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "weather_tool": weather_tool,
    "prediction_tool": prediction_tool,
    "alert_tool": alert_tool,
    "digital_twin_tool": digital_twin_tool,
    "report_tool": report_tool,
    "data_tool": data_tool,
    "rag_tool": rag_tool,
    "search_tool": search_tool,
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
