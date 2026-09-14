# Prediction Agent (Agent 3 of 8)

ML inference & forecasting agent for rainfall, cloudburst, and landslide
hazards, following the diagram's 8-step workflow: receive request →
validate/parse → gather data & build features → select & load model → run
inference → post-process (calibrate, confidence, extreme-event flag) → save
& log → return to Orchestrator.

## What's actually implemented vs. stubbed

| Component | Status |
|---|---|
| Full LangGraph workflow (all 6 nodes) | ✅ Real, tested |
| FastAPI endpoints | ✅ Real, tested |
| **Rainfall model loading + real inference** | ✅ **Real** — loads your actual `model.joblib` via the same `BasePredictor`/`BaseModel` classes from `machine_learning_module`, no mocking. Supports any of your algorithms (lightgbm, xgboost, random_forest, ensemble, deep_learning, transformer) via `RAINFALL_MODEL_ALGO`. |
| Feature engineering (35-column schema → scaled vector) | ⚠️ **Real code, best-effort formulas** — see "Read this before trusting predictions" below |
| Confidence scoring | ✅ Real heuristic (see caveat below) |
| Extreme-event flagging | ✅ Real, threshold-based (matches your `CLOUDBURST_MM = 100.0` from `final_preprocessing.py`) |
| Prediction storage (JSONL + optional Redis) | ✅ Real, tested |
| Cloudburst / landslide models | 🔲 **Stubbed** — honestly reported as "not configured" until you train and point `CLOUDBURST_MODEL_PATH`/`LANDSLIDE_MODEL_PATH` at real artifacts |

## ⚠️ Read this before trusting predictions

I built `feature_builder.py` to reconstruct your exact 35-column feature
schema (I have the real column list from your `X_train.csv`), but I have
**not seen the body of your `final_preprocessing.py`** — only its
docstring. So several formulas are **best-effort reconstructions**, flagged
inline with comments:

- `season` encoding (0=winter, 1=summer, 2=monsoon, 3=post-monsoon) — a
  reasonable guess for Himachal Pradesh, not copied from your code
- `is_monsoon` — June–September — verify your actual cutoff
- `precip_acceleration` — defined here as "change in rolling 3h sum vs. one
  step earlier" — verify this matches your definition
- `wind_u_10m` / `wind_v_10m` — standard meteorological decomposition from
  speed + direction — should be safe, but double-check sign convention
  matches what era5/openmeteo collectors actually produced

**Before trusting this for anything beyond testing the pipeline end-to-end**,
open `feature_builder.py` and check each formula against your real
`final_preprocessing.py`. Where they don't match, fix `feature_builder.py`
— nothing else needs to change.

## `scaler_params.csv` format

`feature_builder.py` expects a CSV with the feature name as the first
column and `mean`/`std` columns, e.g.:

```csv
feature,mean,std
temperature_2m,18.3,4.2
dewpoint_2m,12.1,3.8
...
```

If your actual `scaler_params.csv` has a different shape, adjust
`load_scaler_params()` in `feature_builder.py` — it's a 5-line function.
**If `SCALER_PARAMS_PATH` is unset or the file can't be parsed, predictions
run on UNSCALED features and will likely be wrong** — the agent logs and
reports this loudly in the response `notes` field rather than failing
silently, but it's still on you to notice and fix it.

## Setup

```bash
cd agents/prediction
pip install -r requirements.txt
cp .env.example .env
# edit .env: set ML_MODULE_PATH, RAINFALL_MODEL_PATH, SCALER_PARAMS_PATH
```

## Run

```bash
uvicorn agents.prediction.main:app --reload --port 8002
```

## Test it

```bash
curl -X POST http://localhost:8002/api/v1/models/rainfall/predict \
  -H "Content-Type: application/json" \
  -d '{
    "hazard_type": "rainfall",
    "location": "Mandi, Himachal Pradesh",
    "target_timestamp": "2026-07-17T09:00:00+00:00",
    "horizon": "24h",
    "history": [
      {"timestamp": "2026-07-17T08:00:00+00:00", "temperature_2m": 22.0, "dewpoint_2m": 18.0,
       "relative_humidity": 88.0, "surface_pressure": 1005.0, "wind_speed_10m": 15.0,
       "wind_direction_10m": 210.0, "wind_gusts_10m": 25.0, "cloud_cover": 90.0,
       "cape": 800.0, "precipitation_openmeteo": 2.5, "rain_openmeteo": 2.5, "snowfall": 0.0}
    ]
  }'
```

`history` should ideally contain 72+ hourly readings (oldest first, most
recent last) so the rolling/lag precipitation features are meaningful — a
single reading works (as above) but the response will include a warning
about it and a lower confidence score.

```bash
curl http://localhost:8002/api/v1/models/rainfall/info
curl http://localhost:8002/api/v1/predictions/<prediction_id_from_above>
```

## Wiring in the history feed

Right now, the caller (you, or eventually the Orchestrator) has to supply
`history` directly in the request. The natural next step is to fetch this
automatically from Agent 2 (Weather Analysis Agent) plus your historical
`datasets/source_*` files rather than requiring the caller to assemble it —
that's flagged as a TODO in `graph.py`'s `build_features` node.

## Wiring in the Orchestrator

In the Orchestrator's `tools.py`, replace `prediction_tool`'s stub body:

```python
def prediction_tool(params: dict) -> dict:
    import httpx
    hazard = params.get("hazard_type", "rainfall")
    resp = httpx.post(f"http://localhost:8002/api/v1/models/{hazard}/predict", json=params, timeout=30)
    resp.raise_for_status()
    return resp.json()
```

## Training cloudburst / landslide models

You already have `y_train_cloudburst_flag_balanced.csv` /
`y_train_landslide_risk_balanced.csv` in your `ml_ready/` from
`final_preprocessing.py`'s Step 20. Train them the same way as your
rainfall model:

```bash
python -m models.machine_learning.xgboost.train \
  --task-type binary_classification --data-dir ml_ready \
  --target-column cloudburst_flag \
  --train-x-file X_train_cloudburst_flag_balanced.csv \
  --train-y-file y_train_cloudburst_flag_balanced.csv \
  --experiment-name cloudburst_xgb_v1
```

Then set `CLOUDBURST_MODEL_PATH=machine_learning_module/artifacts/xgboost/cloudburst_xgb_v1/model.joblib`
in `.env` and restart -- no code changes needed, `select_model` already
knows how to load it.

## Notes

- **Confidence score is a transparent heuristic** (data completeness +
  history length), not a calibrated predictive interval. The diagram's
  "Uncertainty" box (prediction intervals, quantile regression, Monte
  Carlo dropout) is real future work, not implemented here yet.
- **CORS is wide open** for local dev — restrict before deploying publicly.
- Given your earlier model comparison (log1p LightGBM was your only model
  that generalized; everything fancier overfit the flat-fill artifact),
  `RAINFALL_MODEL_ALGO=lightgbm` + `RAINFALL_TARGET_TRANSFORM=log1p` pointing
  at `step2_log1p_lgbm` is the right default here — resist the urge to swap
  in a fancier model until the daily-aggregation data fix we discussed
  actually lands.
