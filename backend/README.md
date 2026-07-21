# VARUNA — Multi-Hazard Weather Prediction Platform

A FastAPI backend for the VARUNA platform — real-time weather ingestion, multi-hazard AI prediction (flood, cloudburst, rainfall), agentic pipeline orchestration, and geospatial analytics for Himachal Pradesh, India.

## Stack
- **FastAPI** + **SQLAlchemy 2.0** (async) + **PostgreSQL**
- **Celery** + **Redis** for background agent tasks
- **PyTorch / XGBoost / LightGBM / CatBoost** for ML models
- **OpenTelemetry** + **Prometheus** for observability

## Quick Start
```bash
poetry install --no-root
poetry run uvicorn app.main:app --reload
```
