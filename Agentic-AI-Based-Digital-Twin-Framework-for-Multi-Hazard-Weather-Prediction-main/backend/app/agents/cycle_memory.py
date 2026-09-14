"""
backend/app/agents/cycle_memory.py
────────────────────────────────────────────────────────────────────────────
CycleMemory — the shared, structured context object that flows through the
entire 11-stage orchestration pipeline on each scheduled cycle.

Design
──────
  • The OrchestratorAgent creates one CycleMemory at the start of every cycle.
  • Each agent READS from it and WRITES its own output section into it.
  • The orchestrator passes `cycle_memory.to_context()` as the running `context`
    dict to downstream agents, exactly as the current code passes `context`.
  • After the cycle completes, `cycle_memory.to_summary()` is persisted and
    returned as the orchestrator's result_summary.

Short-term (in-cycle) memory:
  • weather_state     — from WeatherAgent
  • predictions       — from PredictionAgent
  • active_alerts     — from AlertAgent
  • risk_assessment   — from DisasterIntelligenceAgent
  • twin_state        — from DigitalTwinAgent
  • shap_explanations — from ExplainabilityAgent
  • decision_briefs   — from DecisionSupportAgent
  • report_ids        — from ReportAgent
  • notifications     — from NotificationAgent
  • health_status     — from MonitoringAgent

Episodic memory retrieval (RAG) is wired in retrieve_similar_events().
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional


@dataclass
class CycleMemory:
    """
    Structured shared context for a single orchestration cycle.
    Passed between agents so each agent can build on previous outputs.
    """

    cycle_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # ── Per-agent result slots ─────────────────────────────────────────────────
    weather_state:     dict[str, Any] = field(default_factory=dict)
    predictions:       dict[str, Any] = field(default_factory=dict)
    active_alerts:     list[dict]     = field(default_factory=list)
    risk_assessment:   dict[str, Any] = field(default_factory=dict)
    twin_state:        dict[str, Any] = field(default_factory=dict)
    shap_explanations: dict[str, Any] = field(default_factory=dict)
    decision_briefs:   list[dict]     = field(default_factory=list)
    report_ids:        list[str]      = field(default_factory=list)
    notifications:     list[dict]     = field(default_factory=list)
    health_status:     dict[str, Any] = field(default_factory=dict)

    # ── RAG episodic memory ────────────────────────────────────────────────────
    similar_past_events: list[dict] = field(default_factory=list)

    # ── Ensemble model outputs ─────────────────────────────────────────────────
    ensemble_outputs: dict[str, Any] = field(default_factory=dict)

    # ── Escalation state ──────────────────────────────────────────────────────
    escalation_triggered: bool = False
    high_risk_districts:  list[str] = field(default_factory=list)

    def update_from_agent_result(self, agent_name: str, result: dict[str, Any]) -> None:
        """Merge an agent's result_summary into the appropriate slot."""
        slot_map = {
            "weather_intelligence": "weather_state",
            "prediction":           "predictions",
            "alert":                "active_alerts",
            "disaster_intelligence":"risk_assessment",
            "digital_twin":        "twin_state",
            "explainability":      "shap_explanations",
            "decision_support":    "decision_briefs",
            "report_generator":    "report_ids",
            "notification":        "notifications",
            "monitoring":          "health_status",
            "ensemble_fusion":     "ensemble_outputs",
            "model_health":        "health_status",
        }
        slot = slot_map.get(agent_name)
        if slot is None:
            return

        attr = getattr(self, slot)
        if isinstance(attr, list):
            if isinstance(result, list):
                attr.extend(result)
            else:
                attr.append(result)
        elif isinstance(attr, dict):
            attr.update(result)

        # Track escalation state from DisasterIntelligenceAgent
        if agent_name == "disaster_intelligence":
            self.high_risk_districts = result.get("high_risk_districts", [])
            self.escalation_triggered = bool(self.high_risk_districts)

    def to_context(self) -> dict[str, Any]:
        """
        Return a flat dict suitable for passing as `context` to the next agent.
        Matches the keys that existing agents read from payload (e.g. active_alerts,
        district_risk_report, twin_states, prediction_ids).
        """
        return {
            "cycle_id":             self.cycle_id,
            "weather_state":        self.weather_state,
            "current":              self.weather_state.get("current", {}),
            "location":             self.weather_state.get("location", "Mandi"),
            "anomalies_detected":   self.weather_state.get("anomalies_detected", 0),
            "predictions":          self.predictions,
            "active_alerts":        self.active_alerts,
            "district_risk_report": self.risk_assessment.get("district_risk_report", {}),
            "twin_states":          self.twin_state,
            "shap_explanations":    self.shap_explanations,
            "prediction_ids":       list(self.predictions.keys()) if self.predictions else [],
            "decision_briefs":      self.decision_briefs,
            "similar_past_events":  self.similar_past_events,
            "high_risk_districts":  self.high_risk_districts,
            "escalation_triggered": self.escalation_triggered,
            "ensemble_outputs":     self.ensemble_outputs,
        }

    def to_summary(self) -> dict[str, Any]:
        """Return a concise summary for the orchestrator's result_summary."""
        return {
            "cycle_id":              self.cycle_id,
            "started_at":            self.started_at.isoformat(),
            "completed_at":          datetime.now(UTC).isoformat(),
            "predictions_made":      len(self.predictions),
            "active_alerts":         len(self.active_alerts),
            "high_risk_districts":   self.high_risk_districts,
            "escalation_triggered":  self.escalation_triggered,
            "shap_explanations":     len(self.shap_explanations),
            "similar_past_events":   len(self.similar_past_events),
            "ensemble_used":         bool(self.ensemble_outputs),
        }

    async def retrieve_similar_events(
        self, query: str, top_k: int = 5
    ) -> list[dict]:
        """
        Query the episodic disaster memory store and RAG engine for historically similar weather events.
        The results are stored in self.similar_past_events and returned,
        enabling grounded reasoning across the agent pipeline.
        """
        try:
            from app.agents.memory.episodic_memory import get_episodic_memory
            ep_mem = get_episodic_memory()
            episodes = ep_mem.recall(query=query, top_k=top_k)
            if episodes:
                self.similar_past_events = [
                    {
                        "id": ep["id"],
                        "district": ep["district"],
                        "date": ep["date"],
                        "hazard": ep["hazard"],
                        "content": f"{ep['hazard']} in {ep['district'].title()} ({ep['rainfall_mm']}mm): {ep['consequence']}. Effective response: {ep['effective_action']}",
                        "source": "VARUNA Episodic Archive",
                        "similarity": 0.94,
                    }
                    for ep in episodes
                ]
                return self.similar_past_events
        except Exception:
            pass

        try:
            from RAG.knowledge_engine.retrievers.semantic_retriever import (  # type: ignore[import]
                SemanticRetriever,
            )
            retriever = SemanticRetriever()
            docs = retriever.retrieve(query=query, top_k=top_k)
            self.similar_past_events = [
                {
                    "content":    d.get("content", ""),
                    "source":     d.get("metadata", {}).get("source", ""),
                    "similarity": d.get("score", 0.0),
                }
                for d in docs
            ]
        except Exception:
            self.similar_past_events = []

        return self.similar_past_events
