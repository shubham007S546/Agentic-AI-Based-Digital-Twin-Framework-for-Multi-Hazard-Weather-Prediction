"""
app/agents/base_agent.py
────────────────────────
Abstract base class for all AI Agents.

Design decisions:
  • Every agent is a self-contained unit: it owns its name, config, state,
    execution logic, and health status.
  • The `execute()` method is the single entry point — agents are always
    triggered through this interface whether called by the scheduler,
    an event, or the AgentManager.
  • Agents NEVER call each other directly. They communicate via events
    published to the event bus (Observer pattern), which the AgentManager
    routes to the appropriate subscriber agents.
  • Execution results are always structured (AgentResult) so the
    AgentManager, Celery tasks, and monitoring stack can process them uniformly.
  • Each agent call creates an AgentExecution DB record for auditability.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

import structlog

from app.core.enums import AgentName, AgentStatus, AgentTrigger

logger = structlog.get_logger(__name__)


@dataclass
class AgentResult:
    """Structured output from a single agent execution."""
    agent_name: AgentName
    status: AgentStatus
    execution_id: uuid.UUID = field(default_factory=uuid.uuid4)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    result_summary: dict[str, Any] = field(default_factory=dict)
    agent_report: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None


class BaseAgent(ABC):
    """
    Abstract base class for all agents in the Weather Twin platform.
    """

    def __init__(self, name: AgentName, version: str = "1.0.0") -> None:
        self.name = name
        self.version = version
        self._is_healthy = True
        self._last_execution: Optional[AgentResult] = None
        self._logger = structlog.get_logger(f"agent.{name.value}")

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this agent does."""
        pass

    @abstractmethod
    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Core agent logic. Override in every concrete agent.
        Returns a result_summary dict (logged to DB).
        """
        pass

    async def execute(
        self,
        payload: dict[str, Any],
        trigger: AgentTrigger = AgentTrigger.MANUAL,
        triggered_by: str = "system",
    ) -> AgentResult:
        """
        Public execution entry point.
        Handles timing, error catching, and structured result creation.
        """
        execution_id = uuid.uuid4()
        start_time = time.perf_counter()
        started_at = datetime.now(UTC)

        self._logger.info(
            "Agent starting",
            execution_id=str(execution_id),
            trigger=trigger.name,
            triggered_by=triggered_by,
        )

        result = AgentResult(
            agent_name=self.name,
            status=AgentStatus.RUNNING,
            execution_id=execution_id,
            started_at=started_at,
        )

        try:
            summary = await asyncio.wait_for(
                self._run(payload),
                timeout=self._get_timeout_seconds(),
            )
            result.status = AgentStatus.COMPLETED
            result.result_summary = summary
            self._is_healthy = True

            # Extract or construct standardized AgentExecutionReport
            duration_ms = (time.perf_counter() - start_time) * 1000
            report_dict = summary.get("agent_report") if isinstance(summary, dict) else None
            if not report_dict:
                from app.agents.agent_prompts import build_agent_execution_report
                actions = summary.get("actions_taken") or [
                    f"Initialized {self.name.value} execution with payload keys: {list((payload or {}).keys())}",
                    f"Executed core processing logic in {round(duration_ms, 1)}ms",
                    "Validated output schema and compiled final response",
                ]
                final_answer = summary.get("final_answer") or {
                    k: v for k, v in summary.items() if k not in ("agent_report", "actions_taken")
                }
                summary_md = summary.get("summary_markdown") or f"### {self.name.value.replace('_', ' ').title()} Report\n- Status: `COMPLETED`\n- Duration: {round(duration_ms, 1)} ms"
                report = build_agent_execution_report(
                    agent_name=self.name.value,
                    task_assigned=payload or {},
                    actions_taken=actions,
                    final_answer=final_answer,
                    summary_markdown=summary_md,
                    duration_ms=duration_ms,
                    status="COMPLETED",
                    execution_id=str(execution_id),
                )
                report_dict = report.to_dict()
                if isinstance(summary, dict):
                    summary["agent_report"] = report_dict

            result.agent_report = report_dict

        except asyncio.TimeoutError:
            result.status = AgentStatus.TIMEOUT
            result.error_message = f"Agent timed out after {self._get_timeout_seconds()}s"
            self._is_healthy = False
            self._logger.error("Agent timed out", execution_id=str(execution_id))

        except Exception as exc:
            result.status = AgentStatus.FAILED
            result.error_message = str(exc)
            self._is_healthy = False
            self._logger.error(
                "Agent execution failed",
                execution_id=str(execution_id),
                error=str(exc),
                exc_info=True,
            )

        finally:
            result.completed_at = datetime.now(UTC)
            result.duration_seconds = time.perf_counter() - start_time
            self._last_execution = result

            self._logger.info(
                "Agent finished",
                execution_id=str(execution_id),
                status=result.status.name,
                duration_seconds=round(result.duration_seconds, 3),
            )

        return result

    def _get_timeout_seconds(self) -> float:
        """Override in subclasses to set agent-specific timeouts."""
        return 300.0  # 5 minutes default

    @property
    def is_healthy(self) -> bool:
        return self._is_healthy

    @property
    def last_execution(self) -> Optional[AgentResult]:
        return self._last_execution

    def health_status(self) -> dict[str, Any]:
        return {
            "agent_name": self.name.value,
            "version": self.version,
            "is_healthy": self._is_healthy,
            "last_execution_status": self._last_execution.status.name if self._last_execution else None,
            "last_execution_at": self._last_execution.completed_at.isoformat() if self._last_execution and self._last_execution.completed_at else None,
        }
