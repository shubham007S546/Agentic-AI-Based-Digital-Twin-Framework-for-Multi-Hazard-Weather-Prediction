"""
Real (non-stub) data processing: cleaning provider outputs, aggregating
across sources, and rule-based anomaly detection -- matches the diagram's
"Internal Processing Flow": Data Fetching -> Data Validation -> Data
Cleaning -> Aggregation & Interpolation -> Anomaly Detection -> Summary Generation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Thresholds are simple and documented so they're easy to tune once you have
# more sources feeding real data (right now, only open_meteo is real).
_HUMIDITY_HIGH = 90.0
_RAINFALL_HOURLY_HEAVY_MM = 20.0
_RAINFALL_HOURLY_CLOUDBURST_MM = 50.0
_WIND_SPEED_HIGH_KMH = 40.0
_TEMPERATURE_EXTREME_HIGH_C = 40.0
_TEMPERATURE_EXTREME_LOW_C = 2.0


def clean_provider_results(provider_results: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Keep only providers that returned real ("ok") data; stubs/errors are
    dropped from the data used for aggregation (but not from the audit
    trail -- callers should log/return provider_results separately)."""
    return {name: result for name, result in provider_results.items() if result.get("status") == "ok"}


def aggregate_sources(cleaned: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Combine 'current' conditions and 'forecast' across every source that
    returned real data. With only one real source (open_meteo, today) this
    is a pass-through; once IMD/ERA5/NASA GPM are wired in with the same
    current/forecast shape, this averages overlapping fields across sources
    rather than just picking one."""
    if not cleaned:
        return {"current": {}, "forecast": []}

    currents = [r["current"] for r in cleaned.values() if "current" in r]
    forecasts = [r["forecast"] for r in cleaned.values() if "forecast" in r]

    aggregated_current = _average_dicts(currents) if currents else {}
    # forecast: use the longest available series; averaging across sources
    # with different timestamps needs alignment first (future work) -- for
    # now, prefer the series from the first source that has one.
    aggregated_forecast = forecasts[0] if forecasts else []

    return {"current": aggregated_current, "forecast": aggregated_forecast}


def _average_dicts(dicts: List[Dict[str, Optional[float]]]) -> Dict[str, Optional[float]]:
    keys = set()
    for d in dicts:
        keys.update(d.keys())

    result: Dict[str, Optional[float]] = {}
    for key in keys:
        values = [d[key] for d in dicts if d.get(key) is not None]
        result[key] = round(sum(values) / len(values), 2) if values else None
    return result


def detect_anomalies(aggregated: Dict[str, Any]) -> List[str]:
    """Simple, explainable rule-based anomaly flags -- matches the diagram's
    example ('High humidity detected'). Extend with statistical/ML-based
    detection later; rules are intentionally conservative and documented so
    false positives are easy to reason about and tune."""
    anomalies: List[str] = []
    current = aggregated.get("current", {})

    humidity = current.get("humidity")
    if humidity is not None and humidity >= _HUMIDITY_HIGH:
        anomalies.append("High humidity detected")

    rainfall = current.get("rainfall")
    if rainfall is not None:
        if rainfall >= _RAINFALL_HOURLY_CLOUDBURST_MM:
            anomalies.append("Possible cloudburst-intensity rainfall detected")
        elif rainfall >= _RAINFALL_HOURLY_HEAVY_MM:
            anomalies.append("Heavy rainfall detected")

    wind_speed = current.get("wind_speed")
    if wind_speed is not None and wind_speed >= _WIND_SPEED_HIGH_KMH:
        anomalies.append("High wind speed detected")

    temperature = current.get("temperature")
    if temperature is not None:
        if temperature >= _TEMPERATURE_EXTREME_HIGH_C:
            anomalies.append("Extreme heat detected")
        elif temperature <= _TEMPERATURE_EXTREME_LOW_C:
            anomalies.append("Extreme cold detected")

    for point in aggregated.get("forecast", []):
        rf = point.get("rainfall")
        if rf is not None and rf >= _RAINFALL_HOURLY_CLOUDBURST_MM:
            anomalies.append(f"Possible cloudburst-intensity rainfall forecast at {point.get('time')}")
            break  # one flag is enough; avoid spamming one per hour

    return anomalies


def compute_confidence(provider_results: Dict[str, Dict[str, Any]], requested_sources: List[str]) -> float:
    """Confidence reflects how many of the requested sources actually
    returned real ("ok") data vs. stubbed/errored. A single real source
    (today: just open_meteo) caps out below the diagram's multi-source
    example (0.92) on purpose -- confidence should visibly improve as more
    real providers get wired in."""
    if not requested_sources:
        return 0.0
    ok_count = sum(1 for name in requested_sources if provider_results.get(name, {}).get("status") == "ok")
    ratio = ok_count / len(requested_sources)
    return round(min(0.5 + 0.5 * ratio, 0.95) if ok_count else 0.0, 2)
