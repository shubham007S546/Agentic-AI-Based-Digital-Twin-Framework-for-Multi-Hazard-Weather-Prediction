# Agentic AI-Based Digital Twin Framework for Rainfall Prediction and Extreme Weather Intelligence

A modular environmental data engineering framework for collecting, validating, and organizing heterogeneous datasets required for rainfall prediction, cloudburst forecasting, landslide analysis, and digital twin development in Himachal Pradesh.

**Current Focus:** Data Engineering & Environmental Dataset Collection

**Target Districts**

- Mandi
- Kullu
- Chamba

---

# Project Overview

The objective of this project is to build a scalable data engineering pipeline that automatically collects, validates, and organizes multi-source environmental datasets.

The collected datasets will later support:

- Rainfall Prediction
- Cloudburst Prediction
- Landslide Prediction
- Flash Flood Prediction
- Digital Twin Development
- Disaster Intelligence
- Decision Support Systems

This repository currently focuses on **dataset collection and engineering**. Machine Learning, Deep Learning, and Agentic AI will be implemented after the master dataset has been created.

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
Machine Learning
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

├── digital_twin/
│   ├── climate_indices/
│   ├── disaster_history/
│   ├── hydrology/
│   ├── infrastructure/
│   ├── metadata/
│   ├── population/
│   ├── terrain/
│   ├── vegetation/

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
| MODIS (AppEEARS) | 🔄 Running |
| ERA5 | 🔄 Under Update |
| ERA5-Land | 🔄 Under Update |
| India WRIS | ✅ Completed |
| Data.gov | ✅ Completed |
| Census | ✅ Completed |
| Climate Indices | ✅ Completed |
| HPSDMA | ✅ Completed |
| Infrastructure | 🔄 Under Development |
| ReliefWeb | ⏳ Pending API Approval |

---

# Digital Twin Datasets

The project organizes data into thematic layers.

## Climate

- Open-Meteo
- ERA5
- ERA5-Land
- IMD

---

## Satellite

- NASA GPM
- MODIS NDVI

---

## Hydrology

- India WRIS

---

## Disaster History

- HPSDMA
- ReliefWeb

---

## Population

- Census

---

## Infrastructure

- Roads
- Bridges
- Schools
- Hospitals
- Police Stations
- Fire Stations
- Government Offices
- Villages
- Bus Stops
- Railway Stations
- Airports
- Power Infrastructure

---

## Climate Indices

- ENSO
- IOD
- SOI
- CO₂

---

# Setup

Create a virtual environment

```bash
python -m venv .venv
```

Activate

Windows

```bash
.venv\Scripts\activate
```

Linux

```bash
source .venv/bin/activate
```

Install dependencies

```bash
pip install -r requirements.txt
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

where applicable.

Metadata includes

- Source
- Collection Time
- Variables
- Spatial Coverage
- Temporal Coverage
- File Size
- Processing Details

---

# Design Principles

The framework follows several software engineering principles.

- Modular collector architecture
- One source per collector
- Configuration-driven design
- Reproducible data collection
- Metadata-first workflow
- Fault-tolerant downloads
- Independent execution
- Scalable directory hierarchy
- Research-oriented data management

---

# Current Status

Current Phase

**Environmental Data Engineering**

Completed

- Project Architecture
- Collector Framework
- Logging System
- Metadata Framework
- Configuration Management
- District Boundary Extraction
- Most Environmental Collectors

Running

- MODIS AppEEARS
- ERA5
- ERA5-Land

Pending

- Infrastructure
- ReliefWeb

---

# Future Roadmap

Phase 1

Environmental Data Collection

↓

Phase 2

Dataset Validation

↓

Phase 3

Preprocessing

↓

Phase 4

Feature Engineering

↓

Phase 5

Master Dataset Generation

↓

Phase 6

Machine Learning

↓

Phase 7

Deep Learning

↓

Phase 8

Agentic AI

↓

Phase 9

Digital Twin

↓

Phase 10

Decision Support & Early Warning System

---

# Technology Stack

Programming

- Python

Geospatial

- GeoPandas
- Rasterio
- Shapely
- Xarray

Data Processing

- Pandas
- NumPy
- PyArrow

Networking

- Requests
- BeautifulSoup

Visualization

- Matplotlib

Machine Learning (Future)

- Scikit-learn
- XGBoost
- LightGBM
- PyTorch

---

# License

This repository is developed as part of the Summer Internship Programme at **IIT Mandi** for academic and research purposes.