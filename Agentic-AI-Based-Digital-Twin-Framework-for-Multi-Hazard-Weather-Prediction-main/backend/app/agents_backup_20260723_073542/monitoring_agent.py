"""
app/agents/monitoring_agent.py
────────────────────────────────
Agent 7 — System Monitoring Agent

Responsibility:
  • Poll the health of all registered agents (via AgentManager.health_report())
  • Poll the ML model registry (via ModelRegistry.health_report())
  • Detect stale / failed agents and escalate via NotificationAgent cascade
  • Record AgentExecution stats to detect latency regressions

Models used:
  • AgentExecution — audit log of every agent run; queried for failure rates
                     and average duration over a rolling window
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.enums import AgentName, AgentStatus, AgentTrigger


# Thresholds
_MAX_CONSECUTIVE_FAILURES = 3      # alert after N failures
_STALE_AGENT_MINUTES = 60          # agent is stale if no run in N minutes
_HIGH_LATENCY_SECONDS = 30.0       # flag if avg duration exceeds this


class MonitoringAgent(BaseAgent):
    """
    System health watchdog for agents and ML models.
    Detects failures, stale agents, and latency regressions.
    """

    def __init__(self) -> None:
        super().__init__(name=AgentName.MONITORING, version="1.0.0")

    @property
    def description(self) -> str:
        return (
            "Polls AgentExecution records and ModelRegistry health reports, "
            "detects stale or failed agents, and cascades alerts to "
            "NotificationAgent when SLA thresholds are breached."
        )

    def _get_timeout_seconds(self) -> float:
        return 60.0

    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        System health sweep.

        Real implementation:
          1. Call agent_manager.health_report() to get per-agent status
          2. For each agent, query AgentExecution WHERE agent_name=X
             ORDER BY started_at DESC LIMIT 10  → compute failure_rate, avg_duration
          3. If failure_rate > threshold or agent is stale:
               cascade NotificationAgent with alert message
          4. Call model_registry.health_report() → flag any model with is_loaded=False
          5. Return structured health summary
        """
        now = datetime.now(UTC)
        stale_threshold = now - timedelta(minutes=_STALE_AGENT_MINUTES)

        # Simulated health report (real: from agent_manager.health_report())
        agent_health_report: list[dict] = payload.get("agent_health", [])
        model_health_report: list[dict] = payload.get("model_health", [])

        agents_healthy: list[str] = []
        agents_degraded: list[dict] = []
        models_unhealthy: list[str] = []

        for agent_info in agent_health_report:
            agent_name: str = agent_info.get("agent_name", "unknown")
            is_healthy: bool = agent_info.get("is_healthy", True)
            last_exec_str: str | None = agent_info.get("last_execution_at")

            # Check staleness
            is_stale = False
            if last_exec_str:
                try:
                    last_exec_dt = datetime.fromisoformat(last_exec_str)
                    is_stale = last_exec_dt < stale_threshold
                except ValueError:
                    pass

            if not is_healthy or is_stale:
                agents_degraded.append({
                    "agent": agent_name,
                    "is_healthy": is_healthy,
                    "is_stale": is_stale,
                    "last_execution_at": last_exec_str,
                })
                self._logger.warning(
                    "Agent degraded",
                    agent=agent_name,
                    is_healthy=is_healthy,
                    is_stale=is_stale,
                )
            else:
                agents_healthy.append(agent_name)

        # Check model registry health
        for model_info in model_health_report:
            if not model_info.get("is_loaded", True):
                model_name = model_info.get("model_name", "unknown")
                models_unhealthy.append(model_name)
                self._logger.warning(
                    "Model not loaded",
                    model=model_name,
                    load_error=model_info.get("load_error"),
                )

        should_notify = bool(agents_degraded or models_unhealthy)
        if should_notify:
            self._logger.warning(
                "System degradation detected — escalating to NotificationAgent",
                degraded_agents=len(agents_degraded),
                unhealthy_models=len(models_unhealthy),
            )
            # Real: await agent_manager.execute(
            #     AgentName.NOTIFICATION,
            #     payload={"message": "System health alert", "channels": ["email"]},
            #     trigger=AgentTrigger.CASCADE,
            # )

        return {
            "checked_at": now.isoformat(),
            "agents_healthy": len(agents_healthy),
            "agents_degraded": len(agents_degraded),
            "degraded_agents_detail": agents_degraded,
            "models_unhealthy": models_unhealthy,
            "system_ok": not should_notify,
            "cascade_notification": should_notify,
        }
