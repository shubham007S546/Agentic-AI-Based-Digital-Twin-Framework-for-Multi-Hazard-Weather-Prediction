# Report Generation Agent (Agent 6 of 8)

Automated insights & report generation: aggregates data from Agents 2-5,
analyzes it, extracts key insights, and produces real PDF/Excel/JSON
reports with real embedded charts. Follows the diagram's 7-step workflow:
receive request → collect data → process & analyze → generate insights →
create report → export & distribute → log & store.

## What's actually implemented vs. stubbed

Unlike most of the other agents, **almost everything here is real** — report
generation doesn't need external infrastructure the way notifications or
GIS simulation do.

| Component | Status |
|---|---|
| Full 7-step LangGraph workflow | ✅ Real, tested |
| FastAPI endpoints (including file download) | ✅ Real, tested |
| **Data aggregation from Agents 2-5** | ✅ Real HTTP calls, graceful degradation if an agent isn't running |
| **Analytics** (cross-district stats, trends) | ✅ Real, deterministic |
| **Insights** (rule-based key findings) | ✅ Real, always available |
| Narrative summary | ✅ Real if `GROQ_API_KEY` set, sentence-joining fallback otherwise (rule-based insights never depend on it) |
| **PDF export** | ✅ **Real** — reportlab, with real embedded matplotlib charts |
| **Excel export** | ✅ **Real** — openpyxl, with real *native Excel* bar/pie charts (not just images) |
| **JSON / dashboard export** | ✅ Real |
| Report storage + versioning | ✅ Real (JSONL + optional Redis), version increments per (report_type, districts) |
| Distribution decision logic | ✅ Real (which channels, whether to send) |
| Actually sending (email/SMS/WhatsApp) | 🔲 Stubbed — needs real provider credentials, same as Agent 4 |
| Scheduled/recurring reports | 🔲 Not built — diagram's "Scheduler Service (APScheduler/Celery)" is future work; this agent only does on-demand generation for now |

## Report types

`daily_weather`, `rainfall_forecast`, `multi_hazard`, `district_risk`,
`infrastructure_impact`, `event_summary`, `seasonal_outlook`, `custom` —
each pulls from a different subset of Agents 2-5 (see
`_REPORT_TYPE_SOURCES` in `data_aggregator.py`). `GET /api/v1/reports/templates`
lists them all.

One honest caveat: **`seasonal_outlook` currently just pulls current
weather data** — a real seasonal outlook needs actual climatological
baselines (multi-year averages) to compare against, which this agent
doesn't have wired in yet. Treat it as a placeholder report type for now.

## Setup

```bash
cd agents/report
pip install -r requirements.txt
```

## Run

```bash
uvicorn agents.report.main:app --reload --port 8005
```

## Test it

Standalone (no other agents needed, using `data_override`):

```bash
curl -X POST http://localhost:8005/api/v1/reports/generate \
  -H "Content-Type: application/json" \
  -d '{
    "report_type": "daily_weather", "districts": ["Mandi"], "format": "pdf",
    "data_override": {
      "Mandi": {"weather": {"status": "ok", "current": {"temperature": 24.6, "humidity": 92.0, "rainfall": 3.4}, "anomalies": ["High humidity detected"]}}
    }
  }'
```

With Agents 2-5 also running, drop `data_override` and it'll pull real data
automatically:

```bash
curl -X POST http://localhost:8005/api/v1/reports/generate \
  -H "Content-Type: application/json" \
  -d '{"report_type": "multi_hazard", "districts": ["Mandi", "Kullu"], "format": "excel"}'
```

```bash
curl http://localhost:8005/api/v1/reports/<report_id>
curl http://localhost:8005/api/v1/reports/<report_id>/download -o report.pdf
curl http://localhost:8005/api/v1/reports
```

## Wiring in real notification providers

Same pattern as Agent 4 — in `distribution.py`, replace `_send_stub`'s body
per channel with real SendGrid/Twilio/etc. calls.

## Wiring in scheduled reports

Add APScheduler (or Celery beat) as a thin wrapper that calls this agent's
`/api/v1/reports/generate` on a cron schedule — no changes needed to this
agent itself, it's already a clean on-demand API.

## Wiring into the Orchestrator

```python
def report_tool(params: dict) -> dict:
    import httpx
    resp = httpx.post("http://localhost:8005/api/v1/reports/generate", json=params, timeout=60)
    resp.raise_for_status()
    return resp.json()
```

(Note: report generation can take a few seconds with charts — a longer
timeout than the other agents' tools is appropriate here.)

## Notes

- **CORS is wide open** for local dev — restrict before deploying publicly.
- `rainfall_forecast`/`multi_hazard` report types try to build prediction
  history from the weather agent's own forecast series if available — this
  is a best-effort convenience, not guaranteed to match what your real
  `feature_builder.py` (Agent 3) expects; check `is_extreme_event` and
  `predicted_rainfall_mm` values look sane before trusting a generated
  report's numbers.
- Excel sheet titles are truncated to 31 characters (an openpyxl/Excel
  hard limit) — long report-section titles will be cut off in sheet names
  (not in the content itself).
