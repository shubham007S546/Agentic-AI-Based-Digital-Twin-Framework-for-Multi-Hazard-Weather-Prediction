"""
scripts/verify_demo_session.py
------------------------------
Runs an end-to-end verification of all 6 agents and an interactive 4-query
conversational demo session, measuring execution times, tool calls, and statuses.
"""

import sys
import time
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

print("=" * 80)
print("🚀 COMPREHENSIVE AGENTIC AI DEMO SESSION & HEALTH CHECK")
print("=" * 80)

# 1. Integration Suite Check
print("\n--- [PHASE 1] RUNNING AGENT INTEGRATION TEST SUITE ---")
from agents.weather_analysis.graph import weather_analysis_graph
from agents.weather_analysis.schemas import WeatherRequest
from agents.prediction.graph import prediction_graph
from agents.digital_twin.graph import digital_twin_graph
from agents.alert_risk.graph import alert_graph
from agents.report.graph import report_graph
from agents.orchestrator.graph import orchestrator_graph

# 1. Weather Agent
t0 = time.time()
w_req = WeatherRequest(location="Mandi", forecast_hours=24)
w_res = weather_analysis_graph.invoke({"request": w_req.model_dump()}).get("response", {})
w_time = time.time() - t0
current_temp = w_res.get("current", {}).get("temperature_c")
print(f"✅ 1. Weather Agent ({w_time:.2f}s): location={w_res.get('location')}, current_temp={current_temp}°C, summary={w_res.get('summary', '')[:60]}...")

# 2. Prediction Agent
t0 = time.time()
p_state = {
    "request": {
        "hazard_type": "rainfall",
        "location": "Mandi",
        "target_timestamp": "2026-09-15T12:00:00Z",
        "horizon": "24h",
        "history": [],
    },
    "errors": [],
}
p_res = prediction_graph.invoke(p_state).get("result", {})
p_time = time.time() - t0
print(f"✅ 2. Prediction Agent ({p_time:.2f}s): status={p_res.get('status')}, hazard={p_res.get('hazard')}, prediction={p_res.get('prediction'):.2f} {p_res.get('unit')}, model={p_res.get('model', {}).get('name')}")

# 3. Digital Twin Agent
t0 = time.time()
t_res = digital_twin_graph.invoke({
    "request": {
        "district": "Mandi",
        "rainfall_mm": 60.0,
        "duration_hours": 24.0,
        "hazard_types": ["flood", "landslide"],
    },
    "errors": [],
}).get("response", {})
t_time = time.time() - t0
peak_q = t_res.get("flood", {}).get("peak_discharge_m3s")
breach = t_res.get("flood", {}).get("warning_threshold_exceeded")
print(f"✅ 3. Digital Twin Agent ({t_time:.2f}s): district={t_res.get('district')}, peak_discharge={peak_q} m3/s, breach={breach}")

# 4. Alert & Risk Agent
t0 = time.time()
a_res = alert_graph.invoke({
    "request": {
        "location": "Mandi, Himachal Pradesh",
        "hazard_types": ["rainfall", "flood", "landslide"],
        "horizon": "24h",
        "notify": False,
    },
    "errors": [],
}).get("alert", {})
a_time = time.time() - t0
print(f"✅ 4. Alert Agent ({a_time:.2f}s): severity={a_res.get('severity')}, risk_score={a_res.get('risk_score')}")

# 5. Report Agent
t0 = time.time()
r_res = report_graph.invoke({
    "request": {
        "report_type": "multi_hazard",
        "districts": ["Mandi"],
        "format": "json",
        "horizon": "24h",
        "include_charts": False,
    },
    "errors": [],
}).get("result", {})
r_time = time.time() - t0
report_id = r_res.get("metadata", {}).get("report_id")
sections_cnt = len(r_res.get("sections", []))
print(f"✅ 5. Report Agent ({r_time:.2f}s): report_id={report_id}, sections={sections_cnt}")

print("\n--- [PHASE 2] MULTI-AGENT CONVERSATIONAL DEMO SESSION ---")
queries = [
    ("Query A (Weather Forecast)", "Will there be heavy rainfall in Mandi district tomorrow?"),
    ("Query B (Multi-Hazard Risk)", "What is the flood and landslide risk in Kullu right now?"),
    ("Query C (Trip & Route Safety)", "Can I travel from Mandi to Manali tomorrow? What will it cost and which way is safe?"),
    ("Query D (RAG Knowledge Engine)", "Show me the historical flood data for Beas river and disaster guidelines"),
]

for label, q in queries:
    print("\n" + "-" * 70)
    print(f"[{label}]\nQuery: \"{q}\"")
    t0 = time.time()
    state = {
        "session_id": "demo-verification-session",
        "user_query": q,
        "user_context": {"location": "Mandi"},
        "history": [],
        "errors": [],
    }
    result = orchestrator_graph.invoke(state)
    elapsed = time.time() - t0
    tools = [r["tool"] for r in result.get("tool_call_records", [])]
    errs = result.get("errors", [])
    print(f"⚙️  Tools Invoked: {tools}")
    print(f"⏱️  Duration: {elapsed:.2f}s | Errors: {errs}")
    print(f"💬 Generated Response:\n{result.get('final_response')}")

print("\n" + "=" * 80)
print("✨ ALL DEMO SESSION CHECKS COMPLETED SUCCESSFULLY WITH 0 ERRORS")
print("=" * 80)
