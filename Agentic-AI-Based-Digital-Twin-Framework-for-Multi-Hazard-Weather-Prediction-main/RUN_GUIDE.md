# 🚀 Running the Project Locally (Windows)

> Quick start guide for the **Agentic AI Digital Twin Framework**.

---

## Prerequisites

| Tool           | Required Version | Check Command        |
|----------------|-----------------|----------------------|
| Python         | 3.12+           | `python --version`   |
| Node.js        | 18+             | `node --version`     |
| pnpm           | 9+              | `pnpm --version`     |
| Docker Desktop | Latest          | `docker --version`   |
| pip            | Latest          | `pip --version`      |

> **Important**: Make sure **Docker Desktop is running** before starting.

---

## 1️⃣ Start Infrastructure (PostgreSQL + Redis + MinIO)

```powershell
cd backend
docker compose up -d
```

Verify all containers are healthy:
```powershell
docker compose ps
```

| Service    | Port        | Credentials                  |
|------------|-------------|------------------------------|
| PostgreSQL | `5432`      | `postgres` / `password`      |
| Redis      | `6379`      | no auth                      |
| MinIO      | `9000/9001` | `minioadmin` / `minioadmin123` |

---

## 2️⃣ Start the Backend (FastAPI)

```powershell
# From project root
cd backend

# Create virtual environment (first time only)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies (first time only)
pip install -r requirements.txt

# Run database migrations
python -m alembic upgrade head

# Start the server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Verify
- API Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/api/v1/health/live

---

## 3️⃣ Start the Frontend (Next.js)

Open a **new terminal**:

```powershell
# From project root
cd frontend

# Install dependencies (first time only)
pnpm install

# Start the dev server
pnpm dev
```

### Verify
- Dashboard: http://localhost:3000

---

## 🧹 Stopping Everything

```powershell
# Stop frontend: Ctrl+C in the frontend terminal
# Stop backend: Ctrl+C in the backend terminal

# Stop infrastructure
cd backend
docker compose down

# To also delete all data volumes:
docker compose down -v
```

---

## 🔧 Troubleshooting

### "Docker daemon is not running"
→ Open Docker Desktop app and wait for it to fully start.

### "Connection refused" on port 5432/6379
→ Run `docker compose ps` to check container health. Restart with `docker compose down && docker compose up -d`.

### Backend import errors
→ Make sure the virtual environment is activated: `.\.venv\Scripts\Activate.ps1`

### Alembic migration fails
→ Ensure PostgreSQL is running and the `DATABASE_URL` in `.env` matches Docker Compose credentials.

### Frontend build errors
→ Delete `node_modules` and reinstall: `Remove-Item -Recurse node_modules; pnpm install`

---

## 📁 Environment Files

| File | Purpose |
|------|---------|
| `backend/.env` | Backend config (DB, Redis, JWT, etc.) |
| `config/config.yaml` | Data collection config |
| `weather_analysis_agent/agents/weather_analysis/.env` | Weather agent config |
| `report_agent/agents/report/.env` | Report agent config |
