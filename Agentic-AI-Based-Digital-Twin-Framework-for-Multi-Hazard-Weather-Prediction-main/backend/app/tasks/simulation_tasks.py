"""
app/tasks/simulation_tasks.py
──────────────────────────────
Celery tasks for Digital Twin Simulation execution.

Referenced in the celery routing table:
  "app.tasks.simulation_tasks.*" → queue: "simulations"

This dedicated queue ensures simulations (CPU-heavy) don't compete
with real-time weather polling or agent execution.
"""

from __future__ import annotations

import asyncio
import uuid as uuid_mod
from typing import Any

import structlog

from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run_async(coro: Any) -> Any:
    """Run async coroutine inside a synchronous Celery worker."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Loop closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@celery_app.task(
    bind=True,
    name="app.tasks.simulation_tasks.execute_simulation",
    max_retries=0,
    queue="simulations",
)
def execute_simulation(self, simulation_id: str) -> dict:
    """
    Execute a queued Simulation record by ID.

    Triggered by:
      - TwinServiceImpl.create_simulation() when auto_run=True
      - POST /api/v1/twin/simulations/{id}/run endpoint
      - DigitalTwinAgent when scenario_parameters are provided

    Pipeline:
      1. Fetch Simulation record (must be status=PENDING)
      2. Set status=RUNNING, started_at=now
      3. Run the physics/ML simulation engine
         (precipitation multiplier → river levels, landslide risk, infra impact)
      4. Write results back and set status=COMPLETED (or FAILED)
    """
    logger.info("Starting simulation", simulation_id=simulation_id)

    async def _execute():
        from app.database.connection import init_db_engine, get_session_factory
        await init_db_engine()

        session_factory = get_session_factory()
        async with session_factory() as session:
            try:
                from app.repositories.twin_repo_impl import TwinRepositoryImpl
                from app.services.twin_service_impl import TwinServiceImpl
                from app.services.weather_service_impl import WeatherServiceImpl
                from app.integrations.weather.open_meteo import OpenMeteoProvider

                twin_repo = TwinRepositoryImpl(session)
                weather_service = WeatherServiceImpl(
                    weather_repo=None,  # type: ignore[arg-type]
                    providers=[OpenMeteoProvider()],
                )
                twin_service = TwinServiceImpl(
                    twin_repo=twin_repo,
                    weather_service=weather_service,
                )

                sim = await twin_service.run_simulation(uuid_mod.UUID(simulation_id))
                await session.commit()

                return {
                    "simulation_id": simulation_id,
                    "status": sim.status.value,
                    "results": sim.simulation_results,
                    "error": sim.error_message,
                }
            except Exception as exc:
                await session.rollback()
                raise exc

    try:
        result = _run_async(_execute())
        logger.info(
            "Simulation complete",
            simulation_id=simulation_id,
            status=result.get("status"),
        )
        return result
    except Exception as exc:
        logger.error("Simulation failed", simulation_id=simulation_id, error=str(exc))
        return {
            "simulation_id": simulation_id,
            "status": "failed",
            "error": str(exc),
        }


@celery_app.task(
    name="app.tasks.simulation_tasks.cleanup_old_simulations",
    queue="simulations",
)
def cleanup_old_simulations(days_older_than: int = 30) -> dict:
    """
    Periodic cleanup task — removes COMPLETED/FAILED simulation records
    older than `days_older_than` days to keep the table lean.
    Triggered by Celery Beat daily.
    """
    logger.info("Cleaning up old simulation records", older_than_days=days_older_than)

    async def _cleanup():
        from datetime import UTC, datetime, timedelta
        from app.database.connection import init_db_engine, get_session_factory
        from sqlalchemy import delete
        from app.models.digital_twin import Simulation
        from app.core.enums import SimulationStatus

        await init_db_engine()
        session_factory = get_session_factory()

        cutoff = datetime.now(UTC) - timedelta(days=days_older_than)
        async with session_factory() as session:
            result = await session.execute(
                delete(Simulation).where(
                    Simulation.completed_at < cutoff,
                    Simulation.status.in_([
                        SimulationStatus.COMPLETED,
                        SimulationStatus.FAILED,
                    ]),
                )
            )
            await session.commit()
            return result.rowcount

    try:
        deleted = _run_async(_cleanup())
        logger.info("Simulation cleanup complete", deleted=deleted)
        return {"deleted": deleted, "older_than_days": days_older_than}
    except Exception as exc:
        logger.error("Simulation cleanup failed", error=str(exc))
        return {"error": str(exc)}
