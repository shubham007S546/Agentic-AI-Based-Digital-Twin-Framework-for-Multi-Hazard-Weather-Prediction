"""
app/api/v1/routers/agents_router.py
────────────────────────────────────
Agentic AI API endpoints (Phase 9).

Endpoints:
  GET  /agents                     — List all registered agents with status
  POST /agents/{agent_name}/run    — Trigger an agent synchronously (admin)
  POST /agents/{agent_name}/queue  — Queue an agent via Celery (non-blocking)
  GET  /agents/health              — Full health report across all agents
  POST /agents/pipeline/run        — Trigger the full OrchestratorAgent pipeline (admin)
"""

from __future__ import annotations

from typing import Annotated, Any
from fastapi import APIRouter, Depends, Path, status

from app.core.enums import AgentName, AgentTrigger
from app.dependencies.auth import CurrentUserToken, require_admin
from app.schemas.common import ApiResponse

router = APIRouter()


def _get_agent_manager():
    from app.agents.agent_registry import get_agent_registry
    return get_agent_registry()


# ── List all agents ───────────────────────────────────────────────────────────

@router.get(
    "",
    summary="List all registered agents",
)
async def list_agents(
    token_data: CurrentUserToken,
) -> ApiResponse[list[dict]]:
    """
    Returns all registered agents with their name, version, description,
    total executions, and last execution timestamp.
    """
    agent_mgr = _get_agent_manager()
    agents = agent_mgr.list_agents()
    return ApiResponse(data=agents)


# ── Agent health report ───────────────────────────────────────────────────────

@router.get(
    "/health",
    summary="Full agent system health report",
)
async def agents_health(
    token_data: CurrentUserToken,
) -> ApiResponse[dict]:
    """
    Returns per-agent health status including execution counts, failure rates,
    and stale detection (no execution in > 60 minutes).
    """
    agent_mgr = _get_agent_manager()
    report = agent_mgr.health_report()
    return ApiResponse(data=report)


# ── Synchronous agent execution (admin, blocking) ─────────────────────────────

@router.post(
    "/{agent_name}/run",
    status_code=status.HTTP_200_OK,
    summary="Execute an agent synchronously (Admin only)",
    dependencies=[Depends(require_admin)],
)
async def run_agent_sync(
    agent_name: Annotated[str, Path(description="AgentName enum value")],
    token_data: CurrentUserToken,
    payload: dict[str, Any] | None = None,
) -> ApiResponse[dict]:
    """
    Execute a named agent synchronously and return the result.
    This blocks until the agent completes (or times out).
    Use POST /{agent_name}/queue for non-blocking background execution.
    """
    agent_mgr = _get_agent_manager()

    try:
        name_enum = AgentName(agent_name)
    except ValueError:
        return ApiResponse(
            success=False,
            message=f"Unknown agent: '{agent_name}'. Valid agents: {[n.value for n in AgentName]}",
        )

    result = await agent_mgr.execute(
        agent_name=name_enum,
        payload=payload or {},
        trigger=AgentTrigger.MANUAL,
        triggered_by=token_data.user_id,
    )

    return ApiResponse(
        data={
            "agent": name_enum.value,
            "status": result.status.value,
            "duration_seconds": round(result.duration_seconds or 0, 3),
            "result_summary": result.result_summary,
            "error": result.error_message,
        },
        message=f"Agent '{name_enum.value}' execution finished with status: {result.status.value}",
    )


# ── Async agent execution (Celery queue, non-blocking) ───────────────────────

@router.post(
    "/{agent_name}/queue",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue an agent execution via Celery (non-blocking)",
    dependencies=[Depends(require_admin)],
)
async def queue_agent_async(
    agent_name: Annotated[str, Path(description="AgentName enum value")],
    token_data: CurrentUserToken,
    payload: dict[str, Any] | None = None,
) -> ApiResponse[dict]:
    """
    Dispatch an agent execution to the Celery 'agents' queue.
    Returns immediately with a task_id for tracking.
    """
    try:
        AgentName(agent_name)  # validate
    except ValueError:
        return ApiResponse(
            success=False,
            message=f"Unknown agent: '{agent_name}'",
        )

    from app.tasks.agent_tasks import run_agent_on_demand
    task = run_agent_on_demand.delay(
        agent_name=agent_name,
        payload=payload or {},
        triggered_by=token_data.user_id,
    )

    return ApiResponse(
        data={"task_id": task.id, "agent": agent_name, "status": "queued"},
        message=f"Agent '{agent_name}' queued for execution. Track with task_id: {task.id}",
    )


# ── Full pipeline trigger ─────────────────────────────────────────────────────

@router.post(
    "/pipeline/run",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger the full 12-agent pipeline (Admin only)",
    dependencies=[Depends(require_admin)],
)
async def run_full_pipeline(
    token_data: CurrentUserToken,
    payload: dict[str, Any] | None = None,
) -> ApiResponse[dict]:
    """
    Dispatches the full OrchestratorAgent pipeline to the Celery 'agents' queue.
    Equivalent to what Celery Beat triggers every 60 minutes.
    Useful for manual re-runs after data corrections.
    """
    from app.tasks.agent_tasks import run_orchestrator_pipeline
    task = run_orchestrator_pipeline.delay(payload=payload or {})

    return ApiResponse(
        data={"task_id": task.id, "pipeline": "full_12_agent", "status": "queued"},
        message=f"Full agent pipeline queued. Track with task_id: {task.id}",
    )
