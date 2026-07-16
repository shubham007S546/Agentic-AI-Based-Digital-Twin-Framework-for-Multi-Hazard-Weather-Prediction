# Agentic AI-Based Digital Twin Framework for Rainfall Prediction and Extreme Weather Intelligence

A modular environmental data engineering and machine learning framework for collecting, validating, modeling, and organizing heterogeneous datasets for rainfall prediction, cloudburst forecasting, landslide risk analysis, and digital twin development in Himachal Pradesh.

**Current Focus:** Machine Learning Modeling & Frontend Development

**Target Districts**

- Mandi
- Kullu
- Chamba

---

# Project Overview

The objective of this project is to build a scalable end-to-end pipeline that collects, validates, organizes, and models multi-source environmental datasets, surfaced through an interactive frontend and (eventually) an agentic AI-driven digital twin.

The project supports:

- Rainfall Prediction
- Cloudburst Prediction
- Landslide Risk Prediction
- Flash Flood Prediction
- Digital Twin Development
- Disaster Intelligence
- Decision Support Systems

Data engineering, preprocessing, and feature engineering are complete. The project has since moved into **machine learning modeling** (tree-based, ensemble, deep learning, and transformer architectures) and **frontend development**, with Agentic AI and full Digital Twin integration to follow.

---

# Project Workflow

```
External Data Sources
        │
        ▼
Collector Layer
        │
        ▼
Authentication & Validation
        │
        ▼
Metadata Generation
        │
        ▼
Raw Dataset Repository
        │
        ▼
Preprocessing
        │
        ▼
Feature Engineering
        │
        ▼
Master Dataset
        │
        ▼
Machine Learning  ◄── current stage
        │
        ▼
Frontend / Visualization  ◄── current stage
        │
        ▼
Agentic AI
        │
        ▼
Digital Twin
        │
        ▼
Prediction & Early Warning
```

---

# Project Structure

```
Weather_Data_Project/

├── collectors/
│   ├── openmeteo_collector.py
│   ├── imd_collector.py
│   ├── era5_collector.py
│   ├── era5_land_collector.py
│   ├── nasa_collector.py
│   ├── modis_collector.py
│   ├── datagov_collector.py
│   ├── wris_collector.py
│   ├── census_collector.py
│   ├── climate_index_collector.py
│   ├── hpsdma_collector.py
│   ├── infrastructure_collector.py
│   └── reliefweb_collector.py

├── config/
│   ├── config.yaml
│   └── config.example.yaml

├── datasets/
│   ├── source_1_imd/
│   ├── source_2_nasa_gpm/
│   ├── source_3_datagov/
│   ├── source_4_era5/
│   ├── source_5_openmeteo/
│   ├── nasa/
│   ├── digital_twin/
│   └── merged_dataset/

├── feature_engineering/

├── final_preprocessing.py        # Stage B: ML-ready preprocessing pipeline

├── ml_ready/                     # X/y train-val-test splits, scaler params,
│                                  # class weights, temporal CV folds, etc.

├── machine_learning_module/
│   ├── models/
│   │   ├── common/               # BaseModel, BaseTrainer, BaseEvaluator,
│   │   │                         # ModelRegistry, ModelComparator, torch_utils
│   │   ├── machine_learning/
│   │   │   ├── random_forest/
│   │   │   ├── xgboost/
│   │   │   ├── lightgbm/
│   │   │   └── two_stage_rainfall/
│   │   ├── deep_learning/        # LSTM / GRU / TCN
│   │   ├── ensemble/             # stacking / voting / weighted_average
│   │   └── transformer/          # TFT-Lite
│   ├── artifacts/                # trained model.joblib + metrics per experiment
│   ├── logs/
│   └── ml_ready/ (symlink or copy of root ml_ready/, used at run time)

├── frontend/                     # Next.js application
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── store/
│   ├── types/
│   └── public/

├── digital_twin/
│   ├── climate_indices/
│   ├── disaster_history/
│   ├── hydrology/
│   ├── infrastructure/
│   ├── metadata/
│   ├── population/
│   ├── terrain/
│   └── vegetation/

├── evaluation/
├── experiments/
├── reports/
├── utils/
├── logs/
└── README.md
```

---

# Implemented Collectors

| Collector | Status |
|------------|---------|
| Open-Meteo | ✅ Completed |
| IMD | ✅ Completed |
| NASA GPM | ✅ Completed |
| MODIS (AppEEARS) | ✅ Completed |
| ERA5 | ✅ Completed |
| ERA5-Land | ✅ Completed |
| India WRIS | ✅ Completed |
| Data.gov | ✅ Completed |
| Census | ✅ Completed |
| Climate Indices | ✅ Completed |
| HPSDMA | ✅ Completed |
| Infrastructure | 🔄 Under Development |
| ReliefWeb | ⏳ Pending API Approval |

---

# Machine Learning Modeling

All models are trained and evaluated through a shared `BaseModel` /
`BaseTrainer` / `BaseEvaluator` framework in `machine_learning_module/models/`,
so every algorithm — tree-based, ensemble, deep learning, or transformer —
follows the same config → train → evaluate → predict → hyperparameter-tune
CLI pattern.

## Algorithms implemented

| Category | Algorithms |
|---|---|
| Tree-based | Random Forest, XGBoost, LightGBM |
| Two-stage | Classifier (rain/no-rain) + Regressor (amount), for zero-inflated targets |
| Ensemble | Stacking, Voting, Weighted Average (over any combination of the above + deep learning) |
| Deep Learning | LSTM, GRU, TCN (Temporal Convolutional Network) |
| Transformer | TFT-Lite (Temporal Fusion Transformer: variable selection network + LSTM encoder + causal self-attention) |

## Current best result (`imd_rainfall_mm`, hourly regression)

| Model | Val R² | Test R² | Test RMSE |
|---|---|---|---|
| **LightGBM (log1p target transform)** | 0.194 | **0.216** | **9.27** |
| Ensemble stacking (RF+XGB+LGBM) | 0.226 | 0.206 | 9.33 |
| LSTM | 0.367 | 0.147 | 9.70 |
| GRU | 0.385 | 0.146 | 9.67 |
| TCN | 0.392 | 0.102 | 9.92 |
| Two-stage (classifier + regressor) | 0.219 | 0.097 | 9.94 |
| Ensemble stacking (XGB+LGBM) | 0.235 | 0.068 | 10.10 |
| LightGBM (Tweedie loss) | 0.258 | 0.041 | 10.25 |
| TFT-Lite | 0.297 | -0.496 | 12.80 |

**Key finding:** validation score is consistently a poor predictor of test
performance across every algorithm family tried — the more flexible the
model, the better it validates and the worse it generalizes. This traces
back to a known data quality issue: `imd_rainfall_mm` values are IMD
**daily** totals flat-filled across ~24 hourly rows, not genuine hourly
readings, so more expressive models increasingly overfit that artifact
rather than real rainfall signal. The simplest model (single LightGBM with
a log1p transform) is currently the most trustworthy result. **Next step:
re-aggregate the target to its native daily resolution** before further
model comparison, rather than continuing to search over architectures.

---

# Frontend

A Next.js frontend has been added under `frontend/`, providing the
visualization/interaction layer on top of the modeling pipeline (dashboards,
prediction views, etc. — details to be filled in as pages are finalized).

```
frontend/
├── app/            # Next.js app router pages
├── components/     # UI components
├── lib/            # client-side utilities / API helpers
├── store/          # state management
├── types/           # shared TypeScript types
└── public/          # static assets
```

Run locally:

```bash
cd frontend
pnpm install
pnpm dev
```

---

# Digital Twin Datasets

The project organizes data into thematic layers.

## Climate
- Open-Meteo
- ERA5
- ERA5-Land
- IMD

## Satellite
- NASA GPM
- MODIS NDVI

## Hydrology
- India WRIS

## Disaster History
- HPSDMA
- ReliefWeb

## Population
- Census

## Infrastructure
- Roads, Bridges, Schools, Hospitals, Police Stations, Fire Stations,
  Government Offices, Villages, Bus Stops, Railway Stations, Airports,
  Power Infrastructure

## Climate Indices
- ENSO, IOD, SOI, CO₂

---

# Setup

Create a virtual environment

```bash
python -m venv .venv
```

Activate

Windows
```powershell
.venv\Scripts\activate
```

Linux
```bash
source .venv/bin/activate
```

Install dependencies

```bash
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu   # for deep_learning / transformer
pip install optuna                                                    # for hyperparameter tuning
```

Frontend

```bash
cd frontend
pnpm install
```

---

# Configuration

All project settings are controlled through

```
config/config.yaml
```

The configuration file contains

- Study Area
- Districts
- Bounding Boxes
- Date Range
- API Credentials
- Output Paths
- Logging
- Retry Configuration
- Download Settings

No source code modifications are required when changing the study area or date range.

---

# Running Collectors

Run collectors independently from the project root.

```bash
python -m collectors.openmeteo_collector
python -m collectors.imd_collector
python -m collectors.era5_collector
python -m collectors.era5_land_collector
python -m collectors.nasa_collector
python -m collectors.modis_collector
python -m collectors.datagov_collector
python -m collectors.wris_collector
python -m collectors.census_collector
python -m collectors.climate_index_collector
python -m collectors.hpsdma_collector
python -m collectors.infrastructure_collector
```

---

# Running Machine Learning Models

All commands are run from inside `machine_learning_module/`.

```powershell
cd machine_learning_module

# Tree-based / two-stage
python -m models.machine_learning.lightgbm.train --task-type regression --data-dir ..\ml_ready --target-column imd_rainfall_mm --experiment-name lgbm_v1
python -m models.machine_learning.xgboost.train --task-type regression --data-dir ..\ml_ready --target-column imd_rainfall_mm --experiment-name xgb_v1
python -m models.machine_learning.random_forest.train --task-type regression --data-dir ..\ml_ready --target-column imd_rainfall_mm --experiment-name rf_v1
python -m models.machine_learning.two_stage_rainfall.train --data-dir ..\ml_ready --target-column imd_rainfall_mm --classifier-algorithm xgboost --regressor-algorithm lightgbm --experiment-name two_stage_v1

# Ensemble
python -m models.ensemble.train --task-type regression --data-dir ..\ml_ready --target-column imd_rainfall_mm --base-algorithms random_forest,xgboost,lightgbm --ensemble-method stacking --experiment-name ensemble_v1

# Deep learning
python -m models.deep_learning.train --task-type regression --data-dir ..\ml_ready --target-column imd_rainfall_mm --architecture lstm --sequence-length 24 --experiment-name dl_lstm_v1

# Transformer (TFT-Lite)
python -m models.transformer.train --task-type regression --data-dir ..\ml_ready --target-column imd_rainfall_mm --sequence-length 24 --hidden-size 64 --num-attention-heads 4 --experiment-name tft_lite_v1
```

Each package follows the same `train.py` / `evaluate.py` / `predict.py` /
`hyperparameter.py` pattern — see the `README.md` inside each package folder
under `models/` for full options.

---

# Data Engineering Features

Each collector provides

- Configuration-driven execution
- Automatic retry mechanism
- Resume interrupted downloads
- Metadata generation
- Logging
- Validation
- Standardized output
- Progress tracking

---

# Output Structure

Each collector generates

```
raw/
cleaned/
metadata.json
logs/
```

where applicable. Metadata includes Source, Collection Time, Variables,
Spatial Coverage, Temporal Coverage, File Size, Processing Details.

Each ML experiment generates, under `machine_learning_module/artifacts/<algorithm>/<experiment_name>/`:

```
model.joblib
val_metrics.json
test_metrics.json
training_history.json      (deep_learning / transformer only)
feature_importance.csv     (tree-based / ensemble only)
```

---

# Design Principles

- Modular collector architecture
- One source per collector
- Configuration-driven design
- Reproducible data collection and model training
- Metadata-first workflow
- Fault-tolerant downloads
- Independent execution
- Shared BaseModel/BaseTrainer/BaseEvaluator contract across every ML algorithm
- Scalable directory hierarchy
- Research-oriented data management

---

# Current Status

**Current Phase:** Machine Learning Modeling & Frontend Development

Completed
- Project Architecture
- Collector Framework
- Logging System
- Metadata Framework
- Configuration Management
- District Boundary Extraction
- All Environmental Collectors (Infrastructure & ReliefWeb pending)
- Preprocessing & Feature Engineering Pipeline (`final_preprocessing.py`)
- ML Framework (`common/`) — BaseModel, BaseTrainer, BaseEvaluator, ModelRegistry
- Random Forest, XGBoost, LightGBM, Two-Stage Rainfall models
- Ensemble module (stacking / voting / weighted_average)
- Deep Learning module (LSTM / GRU / TCN)
- Transformer module (TFT-Lite)
- Model comparison across 9 experiments — identified data quality issue
  (hourly flat-fill of daily IMD rainfall totals) limiting further ML gains
- Frontend scaffold (Next.js) initialized

In Progress
- Daily-resolution re-aggregation of `imd_rainfall_mm` to resolve the
  flat-fill artifact identified during model comparison
- Frontend pages/dashboards
- Infrastructure & ReliefWeb collectors

Pending
- Agentic AI layer
- Full Digital Twin integration
- Decision Support & Early Warning System

---

# Future Roadmap

Phase 1 — Environmental Data Collection ✅
Phase 2 — Dataset Validation ✅
Phase 3 — Preprocessing ✅
Phase 4 — Feature Engineering ✅
Phase 5 — Master Dataset Generation ✅
Phase 6 — Machine Learning 🔄 (in progress — data quality fix pending)
Phase 7 — Deep Learning ✅ (LSTM/GRU/TCN/TFT-Lite implemented)
Phase 8 — Frontend / Visualization 🔄
Phase 9 — Agentic AI ⏳
Phase 10 — Digital Twin ⏳
Phase 11 — Decision Support & Early Warning System ⏳

---

# Technology Stack

Programming
- Python
- TypeScript / JavaScript (frontend)

Geospatial
- GeoPandas, Rasterio, Shapely, Xarray

Data Processing
- Pandas, NumPy, PyArrow

Machine Learning
- Scikit-learn, XGBoost, LightGBM, PyTorch, Optuna

Frontend
- Next.js, React, pnpm

Networking
- Requests, BeautifulSoup

Visualization
- Matplotlib (modeling), frontend dashboard components (product-facing)

---

# License

This repository is developed as part of the Summer Internship Programme at **IIT Mandi** for academic and research purposes.