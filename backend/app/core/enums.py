"""
app/core/enums.py
─────────────────
Domain-wide enumerations.

Design decisions:
  • All enums use str as mixin so they serialize to JSON naturally (no .value needed).
  • IntEnum is used only for ordered severity levels.
  • Kept in a single file to avoid circular imports — enums have zero dependencies.
  • Used by SQLAlchemy models (as column types), Pydantic schemas, and business logic.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum, auto


# ── Application Environment ───────────────────────────────────────────────────

class Environment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


# ── User & Authentication ─────────────────────────────────────────────────────

class UserRole(StrEnum):
    """
    RBAC roles in ascending privilege order.
    super_admin > admin > researcher > disaster_officer > government_authority > public
    """
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    RESEARCHER = "researcher"
    DISASTER_OFFICER = "disaster_officer"
    GOVERNMENT_AUTHORITY = "government_authority"
    PUBLIC = "public"


class Permission(StrEnum):
    """Fine-grained permissions — roles map to sets of these."""
    # User management
    USER_READ = "user:read"
    USER_CREATE = "user:create"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    USER_MANAGE_ROLES = "user:manage_roles"

    # Predictions
    PREDICTION_CREATE = "prediction:create"
    PREDICTION_READ = "prediction:read"
    PREDICTION_BATCH = "prediction:batch"
    PREDICTION_EXPLAIN = "prediction:explain"

    # Weather data
    WEATHER_READ = "weather:read"
    WEATHER_WRITE = "weather:write"
    WEATHER_DELETE = "weather:delete"

    # Models
    MODEL_READ = "model:read"
    MODEL_LOAD = "model:load"
    MODEL_UNLOAD = "model:unload"
    MODEL_RETRAIN = "model:retrain"

    # Agents
    AGENT_READ = "agent:read"
    AGENT_TRIGGER = "agent:trigger"
    AGENT_MANAGE = "agent:manage"

    # Digital twin
    DIGITAL_TWIN_READ = "digital_twin:read"
    DIGITAL_TWIN_SIMULATE = "digital_twin:simulate"
    DIGITAL_TWIN_MANAGE = "digital_twin:manage"

    # Alerts
    ALERT_READ = "alert:read"
    ALERT_CREATE = "alert:create"
    ALERT_ACKNOWLEDGE = "alert:acknowledge"
    ALERT_MANAGE = "alert:manage"

    # Reports
    REPORT_READ = "report:read"
    REPORT_CREATE = "report:create"
    REPORT_DELETE = "report:delete"

    # Admin
    ADMIN_PANEL = "admin:panel"
    SYSTEM_HEALTH = "system:health"
    METRICS_READ = "metrics:read"
    AUDIT_READ = "audit:read"


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFICATION = "email_verification"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


# ── Hazard & Prediction ───────────────────────────────────────────────────────

class HazardType(StrEnum):
    RAINFALL = "rainfall"
    CLOUDBURST = "cloudburst"
    LANDSLIDE = "landslide"
    FLASH_FLOOD = "flash_flood"
    FLOOD = "flood"
    DROUGHT = "drought"
    HEATWAVE = "heatwave"
    SNOWFALL = "snowfall"
    MULTI_HAZARD = "multi_hazard"


class AlertSeverity(IntEnum):
    """Ordered severity scale — higher = more severe."""
    INFO = 1
    LOW = 2
    MODERATE = 3
    HIGH = 4
    CRITICAL = 5
    EXTREME = 6


class AlertStatus(StrEnum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    ESCALATED = "escalated"
    FALSE_ALARM = "false_alarm"


class PredictionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PredictionType(StrEnum):
    ONLINE = "online"           # Synchronous, single-record
    BATCH = "batch"             # Asynchronous, multiple records via Celery
    SCHEDULED = "scheduled"     # Triggered by agent scheduler


# ── ML Models ─────────────────────────────────────────────────────────────────

class ModelType(StrEnum):
    RANDOM_FOREST = "random_forest"
    XGBOOST = "xgboost"
    LIGHTGBM = "lightgbm"
    CATBOOST = "catboost"
    LSTM = "lstm"
    CNN = "cnn"
    CNN_LSTM = "cnn_lstm"
    TRANSFORMER = "transformer"
    TEMPORAL_FUSION_TRANSFORMER = "temporal_fusion_transformer"
    GNN = "gnn"


class ModelFramework(StrEnum):
    SKLEARN = "sklearn"
    XGBOOST = "xgboost"
    LIGHTGBM = "lightgbm"
    CATBOOST = "catboost"
    PYTORCH = "pytorch"
    ONNX = "onnx"


class ModelStatus(StrEnum):
    REGISTERED = "registered"
    LOADING = "loading"
    LOADED = "loaded"
    UNLOADED = "unloaded"
    DEPRECATED = "deprecated"
    FAILED = "failed"


class ModelStage(StrEnum):
    """Model lifecycle stage — mirrors MLflow conventions."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"


# ── Agents ────────────────────────────────────────────────────────────────────

class AgentName(StrEnum):
    WEATHER_INTELLIGENCE = "weather_intelligence"
    PREDICTION = "prediction"
    ALERT = "alert"
    DISASTER_INTELLIGENCE = "disaster_intelligence"
    DIGITAL_TWIN = "digital_twin"
    REPORT_GENERATOR = "report_generator"
    NOTIFICATION = "notification"
    MONITORING = "monitoring"
    DATA_COLLECTION = "data_collection"
    RESEARCH = "research"
    EXPLAINABILITY = "explainability"
    DECISION_SUPPORT = "decision_support"


class AgentStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    DISABLED = "disabled"
    RETRYING = "retrying"


class AgentTrigger(StrEnum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    EVENT = "event"
    CASCADE = "cascade"         # Triggered by another agent


# ── Weather ───────────────────────────────────────────────────────────────────

class WeatherSource(StrEnum):
    IMD = "imd"
    OPEN_METEO = "open_meteo"
    ERA5 = "era5"
    ERA5_LAND = "era5_land"
    NASA_GPM = "nasa_gpm"
    MODIS = "modis"
    INSAT = "insat"
    INDIA_WRIS = "india_wris"
    SENTINEL = "sentinel"
    COMPUTED = "computed"       # Derived / feature-engineered


class WeatherQuality(StrEnum):
    GOOD = "good"
    SUSPECT = "suspect"
    BAD = "bad"
    MISSING = "missing"


# ── Digital Twin ──────────────────────────────────────────────────────────────

class SimulationStatus(StrEnum):
    QUEUED = "queued"
    INITIALIZING = "initializing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScenarioType(StrEnum):
    HISTORICAL_REPLAY = "historical_replay"
    FUTURE_FORECAST = "future_forecast"
    STRESS_TEST = "stress_test"
    WHAT_IF = "what_if"
    BASELINE = "baseline"


class RiskLevel(StrEnum):
    NEGLIGIBLE = "negligible"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"
    EXTREME = "extreme"


# ── Districts ─────────────────────────────────────────────────────────────────

class District(StrEnum):
    MANDI = "mandi"
    KULLU = "kullu"
    CHAMBA = "chamba"


# ── Tasks ─────────────────────────────────────────────────────────────────────

class TaskStatus(StrEnum):
    PENDING = "pending"
    STARTED = "started"
    SUCCESS = "success"
    FAILURE = "failure"
    RETRY = "retry"
    REVOKED = "revoked"


# ── Reports ───────────────────────────────────────────────────────────────────

class ReportType(StrEnum):
    DAILY_WEATHER = "daily_weather"
    PREDICTION_SUMMARY = "prediction_summary"
    HAZARD_ASSESSMENT = "hazard_assessment"
    ALERT_BULLETIN = "alert_bulletin"
    RESEARCH_EXPORT = "research_export"
    DIGITAL_TWIN_SNAPSHOT = "digital_twin_snapshot"


class ReportFormat(StrEnum):
    PDF = "pdf"
    HTML = "html"
    JSON = "json"
    CSV = "csv"
    XLSX = "xlsx"


class ReportStatus(StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Notifications ─────────────────────────────────────────────────────────────

class NotificationChannel(StrEnum):
    EMAIL = "email"
    WEBHOOK = "webhook"
    SMS = "sms"
    IN_APP = "in_app"
    PUSH = "push"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"


# ── HTTP / API ────────────────────────────────────────────────────────────────

class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class ErrorCode(StrEnum):
    """Application-level error codes for structured error responses."""
    # Auth
    AUTHENTICATION_FAILED = "AUTH_001"
    TOKEN_EXPIRED = "AUTH_002"
    TOKEN_INVALID = "AUTH_003"
    TOKEN_BLACKLISTED = "AUTH_004"
    REFRESH_TOKEN_INVALID = "AUTH_005"
    INSUFFICIENT_PERMISSIONS = "AUTH_006"
    ACCOUNT_LOCKED = "AUTH_007"
    ACCOUNT_INACTIVE = "AUTH_008"
    EMAIL_NOT_VERIFIED = "AUTH_009"

    # User
    USER_NOT_FOUND = "USR_001"
    USER_ALREADY_EXISTS = "USR_002"
    INVALID_CREDENTIALS = "USR_003"

    # Prediction
    PREDICTION_FAILED = "PRED_001"
    MODEL_NOT_FOUND = "PRED_002"
    MODEL_LOAD_FAILED = "PRED_003"
    FEATURE_ENGINEERING_FAILED = "PRED_004"
    INFERENCE_TIMEOUT = "PRED_005"

    # Agent
    AGENT_NOT_FOUND = "AGENT_001"
    AGENT_EXECUTION_FAILED = "AGENT_002"
    AGENT_TIMEOUT = "AGENT_003"
    AGENT_DISABLED = "AGENT_004"

    # Weather
    WEATHER_SOURCE_UNAVAILABLE = "WTH_001"
    WEATHER_DATA_INVALID = "WTH_002"

    # Digital Twin
    SIMULATION_FAILED = "DT_001"
    STATE_SYNC_FAILED = "DT_002"

    # Infrastructure
    DATABASE_ERROR = "INFRA_001"
    CACHE_ERROR = "INFRA_002"
    STORAGE_ERROR = "INFRA_003"
    EXTERNAL_API_ERROR = "INFRA_004"

    # Validation
    VALIDATION_ERROR = "VAL_001"
    RATE_LIMIT_EXCEEDED = "VAL_002"

    # Generic
    NOT_FOUND = "GEN_001"
    INTERNAL_ERROR = "GEN_002"
    SERVICE_UNAVAILABLE = "GEN_003"
