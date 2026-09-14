"""
app/agents/orchestrator_agent.py
─────────────────────────────────
Agent 12 — Orchestrator Agent (Central Coordinator)

Responsibility:
  • Act as the top-level conductor for the entire agent pipeline
  • Utilize CycleMemory for typed, structured inter-agent state passing
  • Dynamic autonomous routing: adapts pipeline execution based on current hazard risk
    (e.g., skips costly explainability when conditions are calm, prioritizes rapid escalation
    and episodic RAG memory retrieval when extreme anomalies are detected)
  • Execute agents in dependency order with failure isolation:
      1. DataCollectionAgent      — satellite & sensor ingestion
      2. WeatherAgent             — observation ingestion & anomaly detection
      3. PredictionAgent          — ML hazard predictions
      4. AlertAgent               — threshold evaluation & alerts
      5. DisasterIntelligenceAgent— compound multi-hazard risk synthesis
      6. DigitalTwinAgent         — sync TwinState with latest telemetry
      7. ExplainabilityAgent      — SHAP explanations for HIGH/EXTREME predictions
      8. DecisionSupportAgent     — SDMA decision briefs & protocol synthesis
      9. ReportAgent              — compile and upload reports
     10. NotificationAgent        — deliver alerts and reports to stakeholders
     11. MonitoringAgent          — health sweep (always runs last)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from app.agents.base_agent import AgentResult, BaseAgent
from app.agents.cycle_memory import CycleMemory
from app.core.enums import AgentName, AgentStatus, AgentTrigger

logger = structlog.get_logger(__name__)

# Orchestration pipeline: list of (AgentName, hard_dependency_on_previous)
_PIPELINE: list[tuple[AgentName, bool]] = [
    (AgentName.DATA_COLLECTION,        False),   # independent
    (AgentName.WEATHER_INTELLIGENCE,   False),   # independent
    (AgentName.PREDICTION,             True),    # needs fresh weather data
    (AgentName.ENSEMBLE_FUSION,        False),   # multi-model consensus & uncertainty bounds
    (AgentName.ALERT,                  False),   # runs on prediction results
    (AgentName.DISASTER_INTELLIGENCE,  False),   # runs on alert data
    (AgentName.DIGITAL_TWIN,           False),   # independent of alert pipeline
    (AgentName.EXPLAINABILITY,         False),   # runs on predictions / alerts
    (AgentName.DECISION_SUPPORT,       False),   # synthesises all above
    (AgentName.REPORT_GENERATOR,       False),   # independent
    (AgentName.NOTIFICATION,           False),   # delivers output of report / alerts
    (AgentName.MODEL_HEALTH,           False),   # evaluates model drift & triggers auto-retraining
    (AgentName.MONITORING,             False),   # always runs last — health sweep
]


class OrchestratorAgent(BaseAgent):
    """
    Master orchestrator that drives the full multi-agent weather intelligence
    pipeline with dynamic routing, episodic memory retrieval, and CycleMemory state passing.
    """

    def __init__(self) -> None:
        super().__init__(name=AgentName.MONITORING, version="orchestrator-2.0.0")

    @property
    def description(self) -> str:
        return (
            "Autonomous central coordinator that executes the VARUNA agent pipeline "
            "using CycleMemory, dynamic risk-based routing, and failure isolation."
        )

    def _get_timeout_seconds(self) -> float:
        return 900.0  # 15 minutes for a full cycle

    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Full dynamic pipeline execution with CycleMemory.
        """
        from app.agents.agent_registry import get_agent_registry

        agent_mgr = get_agent_registry()
        cycle_memory = CycleMemory()
        pipeline_results: dict[str, Any] = {}
        previous_failed = False

        self._logger.info("Starting orchestration cycle", cycle_id=cycle_memory.cycle_id)

        agent_reports: dict[str, Any] = {}
        orchestrator_actions: list[str] = [
            f"Initialized orchestration cycle '{cycle_memory.cycle_id}' with dynamic routing",
        ]

        active_pipeline = list(_PIPELINE)
        if payload.get("source") and payload.get("destination") or payload.get("include_trip"):
            active_pipeline.insert(5, (AgentName.TRIP_ADVISORY, False))
            orchestrator_actions.append(f"Dynamically routed Trip & Route Hazard Advisory Agent for {payload.get('source')} ➔ {payload.get('destination')}")

        for agent_name, hard_dep in active_pipeline:
            # 1. Hard dependency check
            if hard_dep and previous_failed:
                self._logger.warning(
                    "Skipping agent due to hard dependency failure",
                    agent=agent_name.value,
                )
                pipeline_results[agent_name.value] = {
                    "status": AgentStatus.DISABLED.value,
                    "reason": "skipped — hard dependency failed",
                }
                orchestrator_actions.append(f"Skipped {agent_name.value}: hard dependency failed")
                continue

            # 2. Dynamic routing decision
            if agent_name == AgentName.EXPLAINABILITY:
                has_hazards = bool(cycle_memory.active_alerts or cycle_memory.high_risk_districts)
                if not has_hazards and not payload.get("force_explainability", False):
                    self._logger.info(
                        "Dynamic routing: nominal conditions detected, skipping deep SHAP calculations",
                        agent=agent_name.value,
                    )
                    pipeline_results[agent_name.value] = {
                        "status": AgentStatus.COMPLETED.value,
                        "skipped": True,
                        "reason": "nominal conditions — no high-risk hazard requiring SHAP attribution",
                    }
                    orchestrator_actions.append(f"Dynamic routing: bypassed deep SHAP calculations for {agent_name.value} (nominal conditions)")
                    continue

            # 3. Episodic Memory enrichment on weather anomalies
            if agent_name == AgentName.DISASTER_INTELLIGENCE and cycle_memory.weather_state:
                anomalies = cycle_memory.weather_state.get("anomalies_detected", 0)
                if anomalies > 0 and not cycle_memory.similar_past_events:
                    loc = cycle_memory.weather_state.get("location", "Mandi")
                    query = f"Severe rainfall cloudburst precedent in {loc} with sudden pressure drops"
                    try:
                        await cycle_memory.retrieve_similar_events(query=query, top_k=3)
                        orchestrator_actions.append(f"Retrieved 3 historical episodic memory precedents for {loc}")
                    except Exception as err:
                        self._logger.warning("Failed to retrieve episodic memory", error=str(err))

            # 4. Prepare context from CycleMemory
            context = cycle_memory.to_context()
            context.update(payload)

            # 5. Execute agent
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

                # Extract dedicated agent report
                if result.agent_report:
                    agent_reports[agent_name.value] = result.agent_report
                elif isinstance(result.result_summary, dict) and "agent_report" in result.result_summary:
                    agent_reports[agent_name.value] = result.result_summary["agent_report"]

                orchestrator_actions.append(
                    f"Executed {agent_name.value}: status={result.status.value}, duration={round((result.duration_seconds or 0)*1000, 1)}ms"
                )

                # 6. Update shared CycleMemory with agent output
                if result.status == AgentStatus.COMPLETED and result.result_summary:
                    cycle_memory.update_from_agent_result(agent_name.value, result.result_summary)

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
                orchestrator_actions.append(f"Execution failed for {agent_name.value}: {exc}")
                previous_failed = True

        completed = sum(
            1 for r in pipeline_results.values()
            if r.get("status") == AgentStatus.COMPLETED.value
        )
        failed = sum(
            1 for r in pipeline_results.values()
            if r.get("status") == AgentStatus.FAILED.value
        )

        from app.agents.agent_prompts import build_agent_execution_report

        master_final_answer = {
            "mission_status": "COMPLETED" if failed == 0 else "PARTIAL_SUCCESS",
            "cycle_id": cycle_memory.cycle_id,
            "total_agents": len(active_pipeline),
            "completed_agents": completed,
            "failed_agents": failed,
            "active_alerts_count": len(cycle_memory.active_alerts),
            "high_risk_districts": cycle_memory.high_risk_districts,
            "participating_agents": list(pipeline_results.keys()),
        }

        master_report = build_agent_execution_report(
            agent_name="orchestrator",
            task_assigned=payload,
            actions_taken=orchestrator_actions,
            final_answer=master_final_answer,
            summary_markdown=f"### 🎛️ Master Orchestration Summary\n- Total Agents Run: {len(active_pipeline)}\n- Completed: {completed} | Failed: {failed}\n- Cycle ID: `{cycle_memory.cycle_id}`",
            duration_ms=round(sum((r.get("duration_seconds") or 0) * 1000 for r in pipeline_results.values()), 1),
            status="COMPLETED" if failed == 0 else "WARNING",
            execution_id=cycle_memory.cycle_id,
        )

        cycle_summary = cycle_memory.to_summary()
        cycle_summary.update({
            "agents_run": len(active_pipeline),
            "completed": completed,
            "failed": failed,
            "skipped": len(active_pipeline) - completed - failed,
            "pipeline_results": pipeline_results,
            "agent_reports": agent_reports,
            "master_report": master_report.to_dict(),
            "final_answer": master_final_answer,
            "actions_taken": orchestrator_actions,
        })

        return cycle_summary
