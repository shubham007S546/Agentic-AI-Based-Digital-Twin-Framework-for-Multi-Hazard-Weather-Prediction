"""
app/core/constants.py
─────────────────────
System-wide constants and RBAC permission matrices.

Design decisions:
  • All magic numbers and strings live here — no hardcoded values in logic.
  • The ROLE_PERMISSIONS matrix is the single source of truth for authorization.
    Services and middleware reference this dict; no permission logic is scattered.
  • District geo-metadata is stored here so collectors, APIs, and the digital
    twin all use the same coordinates.
  • Token and security constants are centralized to make rotation easy.
"""

from __future__ import annotations

from app.core.enums import District, Permission, UserRole

# ── Application ───────────────────────────────────────────────────────────────

API_V1_PREFIX = "/api/v1"
API_V2_PREFIX = "/api/v2"
DOCS_URL = "/docs"
REDOC_URL = "/redoc"
OPENAPI_URL = "/openapi.json"
HEALTH_URL = "/api/v1/health"
METRICS_URL = "/metrics"

# Request ID header injected by middleware
REQUEST_ID_HEADER = "X-Request-ID"
PROCESS_TIME_HEADER = "X-Process-Time"
VERSION_HEADER = "X-API-Version"

# ── Security ──────────────────────────────────────────────────────────────────

# Minimum bcrypt work factor — NIST SP 800-132 recommends ≥ 10
BCRYPT_ROUNDS = 12

# JWT claim names (custom)
JWT_CLAIM_ROLE = "role"
JWT_CLAIM_PERMISSIONS = "perms"
JWT_CLAIM_JTI = "jti"

# Max failed login attempts before account lock
MAX_LOGIN_ATTEMPTS = 5
ACCOUNT_LOCK_MINUTES = 15

# Password reset token TTL
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 30

# Email verification token TTL
EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS = 24

# Rate limit key prefix in Redis
RATE_LIMIT_KEY_PREFIX = "rl:"

# Token blacklist key prefix in Redis
TOKEN_BLACKLIST_PREFIX = "bl:"

# Refresh token cache key prefix
REFRESH_TOKEN_PREFIX = "rt:"

# ── RBAC Permission Matrix ────────────────────────────────────────────────────
# Maps each role to the frozenset of permissions it carries.
# Design: additive model — roles grant permissions, not deny them.
# Super Admin has every permission; lower roles have subsets.
# This matrix is the ONLY place permissions are defined — services import it.

_PUBLIC_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.WEATHER_READ,
        Permission.PREDICTION_READ,
        Permission.ALERT_READ,
        Permission.REPORT_READ,
        Permission.DIGITAL_TWIN_READ,
    }
)

_GOVERNMENT_AUTHORITY_PERMISSIONS: frozenset[Permission] = _PUBLIC_PERMISSIONS | frozenset(
    {
        Permission.ALERT_ACKNOWLEDGE,
        Permission.PREDICTION_CREATE,
        Permission.PREDICTION_EXPLAIN,
        Permission.AGENT_READ,
        Permission.DIGITAL_TWIN_SIMULATE,
        Permission.SYSTEM_HEALTH,
    }
)

_DISASTER_OFFICER_PERMISSIONS: frozenset[Permission] = _GOVERNMENT_AUTHORITY_PERMISSIONS | frozenset(
    {
        Permission.ALERT_CREATE,
        Permission.REPORT_CREATE,
        Permission.PREDICTION_BATCH,
        Permission.MODEL_READ,
    }
)

_RESEARCHER_PERMISSIONS: frozenset[Permission] = _DISASTER_OFFICER_PERMISSIONS | frozenset(
    {
        Permission.ALERT_MANAGE,
        Permission.REPORT_DELETE,
        Permission.MODEL_LOAD,
        Permission.WEATHER_WRITE,
        Permission.AGENT_READ,
        Permission.AGENT_TRIGGER,
        Permission.DIGITAL_TWIN_MANAGE,
        Permission.METRICS_READ,
        Permission.AUDIT_READ,
    }
)

_ADMIN_PERMISSIONS: frozenset[Permission] = _RESEARCHER_PERMISSIONS | frozenset(
    {
        Permission.USER_READ,
        Permission.USER_CREATE,
        Permission.USER_UPDATE,
        Permission.USER_DELETE,
        Permission.MODEL_UNLOAD,
        Permission.MODEL_RETRAIN,
        Permission.AGENT_MANAGE,
        Permission.WEATHER_DELETE,
        Permission.ADMIN_PANEL,
    }
)

_SUPER_ADMIN_PERMISSIONS: frozenset[Permission] = frozenset(Permission)  # All permissions

ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.PUBLIC: _PUBLIC_PERMISSIONS,
    UserRole.GOVERNMENT_AUTHORITY: _GOVERNMENT_AUTHORITY_PERMISSIONS,
    UserRole.DISASTER_OFFICER: _DISASTER_OFFICER_PERMISSIONS,
    UserRole.RESEARCHER: _RESEARCHER_PERMISSIONS,
    UserRole.ADMIN: _ADMIN_PERMISSIONS,
    UserRole.SUPER_ADMIN: _SUPER_ADMIN_PERMISSIONS,
}

# ── Geographic Constants (Himachal Pradesh) ───────────────────────────────────

DISTRICT_METADATA: dict[str, dict] = {
    District.MANDI: {
        "name": "Mandi",
        "state": "Himachal Pradesh",
        "country": "India",
        "latitude": 31.7081,
        "longitude": 76.9318,
        "bbox": {
            "lat_min": 31.35,
            "lat_max": 32.10,
            "lon_min": 76.50,
            "lon_max": 77.50,
        },
        "elevation_m": 850,
        "area_sq_km": 3950,
        "population_2011": 999518,
        "hazard_zones": ["cloudburst", "landslide", "flash_flood"],
    },
    District.KULLU: {
        "name": "Kullu",
        "state": "Himachal Pradesh",
        "country": "India",
        "latitude": 31.9579,
        "longitude": 77.1095,
        "bbox": {
            "lat_min": 31.45,
            "lat_max": 32.45,
            "lon_min": 76.70,
            "lon_max": 77.85,
        },
        "elevation_m": 1219,
        "area_sq_km": 5503,
        "population_2011": 437474,
        "hazard_zones": ["cloudburst", "landslide", "flash_flood", "snowfall"],
    },
    District.CHAMBA: {
        "name": "Chamba",
        "state": "Himachal Pradesh",
        "country": "India",
        "latitude": 32.5533,
        "longitude": 76.1258,
        "bbox": {
            "lat_min": 32.00,
            "lat_max": 33.30,
            "lon_min": 75.70,
            "lon_max": 76.80,
        },
        "elevation_m": 996,
        "area_sq_km": 6528,
        "population_2011": 518844,
        "hazard_zones": ["cloudburst", "landslide", "snowfall"],
    },
}

# ── Weather Thresholds (IMD / NDMA standards) ─────────────────────────────────
# Source: IMD District Forecast Guidelines, NDMA Guidelines 2020

RAINFALL_THRESHOLDS_MM: dict[str, float] = {
    "light": 2.5,           # < 2.5 mm/hr = light rain
    "moderate": 7.5,        # 2.5–7.5 mm/hr = moderate
    "heavy": 35.5,          # 7.5–35.5 mm/hr = heavy
    "very_heavy": 64.5,     # 35.5–64.5 mm/hr = very heavy
    "extremely_heavy": 124.4,  # 64.5–124.4 mm/hr = extremely heavy
    "cloudburst": 100.0,    # > 100 mm in 3 hours = cloudburst (IMD definition)
}

FLASH_FLOOD_THRESHOLD_MM_24H: float = 150.0   # mm in 24h triggers flash flood watch
LANDSLIDE_RAINFALL_THRESHOLD_MM_24H: float = 80.0  # mm in 24h + slope > 30° = high risk

# ── Celery Queue Names ────────────────────────────────────────────────────────

CELERY_QUEUE_DEFAULT = "default"
CELERY_QUEUE_EMAIL = "email"
CELERY_QUEUE_PREDICTION = "prediction"
CELERY_QUEUE_REPORTS = "reports"
CELERY_QUEUE_AGENTS = "agents"
CELERY_QUEUE_WEATHER = "weather"
CELERY_QUEUE_NOTIFICATIONS = "notifications"

# ── Cache TTLs (seconds) ──────────────────────────────────────────────────────

CACHE_TTL_WEATHER_CURRENT = 300          # 5 minutes — real-time weather
CACHE_TTL_WEATHER_FORECAST = 900         # 15 minutes — forecast changes slowly
CACHE_TTL_WEATHER_HISTORICAL = 3600      # 1 hour — historical is immutable
CACHE_TTL_PREDICTION = 600               # 10 minutes — predictions per feature set
CACHE_TTL_MODEL_METADATA = 1800          # 30 minutes — model registry info
CACHE_TTL_DISTRICT_METADATA = 86400      # 24 hours — static geographic data
CACHE_TTL_USER_PROFILE = 300             # 5 minutes — user profile cache
CACHE_TTL_DIGITAL_TWIN_STATE = 60        # 1 minute — twin state refreshes frequently

# ── Pagination ────────────────────────────────────────────────────────────────

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# ── Date Formats ──────────────────────────────────────────────────────────────

DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"

# ── Model Registry ────────────────────────────────────────────────────────────

MODEL_ALIAS_LATEST = "latest"
MODEL_ALIAS_PRODUCTION = "production"
DEFAULT_RAINFALL_MODEL = "xgboost_rainfall_v1"
DEFAULT_CLOUDBURST_MODEL = "random_forest_cloudburst_v1"
DEFAULT_LANDSLIDE_MODEL = "lightgbm_landslide_v1"

# ── Observability ─────────────────────────────────────────────────────────────

PROMETHEUS_NAMESPACE = "weather_twin"
OTEL_SPAN_NAME_PREFIX = "weather_twin"

# Log field names — consistent across all structured log records
LOG_FIELD_REQUEST_ID = "request_id"
LOG_FIELD_USER_ID = "user_id"
LOG_FIELD_TRACE_ID = "trace_id"
LOG_FIELD_SPAN_ID = "span_id"
LOG_FIELD_ENDPOINT = "endpoint"
LOG_FIELD_METHOD = "method"
LOG_FIELD_STATUS_CODE = "status_code"
LOG_FIELD_DURATION_MS = "duration_ms"
LOG_FIELD_AGENT_NAME = "agent_name"
LOG_FIELD_MODEL_NAME = "model_name"
LOG_FIELD_DISTRICT = "district"

# ── Feature Engineering ───────────────────────────────────────────────────────

# Lag features for time-series models
DEFAULT_LAG_HOURS = [1, 3, 6, 12, 24, 48, 72]
DEFAULT_ROLLING_WINDOWS_HOURS = [3, 6, 12, 24, 48, 72]

# Monsoon season definition (for feature engineering)
MONSOON_START_MONTH = 6   # June
MONSOON_END_MONTH = 9     # September

# ── API Versioning ────────────────────────────────────────────────────────────

CURRENT_API_VERSION = "v1"
SUPPORTED_API_VERSIONS = ["v1"]
DEPRECATED_API_VERSIONS: list[str] = []
