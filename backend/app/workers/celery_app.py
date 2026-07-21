"""
app/workers/celery_app.py
─────────────────────────
Celery application instance and configuration.

Design decisions:
  • Uses Redis as both broker and result backend.
  • Configured with strict task limits (time limits, retries) to prevent runaway processes.
  • OpenTelemetry is instrumented automatically by the Celery extension.
  • Tasks are automatically discovered from the `app.tasks` module.
"""

import os
from celery import Celery
from celery.signals import setup_logging

# We need to access Pydantic settings synchronously here since Celery is sync.
# To do this safely, we ensure the .env is loaded.
from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "weather_twin_worker",
    broker=settings.redis.cache_url,  # Reuse cache URL for broker in this config
    backend=settings.redis.cache_url,
    include=[
        "app.tasks.weather_tasks",
        "app.tasks.agent_tasks",
        "app.tasks.simulation_tasks",
    ],
)

# ── Celery Configuration ──────────────────────────────────────────────────────

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    
    # Task execution limits
    task_time_limit=3600,         # Hard kill after 1 hour (for long simulations)
    task_soft_time_limit=3300,    # Raise SoftTimeLimitExceeded after 55 mins
    
    # Reliability
    task_acks_late=True,          # Don't ack task until it finishes successfully
    task_reject_on_worker_lost=True,
    
    # Routing (Queue definitions)
    task_routes={
        "app.tasks.weather_tasks.*": {"queue": "weather"},
        "app.tasks.agent_tasks.*": {"queue": "agents"},
        "app.tasks.simulation_tasks.*": {"queue": "simulations"},
    },
    
    # Scheduled Tasks (Celery Beat) ──────────────────────────────────────────
    beat_schedule={
        # Phase 5: Weather ingestion — every 60 minutes
        "poll-weather-every-hour": {
            "task": "app.tasks.weather_tasks.poll_all_weather",
            "schedule": 3600.0,
        },
        # Phase 9: Full 12-agent orchestration pipeline — every 60 minutes
        "run-agent-pipeline-every-hour": {
            "task": "app.tasks.agent_tasks.run_orchestrator_pipeline",
            "schedule": 3600.0,
        },
        # Phase 9: Lightweight monitoring sweep — every 15 minutes
        "run-monitoring-sweep": {
            "task": "app.tasks.agent_tasks.run_monitoring_sweep",
            "schedule": 900.0,
        },
        # Phase 10: Simulation cleanup — daily at 02:00 IST
        "cleanup-old-simulations-daily": {
            "task": "app.tasks.simulation_tasks.cleanup_old_simulations",
            "schedule": 86400.0,
            "kwargs": {"days_older_than": 30},
        },
    },
)


@setup_logging.connect
def config_loggers(*args, **kwargs):
    """
    Hook into Celery's startup to configure structlog instead of 
    the default standard library logging.
    """
    from app.logging.structured_logger import setup_logging as setup_structlog
    setup_structlog(
        level=settings.logging.level,
        use_json=(settings.logging.format == "json"),
    )
