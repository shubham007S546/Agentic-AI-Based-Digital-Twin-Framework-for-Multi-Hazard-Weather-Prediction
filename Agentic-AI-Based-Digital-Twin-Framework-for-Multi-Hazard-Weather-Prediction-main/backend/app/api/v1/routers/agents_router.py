"""
app/api/v1/routers/agents_router.py
────────────────────────────────────
Agentic AI API endpoints (Phase 9).

Endpoints:
  GET  /agents                        — List all registered agents with status
  POST /agents/{agent_name}/run       — Trigger an agent synchronously (admin)
  POST /agents/{agent_name}/queue     — Queue an agent via Celery (non-blocking)
  GET  /agents/health                 — Full health report across all agents
  POST /agents/pipeline/run           — Trigger the full OrchestratorAgent pipeline (admin)
  POST /agents/orchestrator/query     — Proxy natural-language queries to the Orchestrator Agent (port 8005)
  POST /agents/assistant/query        — Direct RAG assistant query
"""

from __future__ import annotations

import os
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel, Field

from app.core.enums import AgentName, AgentTrigger
from app.dependencies.auth import CurrentUserToken, require_admin
from app.schemas.common import ApiResponse

router = APIRouter()

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_AGENT_URL", "http://localhost:8005")


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


@router.get(
    "/rag/health",
    summary="Check persisted RAG index readiness",
)
async def rag_health(
    token_data: CurrentUserToken,
) -> ApiResponse[dict[str, Any]]:
    """Report whether the persisted FAISS index can serve assistant queries."""
    from RAG.config import VECTOR_DB_DIR

    index_path = VECTOR_DB_DIR / "index.faiss"
    documents_path = VECTOR_DB_DIR / "documents.pkl"
    data: dict[str, Any] = {
        "ready": index_path.is_file() and documents_path.is_file(),
        "index_path": str(VECTOR_DB_DIR),
        "document_count": 0,
        "vector_count": 0,
    }
    if not data["ready"]:
        data["reason"] = "Run RAG/build_index.py to create index.faiss and documents.pkl."
        return ApiResponse(data=data, message="RAG index is not ready.")

    try:
        import pickle
        import faiss

        with documents_path.open("rb") as handle:
            documents = pickle.load(handle)
        index = faiss.read_index(str(index_path))
        data["document_count"] = len(documents)
        data["vector_count"] = index.ntotal
    except (OSError, ValueError, RuntimeError, pickle.PickleError) as exc:
        data["ready"] = False
        data["reason"] = f"RAG index could not be loaded: {exc}"
        return ApiResponse(data=data, message="RAG index is invalid.")

    return ApiResponse(data=data, message="RAG index is ready.")


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


class AssistantQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Natural language question for the AI assistant")


@router.post(
    "/assistant/query",
    summary="Ask the AI assistant a question",
)
async def query_assistant(
    payload: AssistantQueryRequest,
    token_data: CurrentUserToken,
) -> ApiResponse[dict]:
    try:
        from RAG.app import load_runtime_dependencies
        from RAG.chains.rag_chain import RAGChain
    except ImportError:
        from RAG_project.app import load_runtime_dependencies
        from RAG_project.chains.rag_chain import RAGChain

    try:
        retriever = load_runtime_dependencies()
        rag_chain = RAGChain(retriever)
        result = rag_chain.ask(payload.question)
    except Exception:
        return ApiResponse(
            success=False,
            data={"question": payload.question, "answer": "RAG service is temporarily unavailable.", "sources": []},
            message="RAG query failed. Check the backend and index health logs.",
        )

    return ApiResponse(data=result, message="Assistant response generated")


# ── Orchestrator Agent proxy ───────────────────────────────────────────────────

class OrchestratorQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language query for the Orchestrator Agent")
    session_id: str = Field(default="default", description="Session ID for conversation memory")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional extra context (e.g. district, hazard type, coordinates)",
    )


@router.post(
    "/orchestrator/query",
    summary="Send a natural-language query to the Orchestrator Agent",
)
async def orchestrator_query(
    payload: OrchestratorQueryRequest,
    token_data: CurrentUserToken,
) -> ApiResponse[dict]:
    """
    Proxies the request to the standalone Orchestrator Agent (port 8005).
    The orchestrator routes the query to whichever specialized agents it needs
    (Weather, Prediction, Alert, Digital Twin, RAG, etc.) and returns a
    synthesised response.

    The ORCHESTRATOR_AGENT_URL env var controls the target (default: http://localhost:8005).
    When running via docker-compose.agents.yml it will be http://orchestrator_agent:8005.
    """
    upstream = f"{ORCHESTRATOR_URL}/api/v1/orchestrator/query"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                upstream,
                json={
                    "query": payload.query,
                    "session_id": payload.session_id,
                    "context": payload.context,
                },
            )
            resp.raise_for_status()
            return ApiResponse(
                data=resp.json(),
                message="Orchestrator response received.",
            )
    except httpx.ConnectError:
        return ApiResponse(
            success=False,
            data={},
            message=(
                f"Orchestrator Agent is not reachable at {upstream}. "
                "Start it with: uvicorn orchestrator_agent.agents.orchestrator.main:app --port 8005"
            ),
        )
    except Exception as exc:
        return ApiResponse(
            success=False,
            data={},
            message=f"Orchestrator proxy error: {str(exc)}",
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
