# Orchestrator Agent (Agent 1 of 8)

The central coordinator: understands the user's request, decides which of
Agents 2-8 to call, aggregates their results, and generates the final
natural-language response. This is a working, tested implementation of the
orchestrator itself; Agents 2-8 are stubbed behind a clean tool interface so
you can wire each one in independently, later, without touching this code.

## What's actually implemented vs. stubbed

| Component | Status |
|---|---|
| Orchestrator graph (intent -> plan -> call tools -> aggregate -> respond -> store/log) | ✅ Real, tested |
| FastAPI endpoint (`POST /api/v1/orchestrator/query`) | ✅ Real, tested |
| Conversation memory (in-process, or Redis if `REDIS_URL` set) | ✅ Real, tested |
| LLM calls (intent understanding, task planning, response generation) | ✅ Real (via Groq), with a rule-based fallback if no API key is set |
| `weather_tool` / `prediction_tool` / `alert_tool` / `digital_twin_tool` / `data_tool` / `rag_tool` / `notification_tool` (Agents 2-8) | 🔲 **Stubbed** -- each returns a clearly-labelled placeholder (`"status": "stub"`), see `tools.py` for the exact endpoint each should eventually call |

Every stub response is honestly labelled so nothing gets silently presented
as real data -- `generate_response` is explicitly instructed not to invent
numbers when a tool result is a stub.

## Setup

```bash
cd agents/orchestrator
pip install -r requirements.txt
cp .env.example .env
# edit .env and set GROQ_API_KEY (get one free at https://console.groq.com)
```

## Run

```bash
uvicorn agents.orchestrator.main:app --reload --port 8000
```

Then:

```bash
curl -X POST http://localhost:8000/api/v1/orchestrator/query \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-1",
    "query": "Will there be heavy rainfall in Mandi district tomorrow?",
    "context": {"location": "Mandi", "role": "citizen"}
  }'
```

You'll get back a real LLM-understood intent, a task plan (which tools it
decided to call), the (stubbed) tool results, and a generated response that
honestly says the prediction capability isn't wired in yet -- because right
now, it isn't. Once you wire in `prediction_tool` to your real LightGBM
model, that same query will start returning real numbers with zero changes
needed anywhere else in the orchestrator.

## Wiring in a real agent (example: Agent 3, Prediction)

Open `tools.py` and replace the stub body of `prediction_tool`:

```python
def prediction_tool(params: dict) -> dict:
    from machine_learning_module.models.common.base_model import BasePredictor
    from machine_learning_module.models.machine_learning.lightgbm.model import LightGBMModel
    from machine_learning_module.models.machine_learning.lightgbm.config import LightGBMConfig
    import pandas as pd

    config = LightGBMConfig(task_type="regression", target_transform="log1p")
    predictor = BasePredictor.from_artifact(
        LightGBMModel, config,
        "machine_learning_module/artifacts/lightgbm/step2_log1p_lgbm/model.joblib",
    )
    X = pd.DataFrame([params])  # build the real feature row for this location/date here
    result = predictor.predict_dataframe(X)
    return {"status": "ok", "predicted_mm": float(result["prediction"].iloc[0])}
```

Nothing in `graph.py` or `main.py` needs to change -- the orchestrator
already calls `prediction_tool` through the same registry either way.

## Notes

- **CORS is wide open** (`allow_origins=["*"]`) for local development.
  Restrict this to your actual frontend origin before deploying anywhere
  public.
- The fallback (no-API-key) LLM is a rule-based keyword matcher -- it's
  there so you can test the plumbing without a key, not as a real intent
  classifier. Get a Groq key before using this for anything real.
- `aggregate_and_validate` is currently a pass-through plus basic error
  surfacing. Once Agents 2-8 return real data, this is the right place to
  add cross-agent consistency checks (e.g. flag if `prediction_tool` and
  `alert_tool` disagree on severity for the same location).
