"""
app/models/agent.py
───────────────────
AI Agent Execution domain models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Float, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import AgentName, AgentStatus, AgentTrigger
from app.database.base import Base, UUIDMixin


class AgentExecution(Base, UUIDMixin):
    """
    Audit log of every agent execution (scheduled, event-driven, or manual).
    Used for monitoring agent health, timeouts, and execution histories.
    No SoftDelete/Timestamp mixins here as this is an immutable append-only log.
    """
    
    __tablename__ = "agent_executions"

    agent_name: Mapped[AgentName] = mapped_column(
        Enum(AgentName, name="agent_name_enum", native_enum=True),
        index=True,
        nullable=False,
    )
    
    agent_version: Mapped[str] = mapped_column(String(50), nullable=False)
    
    trigger: Mapped[AgentTrigger] = mapped_column(
        Enum(AgentTrigger, name="agent_trigger_enum", native_enum=True),
        nullable=False,
    )
    
    # ID of the user, system, or upstream agent that triggered this execution
    triggered_by: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus, name="agent_status_enum", native_enum=True),
        default=AgentStatus.RUNNING,
        index=True,
        nullable=False,
    )
    
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Measured in seconds for Prometheus latency histograms
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    # Arbitrary output summary from the agent's execute() method
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return f"<AgentExecution {self.agent_name.name} ({self.status.name})>"
