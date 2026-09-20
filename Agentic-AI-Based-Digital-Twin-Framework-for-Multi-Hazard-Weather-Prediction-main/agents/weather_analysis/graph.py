"""
The Weather Analysis Agent's LangGraph state machine -- implements the
"Detailed Workflow Steps" from the architecture diagram:

    1. Receive Request              (entry point, see main.py)
    2. Extract & Validate Params    -> extract_and_validate
    3. Select Data Sources          -> select_sources
    4. Fetch Data in Parallel       -> fetch_data
    5. Process & Analyze            -> process_and_analyze
    6. Generate Structured Output   -> generate_output
    7. Cache Result                 -> cache_result
    8. Return Response              (handled by main.py from final state)
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict

from langgraph.graph import END, StateGraph

from .cache import weather_cache
from .logging_config import get_logger
from .processing import aggregate_sources, clean_provider_results, compute_confidence, detect_anomalies
from .providers import call_provider
from .schemas import WeatherAnalysisState
from .summary import generate_summary

logger = get_logger(__name__)


HP_DISTRICT_COORDINATES: Dict[str, tuple[float, float]] = {
    "mandi": (31.5892, 76.9182),
    "kullu": (31.9579, 77.1095),
    "chamba": (32.5534, 76.1258),
    "shimla": (31.1048, 77.1734),
    "kangra": (32.0998, 76.2691),
    "dharamshala": (32.2190, 76.3234),
    "solan": (30.9045, 77.0967),
    "sirmaur": (30.6083, 77.3000),
    "sirmour": (30.6083, 77.3000),
    "hamirpur": (31.6862, 76.5213),
    "bilaspur": (31.3260, 76.7562),
    "una": (31.4685, 76.2708),
    "kinnaur": (31.6510, 78.4752),
    "lahaul and spiti": (32.5710, 77.0320),
    "lahaul": (32.5710, 77.0320),
    "spiti": (32.2461, 78.0349),
    "manali": (32.2396, 77.1887),
}


def geocode_district(location: str) -> tuple[float, float]:
    """Resolve latitude and longitude for a given location or district query."""
    loc_lower = location.lower().replace(",", " ").replace("-", " ")
    for dist_name, coords in HP_DISTRICT_COORDINATES.items():
        if dist_name in loc_lower:
            return coords
    # Default to Mandi central catchment
    return (31.5892, 76.9182)


def extract_and_validate(state: WeatherAnalysisState) -> WeatherAnalysisState:
    request = dict(state["request"])
    location = request.get("location")
    if not location:
        raise ValueError("request.location is required")

    # Geocode if latitude or longitude missing
    if request.get("latitude") is None or request.get("longitude") is None:
        lat, lon = geocode_district(location)
        request["latitude"] = lat
        request["longitude"] = lon
        logger.info("Geocoded '%s' to lat=%.4f, lon=%.4f", location, lat, lon)

    # Adjust forecast hours if timeframe indicates tomorrow or multi-day
    date_hint = str(request.get("date", "")).lower()
    if ("tomorrow" in location.lower() or "tomorrow" in date_hint) and request.get("forecast_hours", 24) <= 24:
        request["forecast_hours"] = 48

    cache_key = weather_cache.make_key(
        location, request.get("latitude"), request.get("longitude"), request.get("forecast_hours", 24)
    )
    cached = weather_cache.get(cache_key)
    if cached is not None:
        logger.info("Cache hit for %s", cache_key)
        cached_response = {**cached, "cached": True}
        return {**state, "request": request, "cache_key": cache_key, "cache_hit": True, "response": cached_response}

    return {**state, "request": request, "cache_key": cache_key, "cache_hit": False}


def select_sources(state: WeatherAnalysisState) -> WeatherAnalysisState:
    if state.get("cache_hit"):
        return state
    # Currently: use every preferred source the request asked for. Extend
    # this with availability/health checks per source once more than one
    # provider is real (e.g. skip a source that's been erroring repeatedly).
    return state


def fetch_data(state: WeatherAnalysisState) -> WeatherAnalysisState:
    if state.get("cache_hit"):
        return state

    request = state["request"]
    sources = request.get("preferred_sources", ["open_meteo"])
    params = {
        "location": request.get("location"),
        "latitude": request.get("latitude"),
        "longitude": request.get("longitude"),
        "forecast_hours": request.get("forecast_hours", 24),
    }

    results: Dict[str, Dict[str, Any]] = {}
    errors = []

    with ThreadPoolExecutor(max_workers=max(1, len(sources))) as executor:
        future_to_source = {executor.submit(call_provider, src, params): src for src in sources}
        for future in as_completed(future_to_source):
            src = future_to_source[future]
            result = future.result()
            results[src] = result
            if result.get("status") == "error":
                errors.append(f"{src}: {result.get('note', 'unknown error')}")

    return {**state, "provider_results": results, "provider_errors": errors}


def process_and_analyze(state: WeatherAnalysisState) -> WeatherAnalysisState:
    if state.get("cache_hit"):
        return state

    cleaned = clean_provider_results(state.get("provider_results", {}))
    aggregated = aggregate_sources(cleaned)
    anomalies = detect_anomalies(aggregated)
    confidence = compute_confidence(state.get("provider_results", {}), state["request"].get("preferred_sources", []))

    return {**state, "cleaned": cleaned, "aggregated": aggregated, "anomalies": anomalies, "confidence": confidence}


def generate_output(state: WeatherAnalysisState) -> WeatherAnalysisState:
    if state.get("cache_hit"):
        return state

    request = state["request"]
    aggregated = state.get("aggregated", {"current": {}, "forecast": []})
    anomalies = state.get("anomalies", [])
    sources_used = list(state.get("cleaned", {}).keys())

    summary = generate_summary(request["location"], aggregated.get("current", {}), aggregated.get("forecast", []),
                                anomalies, sources_used)

    response = {
        "location": request["location"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current": aggregated.get("current", {}),
        "forecast": aggregated.get("forecast", []),
        "anomalies": anomalies,
        "sources": sources_used,
        "confidence": state.get("confidence", 0.0),
        "summary": summary,
        "cached": False,
    }
    return {**state, "response": response}


def cache_result(state: WeatherAnalysisState) -> WeatherAnalysisState:
    if state.get("cache_hit"):
        return state
    weather_cache.set(state["cache_key"], state["response"])
    logger.info("Cached result under key=%s", state["cache_key"])
    return state


def build_weather_analysis_graph():
    graph = StateGraph(WeatherAnalysisState)

    graph.add_node("extract_and_validate", extract_and_validate)
    graph.add_node("select_sources", select_sources)
    graph.add_node("fetch_data", fetch_data)
    graph.add_node("process_and_analyze", process_and_analyze)
    graph.add_node("generate_output", generate_output)
    graph.add_node("cache_result", cache_result)

    graph.set_entry_point("extract_and_validate")
    graph.add_edge("extract_and_validate", "select_sources")
    graph.add_edge("select_sources", "fetch_data")
    graph.add_edge("fetch_data", "process_and_analyze")
    graph.add_edge("process_and_analyze", "generate_output")
    graph.add_edge("generate_output", "cache_result")
    graph.add_edge("cache_result", END)

    return graph.compile()


weather_analysis_graph = build_weather_analysis_graph()
