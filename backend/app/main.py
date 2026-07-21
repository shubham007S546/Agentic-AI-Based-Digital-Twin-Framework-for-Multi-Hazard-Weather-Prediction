"""
app/main.py
────────────
FastAPI Application Factory.

Design decisions:
  • Factory pattern (create_application()) instead of a module-level app object.
    Benefits:
    1. Testable — tests can call create_application() with overridden settings.
    2. No circular imports — routers import from app, not the other way.
    3. Enables multiple app instances in the same process (e.g., multi-tenant).

  • Async lifespan context manager (not deprecated @app.on_event).
    The lifespan handles startup/shutdown of:
    - Database connection pool
    - Redis connection pools
    - OpenTelemetry SDK
    - Model registry warm-loading
    - Agent registry initialization

  • Middleware registration ORDER is critical (Starlette processes middleware
    in LIFO order — last registered = outermost = first to execute):
    1. GZipMiddleware          (outermost — compresses all responses)
    2. TrustedHostMiddleware   (reject unknown hosts early)
    3. SecurityHeadersMiddleware
    4. CORSMiddleware
    5. RequestIDMiddleware     (must be early so all others see request_id)
    6. TimingMiddleware
    7. RequestLoggerMiddleware (innermost — has access to full context)

  • Exception handlers are registered BEFORE middleware so they are invoked
    regardless of where an exception propagates to.

  • ORJSONResponse is set as the default response class for 2-5x JSON
    serialization speedup vs stdlib json (critical for prediction endpoints
    returning large numpy arrays).

  • OpenAPI customization provides rich documentation for the research paper
    audience and future API consumers.
"""

from __future__ import annotations

import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

# Ensure the backend can import the RAG_project package located at the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import ORJSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.router import api_v1_router
from app.cache.redis_client import close_redis_pools, init_redis_pools
from app.core.config import get_settings
from app.core.constants import (
    API_V1_PREFIX,
    DOCS_URL,
    METRICS_URL,
    OPENAPI_URL,
    REDOC_URL,
)
from app.exceptions.handlers import register_exception_handlers
from app.logging.structured_logger import setup_logging
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.request_logger import RequestLoggerMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.timing import TimingMiddleware
from app.monitoring.metrics import APP_INFO, DEPENDENCY_HEALTH
from app.telemetry.otel import (
    instrument_fastapi,
    instrument_httpx,
    instrument_redis,
    setup_telemetry,
    shutdown_telemetry,
)

logger = structlog.get_logger(__name__)

# Track application start time for uptime metrics
_APP_START_TIME = time.monotonic()


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Everything before yield = startup.
    Everything after yield = shutdown.

    This replaces the deprecated @app.on_event("startup") pattern.
    Using async context manager ensures proper cleanup even on exceptions.
    """
    settings = get_settings()

    logger.info(
        "Starting Weather Twin Backend",
        version=settings.app.version,
        environment=settings.app.env,
        pid=__import__("os").getpid(),
    )

    # ── 1. Initialize Redis connection pools ──────────────────────────────────
    try:
        init_redis_pools()
        DEPENDENCY_HEALTH.labels(dependency="redis").set(1)
        logger.info("Redis pools initialized")
    except Exception as exc:
        DEPENDENCY_HEALTH.labels(dependency="redis").set(0)
        logger.error("Redis pool initialization failed", error=str(exc))
        # Non-fatal in development; fatal in production
        if settings.app.is_production:
            raise

    # ── 2. Initialize Database connection pool ────────────────────────────────
    try:
        from app.database.connection import init_db_engine
        await init_db_engine()
        DEPENDENCY_HEALTH.labels(dependency="postgresql").set(1)
        logger.info("Database engine initialized")
    except Exception as exc:
        DEPENDENCY_HEALTH.labels(dependency="postgresql").set(0)
        logger.error("Database initialization failed", error=str(exc))
        if settings.app.is_production:
            raise

    # ── 3. Run pending Alembic migrations (optional, controlled by flag) ──────
    # In production, migrations should be run by a separate init container.
    # In development, auto-migrate for convenience.
    # (Implemented in Phase 2)

    # ── 4. Initialize OpenTelemetry SDK ───────────────────────────────────────
    try:
        setup_telemetry(
            service_name=settings.otel.service_name,
            service_version=settings.otel.service_version,
            environment=settings.app.env,
            otlp_endpoint=settings.otel.exporter_otlp_endpoint,
            enabled=settings.otel.enabled,
        )
        instrument_redis()
        instrument_httpx()
        logger.info("OpenTelemetry initialized")
    except Exception as exc:
        logger.warning("OpenTelemetry initialization failed (non-fatal)", error=str(exc))

    # ── 5. Set Prometheus app info labels ────────────────────────────────────
    APP_INFO.info(
        {
            "version": settings.app.version,
            "environment": settings.app.env,
            "python_version": __import__("sys").version,
        }
    )

    # ── 6. Seed and warm-load the Model Registry ──────────────────────────────
    try:
        from app.ml.models_registry.registry import get_model_registry
        from app.ml.serving.model_loader import seed_model_registry
        registry = get_model_registry()
        seed_model_registry(registry)
        await registry.warm_load_all()
        logger.info("Model registry ready")
    except Exception as exc:
        logger.warning("Model registry initialization failed (non-fatal)", error=str(exc))

    # ── 7. Initialize Agent Registry — all 12 agents ─────────────────────────
    try:
        from app.agents.agent_registry import get_agent_registry

        # Existing agents (fixed enum names)
        from app.agents.weather_agent import WeatherAgent
        from app.agents.prediction_agent import PredictionAgent
        from app.agents.alert_agent import AlertAgent
        from app.agents.report_agent import ReportAgent
        from app.agents.notification_agent import NotificationAgent

        # New agents
        from app.agents.disaster_intelligence_agent import DisasterIntelligenceAgent
        from app.agents.digital_twin_agent import DigitalTwinAgent
        from app.agents.monitoring_agent import MonitoringAgent
        from app.agents.data_collection_agent import DataCollectionAgent
        from app.agents.research_agent import ResearchAgent
        from app.agents.explainability_agent import ExplainabilityAgent
        from app.agents.decision_support_agent import DecisionSupportAgent

        agent_mgr = get_agent_registry()

        # Register all 12 agents (order matches AgentName enum)
        agent_mgr.register(WeatherAgent())            # WEATHER_INTELLIGENCE
        agent_mgr.register(PredictionAgent())         # PREDICTION
        agent_mgr.register(AlertAgent())              # ALERT
        agent_mgr.register(DisasterIntelligenceAgent())  # DISASTER_INTELLIGENCE
        agent_mgr.register(DigitalTwinAgent())        # DIGITAL_TWIN
        agent_mgr.register(ReportAgent())             # REPORT_GENERATOR
        agent_mgr.register(NotificationAgent())       # NOTIFICATION
        agent_mgr.register(MonitoringAgent())         # MONITORING
        agent_mgr.register(DataCollectionAgent())     # DATA_COLLECTION
        agent_mgr.register(ResearchAgent())           # RESEARCH
        agent_mgr.register(ExplainabilityAgent())     # EXPLAINABILITY
        agent_mgr.register(DecisionSupportAgent())    # DECISION_SUPPORT

        logger.info("Agent registry ready", total_agents=len(agent_mgr.list_agents()))
    except Exception as exc:
        logger.warning("Agent registry initialization failed (non-fatal)", error=str(exc))

    logger.info(
        "Weather Twin Backend startup complete",
        startup_time_ms=round((time.monotonic() - _APP_START_TIME) * 1000, 2),
    )

    # ── Serve requests ────────────────────────────────────────────────────────
    yield

    # ── Shutdown sequence ────────────────────────────────────────────────────

    logger.info("Initiating graceful shutdown...")

    # Close database connections
    try:
        from app.database.connection import close_db_engine
        await close_db_engine()
        logger.info("Database connections closed")
    except Exception as exc:
        logger.warning("Database shutdown error", error=str(exc))

    # Close Redis pools
    try:
        await close_redis_pools()
        logger.info("Redis connections closed")
    except Exception as exc:
        logger.warning("Redis shutdown error", error=str(exc))

    # Flush OpenTelemetry spans
    try:
        shutdown_telemetry()
    except Exception as exc:
        logger.warning("Telemetry shutdown error", error=str(exc))

    logger.info("Weather Twin Backend shutdown complete")


# ── Application factory ───────────────────────────────────────────────────────

def create_application() -> FastAPI:
    """
    Build and configure the FastAPI application.

    This is called once at process start from the entry point (uvicorn).
    In tests, call this with test settings to get an isolated test app.
    """
    settings = get_settings()

    # ── 1. Configure structured logging (must be first) ──────────────────────
    setup_logging(
        level=settings.logging.level,
        use_json=settings.logging.format == "json",
    )

    # ── 2. Create FastAPI instance ────────────────────────────────────────────
    app = FastAPI(
        title="Weather Twin Backend API",
        description=_get_api_description(),
        version=settings.app.version,
        docs_url=DOCS_URL if not settings.app.is_production else None,
        redoc_url=REDOC_URL if not settings.app.is_production else None,
        openapi_url=OPENAPI_URL if not settings.app.is_production else None,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        contact={
            "name": "Weather Twin Platform",
            "email": "platform@weather-twin.ai",
        },
        license_info={
            "name": "MIT",
        },
        openapi_tags=_get_openapi_tags(),
    )

    # ── 3. Register exception handlers ───────────────────────────────────────
    register_exception_handlers(app)

    # ── 4. Register middleware (LIFO order — last added = outermost) ──────────
    # Innermost middleware (registered first, executed last):
    app.add_middleware(RequestLoggerMiddleware)
    app.add_middleware(TimingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, is_production=settings.app.is_production)

    # CORS must be early in the chain to handle preflight OPTIONS requests
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.security.allowed_origins,
        allow_credentials=settings.security.allow_credentials,
        allow_methods=settings.security.allowed_methods,
        allow_headers=settings.security.allowed_headers,
        expose_headers=[
            "X-Request-ID",
            "X-Process-Time",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ],
    )

    # Outermost middleware (registered last, executed first):
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.security.allowed_hosts,
    )
    app.add_middleware(
        GZipMiddleware,
        minimum_size=1000,   # Only compress responses > 1KB
        compresslevel=6,     # Balance between speed and compression ratio
    )

    # ── 5. Register Rate Limiter (requires Redis — added after pool init) ─────
    # Rate limiter is added as a dependency on specific routers (Phase 3+)
    # rather than as global middleware to allow per-endpoint configuration.

    # ── 6. Register API routers ───────────────────────────────────────────────
    app.include_router(api_v1_router, prefix=API_V1_PREFIX)

    # ── 7. Register Prometheus metrics endpoint ───────────────────────────────
    if settings.app.env != "test":
        Instrumentator(
            should_group_status_codes=True,
            should_ignore_untemplated=True,
            should_respect_env_var=False,
            excluded_handlers=["/metrics", "/api/v1/health/live"],
        ).instrument(app).expose(app, endpoint=METRICS_URL, include_in_schema=False)

    # ── 8. Instrument FastAPI with OpenTelemetry ──────────────────────────────
    # Done here after app creation, before it starts serving
    if settings.otel.enabled and settings.app.env != "test":
        instrument_fastapi(app)

    logger.info("FastAPI application created", env=settings.app.env)
    return app


# ── OpenAPI customization ─────────────────────────────────────────────────────

def _get_api_description() -> str:
    return """
## Agentic AI-Based Digital Twin Framework

Enterprise-grade backend for **Rainfall Prediction and Extreme Weather Intelligence**
in Himachal Pradesh (Mandi, Kullu, Chamba districts).

### Capabilities

- 🌧️ **Multi-source Weather Data** — IMD, ERA5, NASA GPM, Open-Meteo, MODIS
- 🤖 **12 AI Agents** — Weather, Prediction, Alert, Digital Twin, Report, and more
- 🧠 **7 ML Models** — Random Forest, XGBoost, LightGBM, LSTM, CNN-LSTM, Transformer, TFT
- 🌍 **Digital Twin** — Simulation, Scenario, Replay, Risk Assessment
- 🚨 **Early Warning** — Cloudburst, Landslide, Flash Flood alerts
- 📊 **Research Analytics** — Explainability, Feature importance, Model comparison

### Authentication

All endpoints (except health and public weather) require a **Bearer JWT token**.

```
Authorization: Bearer <access_token>
```

Get tokens via `POST /api/v1/auth/login`.

### Error Format

All errors follow a consistent structure:
```json
{
  "success": false,
  "error": {
    "code": "AUTH_001",
    "message": "Authentication failed.",
    "details": {}
  },
  "request_id": "uuid-here",
  "timestamp": "2025-01-01T00:00:00Z"
}
```
"""


def _get_openapi_tags() -> list[dict]:
    return [
        {"name": "Health", "description": "Liveness, readiness, and health probes"},
        {"name": "Authentication", "description": "JWT login, refresh, logout, password reset"},
        {"name": "Users", "description": "User management and RBAC administration"},
        {"name": "Weather", "description": "Real-time and historical weather data"},
        {"name": "Predictions", "description": "AI model predictions for rainfall, cloudbursts, and landslides"},
        {"name": "Model Registry", "description": "ML model registration, versioning, and serving"},
        {"name": "AI Agents", "description": "Agentic AI system — registry, scheduling, and execution"},
        {"name": "Digital Twin", "description": "Simulation engine, scenario runner, and risk assessment"},
        {"name": "Alerts & Hazards", "description": "Hazard alerts and early warning system"},
        {"name": "Reports", "description": "PDF and HTML report generation"},
        {"name": "Notifications", "description": "Multi-channel notification system"},
        {"name": "GIS & Maps", "description": "Geospatial data, district boundaries, and satellite layers"},
    ]


# ── Entry point ───────────────────────────────────────────────────────────────
# The `app` object is what uvicorn imports.
# uvicorn app.main:app --host 0.0.0.0 --port 8000

app = create_application()
