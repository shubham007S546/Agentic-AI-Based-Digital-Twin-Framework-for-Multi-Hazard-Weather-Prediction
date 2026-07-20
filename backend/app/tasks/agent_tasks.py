"""
app/tasks/agent_tasks.py
────────────────────────
Celery tasks for executing AI Agents in the background.

Pipeline tasks (triggered by Beat):
  run_orchestrator_pipeline  — Full 12-agent pipeline, every 60 min
  run_single_agent           — Execute any individual agent by name (on-demand)
  run_monitoring_sweep       — Health sweep every 15 min

On-demand tasks (triggered via API or cascade):
  run_agent_on_demand        — Execute a named agent with a custom payload
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog

from app.core.enums import AgentName, AgentTrigger
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


# ── Async helper ─────────────────────────────────────────────────────────────

def _run_async(coro: Any) -> Any:
    """Run an async coroutine inside a synchronous Celery worker process."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Event loop is closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ── Full orchestrator pipeline ────────────────────────────────────────────────

@celery_app.task(bind=True, name="app.tasks.agent_tasks.run_orchestrator_pipeline", max_retries=0)
def run_orchestrator_pipeline(self, payload: dict[str, Any] | None = None) -> dict:
    """
    Full 12-agent pipeline task. Triggered by Celery Beat every 60 minutes.
    Instantiates the OrchestratorAgent and executes the full pipeline.
    """
    payload = payload or {}
    run_id = str(uuid.uuid4())
    logger.info("Starting full agent pipeline", run_id=run_id)

    async def _execute():
        from app.database.connection import init_db_engine
        await init_db_engine()

        from app.agents.orchestrator_agent import OrchestratorAgent
        orchestrator = OrchestratorAgent()
        result = await orchestrator.run(
            payload=payload,
            trigger=AgentTrigger.SCHEDULED,
            triggered_by="celery_beat",
        )
        return result.result_summary or {}

    try:
        result = _run_async(_execute())
        logger.info("Agent pipeline completed", run_id=run_id, result=result)
        return {"run_id": run_id, "status": "completed", **result}
    except Exception as exc:
        logger.error("Agent pipeline failed", run_id=run_id, error=str(exc))
        return {"run_id": run_id, "status": "failed", "error": str(exc)}


# ── Single agent on-demand ────────────────────────────────────────────────────

@celery_app.task(bind=True, name="app.tasks.agent_tasks.run_agent_on_demand", max_retries=1)
def run_agent_on_demand(
    self,
    agent_name: str,
    payload: dict[str, Any] | None = None,
    triggered_by: str = "api",
) -> dict:
    """
    Execute a single named agent on-demand (manual trigger via API or cascade).

    Args:
        agent_name: AgentName enum value (e.g., "weather_intelligence")
        payload: Optional input payload for the agent
        triggered_by: Origin of the trigger (user_id, service name, etc.)
    """
    payload = payload or {}
    logger.info("Running agent on-demand", agent=agent_name, triggered_by=triggered_by)

    async def _execute():
        from app.database.connection import init_db_engine
        await init_db_engine()

        from app.agents.agent_registry import get_agent_registry
        agent_mgr = get_agent_registry()

        try:
            name_enum = AgentName(agent_name)
        except ValueError:
            logger.error("Unknown agent name", agent_name=agent_name)
            return {"error": f"Unknown agent: {agent_name}"}

        result = await agent_mgr.execute(
            agent_name=name_enum,
            payload=payload,
            trigger=AgentTrigger.MANUAL,
            triggered_by=triggered_by,
        )
        return {
            "status": result.status.value,
            "duration_seconds": result.duration_seconds,
            "summary": result.result_summary,
            "error": result.error_message,
        }

    try:
        result = _run_async(_execute())
        logger.info("Agent on-demand complete", agent=agent_name)
        return result
    except Exception as exc:
        logger.error("Agent on-demand failed", agent=agent_name, error=str(exc))
        raise self.retry(exc=exc)


# ── Monitoring sweep ──────────────────────────────────────────────────────────

@celery_app.task(name="app.tasks.agent_tasks.run_monitoring_sweep")
def run_monitoring_sweep() -> dict:
    """
    Runs only the MonitoringAgent every 15 minutes to detect degraded agents / models.
    Lighter than the full pipeline — no data ingestion or prediction.
    """
    logger.info("Starting monitoring health sweep")

    async def _execute():
        from app.database.connection import init_db_engine
        await init_db_engine()

        from app.agents.agent_registry import get_agent_registry
        from app.ml.models_registry.registry import get_model_registry

        agent_mgr = get_agent_registry()
        model_registry = get_model_registry()

        # Collect health snapshots to pass to MonitoringAgent
        agent_health = agent_mgr.health_report()
        model_health = model_registry.health_report()

        result = await agent_mgr.execute(
            agent_name=AgentName.MONITORING,
            payload={"agent_health": agent_health, "model_health": model_health},
            trigger=AgentTrigger.SCHEDULED,
            triggered_by="celery_beat_monitoring",
        )
        return result.result_summary or {}

    try:
        result = _run_async(_execute())
        logger.info("Monitoring sweep complete", result=result)
        return result
    except Exception as exc:
        logger.error("Monitoring sweep failed", error=str(exc))
        return {"error": str(exc)}
