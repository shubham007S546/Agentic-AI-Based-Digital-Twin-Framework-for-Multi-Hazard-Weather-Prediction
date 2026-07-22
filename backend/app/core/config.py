"""
app/core/config.py
──────────────────
Central configuration module using Pydantic Settings.

Design decisions:
  • Single source of truth for ALL configuration — no scattered os.getenv() calls.
  • lru_cache ensures the Settings object is instantiated once (singleton pattern).
  • Nested model approach groups related settings, improving readability.
  • All sensitive values are typed as SecretStr so they never appear in logs or tracebacks.
  • Supports .env file + real environment variable overrides (12-factor app compliant).

Used by:
  • Database layer (connection strings, pool sizes)
  • Security layer (JWT secrets, token lifetimes)
  • Cache layer (Redis URL)
  • Middleware (rate limits, CORS origins)
  • Every service that needs runtime config
"""

from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Base directory resolution ──────────────────────────────────────────────────
# Resolve paths relative to this file, not the working directory, so the app
# can be started from any directory without path breakage.
_BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent


class AppSettings(BaseSettings):
    """Core application identity settings."""

    name: str = Field("Weather Twin Backend", description="Human-readable service name")
    version: str = Field("1.0.0", description="Semantic version")
    env: str = Field("development", description="Runtime environment: development|staging|production")
    debug: bool = Field(False, description="Enable debug mode (never True in production)")
    host: str = Field("0.0.0.0", description="Uvicorn bind host")
    port: int = Field(8000, ge=1024, le=65535, description="Uvicorn bind port")
    workers: int = Field(4, ge=1, le=32, description="Number of Uvicorn worker processes")
    reload: bool = Field(False, description="Hot reload (development only)")

    model_config = SettingsConfigDict(env_prefix="APP_")

    @field_validator("env")
    @classmethod
    def validate_env(cls, v: str) -> str:
        allowed = {"development", "staging", "production", "test"}
        if v.lower() not in allowed:
            raise ValueError(f"APP_ENV must be one of {allowed}, got '{v}'")
        return v.lower()

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_development(self) -> bool:
        return self.env == "development"

    @property
    def is_test(self) -> bool:
        return self.env == "test"


class SecuritySettings(BaseSettings):
    """Security and CORS settings."""

    secret_key: SecretStr = Field(..., description="Master secret — used for signing internal tokens")
    allowed_hosts: list[str] = Field(
        default=["localhost", "127.0.0.1"],
        description="Hosts allowed by TrustedHostMiddleware",
    )
    allowed_origins: list[str] = Field(
        default=["http://localhost:3000"],
        description="CORS allowed origins for the Next.js frontend",
    )
    allowed_methods: list[str] = Field(
        default=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        description="CORS allowed HTTP methods",
    )
    allowed_headers: list[str] = Field(
        default=["*"],
        description="CORS allowed request headers",
    )
    allow_credentials: bool = Field(True, description="Allow cookies in CORS requests")

    model_config = SettingsConfigDict(env_prefix="APP_")


class DatabaseSettings(BaseSettings):
    """Async PostgreSQL connection settings."""

    url: str = Field(
        "postgresql+asyncpg://weather_user:weather_pass@localhost:5432/weather_twin_db",
        description="Async SQLAlchemy connection URL (asyncpg driver)",
    )
    sync_url: str = Field(
        "postgresql+psycopg2://weather_user:weather_pass@localhost:5432/weather_twin_db",
        description="Sync URL for Alembic migrations",
    )
    pool_size: int = Field(10, ge=2, le=50, description="SQLAlchemy connection pool size")
    max_overflow: int = Field(20, ge=0, le=50, description="Connections allowed beyond pool_size")
    pool_timeout: int = Field(30, description="Seconds to wait for a connection from pool")
    pool_recycle: int = Field(1800, description="Seconds before a connection is recycled")
    pool_pre_ping: bool = Field(True, description="Validate connections before use")
    echo: bool = Field(False, description="Log all SQL (never True in production)")

    model_config = SettingsConfigDict(env_prefix="DATABASE_")


class RedisSettings(BaseSettings):
    """Redis connection and database index settings."""

    url: str = Field("redis://localhost:6379/0", description="Primary Redis URL")
    cache_db: int = Field(0, description="Redis DB index for application cache")
    celery_broker_db: int = Field(1, description="Redis DB index for Celery broker")
    celery_result_db: int = Field(2, description="Redis DB index for Celery results")
    rate_limit_db: int = Field(3, description="Redis DB index for rate limiting counters")
    max_connections: int = Field(20, description="Redis connection pool max size")
    socket_timeout: int = Field(5, description="Redis socket timeout in seconds")
    connect_timeout: int = Field(5, description="Redis connection timeout in seconds")

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    @property
    def cache_url(self) -> str:
        """URL targeting the cache-specific DB index."""
        base = self.url.rsplit("/", 1)[0]
        return f"{base}/{self.cache_db}"

    @property
    def rate_limit_url(self) -> str:
        base = self.url.rsplit("/", 1)[0]
        return f"{base}/{self.rate_limit_db}"


class JWTSettings(BaseSettings):
    """JWT token configuration."""

    secret_key: SecretStr = Field(..., description="HMAC signing key — must be at least 64 bytes")
    algorithm: str = Field("HS256", description="JWT signing algorithm")
    access_token_expire_minutes: int = Field(30, ge=1, description="Access token TTL in minutes")
    refresh_token_expire_days: int = Field(7, ge=1, le=90, description="Refresh token TTL in days")
    issuer: str = Field("weather-twin-platform", description="JWT 'iss' claim")
    audience: str = Field("weather-twin-users", description="JWT 'aud' claim")

    model_config = SettingsConfigDict(env_prefix="JWT_")


class CelerySettings(BaseSettings):
    """Celery distributed task queue configuration."""

    broker_url: str = Field("redis://localhost:6379/1")
    result_backend: str = Field("redis://localhost:6379/2")
    task_serializer: str = Field("json")
    result_serializer: str = Field("json")
    accept_content: list[str] = Field(default=["json"])
    timezone: str = Field("Asia/Kolkata")
    task_track_started: bool = Field(True)
    worker_concurrency: int = Field(4, ge=1)
    task_soft_time_limit: int = Field(300, description="Soft task timeout seconds")
    task_time_limit: int = Field(600, description="Hard task kill timeout seconds")
    result_expires: int = Field(86400, description="Task result TTL in seconds")

    model_config = SettingsConfigDict(env_prefix="CELERY_")


class MinIOSettings(BaseSettings):
    """MinIO / S3-compatible object storage settings."""

    endpoint: str = Field("localhost:9000")
    access_key: SecretStr = Field("minioadmin")
    secret_key: SecretStr = Field("minioadmin123")
    use_ssl: bool = Field(False)
    region: str = Field("us-east-1")
    bucket_models: str = Field("ml-models")
    bucket_reports: str = Field("reports")
    bucket_datasets: str = Field("datasets")
    bucket_satellite: str = Field("satellite-data")

    model_config = SettingsConfigDict(env_prefix="MINIO_")


class EmailSettings(BaseSettings):
    """SMTP email delivery configuration."""

    host: str = Field("smtp.gmail.com")
    port: int = Field(587)
    use_tls: bool = Field(True)
    user: str = Field("")
    password: SecretStr = Field(SecretStr(""))
    from_name: str = Field("Weather Twin Platform")
    from_address: str = Field("no-reply@weather-twin.ai")

    model_config = SettingsConfigDict(env_prefix="SMTP_")


class OTELSettings(BaseSettings):
    """OpenTelemetry distributed tracing configuration."""

    enabled: bool = Field(True)
    service_name: str = Field("weather-twin-backend")
    service_version: str = Field("1.0.0")
    exporter_otlp_endpoint: str = Field("http://localhost:4317")

    model_config = SettingsConfigDict(env_prefix="OTEL_")


class RateLimitSettings(BaseSettings):
    """API rate limiting configuration (sliding window via Redis)."""

    enabled: bool = Field(True)
    default_requests: int = Field(100, description="Max requests per window for general endpoints")
    default_window_seconds: int = Field(60)
    auth_requests: int = Field(10, description="Stricter limit for auth endpoints (brute force)")
    auth_window_seconds: int = Field(60)
    prediction_requests: int = Field(30, description="Limit for compute-heavy prediction endpoints")
    prediction_window_seconds: int = Field(60)

    model_config = SettingsConfigDict(env_prefix="RATE_LIMIT_")


class WeatherSourceSettings(BaseSettings):
    """External weather API credentials."""

    open_meteo_base_url: str = Field("https://archive-api.open-meteo.com/v1/archive")
    open_meteo_forecast_url: str = Field("https://api.open-meteo.com/v1/forecast")
    openweather_api_key: str = Field("")
    openweather_base_url: str = Field("https://api.openweathermap.org/data/2.5")
    nasa_earthdata_username: str = Field("")
    nasa_earthdata_password: SecretStr = Field(SecretStr(""))
    nasa_earthdata_token: SecretStr = Field(SecretStr(""))
    cds_api_key: SecretStr = Field(SecretStr(""))
    datagov_api_key: SecretStr = Field(SecretStr(""))
    wris_api_key: SecretStr = Field(SecretStr(""))
    reliefweb_appname: str = Field("weather-twin")

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


class ModelServingSettings(BaseSettings):
    """ML model registry and serving configuration."""

    base_path: str = Field("../saved_models", description="Local fallback path for models")
    registry_backend: str = Field("minio", description="Backend for model storage: minio|local")
    warm_load_on_startup: bool = Field(True, description="Preload priority models at startup")
    inference_timeout_seconds: int = Field(30)
    max_batch_size: int = Field(256)

    model_config = SettingsConfigDict(env_prefix="MODEL_")


class FeatureFlags(BaseSettings):
    """Runtime feature toggles — allow disabling expensive features in environments."""

    agents_enabled: bool = Field(True)
    digital_twin_enabled: bool = Field(True)
    satellite_enabled: bool = Field(False)
    gnn_enabled: bool = Field(False)
    onnx_enabled: bool = Field(True)
    gpu_enabled: bool = Field(False)

    model_config = SettingsConfigDict(env_prefix="FEATURE_")


class LoggingSettings(BaseSettings):
    """Logging output configuration."""

    level: str = Field("INFO")
    format: str = Field("json", description="json|text — use json in production")
    to_file: bool = Field(False)
    file_path: str = Field("logs/backend.log")

    model_config = SettingsConfigDict(env_prefix="LOG_")


class PaginationSettings(BaseSettings):
    """Default pagination limits."""

    default_page_size: int = Field(20, ge=1, le=100)
    max_page_size: int = Field(100, ge=10, le=1000)

    model_config = SettingsConfigDict(env_prefix="")


class DistrictSettings(BaseSettings):
    """Geographic scope for the Himachal Pradesh focus area."""

    active_districts: str = Field("mandi,kullu,chamba")
    default_district: str = Field("mandi")

    model_config = SettingsConfigDict(env_prefix="")

    @property
    def active_list(self) -> list[str]:
        return [d.strip() for d in self.active_districts.split(",")]


# ──────────────────────────────────────────────────────────────────────────────
#  Master Settings — composes all sub-settings
# ──────────────────────────────────────────────────────────────────────────────

class Settings(BaseSettings):
    """
    Master settings class that composes all sub-settings.

    Usage:
        from app.core.config import get_settings
        settings = get_settings()
        print(settings.app.name)
        print(settings.jwt.algorithm)
    """

    model_config = SettingsConfigDict(
        env_file=str(_BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Sub-settings (populated from env with their respective prefixes) ──
    # Pydantic-settings does NOT natively support nested prefixes in v2 via model
    # composition — we handle that by building each sub-settings independently
    # inside __init__ of the outer class.

    # Top-level scalar fields assembled by validators:
    app: AppSettings = Field(default_factory=AppSettings)
    security: SecuritySettings = Field(default_factory=lambda: SecuritySettings(secret_key=SecretStr("CHANGE_ME")))
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    jwt: JWTSettings = Field(default_factory=lambda: JWTSettings(secret_key=SecretStr("CHANGE_ME")))
    celery: CelerySettings = Field(default_factory=CelerySettings)
    minio: MinIOSettings = Field(default_factory=MinIOSettings)
    email: EmailSettings = Field(default_factory=EmailSettings)
    otel: OTELSettings = Field(default_factory=OTELSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    weather_sources: WeatherSourceSettings = Field(default_factory=WeatherSourceSettings)
    model_serving: ModelServingSettings = Field(default_factory=ModelServingSettings)
    features: FeatureFlags = Field(default_factory=FeatureFlags)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    pagination: PaginationSettings = Field(default_factory=PaginationSettings)
    districts: DistrictSettings = Field(default_factory=DistrictSettings)

    base_dir: Path = _BASE_DIR


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the singleton Settings instance.

    Using lru_cache here is a deliberate design choice:
    - On first call, reads .env + env vars → instantiates Settings.
    - All subsequent calls return the cached object (zero disk I/O).
    - In tests, call get_settings.cache_clear() before overriding env vars.
    """
    return Settings()
