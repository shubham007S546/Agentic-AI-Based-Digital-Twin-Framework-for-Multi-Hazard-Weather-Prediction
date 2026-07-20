# Backend API Documentation

## Overview

The `backend/` directory contains the enterprise-grade FastAPI application for the Weather Twin platform.

---

## Quick Start

```bash
cd backend
pip install uv && uv venv --python 3.12
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
cp .env.example .env        # Edit with your settings
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Visit [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Application Layers

```
Request
   │
   ├──▶  Middleware Stack (Security, Rate Limit, Timing, Logging)
   │
   ├──▶  Router (FastAPI endpoint definitions — thin, no logic)
   │
   ├──▶  Controller (HTTP ↔ Service bridge, input extraction)
   │
   ├──▶  Service (Business logic, domain rules, orchestration)
   │
   ├──▶  Repository (Database queries only — no business logic)
   │
   └──▶  ORM Model (SQLAlchemy mapped table)
```

---

## Architecture Decisions

### 1. Application Factory (`app/main.py`)
The `create_application()` factory builds the FastAPI app on demand. This enables:
- Isolated test instances via `TestClient(create_application())`
- Multiple configuration environments without code changes

### 2. Middleware Ordering
Starlette processes middleware in **LIFO** (last registered = outermost). The order is:
```
GZip → TrustedHost → SecurityHeaders → CORS → RequestID → Timing → RequestLogger
```

### 3. Dependency Injection
All dependencies flow through FastAPI's `Depends()`:
```
Router → Controller → Service → Repository → DB Session
```
This makes every component independently testable with mocked dependencies.

### 4. Exception Strategy
Every domain error raises a typed `AppException` subclass with a machine-readable `error_code` (e.g., `AUTH_001`). A single global handler converts them to the standard JSON envelope.

### 5. Stateless Auth
JWT access tokens are validated entirely in memory + Redis (blacklist check). No Postgres hit per authenticated request means sub-millisecond auth overhead.

---

## Running Tests

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests (requires running DB + Redis)
pytest tests/integration/ -v

# Full suite with coverage
pytest tests/ --cov=app --cov-report=html
```

---

## Database Migrations

```bash
# Create a new migration from model changes
alembic revision --autogenerate -m "add_simulation_results_column"

# Apply to latest
alembic upgrade head

# View migration history
alembic history

# Rollback one step
alembic downgrade -1
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `APP_ENV` | Yes | `development` | Environment name |
| `APP_NAME` | No | `weather-twin-backend` | Service name |
| `APP_VERSION` | No | `0.1.0` | Version tag |
| `SECRET_KEY` | Yes | — | JWT secret (min 32 chars) |
| `ALGORITHM` | No | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `30` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh token lifetime |
| `POSTGRES_HOST` | Yes | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | No | `5432` | PostgreSQL port |
| `POSTGRES_DB` | Yes | — | Database name |
| `POSTGRES_USER` | Yes | — | Database user |
| `POSTGRES_PASSWORD` | Yes | — | Database password |
| `REDIS_URL` | Yes | `redis://localhost:6379/0` | Redis connection URL |
| `MINIO_ENDPOINT` | No | `localhost:9000` | MinIO S3 endpoint |
| `OTEL_ENABLED` | No | `false` | Enable OpenTelemetry |
| `LOG_LEVEL` | No | `INFO` | Log verbosity |
| `LOG_FORMAT` | No | `json` | `json` or `pretty` |
| `ALLOWED_ORIGINS` | No | `*` | CORS allowed origins |

---

## Celery Workers

```bash
# Worker (processes tasks from queues)
celery -A app.workers.celery_app worker -Q weather,agents --loglevel=info

# Scheduler (triggers periodic tasks)
celery -A app.workers.celery_app beat --loglevel=info

# Monitoring dashboard (Flower)
pip install flower
celery -A app.workers.celery_app flower --port=5555
```

---

## Observability

| Tool | URL | Purpose |
|---|---|---|
| Swagger UI | http://localhost:8000/docs | Interactive API explorer |
| Prometheus Metrics | http://localhost:8000/metrics | Raw metrics scrape |
| Health Check | http://localhost:8000/api/v1/health | Dependency health |
| Jaeger (Tracing) | http://localhost:16686 | Distributed traces |
| Grafana | http://localhost:3000 | Dashboards |
