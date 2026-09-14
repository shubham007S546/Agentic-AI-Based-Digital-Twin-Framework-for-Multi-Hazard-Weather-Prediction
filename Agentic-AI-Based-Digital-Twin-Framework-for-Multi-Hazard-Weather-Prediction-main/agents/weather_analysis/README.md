# Weather Analysis Agent (Agent 2 of 8)

Fetches, analyzes, and summarizes real-time and forecast weather conditions
for a location, following the 6-step workflow from the architecture diagram:
receive request → extract/validate params → select sources → fetch data in
parallel → process & analyze (clean, aggregate, detect anomalies) → generate
structured output → cache result → return to Orchestrator.

## What's actually implemented vs. stubbed

| Component | Status |
|---|---|
| LangGraph workflow (all 6 steps) | ✅ Real, tested |
| FastAPI endpoint (`GET /api/v1/weather/forecast`) | ✅ Real, tested |
| **Open-Meteo provider** | ✅ **Real, working HTTP integration** — free, no API key |
| Data cleaning / aggregation / anomaly detection | ✅ Real, rule-based, tested |
| Cache (in-process, or Redis if `REDIS_URL` set) | ✅ Real, tested |
| Natural-language summary | ✅ Real if `GROQ_API_KEY` set, deterministic template fallback otherwise |
| IMD / ERA5 / NASA GPM providers | 🔲 **Stubbed** — see "Why these three are stubbed" below |

## Why IMD / ERA5 / NASA GPM are stubbed (not just "not done yet")

Looking at your own `config.yaml` and collectors, these three are **batch
archive/reanalysis sources**, not live query APIs:

- **IMD**: gridded rainfall via IMDLIB, collected into
  `datasets/source_1_imd/cleaned/imd_<district>_<year>_cleaned.csv` by
  `collectors/imd_collector.py`. There's no "ask IMD for right-now data"
  endpoint to call.
- **ERA5**: Copernicus CDS reanalysis, an async batch-job API (submit
  request → wait → download), collected into
  `datasets/source_4_era5/cleaned/era5_<district>_<yyyymm>_cleaned.csv` by
  `collectors/era5_collector.py`. Not something a live agent call can wait on.
- **NASA GPM**: needs Earthdata auth + HDF5 processing, collected into
  `datasets/source_2_nasa_gpm/` by `collectors/nasa_collector.py`.

So instead of faking a live call to any of these, each stub in `providers.py`
is documented with exactly which already-collected file to read from once
you wire it in — e.g.:

```python
def imd_provider(params: dict) -> dict:
    df = pd.read_csv(f"datasets/source_1_imd/cleaned/imd_{district}_{year}_cleaned.csv")
    latest = df.iloc[-1]
    return {"status": "ok", "source": "imd", "current": {...}}
```

Same registry pattern as the Orchestrator's `tools.py` — swap the stub body,
nothing else in `graph.py` changes.

## Setup

```bash
cd agents/weather_analysis
pip install -r requirements.txt
cp .env.example .env   # optional: add GROQ_API_KEY for richer summaries
```

## Run

```bash
uvicorn agents.weather_analysis.main:app --reload --port 8001
```

(Port 8001, not 8000 -- so it can run alongside the Orchestrator Agent.)

## Test it

```bash
curl "http://localhost:8001/api/v1/weather/forecast?location=Mandi&latitude=31.7081&longitude=76.9318&forecast_hours=24"
```

You'll get back **real current conditions and a 24-hour forecast** from
Open-Meteo for Mandi's coordinates, with rule-based anomaly detection
(matches the diagram's "High humidity detected" example) and a confidence
score that reflects how many of the 4 sources actually returned real data
(currently capped since only Open-Meteo is real -- confidence rises as you
wire in IMD/ERA5/NASA GPM).

## Wiring this into the Orchestrator Agent

In the Orchestrator's `tools.py`, replace `weather_tool`'s stub body with a
real HTTP call to this agent:

```python
def weather_tool(params: dict) -> dict:
    import httpx
    resp = httpx.get("http://localhost:8001/api/v1/weather/forecast", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()
```

## Notes

- **CORS is wide open** for local development -- restrict before deploying publicly.
- Anomaly thresholds (`_HUMIDITY_HIGH`, `_RAINFALL_HOURLY_HEAVY_MM`, etc. in
  `processing.py`) are reasonable generic starting points, not calibrated to
  Mandi/Kullu/Chamba climatology specifically -- tune them once you have a
  sense of what's actually unusual for these districts.
- `aggregate_sources` currently just takes the first source's forecast
  series when more than one source has one, since aligning differently-timed
  series from multiple sources needs interpolation first -- flagged as
  future work in the code, matching the diagram's "Aggregation &
  Interpolation" step, which isn't fully built out yet with only one real source.
