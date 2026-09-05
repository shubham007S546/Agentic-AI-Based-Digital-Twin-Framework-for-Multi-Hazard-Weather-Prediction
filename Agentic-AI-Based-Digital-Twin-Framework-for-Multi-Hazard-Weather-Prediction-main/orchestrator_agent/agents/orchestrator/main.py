"""
FastAPI entrypoint for the Orchestrator Agent.

Run with:
    uvicorn agents.orchestrator.main:app --reload --port 8000

Endpoint (matches the architecture diagram):
    POST /api/v1/orchestrator/query
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .graph import orchestrator_graph
from .logging_config import get_logger
from .memory import conversation_memory
from .schemas import OrchestratorRequest, OrchestratorResponse, ToolCallRecord

logger = get_logger(__name__)

app = FastAPI(
    title="Orchestrator Agent",
    description="Agent 1 of 8 -- the main brain that understands user intent and routes to specialized agents.",
    version="0.1.0",
)

# Loosen this once your frontend's real origin is known.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/v1/orchestrator/query", response_model=OrchestratorResponse)
def query(request: OrchestratorRequest) -> OrchestratorResponse:
    try:
        history = conversation_memory.get_history(request.session_id)

        initial_state = {
            "session_id": request.session_id,
            "user_query": request.query,
            "user_context": request.context.model_dump(),
            "history": history,
            "errors": [],
        }

        final_state = orchestrator_graph.invoke(initial_state)

        return OrchestratorResponse(
            session_id=request.session_id,
            response=final_state.get("final_response", ""),
            intent=final_state.get("intent", {}),
            tools_used=[ToolCallRecord(**r) for r in final_state.get("tool_call_records", [])],
            notifications=final_state.get("notifications", []),
            errors=final_state.get("errors", []),
        )
    except Exception as exc:
        logger.exception("Orchestrator run failed")
        raise HTTPException(status_code=500, detail=str(exc))
