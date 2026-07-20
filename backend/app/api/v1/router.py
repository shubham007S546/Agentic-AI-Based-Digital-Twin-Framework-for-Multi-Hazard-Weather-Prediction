"""
app/api/v1/router.py
──────────────────────
Master API router for v1 — aggregates all domain routers.

Design decisions:
  • Each domain router is imported here and included with its own prefix and tags.
    This is the ONLY place that knows about all routers — adding a new domain
    means adding two lines here (import + include_router).
  • Tags are used for Swagger grouping — each domain gets its own section.
  • All v1 routes are prefixed with /api/v1 (set in main.py when this router is
    included — not here, to keep this file clean).
  • Placeholder routers are imported as comments during Phase 1. They will be
    replaced with real implementations in their respective phases.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routers.health_router import router as health_router

from app.api.v1.routers.auth_router import router as auth_router

from app.api.v1.routers.user_router import router as users_router
from app.api.v1.routers.weather_router import router as weather_router
from app.api.v1.routers.prediction_router import router as prediction_router
from app.api.v1.routers.twin_router import router as twin_router
from app.api.v1.routers.alert_router import router as alert_router
from app.api.v1.routers.report_router import router as report_router
from app.api.v1.routers.models_router import router as models_router
from app.api.v1.routers.notification_router import router as notification_router
from app.api.v1.routers.agents_router import router as agents_router

# ── Aggregate router ──────────────────────────────────────────────────────────
# This is the single router included in main.py under the /api/v1 prefix.
api_v1_router = APIRouter()

# ── Health & Monitoring (always available — no auth required) ─────────────────
api_v1_router.include_router(health_router, prefix="/health", tags=["Health"])

# ── Authentication (Phase 3) ──────────────────────────────────────────────────
api_v1_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])


# ── Users (Phase 4) ──────────────────────────────────────────────────────────
api_v1_router.include_router(users_router, prefix="/users", tags=["Users"])

# ── Weather Data Pipeline (Phase 5) ──────────────────────────────────────────
api_v1_router.include_router(weather_router, prefix="/weather", tags=["Weather"])

# ── Prediction APIs (Phase 7) ─────────────────────────────────────────────────
api_v1_router.include_router(prediction_router, prefix="/predictions", tags=["Predictions"])

# ── Digital Twin (Phase 10) ───────────────────────────────────────────────────
api_v1_router.include_router(twin_router, prefix="/twin", tags=["Digital Twin"])

# ── Model Registry (Phase 8) ─────────────────────────────────────────────────
api_v1_router.include_router(models_router, prefix="/models", tags=["Model Registry"])

# ── Agentic AI (Phase 9) ──────────────────────────────────────────────────────
api_v1_router.include_router(agents_router, prefix="/agents", tags=["AI Agents"])

# ── Alerts & Hazards (Phase 11) ───────────────────────────────────────────────
api_v1_router.include_router(alert_router, prefix="/alerts", tags=["Alerts & Hazards"])

# ── Reports (Phase 12) ────────────────────────────────────────────────────────
api_v1_router.include_router(report_router, prefix="/reports", tags=["Reports"])

# ── Notifications (Phase 12) ──────────────────────────────────────────────────
api_v1_router.include_router(notification_router, prefix="/notifications", tags=["Notifications"])

# ── GIS / Maps ────────────────────────────────────────────────────────────────
# api_v1_router.include_router(gis_router, prefix="/gis", tags=["GIS & Maps"])
