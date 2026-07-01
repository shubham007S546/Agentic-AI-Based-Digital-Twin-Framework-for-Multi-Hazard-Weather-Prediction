# Weather Data Project — Mandi District, Himachal Pradesh

Historical weather dataset collection pipeline for rainfall intensity,
cloudburst, and extreme weather event research.

---

## Project Structure

```
Weather_Data_Project/
│
├── collectors/                    # One file per data source — never mixed
│   ├── openmeteo_collector.py     # Source 1: Open-Meteo ERA5 (no key needed)
│   ├── imd_collector.py           # Source 2: IMD Pune gridded (IMDLIB)
│   ├── datagov_collector.py       # Source 3: data.gov.in IMD district data
│   ├── wris_collector.py          # Source 4: India-WRIS CSV loader
│   └── nasa_collector.py          # Source 5: NASA GPM IMERG
│
├── config/
│   └── config.yaml                # Single source of truth — change location/dates here
│
├── utils/
│   ├── config_loader.py           # Loads and validates config.yaml
│   ├── logger.py                  # Logger factory (file + console handlers)
│   ├── http_client.py             # requests.Session with retry + backoff
│   └── metadata_writer.py         # Generates metadata.json for each source
│
├── datasets/
│   ├── source_1_openmeteo/        # Open-Meteo ERA5
│   │   ├── raw/                   # Per-year raw parquet files
│   │   ├── cleaned/               # Single cleaned parquet + CSV
│   │   ├── metadata.json          # Auto-generated provenance record
│   │   └── logs/                  # Source-specific log files
│   │
│   ├── source_2_imd/              # IMD Pune 0.25° gridded
│   ├── source_3_datagov/          # data.gov.in district rainfall
│   ├── source_4_wris/             # India-WRIS station telemetry
│   ├── source_5_nasa_gpm/         # NASA GPM IMERG satellite
│   └── merged_dataset/            # Reserved for future merging stage
│
└── logs/                          # Global project-level log files
```

---

## Setup

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install requests pandas pyarrow tqdm pyyaml beautifulsoup4 lxml imdlib xarray netCDF4
```

---

## Configuration

Edit `config/config.yaml` to change:
- **Location**: state, district, lat/lon, bounding box
- **Date range**: start_date, end_date
- **API keys**: datagov, nasa_earthdata
- **HTTP settings**: timeouts, retries, backoff

---

## Running Collectors

Each collector is independent. Run only the ones you need:

```bash
# From project root — always run from here
cd Weather_Data_Project

# Source 1: Open-Meteo (no API key needed — run this first)
python -m collectors.openmeteo_collector

# Source 2: IMD gridded (requires imdlib + cdsp.imdpune.gov.in registration)
python -m collectors.imd_collector

# Source 3: data.gov.in (requires API key in config.yaml)
python -m collectors.datagov_collector

# Source 4: India-WRIS (requires manually downloaded CSV)
python -m collectors.wris_collector

# Source 5: NASA GPM (requires NASA Earthdata token in config.yaml)
python -m collectors.nasa_collector
```

---

## Output Per Source

Each collector produces exactly:

| File | Description |
|------|-------------|
| `raw/*.parquet` | Raw data exactly as received from API |
| `cleaned/*.parquet` | Deduplicated, typed, validated |
| `cleaned/*.csv` | Same cleaned data in CSV format |
| `metadata.json` | Full provenance record |
| `logs/*.log` | Rotating log files |

---

## API Access

| Source | Where to register | Time |
|--------|------------------|------|
| Open-Meteo | No registration needed | Instant |
| IMD Pune (IMDLIB) | cdsp.imdpune.gov.in | 1–2 days |
| data.gov.in | data.gov.in → Register | 5 minutes |
| India-WRIS | wdo.indiawris.gov.in → Register | Same day |
| NASA GPM | urs.earthdata.nasa.gov | 5 minutes |

---

## Design Principles

- **Source isolation**: each collector is a self-contained class with no dependencies on other collectors
- **Config-driven**: change state/district/dates in one place
- **No mixing**: one API per collector file, enforced by structure
- **Basic cleaning only**: no normalization, no feature engineering, no ML labels
- **Full provenance**: every output has a metadata.json recording what was downloaded, when, and how

---

## Current Stage

✅ Stage 1: Data Collection (this project)
⬜ Stage 2: Dataset merging (future)
⬜ Stage 3: ML modelling (future)
