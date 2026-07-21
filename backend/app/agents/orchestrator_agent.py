"""
app/agents/orchestrator_agent.py
─────────────────────────────────
Agent 12 — Orchestrator Agent (Central Coordinator)

Responsibility:
  • Act as the top-level conductor for the entire agent pipeline
  • Execute agents in the correct dependency order on each scheduled cycle:
      1. DataCollectionAgent  — satellite data ingestion
      2. WeatherAgent         — weather observation ingestion
      3. PredictionAgent      — ML hazard predictions (uses fresh weather data)
      4. AlertAgent           — threshold evaluation → Alert records
      5. DisasterIntelligenceAgent — compound risk assessment
      6. DigitalTwinAgent     — sync TwinState with latest data
      7. ExplainabilityAgent  — SHAP explanations for HIGH/CRITICAL predictions
      8. DecisionSupportAgent — SDMA decision briefs
      9. ReportAgent          — compile and upload reports
     10. NotificationAgent    — deliver alerts and reports to stakeholders
     11. MonitoringAgent      — health sweep (always runs last)
  • Handle partial failures: if one agent fails, continue others unless
    it is a hard dependency (e.g., WeatherAgent failure → skip PredictionAgent)

Models used:
  • AgentExecution — each orchestration cycle creates one per sub-agent call
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from app.agents.base_agent import AgentResult, BaseAgent
from app.core.enums import AgentName, AgentStatus, AgentTrigger

logger = structlog.get_logger(__name__)

# Orchestration pipeline: list of (AgentName, hard_dependency_on_previous)
# hard_dep=True means if the previous agent FAILED, skip this one
_PIPELINE: list[tuple[AgentName, bool]] = [
    (AgentName.DATA_COLLECTION,        False),   # independent
    (AgentName.WEATHER_INTELLIGENCE,   False),   # independent
    (AgentName.PREDICTION,             True),    # needs fresh weather data
    (AgentName.ALERT,                  False),   # runs on prediction results
    (AgentName.DISASTER_INTELLIGENCE,  False),   # runs on alert data
    (AgentName.DIGITAL_TWIN,           False),   # independent of alert pipeline
    (AgentName.EXPLAINABILITY,         False),   # runs on predictions
    (AgentName.DECISION_SUPPORT,       False),   # synthesises all above
    (AgentName.REPORT_GENERATOR,       False),   # independent
    (AgentName.NOTIFICATION,           False),   # delivers output of report
    (AgentName.MONITORING,             False),   # always runs last — health sweep
]


class OrchestratorAgent(BaseAgent):
    """
    Master orchestrator that drives the full multi-agent weather intelligence
    pipeline in the correct dependency order with failure isolation.

    NOTE: The OrchestratorAgent is NOT registered in the AgentManager registry.
    It is invoked directly by Celery Beat tasks on each scheduled cycle, and it
    internally calls AgentManager.execute() for each of the 12 registered agents.
    """

    def __init__(self) -> None:
        # We use MONITORING as a placeholder name because AgentName has no ORCHESTRATOR entry.
        # In practice, this class is only instantiated by Celery tasks, never registered
        # in the AgentManager registry (which holds the 12 leaf agents).
        super().__init__(name=AgentName.MONITORING, version="orchestrator-1.0.0")

    @property
    def description(self) -> str:
        return (
            "Central coordinator that executes the full 11-stage agent pipeline "
            "in dependency order, collecting results and handling partial failures "
            "without aborting the entire cycle."
        )

    def _get_timeout_seconds(self) -> float:
        return 900.0  # 15 minutes for a full cycle

    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Full pipeline execution.

        Real implementation calls AgentManager.execute() for each agent in
        _PIPELINE order, passing the accumulated result context as payload
        to downstream agents (e.g., AlertAgent receives PredictionAgent output).

        The Celery Beat schedule triggers this agent every 60 minutes so that
        the entire pipeline runs autonomously without manual intervention.
        """
        from app.agents.agent_registry import get_agent_registry

        agent_mgr = get_agent_registry()
        cycle_start = datetime.now(UTC).isoformat()
        pipeline_results: dict[str, Any] = {}
        context: dict[str, Any] = dict(payload)  # accumulated inter-agent context
        previous_failed = False

        for agent_name, hard_dep in _PIPELINE:
            if hard_dep and previous_failed:
                self._logger.warning(
                    "Skipping agent due to hard dependency failure",
                    agent=agent_name.value,
                )
                pipeline_results[agent_name.value] = {
                    "status": AgentStatus.DISABLED.value,
                    "reason": "skipped — hard dependency failed",
                }
                continue

            try:
                self._logger.info("Orchestrating agent", agent=agent_name.value)
                result: AgentResult = await agent_mgr.execute(
                    agent_name=agent_name,
                    payload=context,
                    trigger=AgentTrigger.SCHEDULED,
                    triggered_by="orchestrator_agent",
                )
                pipeline_results[agent_name.value] = {
                    "status": result.status.value,
                    "duration_seconds": round(result.duration_seconds or 0, 3),
                    "summary": result.result_summary,
                }
                # Merge result summary into context for downstream agents
                if result.status == AgentStatus.COMPLETED and result.result_summary:
                    context.update(result.result_summary)

                previous_failed = result.status != AgentStatus.COMPLETED

            except Exception as exc:
                self._logger.error(
                    "Orchestrator: agent execution error",
                    agent=agent_name.value,
                    error=str(exc),
                )
                pipeline_results[agent_name.value] = {
                    "status": AgentStatus.FAILED.value,
                    "error": str(exc),
                }
                previous_failed = True

        completed = sum(
            1 for r in pipeline_results.values()
            if r.get("status") == AgentStatus.COMPLETED.value
        )
        failed = sum(
            1 for r in pipeline_results.values()
            if r.get("status") == AgentStatus.FAILED.value
        )

        return {
            "cycle_start": cycle_start,
            "cycle_end": datetime.now(UTC).isoformat(),
            "agents_run": len(_PIPELINE),
            "completed": completed,
            "failed": failed,
            "skipped": len(_PIPELINE) - completed - failed,
            "pipeline_results": pipeline_results,
        }
