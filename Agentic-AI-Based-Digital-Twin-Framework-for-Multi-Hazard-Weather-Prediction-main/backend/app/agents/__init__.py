"""
app/agents/__init__.py
──────────────────────
Agent package — exports all 14 agents and the registry.

All 14 AgentName members are covered:
  WEATHER_INTELLIGENCE  → WeatherAgent
  PREDICTION            → PredictionAgent
  ALERT                 → AlertAgent
  DISASTER_INTELLIGENCE → DisasterIntelligenceAgent
  DIGITAL_TWIN          → DigitalTwinAgent
  REPORT_GENERATOR      → ReportAgent
  NOTIFICATION          → NotificationAgent
  MONITORING            → MonitoringAgent
  DATA_COLLECTION       → DataCollectionAgent
  RESEARCH              → ResearchAgent
  EXPLAINABILITY        → ExplainabilityAgent
  DECISION_SUPPORT      → DecisionSupportAgent
  MODEL_HEALTH          → ModelHealthAgent
  ENSEMBLE_FUSION       → EnsembleFusionAgent
"""

from app.agents.agent_registry import AgentManager, get_agent_registry
from app.agents.base_agent import AgentResult, BaseAgent
from app.agents.alert_agent import AlertAgent
from app.agents.data_collection_agent import DataCollectionAgent
from app.agents.decision_support_agent import DecisionSupportAgent
from app.agents.digital_twin_agent import DigitalTwinAgent
from app.agents.disaster_intelligence_agent import DisasterIntelligenceAgent
from app.agents.ensemble_fusion_agent import EnsembleFusionAgent
from app.agents.explainability_agent import ExplainabilityAgent
from app.agents.model_health_agent import ModelHealthAgent
from app.agents.monitoring_agent import MonitoringAgent
from app.agents.notification_agent import NotificationAgent
from app.agents.orchestrator_agent import OrchestratorAgent
from app.agents.prediction_agent import PredictionAgent
from app.agents.report_agent import ReportAgent
from app.agents.research_agent import ResearchAgent
from app.agents.trip_agent import TripAgent
from app.agents.weather_agent import WeatherAgent

__all__ = [
    # Registry
    "AgentManager",
    "get_agent_registry",
    # Base
    "BaseAgent",
    "AgentResult",
    # All 15 agents
    "WeatherAgent",
    "PredictionAgent",
    "AlertAgent",
    "DisasterIntelligenceAgent",
    "DigitalTwinAgent",
    "ReportAgent",
    "NotificationAgent",
    "MonitoringAgent",
    "DataCollectionAgent",
    "ResearchAgent",
    "ExplainabilityAgent",
    "DecisionSupportAgent",
    "ModelHealthAgent",
    "EnsembleFusionAgent",
    "TripAgent",
    # Orchestrator
    "OrchestratorAgent",
]
