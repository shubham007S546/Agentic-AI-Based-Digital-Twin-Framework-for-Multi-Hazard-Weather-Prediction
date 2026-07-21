"""
app/monitoring/metrics.py
──────────────────────────
Prometheus metrics registry.

Design decisions:
  • All metrics are declared at module level (not inside functions) so they are
    registered with the default Prometheus registry on import. This prevents
    duplicate registration errors in tests or when modules are reloaded.
  • Naming convention: {namespace}_{subsystem}_{metric_name}_{unit}
    Namespace: "weather_twin" — avoids collisions with library metrics.
  • Histograms use carefully chosen buckets derived from actual SLA targets:
    - HTTP: p99 target < 500ms
    - Inference: p99 target < 200ms for ML models
    - Agent: p99 target < 30s
  • Labels are designed for high cardinality safety:
    - "method" (8 HTTP methods), "status_code" (coarse — 2xx/4xx/5xx),
      "model_name" (bounded — ~10 models), "agent_name" (bounded — ~12 agents)
    - Cardinality is intentionally bounded to prevent Prometheus OOM.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, Info, Summary

# ── Namespace / subsystem ─────────────────────────────────────────────────────
_NS = "weather_twin"


# ══════════════════════════════════════════════════════════════════════════════
#  HTTP / API Metrics
# ══════════════════════════════════════════════════════════════════════════════

HTTP_REQUESTS_TOTAL = Counter(
    name=f"{_NS}_http_requests_total",
    documentation="Total number of HTTP requests received.",
    labelnames=["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    name=f"{_NS}_http_request_duration_seconds",
    documentation="HTTP request processing time in seconds.",
    labelnames=["method", "endpoint", "status_code"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    name=f"{_NS}_http_requests_in_progress",
    documentation="Number of HTTP requests currently being processed.",
    labelnames=["method", "endpoint"],
)

HTTP_RESPONSE_SIZE_BYTES = Histogram(
    name=f"{_NS}_http_response_size_bytes",
    documentation="HTTP response body size in bytes.",
    labelnames=["method", "endpoint"],
    buckets=(100, 500, 1_000, 5_000, 10_000, 50_000, 100_000, 500_000, 1_000_000),
)


# ══════════════════════════════════════════════════════════════════════════════
#  Authentication Metrics
# ══════════════════════════════════════════════════════════════════════════════

AUTH_LOGIN_TOTAL = Counter(
    name=f"{_NS}_auth_login_total",
    documentation="Total login attempts.",
    labelnames=["status"],  # success | failure
)

AUTH_TOKEN_BLACKLISTED_TOTAL = Counter(
    name=f"{_NS}_auth_token_blacklisted_total",
    documentation="Total tokens added to the blacklist (logouts, revocations).",
)

AUTH_FAILED_ATTEMPTS_TOTAL = Counter(
    name=f"{_NS}_auth_failed_attempts_total",
    documentation="Total failed authentication attempts by IP.",
    labelnames=["reason"],  # invalid_credentials | account_locked | token_expired
)


# ══════════════════════════════════════════════════════════════════════════════
#  Prediction / Inference Metrics
# ══════════════════════════════════════════════════════════════════════════════

PREDICTION_REQUESTS_TOTAL = Counter(
    name=f"{_NS}_prediction_requests_total",
    documentation="Total prediction requests.",
    labelnames=["model_name", "hazard_type", "status"],  # success | failure
)

MODEL_INFERENCE_LATENCY_SECONDS = Histogram(
    name=f"{_NS}_model_inference_latency_seconds",
    documentation="Time taken to run a single model inference (excludes feature engineering).",
    labelnames=["model_name", "framework"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

FEATURE_ENGINEERING_LATENCY_SECONDS = Histogram(
    name=f"{_NS}_feature_engineering_latency_seconds",
    documentation="Time taken to run the feature engineering pipeline.",
    labelnames=["hazard_type"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
)

MODELS_LOADED_GAUGE = Gauge(
    name=f"{_NS}_models_loaded_count",
    documentation="Number of models currently loaded in memory.",
    labelnames=["framework"],
)

BATCH_PREDICTION_SIZE = Histogram(
    name=f"{_NS}_batch_prediction_size",
    documentation="Number of records in batch prediction jobs.",
    labelnames=["model_name"],
    buckets=(1, 5, 10, 50, 100, 256, 512, 1024),
)


# ══════════════════════════════════════════════════════════════════════════════
#  Agent Metrics
# ══════════════════════════════════════════════════════════════════════════════

AGENT_EXECUTIONS_TOTAL = Counter(
    name=f"{_NS}_agent_executions_total",
    documentation="Total agent execution runs.",
    labelnames=["agent_name", "trigger", "status"],
)

AGENT_EXECUTION_DURATION_SECONDS = Histogram(
    name=f"{_NS}_agent_execution_duration_seconds",
    documentation="Time taken for an agent to complete execution.",
    labelnames=["agent_name"],
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

AGENT_HEALTH_STATUS = Gauge(
    name=f"{_NS}_agent_health_status",
    documentation="Agent health: 1=healthy, 0=unhealthy.",
    labelnames=["agent_name"],
)

AGENT_LAST_EXECUTION_TIMESTAMP = Gauge(
    name=f"{_NS}_agent_last_execution_timestamp",
    documentation="Unix timestamp of the last successful agent execution.",
    labelnames=["agent_name"],
)


# ══════════════════════════════════════════════════════════════════════════════
#  Database Metrics
# ══════════════════════════════════════════════════════════════════════════════

DB_POOL_CONNECTIONS_ACTIVE = Gauge(
    name=f"{_NS}_db_pool_connections_active",
    documentation="Number of active database connections in the pool.",
)

DB_POOL_CONNECTIONS_IDLE = Gauge(
    name=f"{_NS}_db_pool_connections_idle",
    documentation="Number of idle database connections in the pool.",
)

DB_QUERY_DURATION_SECONDS = Histogram(
    name=f"{_NS}_db_query_duration_seconds",
    documentation="Database query execution time.",
    labelnames=["operation"],  # select | insert | update | delete
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
)

DB_ERRORS_TOTAL = Counter(
    name=f"{_NS}_db_errors_total",
    documentation="Total database errors.",
    labelnames=["operation", "error_type"],
)


# ══════════════════════════════════════════════════════════════════════════════
#  Cache Metrics
# ══════════════════════════════════════════════════════════════════════════════

CACHE_HITS_TOTAL = Counter(
    name=f"{_NS}_cache_hits_total",
    documentation="Cache hit count.",
    labelnames=["cache_key_prefix"],
)

CACHE_MISSES_TOTAL = Counter(
    name=f"{_NS}_cache_misses_total",
    documentation="Cache miss count.",
    labelnames=["cache_key_prefix"],
)

CACHE_OPERATION_DURATION_SECONDS = Histogram(
    name=f"{_NS}_cache_operation_duration_seconds",
    documentation="Redis operation latency.",
    labelnames=["operation"],  # get | set | delete | exists
    buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1),
)


# ══════════════════════════════════════════════════════════════════════════════
#  Alert / Hazard Metrics
# ══════════════════════════════════════════════════════════════════════════════

ALERTS_ISSUED_TOTAL = Counter(
    name=f"{_NS}_alerts_issued_total",
    documentation="Total hazard alerts issued.",
    labelnames=["district", "hazard_type", "severity"],
)

ACTIVE_ALERTS_GAUGE = Gauge(
    name=f"{_NS}_active_alerts",
    documentation="Current number of active (unresolved) alerts.",
    labelnames=["district", "hazard_type"],
)


# ══════════════════════════════════════════════════════════════════════════════
#  Celery / Background Task Metrics
# ══════════════════════════════════════════════════════════════════════════════

CELERY_TASKS_TOTAL = Counter(
    name=f"{_NS}_celery_tasks_total",
    documentation="Total Celery tasks processed.",
    labelnames=["task_name", "queue", "status"],
)

CELERY_TASK_DURATION_SECONDS = Histogram(
    name=f"{_NS}_celery_task_duration_seconds",
    documentation="Celery task execution time.",
    labelnames=["task_name", "queue"],
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0),
)

CELERY_QUEUE_SIZE = Gauge(
    name=f"{_NS}_celery_queue_size",
    documentation="Number of pending tasks in each Celery queue.",
    labelnames=["queue"],
)


# ══════════════════════════════════════════════════════════════════════════════
#  Digital Twin Metrics
# ══════════════════════════════════════════════════════════════════════════════

DIGITAL_TWIN_STATE_SYNC_TOTAL = Counter(
    name=f"{_NS}_digital_twin_state_sync_total",
    documentation="Total digital twin state sync operations.",
    labelnames=["district", "status"],
)

SIMULATION_RUNS_TOTAL = Counter(
    name=f"{_NS}_simulation_runs_total",
    documentation="Total digital twin simulation runs.",
    labelnames=["scenario_type", "district", "status"],
)

SIMULATION_DURATION_SECONDS = Histogram(
    name=f"{_NS}_simulation_duration_seconds",
    documentation="Digital twin simulation wall-clock time.",
    labelnames=["scenario_type"],
    buckets=(0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)


# ══════════════════════════════════════════════════════════════════════════════
#  System / Infrastructure Info
# ══════════════════════════════════════════════════════════════════════════════

APP_INFO = Info(
    name=f"{_NS}_app",
    documentation="Application build information.",
)

DEPENDENCY_HEALTH = Gauge(
    name=f"{_NS}_dependency_health",
    documentation="Health of infrastructure dependencies: 1=healthy, 0=unhealthy.",
    labelnames=["dependency"],  # postgres | redis | minio | celery
)

WEATHER_DATA_COLLECTION_TOTAL = Counter(
    name=f"{_NS}_weather_data_collection_total",
    documentation="Total weather data collection runs.",
    labelnames=["source", "district", "status"],
)

WEATHER_DATA_RECORDS_COLLECTED = Counter(
    name=f"{_NS}_weather_data_records_collected_total",
    documentation="Total weather data records ingested.",
    labelnames=["source", "district"],
)
