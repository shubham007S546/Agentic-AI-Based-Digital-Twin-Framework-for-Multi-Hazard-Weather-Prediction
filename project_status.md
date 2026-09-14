# 🌩️ Agentic AI Digital Twin — Project Status & Run Guide

## ✅ What's Done / Working

| Layer | Module | Status |
|-------|--------|--------|
| 📐 Architecture | Project structure, config, logging | ✅ 100% |
| 🗺️ Spatial Data | GeoJSON for Mandi, Kullu, Chamba | ✅ Done |
| 📡 Data Collectors | Open-Meteo, IMD, NASA GPM, WRIS, Census, HPSDMA, Data.gov, Climate Indices | ✅ Done |
| 🔄 Data Collectors | MODIS (AppEEARS), ERA5, ERA5-Land | 🔄 In Progress |
| ⚙️ Preprocessing | `final_preprocessing.py` | ✅ Done |
| 🔬 Feature Engineering | `feature_engineering.py` | ✅ Done |
| 📊 EDA | `eda_mandi.py` | ✅ Done |
| 🤖 ML Training | XGBoost tuned (`train_xgboost_tuned.py`) | ✅ Done |
| 📈 Benchmarking | `training/benchmark.py`, `evaluate.py` | ✅ Done |
| 🧠 ML Module | `machine_learning_module/` | ✅ Done |
| 🔮 Deep Learning | LSTM/GRU/TCN models | 🔄 60% |
| 🌐 Backend (FastAPI) | Full API with auth, agents, prediction, reports | ✅ Done |
| 💻 Frontend (Next.js) | 28 pages: dashboard, alerts, map, digital twin, XAI, etc. | ✅ Done |
| 🤖 Agentic AI | Weather, Prediction, Alert, Report, Digital Twin agents | ✅ Done |
| 🔗 RAG | Knowledge engine + RAG pipeline | ✅ Done |
| 🏗️ Digital Twin | Core digital twin simulation layer | 🔄 90% |

---

## 🛠️ What's NOT Fully Done

- ERA5 / ERA5-Land collectors (auth issues with CDS API)
- Infrastructure data collector
- Deep learning model benchmark exports (~60% complete)
- ReliefWeb API integration (waiting for approval)
- Trained ML model files not present in `backend/ml_models/` yet (only metrics JSON exists)

---

## 🔧 Prerequisites Check (Your Machine)

| Tool | Required | Yours | Status |
|------|----------|-------|--------|
| Python | 3.12+ | 3.12.10 | ✅ |
| Node.js | 18+ | 24.14.0 | ✅ |
| pnpm | 9+ | 11.13.0 | ✅ |
| Docker Desktop | Latest | 29.7.2 (installed) | ⚠️ Not running |

> **Docker is installed but NOT running** — you need to open Docker Desktop first!

---

## 🚀 Step-by-Step: How to Run Everything

### Step 1 — Open Docker Desktop
Open the **Docker Desktop** app from your Start menu and wait until it shows **"Docker Desktop is running"** (the whale icon in taskbar turns solid).

---

### Step 2 — Start Infrastructure (PostgreSQL + Redis + MinIO)

Open **PowerShell** in the project folder:
```powershell
cd "c:\Users\shubh\Downloads\Agentic-AI-Based-Digital-Twin-Framework-for-Multi-Hazard-Weather-Prediction-main\Agentic-AI-Based-Digital-Twin-Framework-for-Multi-Hazard-Weather-Prediction-main\backend"
docker compose up -d
```
Wait ~30 seconds, then verify:
```powershell
docker compose ps
```
You should see 3 containers: `weather_twin_db`, `weather_twin_redis`, `weather_twin_minio` — all **healthy**.

---

### Step 3 — Set Up & Start the Backend (FastAPI)

In the **same terminal** (still inside `backend/`):
```powershell
# Activate the virtual environment (already created)
.\.venv\Scripts\Activate.ps1

# Copy the env file if not done yet
copy .env.example .env

# Run database migrations
python -m alembic upgrade head

# Start the FastAPI server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Verify at:** http://localhost:8000/docs ← Swagger API docs

---

### Step 4 — Start the Frontend (Next.js)

Open a **NEW** PowerShell terminal:
```powershell
cd "c:\Users\shubh\Downloads\Agentic-AI-Based-Digital-Twin-Framework-for-Multi-Hazard-Weather-Prediction-main\Agentic-AI-Based-Digital-Twin-Framework-for-Multi-Hazard-Weather-Prediction-main\frontend"
pnpm dev
```

**Verify at:** http://localhost:3000

---

## 🌐 What You'll See in the Browser

| URL | What it is |
|-----|------------|
| http://localhost:3000 | 🏠 Main Dashboard (Next.js frontend) |
| http://localhost:3000/dashboard | 📊 Main monitoring dashboard |
| http://localhost:3000/map | 🗺️ Interactive district map |
| http://localhost:3000/alerts | 🚨 Alert system |
| http://localhost:3000/digital-twin | 🌐 Digital Twin view |
| http://localhost:3000/rainfall | 🌧️ Rainfall prediction |
| http://localhost:3000/landslide | ⛰️ Landslide risk |
| http://localhost:3000/forecast | 📅 Forecasting |
| http://localhost:3000/agents | 🤖 Agentic AI status |
| http://localhost:8000/docs | 📘 Backend API Swagger docs |
| http://localhost:9001 | 🗄️ MinIO file storage UI |

---

## 🛑 How to Stop Everything

```powershell
# Stop frontend: Ctrl+C in its terminal
# Stop backend: Ctrl+C in its terminal

# Stop Docker infrastructure
cd backend
docker compose down
```

---

## ⚠️ Known Issues to Watch

1. **Backend `.env` file** — Copy `.env.example` to `.env` in `backend/`. Fill in any API keys if needed.
2. **Alembic migration** — If it fails, make sure Docker containers are healthy first (`docker compose ps`).
3. **ML models not present** — The backend loads ML model files at startup. If `backend/ml_models/` is empty (only `training_metrics.json` exists), some prediction endpoints may return errors — but the rest of the app will still work.
4. **Frontend dependency** — `node_modules` already exists, but if `pnpm dev` errors, run `pnpm install` first.
