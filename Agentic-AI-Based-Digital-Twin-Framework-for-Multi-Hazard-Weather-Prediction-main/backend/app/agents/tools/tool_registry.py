"""
backend/app/agents/tools/tool_registry.py
─────────────────────────────────────────
Central registry for all tools available to VARUNA autonomous agents.
Enables agents to query available tools, fetch schemas, and invoke them dynamically.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.core.enums import AgentName
from app.agents.tools.base_tool import BaseAgentTool
from app.agents.tools.weather_tools import (
    FetchOpenMeteoTool,
    FetchIMDObservationsTool,
    DetectAnomaliesTool,
)
from app.agents.tools.prediction_tools import (
    RunModelInferenceTool,
    GetModelRegistryHealthTool,
)
from app.agents.tools.alert_tools import (
    CheckHazardThresholdTool,
    AssessCompoundRiskTool,
)
from app.agents.tools.memory_tools import (
    QueryEpisodicMemoryTool,
    StoreDisasterEpisodeTool,
)
from app.agents.tools.notification_tools import (
    DispatchCAPAlertTool,
    SendOfficerSMSTool,
)

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Singleton registry managing all agent tools and access mappings.
    """

    _instance: Optional["ToolRegistry"] = None

    def __init__(self) -> None:
        self._tools: Dict[str, BaseAgentTool] = {}
        self._agent_tools: Dict[str, List[str]] = {}
        self._register_default_tools()

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = ToolRegistry()
        return cls._instance

    def register_tool(self, tool: BaseAgentTool) -> None:
        self._tools[tool.name] = tool

    def assign_tool_to_agent(self, agent_name: str, tool_name: str) -> None:
        if agent_name not in self._agent_tools:
            self._agent_tools[agent_name] = []
        if tool_name not in self._agent_tools[agent_name]:
            self._agent_tools[agent_name].append(tool_name)

    def _register_default_tools(self) -> None:
        tools: list[BaseAgentTool] = [
            FetchOpenMeteoTool(),
            FetchIMDObservationsTool(),
            DetectAnomaliesTool(),
            RunModelInferenceTool(),
            GetModelRegistryHealthTool(),
            CheckHazardThresholdTool(),
            AssessCompoundRiskTool(),
            QueryEpisodicMemoryTool(),
            StoreDisasterEpisodeTool(),
            DispatchCAPAlertTool(),
            SendOfficerSMSTool(),
        ]
        for t in tools:
            self.register_tool(t)

        # Map tools to agents
        self.assign_tool_to_agent(AgentName.WEATHER_INTELLIGENCE.value, "fetch_open_meteo")
        self.assign_tool_to_agent(AgentName.WEATHER_INTELLIGENCE.value, "fetch_imd_observations")
        self.assign_tool_to_agent(AgentName.WEATHER_INTELLIGENCE.value, "detect_weather_anomalies")

        self.assign_tool_to_agent(AgentName.PREDICTION.value, "run_model_inference")
        self.assign_tool_to_agent(AgentName.PREDICTION.value, "get_model_registry_health")

        self.assign_tool_to_agent(AgentName.ALERT.value, "check_hazard_threshold")
        self.assign_tool_to_agent(AgentName.ALERT.value, "assess_compound_risk")

        self.assign_tool_to_agent(AgentName.DISASTER_INTELLIGENCE.value, "assess_compound_risk")
        self.assign_tool_to_agent(AgentName.DISASTER_INTELLIGENCE.value, "query_episodic_memory")

        self.assign_tool_to_agent(AgentName.DECISION_SUPPORT.value, "query_episodic_memory")
        self.assign_tool_to_agent(AgentName.DECISION_SUPPORT.value, "store_disaster_episode")

        self.assign_tool_to_agent(AgentName.NOTIFICATION.value, "dispatch_cap_alert")
        self.assign_tool_to_agent(AgentName.NOTIFICATION.value, "send_officer_sms")

        self.assign_tool_to_agent(AgentName.MONITORING.value, "get_model_registry_health")

    def get_tool(self, tool_name: str) -> Optional[BaseAgentTool]:
        return self._tools.get(tool_name)

    def get_tools_for_agent(self, agent_name: str) -> List[BaseAgentTool]:
        names = self._agent_tools.get(agent_name, [])
        return [self._tools[name] for name in names if name in self._tools]

    def get_schemas_for_agent(self, agent_name: str) -> List[dict[str, Any]]:
        """Returns JSON schemas for all tools accessible to an agent, ready for LLM function calling."""
        return [t.get_schema() for t in self.get_tools_for_agent(agent_name)]

    async def execute_tool(self, tool_name: str, **kwargs: Any) -> Any:
        tool = self.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' is not registered.")
        return await tool.execute(**kwargs)


def get_tool_registry() -> ToolRegistry:
    return ToolRegistry.get_instance()
