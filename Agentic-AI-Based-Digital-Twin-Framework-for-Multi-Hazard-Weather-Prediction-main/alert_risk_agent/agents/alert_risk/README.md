# Alert & Risk Assessment Agent (Agent 4 of 8)

Real-time hazard detection and risk assessment: monitors predictions,
weather, and external feeds; runs a transparent rule engine to score risk
and assign a severity level (Red/Orange/Yellow/Green); generates a
structured alert with recommended actions; decides whether to escalate; and
logs everything. Follows the diagram's 7-step workflow: monitor inputs →
detect triggers → assess risk → evaluate impact → generate alert → notify &
escalate → log & update.

## What's actually implemented vs. stubbed

| Component | Status |
|---|---|
| Full 7-step LangGraph workflow | ✅ Real, tested |
| FastAPI endpoints | ✅ Real, tested |
| **Rule Engine / risk scoring** | ✅ **Real** — transparent weighted-sum scoring, every factor's contribution returned in the response |
| **Severity classification (Red/Orange/Yellow/Green)** | ✅ Real, matches the diagram's 4-tier system exactly, thresholds configurable |
| **Agent 2 (Weather) + Agent 3 (Prediction) integration** | ✅ Real HTTP calls, with honest graceful degradation if those agents aren't running |
| **ReliefWeb external feed** | ✅ Real HTTP integration (public API) — verified request format is correct; I couldn't fully live-test it from my sandbox (network restrictions on my end, not yours — see notes) |
| Alert generation (description + recommended actions) | ✅ Real — template-based, or LLM-enhanced via Groq if `GROQ_API_KEY` is set |
| Alert storage (JSONL + optional Redis) | ✅ Real, tested |
| Escalation *decision* logic | ✅ Real (severity-based routing) |
| **Actually sending** notifications (email/SMS/push) | 🔲 Stubbed — needs real provider credentials (Twilio, SendGrid, Firebase) |
| ML Risk Model (trained classifier) | 🔲 Not built — diagram's "ML Risk Model" box is future work once you have historical alert-outcome labels to train on; rules alone drive scoring for now |
| Impact Model (population/infrastructure exposure) | 🔲 Stubbed — your census/infrastructure collectors produce static files, not a queryable API yet |
| CWC Alerts / GSI Landslide / News-Social feeds | 🔲 Stubbed — no confirmed public API for these in your project (documented per-source in `external_feeds.py`) |

## How risk scoring works (fully transparent, no black box)

```
risk_score = rainfall_prediction_contribution      (up to 0.5, scales with predicted mm / cloudburst floor)
           + extreme_event_bonus                    (+0.2 if Agent 3 flagged is_extreme_event)
           + weather_anomalies_contribution          (up to 0.2, scales with anomaly count)
           + recent_external_reports_contribution    (+0.1 if ReliefWeb has matching recent reports)
```

Then mapped to severity via configurable thresholds (`RISK_RED_THRESHOLD` etc.
in `.env`), with one override: **rainfall ≥ `CLOUDBURST_MM_FLOOR` (default
100mm) or an `is_extreme_event` flag always forces at least Orange**,
regardless of the composite score — matching your `CLOUDBURST_MM` constant
from `final_preprocessing.py`.

Every alert's `notes` field includes `data_completeness` (how many of the 3
intended real data sources — prediction, weather, external feeds — actually
returned real data) so you can tell a well-supported alert from one running
on thin data.

## About the ReliefWeb integration

I built this as a **real** HTTP integration (not a stub) — correct request
shape per ReliefWeb's v2 API (POST with `appname` as a query param, JSON
filter body), verified with a mocked realistic response. I could not fully
confirm it against the live API from my own environment (my sandbox's
network is restricted to a fixed allowlist that doesn't include
`api.reliefweb.int`) — but this is a restriction on my end, not something
about your setup. Just run it and check; if ReliefWeb's real API differs in
some way I couldn't verify (field names, pagination), the fix is a small
edit to `external_feeds.py`'s `fetch_reliefweb_reports`.

## Setup

```bash
cd agents/alert_risk
pip install -r requirements.txt
cp .env.example .env
```

## Run

```bash
uvicorn agents.alert_risk.main:app --reload --port 8003
```

(Port 8003 — alongside Orchestrator on 8000, Weather on 8001, Prediction on 8002.)

## Test it

Standalone (no other agents needed — will honestly report reduced data completeness):

```bash
curl -X POST http://localhost:8003/api/v1/alerts/generate \
  -H "Content-Type: application/json" \
  -d '{
    "location": "Mandi, Himachal Pradesh",
    "district": "Mandi",
    "hazard_types": ["rainfall"],
    "horizon": "24h",
    "notify": true
  }'
```

With Agent 2 and Agent 3 also running (`uvicorn agents.weather_analysis.main:app --port 8001` /
`uvicorn agents.prediction.main:app --port 8002`), this same call will pull in
real weather + real predictions automatically — no code changes needed.

To simulate a high-severity scenario without the other agents running, pass
overrides directly:

```bash
curl -X POST http://localhost:8003/api/v1/alerts/generate \
  -H "Content-Type: application/json" \
  -d '{
    "location": "Mandi, Himachal Pradesh", "district": "Mandi",
    "hazard_types": ["rainfall"], "horizon": "24h", "notify": true,
    "prediction_override": {"rainfall": {"status": "ok", "prediction": 120.0, "is_extreme_event": true, "unit": "mm"}},
    "weather_override": {"status": "ok", "anomalies": ["High humidity detected", "Heavy rainfall detected"]}
  }'
```

```bash
curl http://localhost:8003/api/v1/alerts/current
curl http://localhost:8003/api/v1/alerts/<alert_id>
```

## Wiring in real notification providers

In `escalation.py`, replace `_send_notification_stub`'s body per channel:

```python
def _send_notification_stub(channel: str, alert: dict) -> dict:
    if channel == "email":
        sg_client.send(to=..., subject=alert["type"], body=alert["description"])
        return {"channel": "email", "status": "sent"}
    if channel == "sms":
        twilio_client.messages.create(to=..., body=alert["description"])
        return {"channel": "sms", "status": "sent"}
    ...
```

## Wiring in a real ML Risk Model

Once you have historical alert outcomes to train against (did the predicted
severity match what actually happened?), train a classifier the same way as
your other models (`machine_learning_module`'s `train.py` pattern), then
blend its output into `risk_engine.assess_risk` as an additional weighted
factor alongside the existing rules — the rules don't need to go away, an
ML model and a rule engine agreeing is more trustworthy than either alone.

## Wiring into the Orchestrator

In the Orchestrator's `tools.py`, replace `alert_tool`'s stub body:

```python
def alert_tool(params: dict) -> dict:
    import httpx
    resp = httpx.post("http://localhost:8003/api/v1/alerts/generate", json=params, timeout=30)
    resp.raise_for_status()
    return resp.json()
```

## Notes

- **CORS is wide open** for local dev — restrict before deploying publicly.
- Severity thresholds and channel weights are reasonable starting points,
  not calibrated against real historical outcomes for Mandi/Kullu/Chamba —
  tune once you have that.
- `assess_risk_node` currently generates one alert for whichever requested
  hazard scores highest; if you want simultaneous alerts for multiple
  hazards in one call, that's a small change to `generate_alert_node` (loop
  over all hazards above a minimum severity instead of just the top one).
