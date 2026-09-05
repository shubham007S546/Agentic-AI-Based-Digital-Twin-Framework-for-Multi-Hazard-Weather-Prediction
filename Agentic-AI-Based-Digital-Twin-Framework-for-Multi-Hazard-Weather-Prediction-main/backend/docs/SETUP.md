# Backend — Step-by-Step Developer Setup Guide

This guide walks through every step to get the Weather Twin backend running from scratch.

---

## Prerequisites

| Tool | Minimum Version | Install |
|---|---|---|
| Python | 3.12+ | [python.org](https://python.org) |
| Docker Desktop | Latest | [docker.com](https://docker.com) |
| Git | Any | [git-scm.com](https://git-scm.com) |
| `uv` (optional but recommended) | Latest | `pip install uv` |

---

## Step 1 — Clone the Repository

```bash
git clone <your-repo-url>
cd Weather_Data_Project/backend
```

---

## Step 2 — Create Python Virtual Environment

```bash
# Using uv (10x faster than pip)
pip install uv
uv venv --python 3.12
```

**Activate the environment:**

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (CMD)
.venv\Scripts\activate.bat

# Linux / macOS
source .venv/bin/activate
```

You should now see `(.venv)` in your terminal prompt.

---

## Step 3 — Install All Dependencies

```bash
# Install project + dev dependencies
uv pip install -e ".[dev]"

# Alternative (standard pip)
pip install -e ".[dev]"
```

This installs:
- FastAPI, Pydantic v2, SQLAlchemy 2.0, asyncpg
- Redis, Celery, Structlog, OpenTelemetry
- PyJWT, passlib, httpx
- pytest, ruff, mypy (dev tools)

---

## Step 4 — Configure Environment Variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

```dotenv
# Minimum required for local development
APP_ENV=development
SECRET_KEY=change-this-to-a-long-random-string-minimum-32-chars

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=weather_twin_db
POSTGRES_USER=weather_user
POSTGRES_PASSWORD=weather_pass

REDIS_URL=redis://localhost:6379/0
```

---

## Step 5 — Start Infrastructure with Docker

Create a `docker-compose.yml` in the `backend/` folder (or use the one in the project root):

```yaml
# backend/docker-compose.dev.yml
version: "3.9"
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: weather_twin_db
      POSTGRES_USER: weather_user
      POSTGRES_PASSWORD: weather_pass
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"

volumes:
  postgres_data:
```

```bash
# Start all services
docker-compose -f docker-compose.dev.yml up -d

# Verify they are running
docker-compose -f docker-compose.dev.yml ps
```

---

## Step 6 — Initialize the Database

```bash
# Generate the initial migration from your ORM models
alembic revision --autogenerate -m "initial_schema"

# Apply all pending migrations to the database
alembic upgrade head
```

Verify tables were created:
```bash
docker exec -it <postgres_container_name> psql -U weather_user -d weather_twin_db -c "\dt"
```

---

## Step 7 — Start the API Server

```bash
# Development mode (hot reload on code changes)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Alternatively, using the pyproject.toml script
python -m uvicorn app.main:app --reload
```

**Verify it works:**

```bash
curl http://localhost:8000/api/v1/health/live
# Should return: {"status": "alive", "timestamp": "..."}

curl http://localhost:8000/api/v1/health/ready
# Should return all dependencies as "healthy"
```

**Open the Interactive API Docs:**
- Swagger UI → [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc → [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## Step 8 — Start Background Workers

Open **two separate terminals** (with `.venv` activated in each):

**Terminal A — Celery Worker:**
```bash
celery -A app.workers.celery_app worker --loglevel=info -Q weather,agents
```

**Terminal B — Celery Beat Scheduler:**
```bash
celery -A app.workers.celery_app beat --loglevel=info
```

The Beat scheduler will trigger `poll_all_weather` every hour automatically.

**Optional — Flower (Celery monitoring dashboard):**
```bash
pip install flower
celery -A app.workers.celery_app flower --port=5555
# Open http://localhost:5555
```

---

## Step 9 — (Optional) Test a Prediction

First, create a user and get a token:

```bash
# Create admin user (run this in Python shell or add a seed script)
# For now, use the POST /api/v1/users endpoint in Swagger UI

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "adminpass123"}'
```

Then run a prediction:
```bash
curl -X POST http://localhost:8000/api/v1/predictions/run \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "district": "MANDI",
    "hazard_type": "RAINFALL",
    "prediction_type": "ONLINE"
  }'
```

---

## Common Issues & Fixes

### `ModuleNotFoundError: No module named 'app'`
Make sure you installed in editable mode:
```bash
pip install -e ".[dev]"
```

### `sqlalchemy.exc.OperationalError: connection refused`
PostgreSQL is not running. Start it:
```bash
docker-compose -f docker-compose.dev.yml up -d postgres
```

### `redis.exceptions.ConnectionError`
Redis is not running:
```bash
docker-compose -f docker-compose.dev.yml up -d redis
```

### `alembic.util.exc.CommandError: Target database is not up to date`
Run: `alembic upgrade head`

### Celery worker not picking up tasks
Check that the `REDIS_URL` in `.env` matches the running Redis instance. Also ensure the worker is started with the correct queue names: `-Q weather,agents`.

---

## Running the Full Test Suite

```bash
# All tests
pytest tests/ -v

# Unit tests only (no DB/Redis required)
pytest tests/unit/ -v

# With coverage report
pytest tests/ --cov=app --cov-report=html
open htmlcov/index.html
```
