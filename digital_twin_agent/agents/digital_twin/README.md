# Digital Twin Agent (Agent 5 of 8)

Geospatial simulation & scenario analysis: runs what-if flood and landslide
scenarios for a district given a rainfall amount, using **real, citable
hydrology/geotechnical formulas** (not fabricated numbers), with honestly
documented default assumptions wherever your real DEM/GIS layers aren't
wired in yet. Follows the diagram's workflow: receive request → load twin
state → prepare simulation inputs → run simulation → analyze results →
visualize → update twin state → return.

## What's actually implemented vs. stubbed

| Component | Status |
|---|---|
| Full LangGraph workflow | ✅ Real, tested |
| FastAPI endpoints | ✅ Real, tested |
| **Flood model (Rational Method)** | ✅ **Real, standard hydrology formula** — Q=C·I·A/360, a genuine textbook method (ASCE Manual 37) |
| **Landslide model (Caine 1980 threshold)** | ✅ **Real, widely-cited rainfall intensity-duration threshold** — I=14.82·D⁻⁰·³⁹ |
| Affected area / max water depth | ⚠️ **Simplified severity heuristic**, not real 2D hydraulic modeling — clearly labeled |
| **Boundary area calculation** | ✅ Real — loads your actual district GeoJSON + computes area via Shapely, if the file exists on disk |
| **Bridges/roads-at-risk counts** | ✅ Real feature counts from your actual infrastructure GeoJSON, if present — scaled by simulated severity (not a real flood-polygon intersection) |
| Population at risk | 🔲 Stubbed — your census data isn't in queryable/spatial form yet |
| 3D/4D visualization (Cesium/Three.js) | 🔲 Not built — this agent returns a simplified structured summary (risk color + key numbers) for a frontend to render as a basic map/dashboard card |
| Satellite imagery, MODIS, InSAR-based ground deformation | 🔲 Not wired in |

## Read this before treating outputs as real forecasts

The **Rational Method** and **Caine's threshold** are real, standard,
peer-reviewed methods — this isn't fabricated science. But:

1. **Rational Method assumes a single storm intensity** over the whole
   duration. A "150mm in 24h" scenario averages out to 6.25mm/hr — but real
   extreme rainfall (the kind that actually causes flash floods) often
   concentrates in short, much more intense bursts (50-100+ mm/hr for an
   hour or two). Using the flat 24h average will systematically
   *understate* flood risk for bursty storms. If you have sub-hourly
   rainfall data, feed a shorter `duration_hours` with the burst's actual
   intensity for a more meaningful result.
2. **Caine's threshold is global, not regionally calibrated for the
   Himalaya** — regional studies generally find lower, more conservative
   thresholds. Treat "not exceeded" as "not exceeded relative to a global
   average," not "safe."
3. **`catchment_area_km2`, `runoff_coefficient`, `channel_capacity_m3s`,
   `slope_class` are all defaults**, not measured for your specific
   districts. Override them per-request once you have real values (a DEM
   gives you catchment area and slope; a hydrology study or historical
   gauge data gives you a calibrated runoff coefficient and channel
   capacity).

Every response's `assumptions` list spells out exactly which of these
defaults were used, so nothing here pretends to be more certain than it is.

## Setup

```bash
cd agents/digital_twin
pip install -r requirements.txt
```

## Run

```bash
uvicorn agents.digital_twin.main:app --reload --port 8004
```

## Test it

```bash
curl -X POST http://localhost:8004/api/v1/digital-twin/scenario \
  -H "Content-Type: application/json" \
  -d '{
    "district": "Mandi",
    "rainfall_mm": 150,
    "duration_hours": 24,
    "hazard_types": ["flood", "landslide"]
  }'
```

```bash
curl "http://localhost:8004/api/v1/digital-twin/layers?district=Mandi"
curl http://localhost:8004/api/v1/digital-twin/scenario/<scenario_id>
```

## Getting real layers loaded (instead of defaults)

Place your actual boundary/infrastructure GeoJSON files at:

```
digital_twin/metadata/boundaries/<district>_district.geojson    # e.g. mandi_district.geojson
digital_twin/infrastructure/Bridges/<district>_*.geojson
digital_twin/infrastructure/Roads/<district>_*.geojson
```

(matching the paths already in your `config.yaml`'s `paths.*` block) — the
agent will pick them up automatically and switch from "default" to "loaded"
status in `layers_used`, with real boundary area and real bridge/road
counts feeding into the impact assessment.

## Wiring into the Orchestrator

In the Orchestrator's `tools.py`, replace `digital_twin_tool`'s stub body:

```python
def digital_twin_tool(params: dict) -> dict:
    import httpx
    resp = httpx.post("http://localhost:8004/api/v1/digital-twin/scenario", json=params, timeout=30)
    resp.raise_for_status()
    return resp.json()
```

## Natural next steps (in rough priority order)

1. **Load a real DEM** (you already collect SRTM/DEM per your config) to
   derive real catchment area + slope class per district, replacing the
   flat defaults.
2. **Feed sub-hourly rainfall intensity** (from Agent 2/3) instead of a
   flat 24h average, for a more realistic Rational Method peak flow.
3. **Calibrate the runoff coefficient and channel capacity** against any
   real historical flood/discharge data you can find (even a few known
   events helps).
4. Once (1)-(3) are done, a real 2D hydraulic model (even a simplified
   raster-based one) becomes worth building for actual flood-extent
   polygons, rather than the current severity heuristic.

## Notes

- **CORS is wide open** for local dev — restrict before deploying publicly.
- The degree→km² area conversion in `twin_state.py` is a rough constant
  (111km/degree), fine for a quick estimate at this latitude, not
  survey-grade — use a proper projected CRS (e.g. UTM 43N) if you need
  precise areas.
