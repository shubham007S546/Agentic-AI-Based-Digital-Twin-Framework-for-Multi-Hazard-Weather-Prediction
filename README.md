# 🌦️ Agentic AI-Based Digital Twin Framework
## Rainfall Prediction & Extreme Weather Intelligence — Himachal Pradesh

> **Enterprise-grade AI platform for multi-hazard disaster prediction, digital twin simulation, and early warning generation.**
> Designed for research publication and production deployment in Mandi, Kullu, and Chamba districts.

---

## 🗺️ Table of Contents

1. [Project Overview](#-project-overview)
2. [Architecture Overview](#-architecture-overview)
3. [Technology Stack](#-technology-stack)
4. [Backend — Step-by-Step Setup Guide](#-backend--step-by-step-setup-guide)
5. [Project Structure](#-project-structure)
6. [API Reference Summary](#-api-reference-summary)
7. [Environment Variables](#-environment-variables)
8. [Running the Backend Locally](#-running-the-backend-locally)
9. [Running Background Workers](#-running-background-workers)
10. [Development Workflow](#-development-workflow)
11. [Phase Completion Status](#-phase-completion-status)
12. [Contributing](#-contributing)

---

## 🎯 Project Overview

This is a **multi-discipline research platform** that integrates:

| Domain | Capability |
|---|---|
| 🌧️ **Weather Intelligence** | Real-time and historical data from IMD, Open-Meteo, NASA GPM, ERA5 |
| 🤖 **Agentic AI** | 12 autonomous AI agents for monitoring, prediction, reporting, and simulation |
| 🧠 **ML Inference** | Random Forest, XGBoost, LightGBM, LSTM, CNN-LSTM, Transformer, TFT |
| 🌍 **Digital Twin** | Synchronized district-level simulation with scenario replay |
| 🚨 **Early Warning** | Cloudburst, Landslide, Flash Flood alert generation |
| 📊 **Research Analytics** | Explainability (SHAP), feature importance, model comparison |

**Target Districts:** Mandi · Kullu · Chamba (Himachal Pradesh, India)

---

## 🏗️ Architecture Overview

```
┌────────────────────────────────────────────────────────┐
│                   Next.js Frontend                     │
│           (Dashboard · Maps · Reports · Alerts)        │
└──────────────────────────┬─────────────────────────────┘
                           │  HTTPS  /  WebSocket
┌──────────────────────────▼─────────────────────────────┐
│              FastAPI Backend (Python 3.12)              │
│                                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │  Auth    │  │ Weather  │  │Predictions│             │
│  │  Router  │  │  Router  │  │  Router  │             │
│  └──────────┘  └──────────┘  └──────────┘             │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Service Layer (Business Logic)                  │  │
│  │  AuthService · WeatherService · PredictionService│  │
│  └─────────────────────┬────────────────────────────┘  │
│                        │                               │
│  ┌─────────────────────▼────────────────────────────┐  │
│  │  Repository Layer (Data Access)                  │  │
│  │  UserRepo · WeatherRepo · PredictionRepo         │  │
│  └────────┬────────────────────┬────────────────────┘  │
└───────────┼────────────────────┼────────────────────────┘
            │                    │
  ┌─────────▼──────┐   ┌─────────▼──────┐
  │  PostgreSQL 16  │   │   Redis 7.x    │
  │  (Primary DB)   │   │  (Cache / RL)  │
  └─────────────────┘   └────────────────┘
            │
  ┌─────────▼──────┐   ┌────────────────┐
  │   MinIO S3     │   │  Celery Workers │
  │  (Model Store) │   │  (Background)   │
  └─────────────────┘   └────────────────┘
```

---

## 🛠️ Technology Stack

| Layer | Technology |
|---|---|
| **Language** | Python 3.12 |
| **API Framework** | FastAPI (async, Pydantic v2) |
| **Database** | PostgreSQL 16 (asyncpg driver) |
| **ORM** | SQLAlchemy 2.0 (async, type-annotated) |
| **Migrations** | Alembic |
| **Cache / Rate Limiting** | Redis 7 (redis-py asyncio) |
| **Background Jobs** | Celery + Celery Beat |
| **Object Storage** | MinIO (S3-compatible) |
| **Observability** | OpenTelemetry + Prometheus + Grafana |
| **Logging** | Structlog (JSON) |
| **Auth** | JWT (PyJWT) + bcrypt (passlib) |
| **ML** | scikit-learn, XGBoost, LightGBM, PyTorch, ONNX |

---

## ⚡ Backend — Step-by-Step Setup Guide

### Prerequisites

Ensure you have the following installed:

- Python **3.12+**
- Docker Desktop
- `uv` or `pip`

### Step 1 — Clone & Navigate to Backend

```bash
git clone <repo-url>
cd Weather_Data_Project/backend
```

### Step 2 — Create Virtual Environment

```bash
# Using uv (recommended, fast)
pip install uv
uv venv --python 3.12
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\activate         # Windows
```

### Step 3 — Install Dependencies

```bash
uv pip install -e ".[dev]"
# or, using pip:
pip install -e ".[dev]"
```

### Step 4 — Configure Environment Variables

```bash
cp .env.example .env
# Edit .env with your values (DB password, Redis URL, secret keys etc.)
```

See [Environment Variables](#-environment-variables) section for a full reference.

### Step 5 — Start Infrastructure (Docker)

```bash
# From project root
docker-compose up -d postgres redis minio
```

Or create a minimal `docker-compose.yml` inside `/backend` if needed (see `docs/docker-compose.md`).

### Step 6 — Run Database Migrations

```bash
# Generate the first migration from your ORM models
alembic revision --autogenerate -m "initial_schema"

# Apply all pending migrations
alembic upgrade head
```

### Step 7 — Start the API Server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Visit:
- 📖 **Swagger UI** → [http://localhost:8000/docs](http://localhost:8000/docs)
- 📘 **ReDoc** → [http://localhost:8000/redoc](http://localhost:8000/redoc)
- ❤️ **Health** → [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

### Step 8 — Start Background Workers

```bash
# Celery Worker (processes tasks from queue)
celery -A app.workers.celery_app worker --loglevel=info -Q weather,agents

# Celery Beat (triggers scheduled tasks, e.g., hourly weather poll)
celery -A app.workers.celery_app beat --loglevel=info
```

---

## 📁 Project Structure

```
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── controllers/        # HTTP → Service delegation layer
│   │       │   ├── auth_controller.py
│   │       │   ├── user_controller.py
│   │       │   ├── weather_controller.py
│   │       │   └── prediction_controller.py
│   │       ├── routers/            # FastAPI router definitions
│   │       │   ├── auth_router.py
│   │       │   ├── user_router.py
│   │       │   ├── weather_router.py
│   │       │   ├── prediction_router.py
│   │       │   └── health_router.py
│   │       └── router.py           # Master v1 router aggregate
│   │
│   ├── cache/
│   │   ├── redis_client.py         # Async Redis connection pools
│   │   └── cache_manager.py        # High-level cache abstraction
│   │
│   ├── core/
│   │   ├── config.py               # Pydantic Settings singleton
│   │   ├── constants.py            # System-wide constants, RBAC
│   │   └── enums.py                # Domain enumerations
│   │
│   ├── database/
│   │   ├── base.py                 # SQLAlchemy Base + Mixins
│   │   ├── connection.py           # Async engine factory
│   │   └── session.py              # FastAPI session dependency
│   │
│   ├── dependencies/
│   │   ├── auth.py                 # JWT injection, RBAC checker
│   │   ├── repositories.py         # DB repository factories
│   │   └── services.py             # Service layer factories
│   │
│   ├── exceptions/
│   │   ├── base.py                 # AppException root class
│   │   ├── domain.py               # Domain-specific exceptions
│   │   └── handlers.py             # Global FastAPI error handlers
│   │
│   ├── integrations/
│   │   └── weather/
│   │       ├── base.py             # IWeatherProvider interface
│   │       └── open_meteo.py       # Open-Meteo API client
│   │
│   ├── logging/
│   │   └── structured_logger.py    # Structlog JSON setup
│   │
│   ├── middleware/
│   │   ├── request_id.py           # UUID injection per request
│   │   ├── timing.py               # Latency measurement
│   │   ├── request_logger.py       # Structured access log
│   │   ├── security_headers.py     # OWASP security headers
│   │   └── rate_limiter.py         # Redis sliding window
│   │
│   ├── ml/
│   │   └── inference/
│   │       ├── base.py             # IModelPredictor interface
│   │       └── rainfall_model.py   # Rainfall model stub
│   │
│   ├── models/                     # SQLAlchemy ORM models
│   │   ├── __init__.py             # Central model registry
│   │   ├── user.py
│   │   ├── auth.py
│   │   ├── weather.py
│   │   ├── prediction.py
│   │   ├── agent.py
│   │   ├── alert.py
│   │   ├── digital_twin.py
│   │   └── report.py
│   │
│   ├── monitoring/
│   │   └── metrics.py              # Prometheus metrics registry
│   │
│   ├── repositories/
│   │   ├── interfaces/             # Abstract data access contracts
│   │   └── *_impl.py               # SQLAlchemy implementations
│   │
│   ├── schemas/                    # Pydantic v2 request/response schemas
│   │   ├── common.py               # ApiResponse, Pagination
│   │   ├── auth.py
│   │   ├── user.py
│   │   ├── weather.py
│   │   └── prediction.py
│   │
│   ├── security/
│   │   └── authentication/
│   │       ├── jwt.py              # Token generation & validation
│   │       └── passwords.py        # bcrypt hashing
│   │
│   ├── services/
│   │   ├── interfaces/             # Abstract business logic contracts
│   │   ├── auth_service_impl.py
│   │   ├── user_service_impl.py
│   │   ├── weather_service_impl.py
│   │   └── prediction_service_impl.py
│   │
│   ├── tasks/
│   │   ├── weather_tasks.py        # Celery tasks: weather polling
│   │   └── agent_tasks.py          # Celery tasks: agent execution
│   │
│   ├── telemetry/
│   │   └── otel.py                 # OpenTelemetry SDK setup
│   │
│   ├── workers/
│   │   └── celery_app.py           # Celery application instance
│   │
│   └── main.py                     # FastAPI application factory
│
├── alembic/                        # Database migrations
├── alembic.ini
├── pyproject.toml                  # Dependencies & project config
└── .env.example                    # Environment variable template
```

---

## 🔌 API Reference Summary

All endpoints use the `/api/v1/` prefix and return responses in the standard envelope:

```json
{
  "success": true,
  "data": { ... },
  "message": "OK",
  "request_id": "uuid",
  "timestamp": "2025-01-01T00:00:00Z"
}
```

### Health

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/health/live` | None | Kubernetes liveness probe |
| `GET` | `/api/v1/health/ready` | None | Kubernetes readiness probe (checks DB + Redis) |
| `GET` | `/api/v1/health` | None | Detailed health report |

### Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/auth/login` | None | Login, returns JWT tokens |
| `POST` | `/api/v1/auth/logout` | Bearer | Revoke active token |

### Users

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/users/me` | Bearer | Current user profile |
| `GET` | `/api/v1/users` | Admin | Paginated user list |
| `POST` | `/api/v1/users` | Admin | Create new user |
| `PATCH` | `/api/v1/users/{id}` | Admin | Update user |
| `DELETE` | `/api/v1/users/{id}` | Admin | Soft-delete user |

### Weather

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/weather/current/{district}` | Bearer | Latest observation |
| `GET` | `/api/v1/weather/recent/{district}` | Bearer | Recent timeseries |
| `POST` | `/api/v1/weather/ingest/{district}` | Admin | Force upstream poll |

### Predictions

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/predictions/run` | Bearer | Run an ML prediction |

---

## 🔑 Environment Variables

Key variables to configure in `.env`:

| Variable | Description |
|---|---|
| `APP_ENV` | `development` / `staging` / `production` |
| `SECRET_KEY` | JWT signing secret (min 32 chars) |
| `POSTGRES_DSN` | `postgresql+asyncpg://user:pass@host/db` |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `MINIO_ENDPOINT` | `localhost:9000` |
| `OTEL_ENABLED` | `true` / `false` |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` |
| `LOG_FORMAT` | `json` (prod) / `pretty` (dev) |

See [`.env.example`](./backend/.env.example) for the full list.

---

## 🚀 Running the Backend Locally

```bash
# Quick start (all-in-one)
cd backend
uvicorn app.main:app --reload --port 8000

# With specific log level
LOG_LEVEL=DEBUG uvicorn app.main:app --reload

# Production mode (no hot reload)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## ⚙️ Running Background Workers

```bash
# Single worker with weather + agent queues
celery -A app.workers.celery_app worker -Q weather,agents --loglevel=info

# Scheduled task trigger (runs hourly weather polls etc.)
celery -A app.workers.celery_app beat --loglevel=info

# Inspect active tasks
celery -A app.workers.celery_app inspect active
```

---

## 🔄 Development Workflow

```bash
# Run tests
pytest tests/ -v --cov=app

# Lint
ruff check app/

# Format
ruff format app/

# Generate new migration
alembic revision --autogenerate -m "add_new_field"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

---

## ✅ Phase Completion Status

| Phase | Title | Status |
|---|---|---|
| **Phase 0** | Research & Data Engineering | ✅ Complete |
| **Phase 1** | Backend Architecture & Core Infrastructure | ✅ Complete |
| **Phase 2** | Database Models & ORM | ✅ Complete |
| **Phase 3** | Authentication & Security (JWT + bcrypt) | ✅ Complete |
| **Phase 4** | User Management & RBAC | ✅ Complete |
| **Phase 5** | Weather Data Pipeline & Ingestion | ✅ Complete |
| **Phase 6** | Celery Background Workers & Scheduling | ✅ Complete |
| **Phase 7** | ML Pipeline & Prediction APIs | ✅ Complete |
| **Phase 8** | Model Registry & Serving | ✅ Complete |
| **Phase 9** | Agentic AI (12 Autonomous Agents) | ✅ Complete |
| **Phase 10** | Digital Twin Framework | ✅ Complete |
| **Phase 11** | Alert & Early Warning System | ✅ Complete |
| **Phase 12** | Reporting & Notifications | ✅ Complete |
| **Phase 13** | Testing & QA | ✅ Complete |
| **Phase 14** | Deployment & Docker Compose | ✅ Complete |

---

## 👥 Contributing

This project follows **Clean Architecture** with strict SOLID principles:

- Never write business logic in routers.
- Always define an interface (`I*`) before an implementation.
- Business logic lives in `services/`, data access in `repositories/`.
- API contracts are defined in `schemas/`.

---

*Built for research in disaster risk reduction and early warning systems — Himachal Pradesh, India.*