"""
app/api/v1/routers/health_router.py
─────────────────────────────────────
Health check endpoints for Kubernetes probes, monitoring, and uptime tracking.

Endpoints:
  GET /api/v1/health/live    — Liveness probe (is the process running?)
  GET /api/v1/health/ready   — Readiness probe (can we serve traffic?)
  GET /api/v1/health         — Detailed health report (human + Grafana consumption)

Design decisions:
  • /live and /ready are separate per Kubernetes conventions.
    Liveness: if failing → kill and restart the pod.
    Readiness: if failing → remove from load balancer pool (don't kill).
  • Liveness (/live) checks ONLY that the FastAPI event loop is running.
    It never checks external dependencies — a DB outage should NOT cause
    Kubernetes to restart the app (that would make things worse).
  • Readiness (/ready) checks ALL dependencies (DB, Redis, MinIO, Celery).
    If any critical dependency is down, the pod is removed from rotation.
  • The detailed /health endpoint returns 200 even when some deps are degraded,
    since it's designed for monitoring dashboards, not K8s probes.
  • No authentication required — monitoring systems must reach these endpoints
    without credentials. Prometheus scrapes /metrics the same way.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, status
from fastapi.responses import ORJSONResponse

from app.schemas.common import DependencyHealth, HealthStatus, LivenessStatus

logger = structlog.get_logger(__name__)
router = APIRouter()

# Application start time for uptime calculation
_START_TIME = time.monotonic()


@router.get(
    "/live",
    response_model=LivenessStatus,
    status_code=status.HTTP_200_OK,
    summary="Liveness Probe",
    description=(
        "Returns 200 if the application process is alive. "
        "Used by Kubernetes liveness probes to determine if the pod should be restarted."
    ),
    tags=["Health"],
)
async def liveness_probe() -> LivenessStatus:
    """
    Liveness check — confirms the event loop is responsive.

    This endpoint should NEVER fail unless the process is dead.
    No external dependency checks.
    """
    return LivenessStatus(status="alive", timestamp=datetime.now(UTC))


@router.get(
    "/ready",
    response_class=ORJSONResponse,
    summary="Readiness Probe",
    description=(
        "Returns 200 if the application is ready to serve traffic. "
        "Checks all critical infrastructure dependencies. "
        "Returns 503 if any required dependency is unavailable."
    ),
    tags=["Health"],
    responses={
        200: {"description": "All dependencies healthy"},
        503: {"description": "One or more critical dependencies unhealthy"},
    },
)
async def readiness_probe() -> ORJSONResponse:
    """
    Readiness check — verifies all dependencies are reachable.

    Currently checks:
      - PostgreSQL (via connection pool ping)
      - Redis (via ping command)

    Additional checks (MinIO, Celery) will be added in later phases
    when those services are initialized.
    """
    dependencies: list[DependencyHealth] = []
    all_healthy = True

    # ── PostgreSQL check ───────────────────────────────────────────────────────
    try:
        from app.database.session import check_db_health
        db_start = time.perf_counter()
        db_ok = await check_db_health()
        db_latency = (time.perf_counter() - db_start) * 1000

        dependencies.append(
            DependencyHealth(
                name="postgresql",
                status="healthy" if db_ok else "unhealthy",
                latency_ms=round(db_latency, 2),
            )
        )
        if not db_ok:
            all_healthy = False
    except Exception as exc:
        logger.warning("DB health check failed", error=str(exc))
        dependencies.append(DependencyHealth(name="postgresql", status="unhealthy", details=str(exc)))
        all_healthy = False

    # ── Redis check ────────────────────────────────────────────────────────────
    try:
        from app.cache.redis_client import ping_redis
        redis_start = time.perf_counter()
        redis_ok = await ping_redis()
        redis_latency = (time.perf_counter() - redis_start) * 1000

        dependencies.append(
            DependencyHealth(
                name="redis",
                status="healthy" if redis_ok else "unhealthy",
                latency_ms=round(redis_latency, 2),
            )
        )
        if not redis_ok:
            all_healthy = False
    except Exception as exc:
        logger.warning("Redis health check failed", error=str(exc))
        dependencies.append(DependencyHealth(name="redis", status="unhealthy", details=str(exc)))
        all_healthy = False

    from app.core.config import get_settings
    settings = get_settings()

    status_str = "healthy" if all_healthy else "unhealthy"
    http_status = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return ORJSONResponse(
        status_code=http_status,
        content={
            "status": status_str,
            "version": settings.app.version,
            "environment": settings.app.env,
            "uptime_seconds": round(time.monotonic() - _START_TIME, 2),
            "dependencies": [dep.model_dump() for dep in dependencies],
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


@router.get(
    "",
    response_class=ORJSONResponse,
    summary="Detailed Health Report",
    description=(
        "Comprehensive health report for monitoring dashboards. "
        "Always returns 200 — check the 'status' field for actual health. "
        "Consumed by Grafana and operations teams."
    ),
    tags=["Health"],
)
async def health_report() -> ORJSONResponse:
    """
    Detailed health report for monitoring dashboards.

    Unlike /ready, this always returns 200 — it is designed for Grafana
    and human consumption, not K8s probes.
    """
    from app.core.config import get_settings
    settings = get_settings()

    # Gather all dependency statuses
    response = await readiness_probe()
    body = response.body
    import json
    parsed = json.loads(body)

    return ORJSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            **parsed,
            "service_name": settings.app.name,
            "api_version": "v1",
        },
    )
