# ──────────────────────────────────────────────────────────────────────────────
# Dockerfile — Enterprise multi-stage build for FastAPI backend
# ──────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Base & Dependency Resolution ─────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /build

# Install uv for blazingly fast dependency resolution
RUN pip install uv

# Copy only what's needed for dependency resolution
COPY pyproject.toml .

# Install dependencies into the system python (safe in builder image)
RUN uv pip install -e ".[production]"

# ── Stage 2: Production Image ─────────────────────────────────────────────────
FROM python:3.12-slim AS production

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production \
    PYTHONPATH=/app

WORKDIR /app

# Install runtime dependencies (e.g., for psycopg2/asyncpg if needed natively)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy python dependencies from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy application code
COPY alembic.ini .
COPY alembic/ ./alembic/
COPY app/ ./app/

# Create a non-root user for security
RUN groupadd -r appgroup && useradd -r -g appgroup appuser \
    && chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

# Healthcheck maps to the Kubernetes liveness probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/live || exit 1

# Start Uvicorn with Gunicorn process manager (production standard)
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--proxy-headers", "--forwarded-allow-ips", "*"]
