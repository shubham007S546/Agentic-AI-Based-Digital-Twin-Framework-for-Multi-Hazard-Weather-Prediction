"""
app/tasks/weather_tasks.py
──────────────────────────
Celery background tasks for weather ingestion.
"""

import asyncio
import structlog
from typing import Any

from app.core.enums import District
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run_async(coro: Any) -> Any:
    """Helper to run async code inside synchronous Celery workers."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def poll_weather_for_district(self, district_name: str) -> None:
    """
    Background task to poll weather for a single district.
    """
    logger.info("Starting background weather poll", district=district_name)
    
    # We must initialize DB engines for background tasks since they run in a different process
    from app.database.connection import init_db_engine, get_session_factory
    from app.repositories.weather_repo_impl import WeatherRepositoryImpl
    from app.services.weather_service_impl import WeatherServiceImpl
    from app.integrations.weather.open_meteo import OpenMeteoProvider
    
    district = District[district_name]
    
    async def _do_poll():
        await init_db_engine()
        session_factory = get_session_factory()
        
        async with session_factory() as session:
            try:
                repo = WeatherRepositoryImpl(session)
                service = WeatherServiceImpl(weather_repo=repo, providers=[OpenMeteoProvider()])
                
                observations = await service.ingest_current_weather(district)
                await session.commit()
                return len(observations)
            except Exception as exc:
                await session.rollback()
                raise exc

    try:
        count = _run_async(_do_poll())
        logger.info("Background weather poll complete", district=district_name, count=count)
    except Exception as exc:
        logger.error("Weather poll failed", district=district_name, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task
def poll_all_weather() -> None:
    """
    Master task triggered by Celery Beat every hour.
    Dispatches a sub-task for each district so they process in parallel.
    """
    logger.info("Dispatching weather poll for all districts")
    for district in District:
        poll_weather_for_district.delay(district.name)
