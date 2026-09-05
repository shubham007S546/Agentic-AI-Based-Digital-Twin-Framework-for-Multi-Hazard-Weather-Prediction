"""
scripts/test_agents_integration.py
-----------------------------------
End-to-end local integration test for all 6 agent microservices.
Validates that each agent graph can execute its workflow without errors.
"""

import sys
import os
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

print("=" * 70)
print("RUNNING AGENT INTEGRATION TEST SUITE")
print("=" * 70)

# 1. Weather Analysis Agent
print("\n[1/6] Testing Weather Analysis Agent...")
try:
    from weather_analysis_agent.agents.weather_analysis.graph import weather_analysis_graph
    from weather_analysis_agent.agents.weather_analysis.schemas import WeatherRequest
    req = WeatherRequest(location="Mandi", forecast_hours=24)
    state = {"request": req.model_dump()}
    result = weather_analysis_graph.invoke(state)
    resp = result.get("response", {})
    print(f"  --> Weather Agent OK: location={resp.get('location')}, summary={resp.get('summary')[:60]}...")
except Exception as e:
    print(f"  --> Weather Agent FAILED: {e}")

# 2. Prediction Agent
print("\n[2/6] Testing Prediction Agent...")
try:
    from prediction_agent.agents.prediction.graph import prediction_graph
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    req_pred = {
        "hazard_type": "rainfall",
        "location": "Mandi, Himachal Pradesh",
        "target_timestamp": now_iso,
        "horizon": "24h",
        "history": [
            {
                "timestamp": now_iso,
                "temperature_2m": 21.5,
                "dewpoint_2m": 17.0,
                "relative_humidity": 78.0,
                "surface_pressure": 1012.0,
                "wind_speed_10m": 12.0,
                "wind_direction_10m": 190.0,
                "wind_gusts_10m": 18.0,
                "cloud_cover": 85.0,
                "cape": 500.0,
                "precipitation_openmeteo": 3.0,
                "rain_openmeteo": 3.0,
                "snowfall": 0.0,
            }
        ],
    }
    state = {"request": req_pred, "errors": []}
    result = prediction_graph.invoke(state)
    pred_res = result.get("result", {})
    print(f"  --> Prediction Agent OK: hazard={pred_res.get('hazard')}, status={pred_res.get('status')}, prediction_id={pred_res.get('prediction_id')}")
except Exception as e:
    print(f"  --> Prediction Agent FAILED: {e}")

# 3. Digital Twin Agent
print("\n[3/6] Testing Digital Twin Agent...")
try:
    from digital_twin_agent.agents.digital_twin.graph import digital_twin_graph
    req_twin = {
        "district": "Mandi",
        "rainfall_mm": 75.0,
        "duration_hours": 24.0,
        "hazard_types": ["flood", "landslide"],
    }
    state = {"request": req_twin, "errors": []}
    result = digital_twin_graph.invoke(state)
    twin_res = result.get("response", {})
    print(f"  --> Digital Twin Agent OK: district={twin_res.get('district')}, flood peak={twin_res.get('flood', {}).get('peak_discharge_m3s')} m3/s")
except Exception as e:
    print(f"  --> Digital Twin Agent FAILED: {e}")

# 4. Alert & Risk Agent
print("\n[4/6] Testing Alert & Risk Agent...")
try:
    from alert_risk_agent.agents.alert_risk.graph import alert_graph
    req_alert = {
        "location": "Mandi, Himachal Pradesh",
        "hazard_types": ["rainfall", "cloudburst", "landslide", "flood"],
        "horizon": "24h",
        "notify": False,
    }
    state = {"request": req_alert, "errors": []}
    result = alert_graph.invoke(state)
    alert_res = result.get("alert", {})
    print(f"  --> Alert Agent OK: severity={alert_res.get('severity')}, risk_score={alert_res.get('risk_score')}")
except Exception as e:
    print(f"  --> Alert Agent FAILED: {e}")

# 5. Report Agent
print("\n[5/6] Testing Report Agent...")
try:
    from report_agent.agents.report.graph import report_graph
    req_report = {
        "report_type": "multi_hazard",
        "districts": ["Mandi"],
        "format": "json",
        "horizon": "24h",
        "include_charts": False,
    }
    state = {"request": req_report, "errors": []}
    result = report_graph.invoke(state)
    report_res = result.get("result", {})
    print(f"  --> Report Agent OK: report_id={report_res.get('metadata', {}).get('report_id')}, sections={len(report_res.get('sections', []))}")
except Exception as e:
    print(f"  --> Report Agent FAILED: {e}")

# 6. Orchestrator Agent
print("\n[6/6] Testing Orchestrator Agent...")
try:
    from orchestrator_agent.agents.orchestrator.graph import orchestrator_graph
    initial_state = {
        "session_id": "test-session-101",
        "user_query": "What is the weather and flood risk in Mandi tomorrow?",
        "user_context": {"location": "Mandi"},
        "history": [],
        "errors": [],
    }
    result = orchestrator_graph.invoke(initial_state)
    print(f"  --> Orchestrator Agent OK:")
    print(f"      Intent: {result.get('intent', {}).get('intent')}")
    print(f"      Tools called: {[r['tool'] for r in result.get('tool_call_records', [])]}")
    resp_text = result.get('final_response', '')[:120].encode('ascii', errors='replace').decode('ascii')
    print(f"      Response: {resp_text}...")
except Exception as e:
    print(f"  --> Orchestrator Agent FAILED: {e}")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
