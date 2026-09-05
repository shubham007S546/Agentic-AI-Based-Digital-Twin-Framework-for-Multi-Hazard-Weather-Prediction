"""Request/response schemas for the Orchestrator Agent's API, and the
TypedDict that flows through the LangGraph state machine internally."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    """Optional context the frontend can pass alongside a query -- matches
    the diagram's 'User context (location, role, preferences)' input."""

    location: Optional[str] = None            # e.g. "Mandi"
    role: Optional[str] = None                 # e.g. "citizen", "disaster_officer"
    preferences: Dict[str, Any] = Field(default_factory=dict)


class OrchestratorRequest(BaseModel):
    session_id: str = Field(..., description="Stable id for this conversation; used to load/store memory.")
    query: str = Field(..., description="The user's message, e.g. 'Will there be heavy rainfall in Mandi district tomorrow?'")
    context: UserContext = Field(default_factory=UserContext)


class ToolCallRecord(BaseModel):
    tool: str
    params: Dict[str, Any]
    result: Dict[str, Any]
    status: str  # "ok" | "error" | "stub"


class OrchestratorResponse(BaseModel):
    session_id: str
    response: str
    intent: Dict[str, Any]
    tools_used: List[ToolCallRecord]
    notifications: List[Dict[str, Any]]
    errors: List[str]


class OrchestratorState(TypedDict, total=False):
    """Internal state threaded through every LangGraph node."""

    session_id: str
    user_query: str
    user_context: Dict[str, Any]
    history: List[Dict[str, str]]

    intent: Dict[str, Any]
    task_plan: List[Dict[str, Any]]
    tool_results: Dict[str, Dict[str, Any]]
    tool_call_records: List[Dict[str, Any]]

    final_response: str
    notifications: List[Dict[str, Any]]
    errors: List[str]
